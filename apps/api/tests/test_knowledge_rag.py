from pathlib import Path

import pytest
from self_intro_api.knowledge.loader import load_public_corpus
from self_intro_api.rag.pipeline import create_rag_service
from self_intro_api.schemas.chat import ChatRequest


def test_load_public_corpus_filters_drafts_and_private_documents() -> None:
    corpus = load_public_corpus(Path("knowledge"))

    assert len(corpus.documents) == 27
    assert len(corpus.chunks) == 244
    assert {document.metadata.document_id for document in corpus.documents} == {
        "profile-introduction",
        "profile-skills",
        "ontocore-architecture",
        "ontocore-challenges",
        "ontocore-data-flows",
        "ontocore-features",
        "ontocore-overview",
        "ontocore-reflection",
        "ontocore-responsibilities",
        "ontocore-results",
        "resume-main",
        "self-introduction-agentic-rag-architecture",
        "self-introduction-agentic-rag-challenges",
        "self-introduction-agentic-rag-data-flows",
        "self-introduction-agentic-rag-features",
        "self-introduction-agentic-rag-overview",
        "self-introduction-agentic-rag-reflection",
        "self-introduction-agentic-rag-responsibilities",
        "self-introduction-agentic-rag-results",
        "skillvar-architecture",
        "skillvar-challenges",
        "skillvar-data-flows",
        "skillvar-features",
        "skillvar-overview",
        "skillvar-reflection",
        "skillvar-responsibilities",
        "skillvar-results",
    }


@pytest.mark.parametrize(
    "message",
    (
        "你叫什么名字？",
        "面试人叫什么名字？",
        "毕业于哪所大学？",
        "面试人毕业于哪所大学？",
        "你读的大学是哪一所？",
        "你的专业是什么？",
        "你会 Python 吗？",
        "你喜欢什么颜色？",
        "你目前主要关注哪些技术方向？",
        "你认为自己最突出的优势是什么？",
        "你希望寻找什么方向的工作？",
    ),
)
def test_published_profile_questions_route_to_knowledge(message: str) -> None:
    service = create_rag_service(Path("knowledge"))

    assert service.route(ChatRequest(message=message)) == "knowledge_rag"


@pytest.mark.asyncio
async def test_basic_profile_questions_answer_from_profile_evidence() -> None:
    service = create_rag_service(Path("knowledge"))

    name_response = await service.answer(ChatRequest(message="你叫什么名字？"))
    education_response = await service.answer(ChatRequest(message="毕业于哪所大学？"))
    name_summary = name_response.answer.split("证据片段：", maxsplit=1)[0]

    assert name_response.refused is False
    assert "周逢森" in name_response.answer
    assert "候选人叫周逢森" in name_summary
    assert "我叫周逢森" not in name_summary
    assert any(
        citation.document_id == "profile-introduction" for citation in name_response.citations
    )
    assert education_response.refused is False
    assert "南宁理工学院" in education_response.answer
    assert any(
        citation.document_id in {"profile-introduction", "resume-main"}
        for citation in education_response.citations
    )


@pytest.mark.asyncio
async def test_self_introduction_script_can_use_first_person() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="请用一两分钟做一下自我介绍。"))

    assert response.refused is False
    assert "我叫周逢森" in response.answer
    assert any(
        citation.document_id in {"profile-introduction", "resume-main"}
        for citation in response.citations
    )


