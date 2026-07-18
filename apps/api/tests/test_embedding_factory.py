import pytest
from self_intro_api.embedding.factory import create_embedding_provider
from self_intro_api.embedding.hashing import HashingEmbeddingProvider
from self_intro_api.embedding.sentence_transformer import (
    MULTILINGUAL_E5_SMALL_CONFIG,
    MULTILINGUAL_E5_SMALL_SPEC,
)


def test_create_hashing_provider() -> None:
    provider = create_embedding_provider("hashing")

    assert isinstance(provider, HashingEmbeddingProvider)


def test_create_unknown_provider_fails() -> None:
    with pytest.raises(ValueError, match="unknown embedding provider"):
        create_embedding_provider("missing-provider")


def test_multilingual_e5_configuration_is_pinned() -> None:
    assert MULTILINGUAL_E5_SMALL_SPEC.name == "multilingual-e5-small"
    assert MULTILINGUAL_E5_SMALL_SPEC.revision == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert MULTILINGUAL_E5_SMALL_SPEC.dimension == 384
    assert MULTILINGUAL_E5_SMALL_CONFIG.model_id == "intfloat/multilingual-e5-small"
    assert MULTILINGUAL_E5_SMALL_CONFIG.query_prefix == "query: "
    assert MULTILINGUAL_E5_SMALL_CONFIG.passage_prefix == "passage: "
