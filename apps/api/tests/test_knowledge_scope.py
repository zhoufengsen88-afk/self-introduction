from pathlib import Path

import pytest
from self_intro_api.rag.pipeline import create_rag_service
from self_intro_api.schemas.chat import ChatRequest


def _write_project_document(
    root: Path,
    *,
    filename: str,
    document_id: str,
    title: str,
    project_id: str,
    status: str,
    aliases: str = "",
    body: str,
) -> None:
    project_dir = root / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: {aliases}\n" if aliases else ""
    (project_dir / filename).write_text(
        f"""---
document_id: {document_id}
title: {title}
category: project
project_id: {project_id}
visibility: public
status: {status}
updated_at: 2026-07-18
{alias_line}---

{body}
""",
        encoding="utf-8",
    )


@pytest.fixture
def dynamic_knowledge_root(tmp_path: Path) -> Path:
    _write_project_document(
        tmp_path,
        filename="overview.md",
        document_id="nebula-forge-overview",
        title="Nebula Forge 项目概述",
        project_id="nebula-forge",
        status="published",
        aliases="星云工坊,Nebula",
        body="""# Nebula Forge 项目概述

## 项目摘要

Nebula Forge 是一个用于验证动态项目注册能力的公开测试项目。
""",
    )
    _write_project_document(
        tmp_path,
        filename="architecture.md",
        document_id="nebula-forge-architecture",
        title="Nebula Forge 项目架构",
        project_id="nebula-forge",
        status="published",
        body="""# Nebula Forge 项目架构

## 逻辑架构

项目由 API、业务服务和数据库三个组件组成。
""",
    )
    _write_project_document(
        tmp_path,
        filename="overview.md",
        document_id="hidden-quartz-overview",
        title="Hidden Quartz 项目概述",
        project_id="hidden-quartz",
        status="draft",
        body="# Hidden Quartz\n\n这是不应进入公开检索的草稿项目。",
    )
    return tmp_path


@pytest.mark.parametrize(
    "message",
    (
        "请介绍 Nebula Forge",
        "请介绍一下星云工坊",
        "What is Nebula?",
    ),
)
def test_published_project_names_and_aliases_are_registered_dynamically(
    dynamic_knowledge_root: Path,
    message: str,
) -> None:
    service = create_rag_service(dynamic_knowledge_root)
    request = ChatRequest(message=message)

    assert service.route(request) == "knowledge_rag"
    assert service.intent(request).name == "project_overview"


@pytest.mark.asyncio
async def test_dynamic_project_architecture_is_scoped_to_its_own_documents(
    dynamic_knowledge_root: Path,
) -> None:
    service = create_rag_service(dynamic_knowledge_root)
    request = ChatRequest(message="Nebula Forge 的架构是什么？")

    response = await service.answer(request)

    assert response.refused is False
    assert response.citations[0].document_id == "nebula-forge-architecture"
    assert {citation.document_id for citation in response.citations} <= {
        "nebula-forge-overview",
        "nebula-forge-architecture",
    }


def test_draft_project_is_not_registered(dynamic_knowledge_root: Path) -> None:
    service = create_rag_service(dynamic_knowledge_root)

    assert service.route(ChatRequest(message="请介绍 Hidden Quartz")) == "out_of_scope"
    assert {project.project_id for project in service.knowledge_scope.projects} == {
        "nebula-forge"
    }
