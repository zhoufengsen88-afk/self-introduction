from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingSpec:
    name: str
    revision: str
    dimension: int


class EmbeddingProvider(Protocol):
    spec: EmbeddingSpec

    def embed_passages(self, passages: Sequence[str]) -> list[list[float]]:
        """Embed corpus passages in provider-native passage mode."""

    def embed_query(self, query: str) -> list[float]:
        """Embed one user query in provider-native query mode."""
