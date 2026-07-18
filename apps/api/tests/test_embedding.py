import math

import pytest
from self_intro_api.embedding.hashing import HashingEmbeddingProvider
from self_intro_api.embedding.vector import vector_literal


def test_hashing_embedding_is_deterministic_and_normalized() -> None:
    provider = HashingEmbeddingProvider()

    first = provider.embed_query("Skillvar 混合检索 FastAPI MongoDB")
    second = provider.embed_query("Skillvar 混合检索 FastAPI MongoDB")

    assert first == second
    assert len(first) == provider.spec.dimension
    assert math.isclose(sum(value * value for value in first), 1.0)


def test_hashing_embedding_handles_empty_text() -> None:
    provider = HashingEmbeddingProvider()

    embedding = provider.embed_query("")

    assert len(embedding) == provider.spec.dimension
    assert set(embedding) == {0.0}


def test_vector_literal_uses_pgvector_input_format() -> None:
    provider = HashingEmbeddingProvider()
    values = [0.0] * provider.spec.dimension
    values[0] = 1.25

    literal = vector_literal(values, provider.spec.dimension)

    assert literal.startswith("[1.25,0,0")
    assert literal.endswith("]")


def test_vector_literal_rejects_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="expected 384 dimensions"):
        vector_literal([0.0, 1.0], 384)
