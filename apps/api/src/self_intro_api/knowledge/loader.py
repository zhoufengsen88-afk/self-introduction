from pathlib import Path

from .chunker import chunk_document
from .frontmatter import content_hash, parse_front_matter
from .models import Corpus, KnowledgeDocument


class KnowledgeLoadError(RuntimeError):
    pass


def load_public_documents(root: Path) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    seen_ids: set[str] = set()
    for path in sorted(root.rglob("*.md")):
        if path.name == "README.md" or "_template" in path.parts:
            continue
        metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if metadata.document_id in seen_ids:
            raise KnowledgeLoadError(f"duplicate document_id: {metadata.document_id}")
        seen_ids.add(metadata.document_id)
        if metadata.visibility != "public" or metadata.status != "published":
            continue
        documents.append(KnowledgeDocument(path, metadata, body, content_hash(body)))
    return documents


def load_public_corpus(root: Path, max_chars: int = 1200) -> Corpus:
    documents = load_public_documents(root)
    chunks = [chunk for document in documents for chunk in chunk_document(document, max_chars)]
    return Corpus(documents=tuple(documents), chunks=tuple(chunks))
