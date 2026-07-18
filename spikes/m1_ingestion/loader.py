import hashlib
from pathlib import Path
from typing import List

from .frontmatter import FrontMatterError, parse_front_matter
from .models import KnowledgeDocument


class KnowledgeLoadError(ValueError):
    pass


def load_documents(knowledge_root: Path) -> List[KnowledgeDocument]:
    documents: List[KnowledgeDocument] = []
    document_ids = {}

    for path in sorted(knowledge_root.rglob("*.md")):
        if path.name == "README.md" or "_template" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            metadata, body = parse_front_matter(text)
        except (OSError, UnicodeError, FrontMatterError) as exc:
            raise KnowledgeLoadError(f"failed to load {path}: {exc}") from exc
        if metadata.document_id in document_ids:
            previous = document_ids[metadata.document_id]
            raise KnowledgeLoadError(f"duplicate document_id {metadata.document_id}: {previous} and {path}")
        document_ids[metadata.document_id] = path
        documents.append(
            KnowledgeDocument(
                path=path,
                metadata=metadata,
                body=body,
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
        )
    return documents


def load_published_documents(knowledge_root: Path) -> List[KnowledgeDocument]:
    return [
        document
        for document in load_documents(knowledge_root)
        if document.metadata.visibility == "public" and document.metadata.status == "published"
    ]
