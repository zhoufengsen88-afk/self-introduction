from collections.abc import AsyncIterator, Sequence
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path

import pytest
from self_intro_api.core.observability import (
    CompositeTraceSink,
    LiteLLMOpsTraceSink,
    ObservedSpan,
    RagTrace,
)
from self_intro_api.llm.base import LLMMessage, LLMStreamChunk, LLMUsage
from self_intro_api.rag.pipeline import LLMAnswerGenerator, create_rag_service
from self_intro_api.schemas.chat import ChatRequest


class CollectingTraceSink:
    def __init__(self) -> None:
        self.traces: list[RagTrace] = []

    def record(self, trace: RagTrace) -> None:
        self.traces.append(trace)


class FailingTraceSink:
    def record(self, trace: RagTrace) -> None:
        raise RuntimeError("trace backend unavailable")


class UsageReportingLLMProvider:
    model = "fake-interview-model"

    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    async def stream_chat_with_usage(
        self,
        messages: Sequence[LLMMessage],
    ) -> AsyncIterator[LLMStreamChunk]:
        self.messages = list(messages)
        yield LLMStreamChunk(content="周逢森负责平台后端和 RAG 链路。")
        yield LLMStreamChunk(
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated=False,
            )
        )

    async def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        async for chunk in self.stream_chat_with_usage(messages):
            if chunk.content:
                yield chunk.content


class FakeLiteLLMOpsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

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
        self.calls.append(
            (
                "create_trace",
                {
                    "user_input": user_input,
                    "trace_id": trace_id,
                    "model_name": model_name,
                    "status": status,
                    "total_latency_ms": total_latency_ms,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                },
            )
        )
        return trace_id or "generated-trace"

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
        self.calls.append(
            (
                "create_span",
                {
                    "trace_id": trace_id,
                    "span_type": span_type,
                    "name": name,
                    "input": input,
                    "output": output,
                    "status": status,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost": cost,
                    "metadata": metadata or {},
                    "parent_span_id": parent_span_id,
                    "span_id": span_id,
                    "error_message": error_message,
                },
            )
        )
        return {"ok": True}

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
        self.calls.append(
            (
                "update_trace",
                {
                    "trace_id": trace_id,
                    "final_output": final_output,
                    "status": status,
                    "model_name": model_name,
                    "total_latency_ms": total_latency_ms,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                },
            )
        )
        return {"ok": True}


def _sample_trace(error_code: str | None = None) -> RagTrace:
    return RagTrace(
        trace_id="trace-test-lite-llmops",
        route="knowledge_rag",
        intent="responsibility",
        retrieved_chunk_ids=("skillvar-1", "skillvar-2"),
        generation_strategy="deterministic",
        refused=False,
        refusal_reason=None,
        streaming=False,
        first_token_ms=None,
        total_latency_ms=12.34,
        error_code=error_code,
    )


def test_composite_trace_sink_forwards_to_each_sink() -> None:
    first = CollectingTraceSink()
    second = CollectingTraceSink()
    trace = _sample_trace()

    CompositeTraceSink([first, second]).record(trace)

    assert first.traces == [trace]
    assert second.traces == [trace]


def test_lite_llmops_trace_sink_reports_privacy_preserving_summary() -> None:
    client = FakeLiteLLMOpsClient()
    sink = LiteLLMOpsTraceSink(
        base_url="http://127.0.0.1:8001",
        app_id=1,
        api_key="test-api-key",
        model_name="self-introduction-agentic-rag",
        client=client,
    )

    sink.record(_sample_trace())

    assert [name for name, _ in client.calls] == ["create_trace", "create_span", "update_trace"]
    _, trace_payload = client.calls[0]
    _, span_payload = client.calls[1]
    _, update_payload = client.calls[2]
    assert trace_payload["user_input"] is None
    assert span_payload["input"] is None
    assert span_payload["output"] is None
    assert span_payload["status"] == "success"
    assert span_payload["latency_ms"] == 12.34
    assert span_payload["metadata"] == _sample_trace().as_log_fields()
    assert update_payload["final_output"] is None
    assert update_payload["status"] == "success"


def test_lite_llmops_trace_sink_reports_detailed_spans() -> None:
    client = FakeLiteLLMOpsClient()
    sink = LiteLLMOpsTraceSink(
        base_url="http://127.0.0.1:8001",
        app_id=1,
        api_key="test-api-key",
        model_name="fallback-model",
        client=client,
    )
    trace = replace(
        _sample_trace(),
        retrieved_chunk_ids=("skillvar-1",),
        error_code=None,
        user_input="介绍一下 Skillvar",
        final_output="这是最终回答",
        model_name="fake-interview-model",
        spans=(
            ObservedSpan(
                span_id="trace-test-lite-llmops:llm",
                span_type="llm",
                name="调用大模型生成回答",
                input="prompt",
                output="answer",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cost=Decimal("0.000020"),
                metadata={"usage_estimated": False},
            ),
        ),
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        total_cost=Decimal("0.000020"),
    )

    sink.record(trace)

    _, trace_payload = client.calls[0]
    _, span_payload = client.calls[1]
    _, update_payload = client.calls[2]
    assert trace_payload["user_input"] == "介绍一下 Skillvar"
    assert trace_payload["model_name"] == "fake-interview-model"
    assert span_payload["input"] == "prompt"
    assert span_payload["output"] == "answer"
    assert span_payload["total_tokens"] == 15
    assert update_payload["final_output"] == "这是最终回答"
    assert update_payload["total_tokens"] == 15
    assert update_payload["total_cost"] == Decimal("0.000020")


