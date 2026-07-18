from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from self_intro_api.embedding.base import EmbeddingSpec

MULTILINGUAL_E5_SMALL_SPEC = EmbeddingSpec(
    name="multilingual-e5-small",
    revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
    dimension=384,
)


@dataclass(frozen=True)
class SentenceTransformerModelConfig:
    model_id: str
    query_prefix: str
    passage_prefix: str
    device: str = "cpu"
    batch_size: int = 16


MULTILINGUAL_E5_SMALL_CONFIG = SentenceTransformerModelConfig(
    model_id="intfloat/multilingual-e5-small",
    query_prefix="query: ",
    passage_prefix="passage: ",
)


class SentenceTransformerEmbeddingProvider:
    """Real dense embedding provider backed by sentence-transformers."""

    def __init__(
        self,
        spec: EmbeddingSpec = MULTILINGUAL_E5_SMALL_SPEC,
        config: SentenceTransformerModelConfig = MULTILINGUAL_E5_SMALL_CONFIG,
    ):
        self.spec = spec
        self.config = config
        self._model = _load_sentence_transformer(config.model_id, spec.revision, config.device)

    def embed_passages(self, passages: Sequence[str]) -> list[list[float]]:
        prefixed = [self.config.passage_prefix + passage for passage in passages]
        return self._encode(prefixed, batch_size=self.config.batch_size)

    def embed_query(self, query: str) -> list[float]:
        return self._encode([self.config.query_prefix + query], batch_size=1)[0]

    def _encode(self, texts: Sequence[str], batch_size: int) -> list[list[float]]:
        embeddings = self._model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        rows = embeddings.tolist()
        vectors = [[float(value) for value in row] for row in rows]
        for vector in vectors:
            if len(vector) != self.spec.dimension:
                raise ValueError(
                    f"{self.spec.name} expected {self.spec.dimension} dimensions, got {len(vector)}"
                )
        return vectors


def _load_sentence_transformer(model_id: str, revision: str, device: str) -> Any:
    try:
        module = import_module("sentence_transformers")
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Run `uv add sentence-transformers` or use `--embedding-provider hashing`."
        ) from exc
    model_class = module.SentenceTransformer
    return model_class(model_id, revision=revision, device=device)
