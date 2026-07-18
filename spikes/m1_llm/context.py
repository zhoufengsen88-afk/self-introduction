from pathlib import Path
from typing import Dict, List, Sequence

from spikes.m1_ingestion.chunker import chunk_document
from spikes.m1_ingestion.loader import load_published_documents
from spikes.m1_ingestion.models import Chunk

from .contracts import Evidence, LlmEvaluationCase


def load_public_chunks(knowledge_path: Path, max_chars: int = 1200) -> List[Chunk]:
    documents = load_published_documents(knowledge_path)
    return [chunk for document in documents for chunk in chunk_document(document, max_chars)]


def chunk_lookup(chunks: Sequence[Chunk]) -> Dict[str, Chunk]:
    return {chunk.chunk_id: chunk for chunk in chunks}


def build_oracle_context(
    case: LlmEvaluationCase,
    chunks_by_id: Dict[str, Chunk],
    max_chunks: int = 8,
) -> List[Evidence]:
    context: List[Evidence] = []
    for chunk_id in case.expected_chunk_ids[:max_chunks]:
        chunk = chunks_by_id.get(chunk_id)
        if not chunk:
            continue
        context.append(
            Evidence(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                heading_path=chunk.heading_path,
                content=chunk.content,
            )
        )
    return context
