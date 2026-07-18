from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from self_intro_api.llm.base import LLMMessage
from self_intro_api.rag.context import build_source_context
from self_intro_api.rag.pipeline import LLMAnswerGenerator, create_rag_service
from self_intro_api.schemas.chat import ChatRequest


class StubLLMProvider:
    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    async def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        self.messages = list(messages)
        yield "我负责平台后端、混合检索和 Agent 工作流相关能力。"


class UnexpectedLLMProvider:
    async def stream_chat(self, messages: Sequence[LLMMessage]) -> AsyncIterator[str]:
        raise AssertionError("AI-assisted responsibility boundary must not call the LLM")
        yield "unreachable"


@pytest.mark.asyncio
async def test_llm_answer_generator_uses_retrieved_context() -> None:
    provider = StubLLMProvider()
    service = create_rag_service(Path("knowledge"), LLMAnswerGenerator(provider))

    response = await service.answer(ChatRequest(message="你在 Skillvar 中具体负责什么？"))

    assert response.refused is False
    assert "平台后端" in response.answer
    assert response.citations
    prompt = "\n".join(message.content for message in provider.messages)
    assert "SOURCES:" in prompt
    assert "skillvar-responsibilities" in prompt


def test_build_source_context_contains_chunk_metadata() -> None:
    service = create_rag_service(Path("knowledge"))
    results = service.retrieve("Skillvar 权限难点", top_k=1)

    context = build_source_context(results)

    assert "[SOURCE 1]" in context
    assert "chunk_id:" in context
    assert "document_id:" in context
    assert "content:" in context


@pytest.mark.asyncio
async def test_llm_prompt_disambiguates_candidate_from_assistant_identity() -> None:
    provider = StubLLMProvider()
    service = create_rag_service(Path("knowledge"), LLMAnswerGenerator(provider))

    response = await service.answer(ChatRequest(message="你叫什么名字？"))

    assert response.refused is False
    prompt = "\n".join(message.content for message in provider.messages)
    assert "默认使用第三人称介绍候选人周逢森" in prompt
    assert "不要用“我”代指候选人" in prompt
    assert "用户问题中的“你”“我”“面试人”“候选人”默认都指候选人周逢森" in prompt
    assert "不要把助手名称" in prompt
    assert "profile-introduction" in prompt or "resume-main" in prompt


@pytest.mark.asyncio
async def test_llm_prompt_allows_first_person_for_self_introduction_script() -> None:
    provider = StubLLMProvider()
    service = create_rag_service(Path("knowledge"), LLMAnswerGenerator(provider))

    response = await service.answer(ChatRequest(message="请用一两分钟做一下自我介绍。"))

    assert response.refused is False
    prompt = "\n".join(message.content for message in provider.messages)
    assert "用户正在请求第一人称表达、自我介绍稿或面试口述稿" in prompt
    assert "可以使用候选人第一人称" in prompt


@pytest.mark.asyncio
async def test_ai_assisted_development_uses_grounded_policy_answer() -> None:
    service = create_rag_service(
        Path("knowledge"),
        LLMAnswerGenerator(UnexpectedLLMProvider()),
    )

    response = await service.answer(
        ChatRequest(
            message="你使用 Codex 和 GLM-5.2 辅助开发，怎么证明这些工作仍然是你的能力？"
        )
    )

    assert response.refused is False
    assert "周逢森使用 Codex 和 GLM-5.2" in response.answer
    assert "理解、集成、调试、测试、部署和验证" in response.answer
    assert "不能作这种夸大表述" in response.answer
    assert "独立完成所有架构" not in response.answer
    assert {citation.document_id for citation in response.citations} >= {
        "skillvar-responsibilities"
    }


@pytest.mark.asyncio
async def test_agentic_rag_ai_assisted_development_uses_project_policy_answer() -> None:
    service = create_rag_service(
        Path("knowledge"),
        LLMAnswerGenerator(UnexpectedLLMProvider()),
    )

    response = await service.answer(
        ChatRequest(
            message=(
                "Agentic RAG 个人经历助手也用了 Codex 辅助开发，"
                "怎么证明这仍然是你的能力？"
            )
        )
    )

    assert response.refused is False
    assert "周逢森使用 Codex 辅助代码实现" in response.answer
    assert "确认公开边界" in response.answer
    assert "运行验证" in response.answer
    assert "GLM-5.2" not in response.answer
    assert "Skillvar 开发中" not in response.answer
    assert {citation.document_id for citation in response.citations} >= {
        "self-introduction-agentic-rag-responsibilities"
    }
