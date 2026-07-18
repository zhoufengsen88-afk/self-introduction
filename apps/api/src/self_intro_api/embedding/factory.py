from self_intro_api.embedding.base import EmbeddingProvider
from self_intro_api.embedding.hashing import HashingEmbeddingProvider
from self_intro_api.embedding.sentence_transformer import SentenceTransformerEmbeddingProvider

HASHING_PROVIDER_NAME = "hashing"
MULTILINGUAL_E5_PROVIDER_NAME = "multilingual-e5-small"


def create_embedding_provider(name: str) -> EmbeddingProvider:
    normalized = name.strip().lower()
    if normalized in {HASHING_PROVIDER_NAME, "local-hashing-embedding"}:
        return HashingEmbeddingProvider()
    if normalized in {MULTILINGUAL_E5_PROVIDER_NAME, "e5", "e5-small"}:
        return SentenceTransformerEmbeddingProvider()
    raise ValueError(
        f"unknown embedding provider: {name}. "
        f"Available providers: {HASHING_PROVIDER_NAME}, {MULTILINGUAL_E5_PROVIDER_NAME}"
    )