@pytest.mark.asyncio
async def test_llm_rag_trace_contains_agent_steps_prompt_answer_and_tokens() -> None:
    sink = CollectingTraceSink()
    provider = UsageReportingLLMProvider()
    service = create_rag_service(
        Path("knowledge"),
        LLMAnswerGenerator(
            provider,
            prompt_cost_per_1k=0.001,
            completion_cost_per_1k=0.002,
        ),
        trace_sink=sink,
    )

    response = await service.answer(
        ChatRequest(message="介绍一下 Skillvar"),
        trace_id="trace-test-detailed-llm",
    )

    assert response.answer == "周逢森负责平台后端和 RAG 链路。"
    trace = sink.traces[0]
    assert trace.user_input == "介绍一下 Skillvar"
    assert trace.final_output == response.answer
    assert trace.model_name == "fake-interview-model"
    assert trace.prompt_tokens == 10
    assert trace.completion_tokens == 5
    assert trace.total_tokens == 15
    assert trace.total_cost == Decimal("0.000020")
    span_types = [span.span_type for span in trace.spans]
    assert span_types == ["agent", "agent", "agent", "tool", "rag", "prompt", "llm", "agent"]
    prompt_span = next(span for span in trace.spans if span.span_type == "prompt")
    llm_span = next(span for span in trace.spans if span.span_type == "llm")
    retrieval_span = next(span for span in trace.spans if span.span_type == "tool")
    assert "SOURCES" in prompt_span.output
    assert "介绍一下 Skillvar" in llm_span.input
    assert llm_span.output == response.answer
    assert llm_span.total_tokens == 15
    assert llm_span.metadata["usage_estimated"] is False
    assert "skillvar" in retrieval_span.input.lower()


@pytest.mark.asyncio
async def test_knowledge_answer_records_non_sensitive_trace() -> None:
    sink = CollectingTraceSink()
    service = create_rag_service(Path("knowledge"), trace_sink=sink)

    response = await service.answer(
        ChatRequest(message="你在 Skillvar 中具体负责什么？"),
        trace_id="trace-test-knowledge",
    )

    assert response.refused is False
    assert len(sink.traces) == 1
    trace = sink.traces[0]
    assert trace.trace_id == "trace-test-knowledge"
    assert trace.route == "knowledge_rag"
    assert trace.intent == "responsibility"
    assert trace.generation_strategy == "deterministic"
    assert trace.retrieved_chunk_ids
    assert trace.refused is False
    assert trace.streaming is False
    assert trace.total_latency_ms >= 0
    assert {field.name for field in fields(RagTrace)}.isdisjoint(
        {"question", "message", "history", "answer", "prompt", "api_key", "base_url"}
    )


@pytest.mark.asyncio
async def test_insufficient_evidence_trace_has_no_retrieved_chunks() -> None:
    sink = CollectingTraceSink()
    service = create_rag_service(Path("knowledge"), trace_sink=sink)

    response = await service.answer(
        ChatRequest(message="候选人的 AWS 认证证书编号是什么？"),
        trace_id="trace-test-insufficient",
    )

    assert response.refused is True
    trace = sink.traces[0]
    assert trace.generation_strategy == "evidence_policy"
    assert trace.retrieved_chunk_ids == ()
    assert trace.refused is True
    assert trace.refusal_reason == "insufficient_evidence"


@pytest.mark.asyncio
async def test_normal_chat_stream_records_first_token_and_route_policy() -> None:
    sink = CollectingTraceSink()
    service = create_rag_service(Path("knowledge"), trace_sink=sink)

    events = [
        event
        async for event in service.stream(
            ChatRequest(message="你好"),
            trace_id="trace-test-stream",
        )
    ]

    assert events[-1]["event"] == "done"
    trace = sink.traces[0]
    assert trace.trace_id == "trace-test-stream"
    assert trace.route == "normal_chat"
    assert trace.intent is None
    assert trace.generation_strategy == "route_policy"
    assert trace.streaming is True
    assert trace.first_token_ms is not None


@pytest.mark.asyncio
async def test_trace_sink_failure_does_not_break_chat_response() -> None:
    service = create_rag_service(Path("knowledge"), trace_sink=FailingTraceSink())

    response = await service.answer(ChatRequest(message="你好"))

    assert response.refused is False
    assert "个人经历" in response.answer
