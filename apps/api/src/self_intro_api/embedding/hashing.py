import hashlib
import math
from collections.abc import Sequence

from self_intro_api.embedding.base import EmbeddingSpec
from self_intro_api.knowledge.retrieval import tokenize

DEFAULT_HASHING_EMBEDDING_SPEC = EmbeddingSpec(
    name="local-hashing-embedding",
    revision="m3.2-v1",
    dimension=384,
)


class HashingEmbeddingProvider:
    """Deterministic local embedding baseline.

    This provider is intentionally simple: it hashes lexical tokens into a fixed-size vector and
    L2-normalizes the result. It is useful for validating ingestion, revision isolation and pgvector
    SQL without requiring a paid or heavyweight model during M3.2.
    """

    def __init__(self, spec: EmbeddingSpec = DEFAULT_HASHING_EMBEDDING_SPEC):
        self.spec = spec

    def embed_passages(self, passages: Sequence[str]) -> list[list[float]]:
        return [_embed_text(text, self.spec.dimension) for text in passages]

    def embed_query(self, query: str) -> list[float]:
        return _embed_text(query, self.spec.dimension)


def _embed_text(text: str, dimension: int) -> list[float]:
    vector = [0.0] * dimension
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
