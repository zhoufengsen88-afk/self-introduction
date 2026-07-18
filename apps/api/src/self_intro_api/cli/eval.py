import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from self_intro_api.rag.pipeline import RagService, create_rag_service
from self_intro_api.schemas.chat import ChatRequest, ChatResponse


async def evaluate_case(service: RagService, record: dict[str, Any]) -> dict[str, Any]:
    response: ChatResponse = await service.answer(
        ChatRequest(message=record["question"], history=record.get("history", [])),
    )
    cited_chunk_ids = {citation.chunk_id for citation in response.citations}
    cited_document_ids = {citation.document_id for citation in response.citations}
    expected_chunk_ids = set(record.get("expected_chunk_ids", ()))
    expected_document_ids = set(record.get("expected_document_ids", ()))
    required_facts = record.get("required_facts", ())
    forbidden_facts = record.get("forbidden_facts", ())
    required_hits = [fact for fact in required_facts if fact in response.answer]
    forbidden_hits = [fact for fact in forbidden_facts if fact and fact in response.answer]
    document_hit = (
        bool(cited_document_ids & expected_document_ids)
        if expected_document_ids
        else not cited_document_ids
    )
    citation_hit = (
        bool(cited_chunk_ids & expected_chunk_ids) if expected_chunk_ids else document_hit
    )
    return {
        "id": record["id"],
        "question": record["question"],
        "refused": response.refused,
        "citation_hit": citation_hit,
        "document_hit": document_hit,
        "required_recall": len(required_hits) / len(required_facts) if required_facts else 1.0,
        "forbidden_ok": not forbidden_hits,
        "cited_chunk_ids": sorted(cited_chunk_ids),
        "cited_document_ids": sorted(cited_document_ids),
        "expected_chunk_ids": sorted(expected_chunk_ids),
        "expected_document_ids": sorted(expected_document_ids),
        "missing_required_facts": [fact for fact in required_facts if fact not in required_hits],
        "forbidden_hits": forbidden_hits,
    }


async def run(dataset: Path, output: Path) -> None:
    service = create_rag_service(Path("knowledge"))
    records: list[dict[str, Any]] = []
    with dataset.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("enabled"):
                records.append(record)

    rows = [await evaluate_case(service, record) for record in records]
    denominator = len(rows) or 1
    summary = {
        "case_count": len(rows),
        "citation_hit_rate": round(sum(row["citation_hit"] for row in rows) / denominator, 4),
        "document_hit_rate": round(sum(row["document_hit"] for row in rows) / denominator, 4),
        "mean_required_recall": round(
            sum(float(row["required_recall"]) for row in rows) / denominator,
            4,
        ),
        "forbidden_pass_rate": round(sum(row["forbidden_ok"] for row in rows) / denominator, 4),
    }
    metadata = {
        "run_id": output.stem,
        "started_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset),
        "knowledge_path": "knowledge",
        "retrieval_strategy": "in_memory_bm25_with_intent_rerank",
        "top_k": 8,
        "answer_strategy": "deterministic_evidence_composer",
        "embedding_model": None,
        "llm_model": None,
    }
    payload = {"metadata": metadata, "summary": summary, "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local RAG evaluation baseline")
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evals/results/m3-baseline.json"))
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output))


if __name__ == "__main__":
    main()