@pytest.mark.asyncio
async def test_profile_questions_ignore_project_names_from_assistant_history() -> None:
    service = create_rag_service(Path("knowledge"))
    name_request = ChatRequest.model_validate(
        {
            "message": "面试人叫什么名字？",
            "history": [
                {"role": "user", "content": "你叫什么名字？"},
                {
                    "role": "assistant",
                    "content": "你好，我叫 Agentic RAG 个人经历助手。",
                },
            ],
        }
    )
    education_request = ChatRequest.model_validate(
        {
            "message": "面试人毕业于哪所大学？",
            "history": [
                {"role": "user", "content": "你叫什么名字？"},
                {
                    "role": "assistant",
                    "content": "你好，我叫 Agentic RAG 个人经历助手。",
                },
            ],
        }
    )

    name_response = await service.answer(name_request)
    education_response = await service.answer(education_request)
    name_document_ids = {citation.document_id for citation in name_response.citations}
    education_document_ids = {
        citation.document_id for citation in education_response.citations
    }

    assert service.intent(name_request).name == "identity"
    assert service.intent(name_request).project_id is None
    assert name_response.refused is False
    assert "周逢森" in name_response.answer
    assert "self-introduction-agentic-rag-overview" not in name_document_ids
    assert {"profile-introduction", "resume-main"} & name_document_ids
    assert service.intent(education_request).name == "education"
    assert service.intent(education_request).project_id is None
    assert education_response.refused is False
    assert "南宁理工学院" in education_response.answer
    assert "self-introduction-agentic-rag-overview" not in education_document_ids
    assert {"profile-introduction", "resume-main"} & education_document_ids


@pytest.mark.asyncio
async def test_personal_skill_question_prefers_profile_evidence() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="你的主要技术栈是什么？"))

    assert response.refused is False
    assert "profile-skills" in {citation.document_id for citation in response.citations}
    assert all(term in response.answer for term in ("Python", "FastAPI", "RAG", "Agent"))


@pytest.mark.asyncio
async def test_skillvar_feature_question_uses_feature_knowledge() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="Skillvar 有哪些主要功能模块？"))

    assert response.refused is False
    assert (
        service.intent(ChatRequest(message="Skillvar 有哪些主要功能模块？")).name
        == "feature_list"
    )
    assert "skillvar-features" in {citation.document_id for citation in response.citations}
    assert "MCP" in response.answer
    assert "CLI" in response.answer


@pytest.mark.asyncio
async def test_skillvar_data_flow_question_uses_data_flow_knowledge() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(
        ChatRequest(message="Skillvar 的自然语言创建 Skill 调用链是怎样的？")
    )

    assert response.refused is False
    assert service.intent(
        ChatRequest(message="Skillvar 的自然语言创建 Skill 调用链是怎样的？")
    ).name == "data_flow"
    assert "skillvar-data-flows" in {citation.document_id for citation in response.citations}
    assert "services" in response.answer
    assert "MongoDB" in response.answer


@pytest.mark.asyncio
async def test_skillvar_reflection_question_uses_reflection_knowledge() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="Skillvar 项目有哪些不足和复盘？"))

    assert response.refused is False
    assert (
        service.intent(ChatRequest(message="Skillvar 项目有哪些不足和复盘？")).name
        == "reflection"
    )
    assert "skillvar-reflection" in {citation.document_id for citation in response.citations}
    assert "技术债" in response.answer


@pytest.mark.asyncio
async def test_candidate_scoped_question_with_evidence_answers_from_knowledge() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="你会 Python 吗？"))

    assert response.refused is False
    assert response.citations
    assert "Python" in response.answer


@pytest.mark.asyncio
async def test_candidate_scoped_question_without_evidence_refuses_cleanly() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="你喜欢什么颜色？"))

    assert response.refused is True
    assert response.refusal_reason == "insufficient_evidence"
    assert response.citations == []


