from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    title: str
    category: str
    project_id: str | None
    visibility: str
    status: str
    updated_at: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeDocument:
    path: Path
    metadata: DocumentMetadata
    body: str
    content_hash: str


@dataclass(frozen=True)
class Section:
    heading_path: tuple[str, ...]
    blocks: tuple[str, ...]


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    project_id: str | None
    document_title: str
    heading_path: tuple[str, ...]
    ordinal: int
    content: str
    content_hash: str
    previous_chunk_id: str | None = field(default=None)
    next_chunk_id: str | None = field(default=None)

    @property
    def search_text(self) -> str:
        headings = " ".join(self.heading_path)
        project = self.project_id or ""
        return f"{self.document_title} {project} {headings} {self.content}".strip()


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class Corpus:
    documents: tuple[KnowledgeDocument, ...]
    chunks: tuple[Chunk, ...]
