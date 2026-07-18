import logging
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class RagTrace:
    trace_id: str
    route: str
    intent: str | None
    retrieved_chunk_ids: tuple[str, ...]
    generation_strategy: str
    refused: bool
    refusal_reason: str | None
    streaming: bool
    first_token_ms: float | None
    total_latency_ms: float
    error_code: str | None

    def as_log_fields(self) -> dict[str, object]:
        return asdict(self)


class TraceSink(Protocol):
    def record(self, trace: RagTrace) -> None:
        """Record one completed RAG request without prompt or answer content."""
        ...


class LoggingTraceSink:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("self_intro_api.rag_trace")

    def record(self, trace: RagTrace) -> None:
        self.logger.info("rag_request_completed", extra={"event_data": trace.as_log_fields()})
