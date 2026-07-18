import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .models import Chunk


LATIN_RE = re.compile(r"[a-z0-9][a-z0-9_.+/-]*", re.IGNORECASE)
HAN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> List[str]:
    normalized = text.lower()
    tokens = LATIN_RE.findall(normalized)
    for sequence in HAN_RE.findall(normalized):
        tokens.extend(sequence)
        for size in (2, 3):
            tokens.extend(sequence[index : index + size] for index in range(len(sequence) - size + 1))
    return tokens


class BM25Index:
    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self.term_frequencies = [Counter(tokenize(chunk.search_text)) for chunk in self.chunks]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        document_frequency: Dict[str, int] = defaultdict(int)
        for frequencies in self.term_frequencies:
            for term in frequencies:
                document_frequency[term] += 1
        count = len(self.chunks)
        self.idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, limit: int = 10) -> List[Tuple[Chunk, float]]:
        if not self.chunks:
            return []
        query_terms = Counter(tokenize(query))
        scores: List[Tuple[Chunk, float]] = []
        for chunk, frequencies, length in zip(self.chunks, self.term_frequencies, self.lengths):
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * length / max(self.average_length, 1.0)
                )
                term_score = self.idf.get(term, 0.0) * frequency * (self.k1 + 1.0) / denominator
                score += term_score * (1.0 + min(query_frequency - 1, 2) * 0.05)
            scores.append((chunk, score))
        return sorted(scores, key=lambda item: (-item[1], item[0].chunk_id))[:limit]


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_document_ids: Tuple[str, ...]
    expected_chunk_ids: Tuple[str, ...]


def load_enabled_cases(path: Path) -> List[EvaluationCase]:
    cases: List[EvaluationCase] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if record.get("enabled"):
                expected_chunk_ids = tuple(record.get("expected_chunk_ids", ()))
                if not expected_chunk_ids:
                    raise ValueError(
                        f"enabled evaluation case at line {line_number} requires expected_chunk_ids"
                    )
                cases.append(
                    EvaluationCase(
                        case_id=record["id"],
                        question=record["question"],
                        expected_document_ids=tuple(record["expected_document_ids"]),
                        expected_chunk_ids=expected_chunk_ids,
                    )
                )
    return cases


def ranked_document_ids(results: Iterable[Tuple[Chunk, float]]) -> List[str]:
    ranked: List[str] = []
    for chunk, _ in results:
        if chunk.document_id not in ranked:
            ranked.append(chunk.document_id)
    return ranked


def evaluate(index: BM25Index, cases: Sequence[EvaluationCase], top_ks: Sequence[int] = (1, 3, 5)) -> dict:
    rows = []
    document_hit_totals = {top_k: 0 for top_k in top_ks}
    document_recall_totals = {top_k: 0.0 for top_k in top_ks}
    chunk_hit_totals = {top_k: 0 for top_k in top_ks}
    chunk_recall_totals = {top_k: 0.0 for top_k in top_ks}
    for case in cases:
        results = index.search(case.question, limit=max(top_ks) * 4)
        ranked_documents = ranked_document_ids(results)
        ranked_chunks = [chunk.chunk_id for chunk, _ in results]
        expected_documents = set(case.expected_document_ids)
        expected_chunks = set(case.expected_chunk_ids)
        document_metrics = {}
        chunk_metrics = {}
        for top_k in top_ks:
            found_documents = expected_documents.intersection(ranked_documents[:top_k])
            document_hit = bool(found_documents)
            document_recall = len(found_documents) / len(expected_documents) if expected_documents else 1.0
            document_hit_totals[top_k] += int(document_hit)
            document_recall_totals[top_k] += document_recall
            document_metrics[str(top_k)] = {
                "hit": document_hit,
                "expected_recall": round(document_recall, 4),
            }

            found_chunks = expected_chunks.intersection(ranked_chunks[:top_k])
            chunk_hit = bool(found_chunks)
            chunk_recall = len(found_chunks) / len(expected_chunks) if expected_chunks else 1.0
            chunk_hit_totals[top_k] += int(chunk_hit)
            chunk_recall_totals[top_k] += chunk_recall
            chunk_metrics[str(top_k)] = {"hit": chunk_hit, "expected_recall": round(chunk_recall, 4)}
        rows.append(
            {
                "id": case.case_id,
                "question": case.question,
                "expected_document_ids": list(case.expected_document_ids),
                "expected_chunk_ids": list(case.expected_chunk_ids),
                "ranked_document_ids": ranked_documents[: max(top_ks)],
                "ranked_chunk_ids": ranked_chunks[: max(top_ks)],
                "document_metrics": document_metrics,
                "chunk_metrics": chunk_metrics,
            }
        )
    denominator = len(cases) or 1
    return {
        "case_count": len(cases),
        "summary": {
            f"document_hit_rate@{top_k}": round(document_hit_totals[top_k] / denominator, 4)
            for top_k in top_ks
        }
        | {
            f"document_mean_expected_recall@{top_k}": round(
                document_recall_totals[top_k] / denominator, 4
            )
            for top_k in top_ks
        }
        | {
            f"chunk_hit_rate@{top_k}": round(chunk_hit_totals[top_k] / denominator, 4)
            for top_k in top_ks
        }
        | {
            f"chunk_mean_expected_recall@{top_k}": round(chunk_recall_totals[top_k] / denominator, 4)
            for top_k in top_ks
        },
        "cases": rows,
    }
