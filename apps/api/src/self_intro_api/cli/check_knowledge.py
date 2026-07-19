import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from self_intro_api.knowledge.chunker import chunk_document
from self_intro_api.knowledge.frontmatter import (
    FrontMatterError,
    content_hash,
    parse_front_matter,
)
from self_intro_api.knowledge.models import KnowledgeDocument
from self_intro_api.knowledge.scope import build_knowledge_scope


@dataclass(frozen=True)
class KnowledgeCheckIssue:
    level: str
    path: str
    message: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether the local knowledge base can be ingested safely."
    )
    parser.add_argument("--root", default="knowledge", help="Knowledge root directory.")
    args = parser.parse_args()

    payload = check_knowledge(Path(args.root))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    error_count = payload["error_count"]
    if isinstance(error_count, int) and error_count > 0:
        raise SystemExit(1)


def check_knowledge(root: Path) -> dict[str, object]:
    issues: list[KnowledgeCheckIssue] = []
    documents: list[KnowledgeDocument] = []
    seen_ids: dict[str, Path] = {}

    if not root.exists():
        issues.append(KnowledgeCheckIssue("error", str(root), "knowledge root does not exist"))
        return _payload(root, issues, documents)

    for path in _iter_knowledge_markdown(root):
        relative_path = path.relative_to(root)
        try:
            metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
        except FrontMatterError as exc:
            issues.append(KnowledgeCheckIssue("error", str(relative_path), str(exc)))
            continue

        if previous_path := seen_ids.get(metadata.document_id):
            issues.append(
                KnowledgeCheckIssue(
                    "error",
                    str(relative_path),
                    f"duplicate document_id with {previous_path.relative_to(root)}: "
                    f"{metadata.document_id}",
                )
            )
        else:
            seen_ids[metadata.document_id] = path

        if metadata.visibility == "public" and metadata.status == "published":
            if not body.strip():
                issues.append(
                    KnowledgeCheckIssue(
                        "error",
                        str(relative_path),
                        "public published document has empty body",
                    )
                )
            if _is_project_document(path, root) and not metadata.project_id:
                issues.append(
                    KnowledgeCheckIssue(
                        "warning",
                        str(relative_path),
                        "project document should set project_id for dynamic routing",
                    )
                )
            documents.append(KnowledgeDocument(path, metadata, body, content_hash(body)))

    return _payload(root, issues, documents)


def _payload(
    root: Path,
    issues: list[KnowledgeCheckIssue],
    documents: list[KnowledgeDocument],
) -> dict[str, object]:
    scope = build_knowledge_scope(documents)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    error_count = sum(1 for issue in issues if issue.level == "error")
    warning_count = sum(1 for issue in issues if issue.level == "warning")
    return {
        "status": "ok" if error_count == 0 else "error",
        "root": str(root),
        "error_count": error_count,
        "warning_count": warning_count,
        "public_published_document_count": len(documents),
        "chunk_count": len(chunks),
        "projects": [
            {
                "project_id": project.project_id,
                "alias_count": len(project.aliases),
                "document_count": len(project.document_ids),
                "document_ids": list(project.document_ids),
            }
            for project in scope.projects
        ],
        "issues": [
            {
                "level": issue.level,
                "path": issue.path,
                "message": issue.message,
            }
            for issue in issues
        ],
    }


def _iter_knowledge_markdown(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.md"))
        if path.name != "README.md" and "_template" not in path.parts
    ]


def _is_project_document(path: Path, root: Path) -> bool:
    return len(path.relative_to(root).parts) >= 3 and path.relative_to(root).parts[0] == "projects"


if __name__ == "__main__":
    main()
