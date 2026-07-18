import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from self_intro_api.core.config import Settings
from self_intro_api.embedding.factory import HASHING_PROVIDER_NAME, create_embedding_provider
from self_intro_api.knowledge.loader import load_public_corpus
from self_intro_api.knowledge.scope import load_knowledge_scope
from self_intro_api.llm.factory import create_llm_provider
from self_intro_api.rag.pipeline import (
    LLMAnswerGenerator,
    QueryRoute,
    RagService,
    create_rag_service,
)
from self_intro_api.schemas.chat import ChatRequest, Citation

DEFAULT_DATASET = Path("evals/datasets/m5-agent-qa-v1.jsonl")
DEFAULT_OUTPUT = Path("evals/results/m5-current-llm-memory.json")


@dataclass(frozen=True)
class ObservedResponse:
    answer: str
    citations: list[Citation]
    refused: bool
    refusal_reason: str | None
    first_token_ms: float | None
    total_latency_ms: float
    error_code: str | None


def load_enabled_records(
    dataset: Path,
    case_ids: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with dataset.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record: dict[str, Any] = json.loads(line)
            if not record.get("enabled"):
                continue
            if case_ids and record["id"] not in case_ids:
                continue
            records.append(record)
            if limit is not None and len(records) >= limit:
                break
    return records


def create_llm_eval_service(
    settings: Settings,
    backend: str,
    embedding_provider: str,
) -> tuple[RagService, dict[str, Any]]:
    generator = LLMAnswerGenerator(create_llm_provider(settings))
    if backend == "memory":
        return create_rag_service(Path("knowledge"), generator), {
            "retrieval_backend": "memory",
            "retrieval_strategy": "in_memory_bm25_with_intent_rerank",
            "embedding_model": None,
            "embedding_revision": None,
            "embedding_dimension": None,
        }
    if backend == "pgvector":
        from self_intro_api.db.session import engine
        from self_intro_api.knowledge.db_repository import PgVectorSearchBackend

        provider = create_embedding_provider(embedding_provider)
        service = RagService(
            PgVectorSearchBackend(engine, provider),
            generator,
            knowledge_scope=load_knowledge_scope(Path("knowledge")),
        )
        return service, {
            "retrieval_backend": "pgvector",
            "retrieval_strategy": "pgvector_dense_embedding_with_intent_rerank",
            "embedding_model": provider.spec.name,
            "embedding_revision": provider.spec.revision,
            "embedding_dimension": provider.spec.dimension,
        }
    raise ValueError(f"Unsupported evaluation backend: {backend}")


async def collect_streamed_response(
    service: RagService,
    request: ChatRequest,
    top_k: int,
) -> ObservedResponse:
    started = perf_counter()
    first_token_ms: float | None = None
    answer_parts: list[str] = []
    citations: list[Citation] = []
    refused = False
    refusal_reason: str | None = None
    error_code: str | None = None

    async for event in service.stream(request, top_k=top_k):
        event_name = event.get("event")
        data = event.get("data", {})
        if event_name == "delta":
            content = data.get("content", "")
            if isinstance(content, str) and content:
                if first_token_ms is None:
                    first_token_ms = (perf_counter() - started) * 1000
                answer_parts.append(content)
        elif event_name == "done":
            citations = [Citation.model_validate(item) for item in data.get("citations", [])]
            refused = bool(data.get("refused", False))
            reason = data.get("refusal_reason")
            refusal_reason = reason if isinstance(reason, str) else None
        elif event_name == "error":
            message = data.get("message")
            if isinstance(message, str):
                answer_parts.append(message)
            code = data.get("code")
            error_code = code if isinstance(code, str) else "unknown_error"

    return ObservedResponse(
        answer="".join(answer_parts).strip(),
        citations=citations,
        refused=refused,
        refusal_reason=refusal_reason,
        first_token_ms=round(first_token_ms, 2) if first_token_ms is not None else None,
        total_latency_ms=round((perf_counter() - started) * 1000, 2),
        error_code=error_code,
    )


async def evaluate_case(
    service: RagService,
    record: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    request = ChatRequest.model_validate(
        {"message": record["question"], "history": record.get("history", [])}
    )
    actual_route: QueryRoute = service.route(request)
    actual_intent = service.intent(request).name if actual_route == "knowledge_rag" else None
    observed = await collect_streamed_response(service, request, top_k)
    if actual_route != "knowledge_rag":
        generation_strategy = "route_policy"
    elif observed.refused and observed.refusal_reason == "insufficient_evidence":
        generation_strategy = "evidence_policy"
    elif actual_intent == "ai_assisted_development":
        generation_strategy = "grounded_policy"
    else:
        generation_strategy = "llm"
    cited_document_ids = {citation.document_id for citation in observed.citations}
    cited_chunk_ids = {citation.chunk_id for citation in observed.citations}
    expected_document_ids = set(record.get("expected_document_ids", ()))
    expected_chunk_ids = set(record.get("expected_chunk_ids", ()))
    required_facts = record.get("required_facts", ())
    forbidden_facts = record.get("forbidden_facts", ())
    required_hits = [fact for fact in required_facts if fact in observed.answer]
    forbidden_hits = [fact for fact in forbidden_facts if fact and fact in observed.answer]

    document_hit = (
        bool(cited_document_ids & expected_document_ids)
        if expected_document_ids
        else not cited_document_ids
    )
    chunk_hit = bool(cited_chunk_ids & expected_chunk_ids) if expected_chunk_ids else document_hit
    expected_reason = record.get("refusal_reason")
    refusal_ok = observed.refused == bool(record["should_refuse"])
    if record["should_refuse"] and expected_reason:
        refusal_ok = refusal_ok and observed.refusal_reason == expected_reason
    citation_presence_ok = bool(observed.citations) == bool(record["citation_required"])
    route_ok = actual_route == record["expected_route"]
    deterministic_checks_pass = all(
        (
            route_ok,
            citation_presence_ok,
            document_hit,
            chunk_hit,
            refusal_ok,
            not forbidden_hits,
            observed.error_code is None,
        )
    )

    return {
        "id": record["id"],
        "category": record["category"],
        "question": record["question"],
        "expected_route": record["expected_route"],
        "actual_route": actual_route,
        "actual_intent": actual_intent,
        "generation_strategy": generation_strategy,
        "route_ok": route_ok,
        "answer": observed.answer,
        "refused": observed.refused,
        "expected_refused": record["should_refuse"],
        "refusal_reason": observed.refusal_reason,
        "expected_refusal_reason": expected_reason,
        "refusal_ok": refusal_ok,
        "citation_required": record["citation_required"],
        "citation_presence_ok": citation_presence_ok,
        "document_hit": document_hit,
        "chunk_hit": chunk_hit,
        "citations": [citation.model_dump() for citation in observed.citations],
        "cited_document_ids": sorted(cited_document_ids),
        "cited_chunk_ids": sorted(cited_chunk_ids),
        "expected_document_ids": sorted(expected_document_ids),
        "expected_chunk_ids": sorted(expected_chunk_ids),
        "required_hits": required_hits,
        "missing_required_facts": [fact for fact in required_facts if fact not in required_hits],
        "required_string_recall": (
            round(len(required_hits) / len(required_facts), 4) if required_facts else 1.0
        ),
        "forbidden_hits": forbidden_hits,
        "forbidden_ok": not forbidden_hits,
        "first_token_ms": observed.first_token_ms,
        "total_latency_ms": observed.total_latency_ms,
        "error_code": observed.error_code,
        "deterministic_checks_pass": deterministic_checks_pass,
        "human_review": {
            "acceptance_criteria": record["acceptance_criteria"],
            "faithfulness_score": None,
            "citation_support_score": None,
            "interview_quality_score": None,
            "notes": None,
        },
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows) or 1

    def rate(field: str) -> float:
        return round(sum(bool(row[field]) for row in rows) / denominator, 4)

    latencies = [float(row["total_latency_ms"]) for row in rows]
    first_tokens = [
        float(row["first_token_ms"]) for row in rows if row["first_token_ms"] is not None
    ]
    return {
        "case_count": len(rows),
        "route_accuracy": rate("route_ok"),
        "citation_presence_accuracy": rate("citation_presence_ok"),
        "document_hit_rate": rate("document_hit"),
        "chunk_hit_rate": rate("chunk_hit"),
        "refusal_accuracy": rate("refusal_ok"),
        "forbidden_pass_rate": rate("forbidden_ok"),
        "deterministic_checks_pass_rate": rate("deterministic_checks_pass"),
        "mean_required_string_recall": round(
            sum(float(row["required_string_recall"]) for row in rows) / denominator,
            4,
        ),
        "mean_first_token_ms": round(sum(first_tokens) / len(first_tokens), 2)
        if first_tokens
        else None,
        "mean_total_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "provider_error_count": sum(row["error_code"] is not None for row in rows),
        "human_review_completed": False,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _knowledge_version() -> str:
    corpus = load_public_corpus(Path("knowledge"))
    digest = hashlib.sha256()
    for document in sorted(corpus.documents, key=lambda item: item.metadata.document_id):
        digest.update(document.metadata.document_id.encode())
        digest.update(document.content_hash.encode())
    return digest.hexdigest()


async def run(
    dataset: Path,
    output: Path,
    backend: str,
    embedding_provider: str,
    top_k: int,
    case_ids: set[str] | None,
    limit: int | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = settings or Settings()
    service, retrieval_metadata = create_llm_eval_service(
        active_settings, backend, embedding_provider
    )
    records = load_enabled_records(dataset, case_ids, limit)
    if not records:
        raise ValueError("No enabled evaluation cases matched the selection")

    started_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        print(f"[{index}/{len(records)}] {record['id']}")
        rows.append(await evaluate_case(service, record, top_k))

    payload = {
        "metadata": {
            "schema_version": "m5.2-llm-eval-v1",
            "run_id": output.stem,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "dataset": str(dataset),
            "dataset_sha256": _sha256(dataset),
            "knowledge_path": "knowledge",
            "knowledge_base_version": _knowledge_version(),
            "top_k": top_k,
            "max_context_chunks": min(top_k, 6),
            "answer_generator": "hybrid_llm_and_grounded_policy",
            "llm_provider": active_settings.llm_provider,
            "llm_model": active_settings.llm_model,
            "llm_temperature": active_settings.llm_temperature,
            "prompt_version": "m5.3-rag-prompt-v2",
            "agent_route_version": "m5.3-lightweight-router-v2",
            "evidence_policy_version": "m5.3-public-top6-anchor-gate-v2",
            **retrieval_metadata,
        },
        "summary": build_summary(rows),
        "cases": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M5.2 real-LLM interview evaluation")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backend", choices=("memory", "pgvector"), default="memory")
    parser.add_argument("--embedding-provider", default=HASHING_PROVIDER_NAME)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    payload = asyncio.run(
        run(
            dataset=args.dataset,
            output=args.output,
            backend=args.backend,
            embedding_provider=args.embedding_provider,
            top_k=args.top_k,
            case_ids=set(args.case_ids) if args.case_ids else None,
            limit=args.limit,
        )
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
