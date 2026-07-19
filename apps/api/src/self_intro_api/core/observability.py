import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from importlib import import_module
from typing import Any, Protocol, cast


@dataclass(frozen=True)
class ObservedSpan:
    span_id: str
    span_type: str
    name: str
    input: str | None = None
    output: str | None = None
    status: str = "success"
    latency_ms: float = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: Decimal = Decimal("0")
    metadata: dict[str, object] = field(default_factory=dict)
    parent_span_id: str | None = None
    error_message: str | None = None


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
    user_input: str | None = None
    final_output: str | None = None
    model_name: str | None = None
    spans: tuple[ObservedSpan, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: Decimal = Decimal("0")

    def as_log_fields(self) -> dict[str, object]:
        """Return non-sensitive fields for application logs."""

        return {
            "trace_id": self.trace_id,
            "route": self.route,
            "intent": self.intent,
            "retrieved_chunk_ids": self.retrieved_chunk_ids,
            "generation_strategy": self.generation_strategy,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "streaming": self.streaming,
            "first_token_ms": self.first_token_ms,
            "total_latency_ms": self.total_latency_ms,
            "error_code": self.error_code,
            "model_name": self.model_name,
            "span_count": len(self.spans),
            "total_tokens": self.total_tokens,
            "total_cost": str(self.total_cost),
        }


class TraceSink(Protocol):
    def record(self, trace: RagTrace) -> None:
        """Record one completed RAG request."""
        ...


class LiteLLMOpsClientLike(Protocol):
    def create_trace(
        self,
        user_input: str | None = None,
        trace_id: str | None = None,
        model_name: str | None = None,
        status: str = "running",
        total_latency_ms: int = 0,
        total_tokens: int = 0,
        total_cost: Decimal = Decimal("0"),
    ) -> str:
        """Create one remote trace."""
        ...

    def create_span(
        self,
        trace_id: str,
        span_type: str,
        name: str,
        input: str | None = None,
        output: str | None = None,
        status: str = "success",
        latency_ms: float = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cost: Decimal = Decimal("0"),
        metadata: dict[str, object] | None = None,
        parent_span_id: str | None = None,
        span_id: str | None = None,
        error_message: str | None = None,
    ) -> object:
        """Create one remote span."""
        ...

    def update_trace(
        self,
        trace_id: str,
        final_output: str | None = None,
        status: str | None = None,
        model_name: str | None = None,
        total_latency_ms: int | None = None,
        total_tokens: int | None = None,
        total_cost: Decimal | None = None,
    ) -> object:
        """Update one remote trace."""
        ...


class LoggingTraceSink:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("self_intro_api.rag_trace")

    def record(self, trace: RagTrace) -> None:
        self.logger.info("rag_request_completed", extra={"event_data": trace.as_log_fields()})


class CompositeTraceSink:
    def __init__(
        self,
        sinks: Iterable[TraceSink],
        logger: logging.Logger | None = None,
    ) -> None:
        self.sinks = tuple(sinks)
        self.logger = logger or logging.getLogger("self_intro_api.rag_trace")

    def record(self, trace: RagTrace) -> None:
        for sink in self.sinks:
            try:
                sink.record(trace)
            except Exception:
                self.logger.exception(
                    "trace_sink_record_failed",
                    extra={
                        "event_data": {
                            "sink": type(sink).__name__,
                            "trace_id": trace.trace_id,
                        }
                    },
                )


class LiteLLMOpsTraceSink:
    """Report detailed Agent/RAG traces to LiteLLMOps."""

    def __init__(
        self,
        *,
        base_url: str,
        app_id: int,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 2.0,
        client: LiteLLMOpsClientLike | None = None,
    ) -> None:
        self.model_name = model_name
        self.client = client or self._create_client(
            base_url=base_url,
            app_id=app_id,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def record(self, trace: RagTrace) -> None:
        status = "error" if trace.error_code else "success"
        model_name = trace.model_name or self.model_name
        self.client.create_trace(
            user_input=trace.user_input,
            trace_id=trace.trace_id,
            model_name=model_name,
        )
        for span in trace.spans or self._summary_spans(trace, status):
            self.client.create_span(
                trace_id=trace.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                span_type=span.span_type,
                name=span.name,
                input=span.input,
                output=span.output,
                status=span.status,
                latency_ms=span.latency_ms,
                prompt_tokens=span.prompt_tokens,
                completion_tokens=span.completion_tokens,
                total_tokens=span.total_tokens,
                cost=span.cost,
                metadata=span.metadata,
                error_message=span.error_message,
            )
        self.client.update_trace(
            trace_id=trace.trace_id,
            final_output=trace.final_output,
            status=status,
            model_name=model_name,
            total_latency_ms=int(trace.total_latency_ms),
            total_tokens=trace.total_tokens,
            total_cost=trace.total_cost,
        )

    @staticmethod
    def _summary_spans(trace: RagTrace, status: str) -> tuple[ObservedSpan, ...]:
        return (
            ObservedSpan(
                span_id=f"{trace.trace_id}:rag-summary",
                span_type="rag",
                name="RAG 请求汇总",
                status=status,
                latency_ms=trace.total_latency_ms,
                metadata=trace.as_log_fields(),
                error_message=trace.error_code,
            ),
        )

    @staticmethod
    def _create_client(
        *,
        base_url: str,
        app_id: int,
        api_key: str,
        timeout_seconds: float,
    ) -> LiteLLMOpsClientLike:
        try:
            lite_llmops = import_module("lite_llmops")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "LiteLLMOps SDK is not installed. Run: "
                "uv pip install -e /Users/zfs/Documents/lite-llmops/sdk/python"
            ) from exc
        client_factory = cast(Any, lite_llmops).LiteLLMOpsClient
        return cast(
            LiteLLMOpsClientLike,
            client_factory(
                base_url=base_url,
                app_id=app_id,
                api_key=api_key,
                timeout=timeout_seconds,
                raise_on_error=False,
            ),
        )
