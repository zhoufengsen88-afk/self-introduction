from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from self_intro_api.cli.eval_llm import build_summary, evaluate_case, load_enabled_records
from self_intro_api.llm.base import LLMMessage
from self_intro_api.rag.pipeline import LLMAnswerGenerator, create_rag_service


class InterviewAnswerProvider:
    async def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        prompt = "\n".join(message.content for message in messages)
        assert "skillvar-responsibilities" in prompt
        yield "我负责平台后端和混合检索，"
        yield "并负责测试和部署运维。"


@pytest.mark.asyncio
async def test_evaluate_llm_case_records_route_citations_and_latency() -> None:
    service = create_rag_service(
        Path("knowledge"),
        LLMAnswerGenerator(InterviewAnswerProvider()),
    )
    record = {
        "id": "test-responsibility",
        "category": "responsibility",
        "question": "你在 Skillvar 中负责什么？",
        "history": [],
        "expected_route": "knowledge_rag",
        "citation_required": True,
        "expected_document_ids": ["skillvar-responsibilities"],
        "expected_chunk_ids": [],
        "required_facts": ["平台后端", "混合检索", "测试和部署运维"],
        "forbidden_facts": ["负责产品规划"],
        "should_refuse": False,
        "refusal_reason": None,
        "acceptance_criteria": ["区分个人与团队职责"],
    }

    row = await evaluate_case(service, record, top_k=8)

    assert row["actual_route"] == "knowledge_rag"
    assert row["actual_intent"] == "responsibility"
    assert row["generation_strategy"] == "llm"
    assert row["route_ok"] is True
    assert row["citation_presence_ok"] is True
    assert row["document_hit"] is True
    assert row["required_string_recall"] == 1.0
    assert row["forbidden_ok"] is True
    assert row["first_token_ms"] is not None
    assert row["total_latency_ms"] >= row["first_token_ms"]
    assert row["human_review"]["faithfulness_score"] is None


def test_load_enabled_records_supports_case_selection_and_limit() -> None:
    records = load_enabled_records(
        Path("evals/datasets/m5-agent-qa-v1.jsonl"),
        case_ids={"m5-skillvar-overview-001", "m5-restricted-001"},
        limit=1,
    )

    assert len(records) == 1
    assert records[0]["id"] == "m5-skillvar-overview-001"


def test_build_summary_keeps_human_review_separate_from_deterministic_checks() -> None:
    row = {
        "route_ok": True,
        "citation_presence_ok": True,
        "document_hit": True,
        "chunk_hit": True,
        "refusal_ok": True,
        "forbidden_ok": True,
        "deterministic_checks_pass": True,
        "required_string_recall": 0.5,
        "first_token_ms": 120.0,
        "total_latency_ms": 350.0,
        "error_code": None,
    }

    summary = build_summary([row])

    assert summary["deterministic_checks_pass_rate"] == 1.0
    assert summary["mean_required_string_recall"] == 0.5
    assert summary["human_review_completed"] is False
