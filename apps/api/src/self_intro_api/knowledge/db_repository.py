import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Engine, bindparam, text

from self_intro_api.embedding.base import EmbeddingProvider
from self_intro_api.embedding.vector import vector_literal
from self_intro_api.knowledge.models import Chunk, Corpus, SearchResult
from self_intro_api.rag.pipeline import RetrievalIntent, rerank_score


@dataclass(frozen=True)
class IngestStats:
    document_count: int
    chunk_count: int
    embedding_count: int
    embedding_model: str
    embedding_revision: str
    embedding_dimension: int


def ingest_corpus(engine: Engine, corpus: Corpus, provider: EmbeddingProvider) -> IngestStats:
    passages = [chunk.search_text for chunk in corpus.chunks]
    embeddings = provider.embed_passages(passages)
    if len(embeddings) != len(corpus.chunks):
        raise ValueError("embedding count does not match chunk count")

    spec = provider.spec
    with engine.begin() as connection:
        for document in corpus.documents:
            metadata = document.metadata
            connection.execute(
                text(
                    """
                    insert into knowledge_documents (
                        document_id, source_path, title, category, project_id,
                        visibility, status, updated_at, content_hash, refreshed_at
                    )
                    values (
                        :document_id, :source_path, :title, :category, :project_id,
                        :visibility, :status, :updated_at, :content_hash, now()
                    )
                    on conflict (document_id) do update set
                        source_path = excluded.source_path,
                        title = excluded.title,
                        category = excluded.category,
                        project_id = excluded.project_id,
                        visibility = excluded.visibility,
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        content_hash = excluded.content_hash,
                        refreshed_at = now()
                    """
                ),
                {
                    "document_id": metadata.document_id,
                    "source_path": str(document.path),
                    "title": metadata.title,
                    "category": metadata.category,
                    "project_id": metadata.project_id,
                    "visibility": metadata.visibility,
                    "status": metadata.status,
                    "updated_at": date.fromisoformat(metadata.updated_at),
                    "content_hash": document.content_hash,
                },
            )

        for chunk, embedding in zip(corpus.chunks, embeddings, strict=True):
            connection.execute(
                text(
                    """
                    insert into knowledge_chunks (
                        chunk_id, document_id, project_id, document_title, heading_path,
                        ordinal, content, search_text, content_hash,
                        previous_chunk_id, next_chunk_id, refreshed_at
                    )
                    values (
                        :chunk_id, :document_id, :project_id, :document_title, :heading_path,
                        :ordinal, :content, :search_text, :content_hash,
                        :previous_chunk_id, :next_chunk_id, now()
                    )
                    on conflict (chunk_id) do update set
                        document_id = excluded.document_id,
                        project_id = excluded.project_id,
                        document_title = excluded.document_title,
                        heading_path = excluded.heading_path,
                        ordinal = excluded.ordinal,
                        content = excluded.content,
                        search_text = excluded.search_text,
                        content_hash = excluded.content_hash,
                        previous_chunk_id = excluded.previous_chunk_id,
                        next_chunk_id = excluded.next_chunk_id,
                        refreshed_at = now()
                    """
                ),
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "project_id": chunk.project_id,
                    "document_title": chunk.document_title,
                    "heading_path": serialize_heading_path(chunk.heading_path),
                    "ordinal": chunk.ordinal,
                    "content": chunk.content,
                    "search_text": chunk.search_text,
                    "content_hash": chunk.content_hash,
                    "previous_chunk_id": chunk.previous_chunk_id,
                    "next_chunk_id": chunk.next_chunk_id,
                },
            )
            connection.execute(
                text(
                    """
                    insert into chunk_embeddings (
                        chunk_id, embedding_model, embedding_revision,
                        embedding_dimension, embedding, refreshed_at
                    )
                    values (
                        :chunk_id, :embedding_model, :embedding_revision,
                        :embedding_dimension, cast(:embedding as vector), now()
                    )
                    on conflict (chunk_id, embedding_model, embedding_revision) do update set
                        embedding_dimension = excluded.embedding_dimension,
                        embedding = excluded.embedding,
                        refreshed_at = now()
                    """
                ),
                {
                    "chunk_id": chunk.chunk_id,
                    "embedding_model": spec.name,
                    "embedding_revision": spec.revision,
                    "embedding_dimension": spec.dimension,
                    "embedding": vector_literal(embedding, spec.dimension),
                },
            )

    return IngestStats(
        document_count=len(corpus.documents),
        chunk_count=len(corpus.chunks),
        embedding_count=len(embeddings),
        embedding_model=spec.name,
        embedding_revision=spec.revision,
        embedding_dimension=spec.dimension,
    )


