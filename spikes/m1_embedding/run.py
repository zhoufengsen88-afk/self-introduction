import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from spikes.m1_ingestion.chunker import chunk_document
from spikes.m1_ingestion.loader import load_published_documents
from spikes.m1_ingestion.models import Chunk
from spikes.m1_ingestion.retrieval import EvaluationCase, evaluate, load_enabled_cases


@dataclass(frozen=True)
class ModelSpec:
    name: str
    model_id: str
    revision: str
    query_prefix: str
    passage_prefix: str


MODEL_SPECS: Dict[str, ModelSpec] = {
    "bge-small-zh-v1.5": ModelSpec(
        name="bge-small-zh-v1.5",
        model_id="BAAI/bge-small-zh-v1.5",
        revision="7999e1d3359715c523056ef9478215996d62a620",
        query_prefix="为这个句子生成表示以用于检索相关文章：",
        passage_prefix="",
    ),
    "multilingual-e5-small": ModelSpec(
        name="multilingual-e5-small",
        model_id="intfloat/multilingual-e5-small",
        revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
        query_prefix="query: ",
        passage_prefix="passage: ",
    ),
}


class DenseIndex:
    def __init__(self, chunks: Sequence[Chunk], model, spec: ModelSpec):
        self.chunks = list(chunks)
        self.model = model
        self.spec = spec
        passages = [spec.passage_prefix + chunk.search_text for chunk in chunks]
        started = time.perf_counter()
        self.embeddings = model.encode(
            passages,
            batch_size=16,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        self.corpus_encode_seconds = time.perf_counter() - started
        self.query_latencies_ms: List[float] = []

    def search(self, query: str, limit: int = 10) -> List[Tuple[Chunk, float]]:
        started = time.perf_counter()
        query_embedding = self.model.encode(
            [self.spec.query_prefix + query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        self.query_latencies_ms.append((time.perf_counter() - started) * 1000)
        scores = self.embeddings @ query_embedding
        ranked_indices = scores.argsort()[::-1][:limit]
        return [(self.chunks[index], float(scores[index])) for index in ranked_indices]


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def benchmark(spec: ModelSpec, chunks: Sequence[Chunk], cases: Sequence[EvaluationCase]) -> dict:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is missing; install spikes/m1_embedding/requirements.txt"
        ) from exc

    load_started = time.perf_counter()
    model = SentenceTransformer(spec.model_id, revision=spec.revision, device="cpu")
    load_seconds = time.perf_counter() - load_started
    index = DenseIndex(chunks, model, spec)

    # 单独预热，避免首次推理初始化影响 16 条查询的延迟分布。
    index.search("预热查询", limit=1)
    index.query_latencies_ms.clear()
    result = evaluate(index, cases)
    latencies = index.query_latencies_ms
    dimension = int(index.embeddings.shape[1])
    return {
        "configuration": spec.name,
        "model_id": spec.model_id,
        "model_revision": spec.revision,
        "dimension": dimension,
        "distance": "cosine (L2-normalized dot product)",
        "query_prefix": spec.query_prefix,
        "passage_prefix": spec.passage_prefix,
        "load_seconds": round(load_seconds, 4),
        "corpus_encode_seconds": round(index.corpus_encode_seconds, 4),
        "query_latency_ms": {
            "mean": round(statistics.mean(latencies), 4),
            "p50": round(statistics.median(latencies), 4),
            "p95": round(percentile(latencies, 0.95), 4),
            "sample_count": len(latencies),
        },
        "evaluation": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare local embedding candidates")
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=sorted(MODEL_SPECS),
        default=list(MODEL_SPECS),
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="omit per-case rankings from JSON output",
    )
    args = parser.parse_args()

    documents = load_published_documents(args.knowledge)
    chunks = [chunk for document in documents for chunk in chunk_document(document, args.max_chars)]
    cases = load_enabled_cases(args.dataset)
    results = [benchmark(MODEL_SPECS[name], chunks, cases) for name in args.models]
    if args.summary_only:
        for result in results:
            result["evaluation"] = {
                "case_count": result["evaluation"]["case_count"],
                "summary": result["evaluation"]["summary"],
            }
    output = {
        "environment": {
            "device": "cpu",
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "case_count": len(cases),
            "max_chars": args.max_chars,
        },
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
