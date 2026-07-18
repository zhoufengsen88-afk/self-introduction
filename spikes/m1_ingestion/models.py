from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    title: str
    category: str
    project_id: Optional[str]
    visibility: str
    status: str
    updated_at: str


@dataclass(frozen=True)
class KnowledgeDocument:
    path: Path
    metadata: DocumentMetadata
    body: str
    content_hash: str


@dataclass(frozen=True)
class Section:
    heading_path: Tuple[str, ...]
    blocks: Tuple[str, ...]


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    project_id: Optional[str]
    document_title: str
    heading_path: Tuple[str, ...]
    ordinal: int
    content: str
    content_hash: str
    previous_chunk_id: Optional[str] = field(default=None)
    next_chunk_id: Optional[str] = field(default=None)

    @property
    def search_text(self) -> str:
        headings = " ".join(self.heading_path)
        project = self.project_id or ""
        return f"{self.document_title} {project} {headings} {self.content}".strip()