class PgVectorSearchBackend:
    def __init__(self, engine: Engine, provider: EmbeddingProvider):
        self.engine = engine
        self.provider = provider

    def search(self, query: str, intent: RetrievalIntent, top_k: int) -> list[SearchResult]:
        spec = self.provider.spec
        query_embedding = vector_literal(self.provider.embed_query(query), spec.dimension)
        candidate_limit = max(top_k * 4, top_k, 20)
        document_scope_clause = ""
        if intent.allowed_document_ids:
            document_scope_clause = "and c.document_id in :allowed_document_ids"
        statement = text(
            f"""
            select
                c.chunk_id,
                c.document_id,
                c.project_id,
                coalesce(c.document_title, d.title) as document_title,
                c.heading_path,
                c.ordinal,
                c.content,
                c.content_hash,
                c.previous_chunk_id,
                c.next_chunk_id,
                1 - (e.embedding <=> cast(:embedding as vector)) as score
            from chunk_embeddings e
            join knowledge_chunks c on c.chunk_id = e.chunk_id
            join knowledge_documents d on d.document_id = c.document_id
            where
                e.embedding_model = :embedding_model
                and e.embedding_revision = :embedding_revision
                and e.embedding_dimension = :embedding_dimension
                and d.visibility = 'public'
                and d.status = 'published'
                {document_scope_clause}
            order by e.embedding <=> cast(:embedding as vector), c.chunk_id
            limit :candidate_limit
            """
        )
        if intent.allowed_document_ids:
            statement = statement.bindparams(bindparam("allowed_document_ids", expanding=True))
        parameters: dict[str, object] = {
            "embedding": query_embedding,
            "embedding_model": spec.name,
            "embedding_revision": spec.revision,
            "embedding_dimension": spec.dimension,
            "candidate_limit": candidate_limit,
        }
        if intent.allowed_document_ids:
            parameters["allowed_document_ids"] = intent.allowed_document_ids
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement,
                parameters,
            ).mappings()
            results = [_row_to_search_result(row) for row in rows]

        reranked = [
            SearchResult(chunk=result.chunk, score=rerank_score(result, intent))
            for result in results
        ]
        reranked = [result for result in reranked if result.score > 0]
        reranked.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return reranked[:top_k]


def serialize_heading_path(heading_path: tuple[str, ...]) -> str:
    return json.dumps(list(heading_path), ensure_ascii=False, separators=(",", ":"))


def deserialize_heading_path(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return tuple(part.strip() for part in value.split(">") if part.strip())
    if not isinstance(decoded, list):
        return ()
    return tuple(str(item) for item in decoded)


def _row_to_search_result(row: Any) -> SearchResult:
    chunk = Chunk(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        project_id=_optional_str(row["project_id"]),
        document_title=str(row["document_title"]),
        heading_path=deserialize_heading_path(_optional_str(row["heading_path"])),
        ordinal=int(row["ordinal"]),
        content=str(row["content"]),
        content_hash=str(row["content_hash"]),
        previous_chunk_id=_optional_str(row["previous_chunk_id"]),
        next_chunk_id=_optional_str(row["next_chunk_id"]),
    )
    return SearchResult(chunk=chunk, score=float(row["score"]))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
