from dataclasses import fields
from pathlib import Path

import pytest
from self_intro_api.core.observability import RagTrace
from self_intro_api.rag.pipeline import create_rag_service
from self_intro_api.schemas.chat import ChatRequest


class CollectingTraceSink:
    def __init__(self) -> None:
        self.traces: list[RagTrace] = []

    def record(self, trace: RagTrace) -> None:
        self.traces.append(trace)


class FailingTraceSink:
    def record(self, trace: RagTrace) -> None:
        raise RuntimeError("trace backend unavailable")


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