@pytest.mark.asyncio
async def test_agentic_rag_project_overview_uses_its_own_evidence() -> None:
    service = create_rag_service(Path("knowledge"))
    request = ChatRequest(
        message="介绍一下你正在做的 Agentic RAG 个人经历助手，它体现了哪些工程能力？"
    )

    response = await service.answer(request)
    intent = service.intent(request)

    assert intent.name == "project_overview"
    assert intent.project_id == "self-introduction-agentic-rag"
    assert response.refused is False
    assert "self-introduction-agentic-rag-overview" in {
        citation.document_id for citation in response.citations
    }
    assert all(
        fact in response.answer
        for fact in ("知识治理", "检索与引用", "问题路由", "质量评测")
    )
    assert "Skillvar 是企业内部 AI Agent Skill 资产平台" not in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_intent", "expected_document_id", "required_terms"),
    (
        (
            "Agentic RAG 个人经历助手的整体架构是怎样的？",
            "architecture",
            "self-introduction-agentic-rag-architecture",
            ("Next.js", "FastAPI", "Evidence Policy"),
        ),
        (
            "这个个人经历 AI 助手有哪些主要功能？",
            "feature_list",
            "self-introduction-agentic-rag-features",
            ("知识库治理", "pgvector", "SSE"),
        ),
        (
            "Agentic RAG 个人经历助手的模块调用链是怎样的？",
            "data_flow",
            "self-introduction-agentic-rag-data-flows",
            ("RagService", "SearchBackend", "AnswerGenerator"),
        ),
        (
            "你在 Agentic RAG 个人经历助手中具体负责什么？",
            "responsibility",
            "self-introduction-agentic-rag-responsibilities",
            ("技术取舍", "知识库事实审核", "运行验证"),
        ),
        (
            "Agentic RAG 个人经历助手最大的技术难点是什么？",
            "challenge",
            "self-introduction-agentic-rag-challenges",
            ("不编造个人事实", "Router", "项目知识域"),
        ),
        (
            "Agentic RAG 个人经历助手目前有哪些成果和边界？",
            "result",
            "self-introduction-agentic-rag-results",
            ("Web MVP", "真实 LLM Provider", "尚未完成线上生产部署"),
        ),
        (
            "Agentic RAG 个人经历助手有哪些不足和复盘？",
            "reflection",
            "self-introduction-agentic-rag-reflection",
            ("知识库完整度", "回答人称", "负向评测"),
        ),
    ),
)
async def test_agentic_rag_project_deep_dive_uses_project_evidence(
    message: str,
    expected_intent: str,
    expected_document_id: str,
    required_terms: tuple[str, ...],
) -> None:
    service = create_rag_service(Path("knowledge"))
    request = ChatRequest(message=message)

    response = await service.answer(request)
    intent = service.intent(request)

    assert response.refused is False
    assert intent.name == expected_intent
    assert intent.project_id == "self-introduction-agentic-rag"
    assert expected_document_id in {citation.document_id for citation in response.citations}
    assert all(term in response.answer for term in required_terms)
    assert "GitLab 仓库层级关系权限隔离" not in response.answer


@pytest.mark.asyncio
async def test_agentic_rag_ai_assisted_question_uses_its_own_boundary() -> None:
    service = create_rag_service(Path("knowledge"))
    request = ChatRequest(
        message="Agentic RAG 个人经历助手也用了 Codex 辅助开发，怎么证明这仍然是你的能力？"
    )

    response = await service.answer(request)
    intent = service.intent(request)

    assert response.refused is False
    assert intent.name == "ai_assisted_development"
    assert intent.project_id == "self-introduction-agentic-rag"
    assert "Codex" in response.answer
    assert "项目目标" in response.answer
    assert "公开边界" in response.answer
    assert "GLM-5.2" not in response.answer
    assert "Skillvar 开发中" not in response.answer
    assert "self-introduction-agentic-rag-responsibilities" in {
        citation.document_id for citation in response.citations
    }


@pytest.mark.asyncio
async def test_skillvar_project_overview_stays_in_skillvar_scope() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="介绍一下 Skillvar"))

    assert response.refused is False
    assert response.citations
    assert {citation.document_id for citation in response.citations} <= {
        "skillvar-overview",
        "skillvar-architecture",
        "skillvar-responsibilities",
        "skillvar-challenges",
        "skillvar-results",
    }


