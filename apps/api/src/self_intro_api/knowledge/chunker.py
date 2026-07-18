import hashlib
import re
import unicodedata
from collections.abc import Iterable

from .markdown import split_sections
from .models import Chunk, KnowledgeDocument

FENCED_BLOCK_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    slug = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", normalized).strip("-")
    return slug[:80] or "root"


def _split_long_block(block: str, max_chars: int) -> Iterable[str]:
    if len(block) <= max_chars or FENCED_BLOCK_RE.match(block):
        yield block
        return

    lines = block.split("\n")
    buffer = ""
    for line in lines:
        units = [line[index : index + max_chars] for index in range(0, len(line), max_chars)] or [
            ""
        ]
        for unit in units:
            candidate = f"{buffer}\n{unit}".strip() if buffer else unit
            if buffer and len(candidate) > max_chars:
                yield buffer
                buffer = unit
            else:
                buffer = candidate
    if buffer:
        yield buffer


def chunk_document(document: KnowledgeDocument, max_chars: int = 1200) -> list[Chunk]:
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")

    chunks: list[Chunk] = []
    for section in split_sections(document.body):
        groups: list[str] = []
        current = ""
        for original_block in section.blocks:
            for block in _split_long_block(original_block, max_chars):
                candidate = f"{current}\n\n{block}" if current else block
                if current and len(candidate) > max_chars:
                    groups.append(current)
                    current = block
                else:
                    current = candidate
        if current:
            groups.append(current)

        section_key = _slug("-".join(section.heading_path))
        for ordinal, content in enumerate(groups, start=1):
            chunk_id = f"{document.metadata.document_id}--{section_key}--{ordinal:03d}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=document.metadata.document_id,
                    project_id=document.metadata.project_id,
                    document_title=document.metadata.title,
                    heading_path=section.heading_path,
                    ordinal=ordinal,
                    content=content,
                    content_hash=_hash(content),
                )
            )

    for index, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[index - 1].chunk_id if index else None
        chunk.next_chunk_id = chunks[index + 1].chunk_id if index + 1 < len(chunks) else None
    return chunks
