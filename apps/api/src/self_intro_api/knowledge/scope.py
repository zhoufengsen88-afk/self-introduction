import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from self_intro_api.knowledge.models import KnowledgeDocument

PROJECT_TITLE_SUFFIX_RE = re.compile(
    r"(?:项目)?(?:概述|架构|职责|难点|成果|复盘|功能清单|模块调用链|源码核验记录)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProjectKnowledge:
    project_id: str
    aliases: tuple[str, ...]
    document_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeScope:
    projects: tuple[ProjectKnowledge, ...] = ()

    def match_project(self, text: str) -> ProjectKnowledge | None:
        normalized = normalize_scope_text(text)
        matches = [
            (len(normalize_scope_text(alias)), project)
            for project in self.projects
            for alias in project.aliases
            if normalize_scope_text(alias) in normalized
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], item[1].project_id))
        return matches[0][1]


def build_knowledge_scope(documents: Iterable[KnowledgeDocument]) -> KnowledgeScope:
    aliases_by_project: dict[str, set[str]] = defaultdict(set)
    documents_by_project: dict[str, set[str]] = defaultdict(set)
    for document in documents:
        metadata = document.metadata
        if not metadata.project_id:
            continue
        project_id = metadata.project_id
        aliases_by_project[project_id].update(
            {
                project_id,
                project_id.replace("-", " "),
                _project_title_alias(metadata.title),
                *metadata.aliases,
            }
        )
        documents_by_project[project_id].add(metadata.document_id)

    projects = []
    for project_id in sorted(documents_by_project):
        aliases = tuple(
            sorted(
                {
                    alias.strip()
                    for alias in aliases_by_project[project_id]
                    if len(normalize_scope_text(alias)) >= 2
                },
                key=lambda alias: (-len(normalize_scope_text(alias)), alias.lower()),
            )
        )
        projects.append(
            ProjectKnowledge(
                project_id=project_id,
                aliases=aliases,
                document_ids=tuple(sorted(documents_by_project[project_id])),
            )
        )
    return KnowledgeScope(tuple(projects))


def load_knowledge_scope(root: Path) -> KnowledgeScope:
    from self_intro_api.knowledge.loader import load_public_documents

    return build_knowledge_scope(load_public_documents(root))


def normalize_scope_text(text: str) -> str:
    return "".join(text.lower().split())


def _project_title_alias(title: str) -> str:
    return PROJECT_TITLE_SUFFIX_RE.sub("", title.strip()).strip()
