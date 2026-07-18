from typing import Sequence


EMBEDDING_DIMENSION = 384


def vector_literal(values: Sequence[float]) -> str:
    if len(values) != EMBEDDING_DIMENSION:
        raise ValueError(f"expected {EMBEDDING_DIMENSION} dimensions, got {len(values)}")
    return "[" + ",".join(f"{float(value):.10g}" for value in values) + "]"
