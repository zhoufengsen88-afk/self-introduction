from collections.abc import Sequence


def vector_literal(values: Sequence[float], dimension: int) -> str:
    if len(values) != dimension:
        raise ValueError(f"expected {dimension} dimensions, got {len(values)}")
    return "[" + ",".join(f"{float(value):.10g}" for value in values) + "]"