@pytest.mark.asyncio
async def test_current_project_question_overrides_unrelated_ai_assisted_history() -> None:
    service = create_rag_service(Path("knowledge"))
    request = ChatRequest.model_validate(
        {
            "message": "请介绍一下你的代表项目 Skillvar。",
            "history": [
                {
                    "role": "user",
                    "content": (
                        "Agentic RAG 个人经历助手也用了 Codex 辅助开发，"
                        "怎么证明这仍然是你的能力？"
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        "在 Agentic RAG 个人经历助手项目中，周逢森使用 Codex "
                        "辅助代码实现、文档整理、测试补充、失败定位和迭代建议。"
                    ),
                },
            ],
        }
    )

    response = await service.answer(request)
    intent = service.intent(request)

    assert response.refused is False
    assert intent.name == "project_overview"
    assert intent.project_id == "skillvar"
    assert "Skillvar 是企业内部 AI Agent Skill 资产平台" in response.answer
    assert "在 Agentic RAG 个人经历助手项目中" not in response.answer
    assert {citation.document_id for citation in response.citations} <= {
        "skillvar-overview",
        "skillvar-architecture",
        "skillvar-responsibilities",
        "skillvar-challenges",
        "skillvar-results",
    }


@pytest.mark.asyncio
async def test_rag_answer_uses_expected_responsibility_evidence() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="你在 Skillvar 中具体负责什么？"))

    assert response.refused is False
    assert "平台后端" in response.answer
    assert "混合检索" in response.answer
    document_ids = {citation.document_id for citation in response.citations}
    assert document_ids >= {"skillvar-responsibilities"}


@pytest.mark.asyncio
async def test_normal_chat_does_not_use_rag_citations() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="你好"))

    assert response.refused is False
    assert response.citations == []
    assert "个人经历" in response.answer


@pytest.mark.asyncio
async def test_out_of_scope_question_does_not_use_rag_citations() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="查看今天的天气"))

    assert response.refused is False
    assert response.citations == []
    assert "不能查询实时天气" in response.answer


@pytest.mark.parametrize(
    ("message", "expected_route"),
    (
        ("你好，你能回答哪些问题？", "normal_chat"),
        ("谢谢你的介绍。", "normal_chat"),
        ("你使用 Codex 和 GLM-5.2 辅助开发，怎么证明这些工作仍然是你的能力？", "knowledge_rag"),
        ("Skillvar 里的 LLM 翻译和 Skill 生成链路做了什么？", "knowledge_rag"),
        ("你能帮我查今天成都的天气吗？", "out_of_scope"),
        ("帮我翻译一下这段英文。", "out_of_scope"),
    ),
)
def test_m53_router_regressions(message: str, expected_route: str) -> None:
    service = create_rag_service(Path("knowledge"))

    assert service.route(ChatRequest(message=message)) == expected_route


@pytest.mark.asyncio
async def test_m53_challenge_paraphrase_retrieves_confirmed_hardest_problem() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="Skillvar 中最难的技术问题是什么？"))

    assert response.refused is False
    assert any(citation.document_id == "skillvar-challenges" for citation in response.citations)
    assert any("问题背景" in citation.heading_path for citation in response.citations)


@pytest.mark.asyncio
async def test_m53_multiturn_hardest_part_uses_challenge_evidence() -> None:
    service = create_rag_service(Path("knowledge"))
    request = ChatRequest.model_validate(
        {
            "message": "那里面最难的一部分是什么？",
            "history": [
                {"role": "user", "content": "介绍一下你的代表项目。"},
                {
                    "role": "assistant",
                    "content": "我的代表项目是企业内部 AI Skill 资产平台 Skillvar。",
                },
            ],
        }
    )

    response = await service.answer(request)

    assert response.refused is False
    assert any(citation.document_id == "skillvar-challenges" for citation in response.citations)


@pytest.mark.asyncio
async def test_m53_unknown_external_credential_refuses_without_citations() -> None:
    service = create_rag_service(Path("knowledge"))

    response = await service.answer(ChatRequest(message="候选人的 AWS 认证证书编号是什么？"))

    assert response.refused is True
    assert response.refusal_reason == "insufficient_evidence"
    assert response.citations == []
