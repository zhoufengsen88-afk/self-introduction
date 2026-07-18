import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

from .models import Chunk, SearchResult

LATIN_RE = re.compile(r"[a-z0-9][a-z0-9_.+/-]*", re.IGNORECASE)
HAN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    tokens = LATIN_RE.findall(normalized)
    for sequence in HAN_RE.findall(normalized):
        tokens.extend(sequence)
        for size in (2, 3):
            tokens.extend(
                sequence[index : index + size] for index in range(len(sequence) - size + 1)
            )
    return tokens


class BM25Retriever:
    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self.term_frequencies = [Counter(tokenize(chunk.search_text)) for chunk in self.chunks]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        document_frequency: dict[str, int] = defaultdict(int)
        for frequencies in self.term_frequencies:
            for term in frequencies:
                document_frequency[term] += 1
        count = len(self.chunks)
        self.idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        if not self.chunks:
            return []
        query_terms = Counter(tokenize(query))
        results: list[SearchResult] = []
        for chunk, frequencies, length in zip(
            self.chunks, self.term_frequencies, self.lengths, strict=True
        ):
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
            results.append(SearchResult(chunk=chunk, score=score))
        return sorted(results, key=lambda item: (-item.score, item.chunk.chunk_id))[:limit]


def ranked_document_ids(results: Iterable[SearchResult]) -> list[str]:
    ranked: list[str] = []
    for result in results:
        if result.chunk.document_id not in ranked:
            ranked.append(result.chunk.document_id)
    return ranked
