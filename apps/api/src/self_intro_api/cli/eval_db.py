import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from self_intro_api.cli.eval import evaluate_case
from self_intro_api.db.session import engine
from self_intro_api.embedding.factory import HASHING_PROVIDER_NAME, create_embedding_provider
from self_intro_api.embedding.hashing import DEFAULT_HASHING_EMBEDDING_SPEC
from self_intro_api.knowledge.db_repository import PgVectorSearchBackend
from self_intro_api.knowledge.scope import load_knowledge_scope
from self_intro_api.rag.pipeline import RagService


async def run(dataset: Path, output: Path, embedding_provider: str) -> None:
    provider = create_embedding_provider(embedding_provider)
    service = RagService(
        PgVectorSearchBackend(engine, provider),
        knowledge_scope=load_knowledge_scope(Path("knowledge")),
    )
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
    is_hashing_baseline = provider.spec.name == DEFAULT_HASHING_EMBEDDING_SPEC.name
    metadata = {
        "run_id": output.stem,
        "started_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset),
        "knowledge_path": "knowledge",
        "retrieval_strategy": (
            "pgvector_hash_embedding_with_intent_rerank"
            if is_hashing_baseline
            else "pgvector_dense_embedding_with_intent_rerank"
        ),
        "top_k": 8,
        "answer_strategy": "deterministic_evidence_composer",
        "embedding_model": provider.spec.name,
        "embedding_revision": provider.spec.revision,
        "embedding_dimension": provider.spec.dimension,
        "llm_model": None,
    }
    payload = {"metadata": metadata, "summary": summary, "cases": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pgvector-backed RAG evaluation baseline")
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--embedding-provider", default=HASHING_PROVIDER_NAME)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results/m3.2-pgvector-baseline.json"),
    )
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output, args.embedding_provider))


if __name__ == "__main__":
    main()
