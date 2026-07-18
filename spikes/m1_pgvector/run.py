import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row

from spikes.m1_embedding.run import MODEL_SPECS, ModelSpec
from spikes.m1_ingestion.chunker import chunk_document
from spikes.m1_ingestion.loader import load_published_documents
from spikes.m1_ingestion.models import Chunk, DocumentMetadata, KnowledgeDocument
from spikes.m1_ingestion.retrieval import EvaluationCase, evaluate, load_enabled_cases
from spikes.m1_pgvector.utils import EMBEDDING_DIMENSION, vector_literal


SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DATABASE_URL = "postgresql:///self_intro_m1_spike?host=/tmp&port=55432"
EMBEDDING_NAME = "multilingual-e5-small"


class PgVectorSpikeError(RuntimeError):
    pass


class InMemoryDenseIndex:
    def __init__(self, chunks: Sequence[Chunk], embeddings, model, spec: ModelSpec):
        self.chunks = list(chunks)
        self.embeddings = embeddings
        self.model = model
        self.spec = spec

    def search(self, query: str, limit: int = 10) -> List[Tuple[Chunk, float]]:
        query_embedding = encode_query(self.model, self.spec, query)
        scores = self.embeddings @ query_embedding
        ranked_indices = scores.argsort()[::-1][:limit]
        return [(self.chunks[index], float(scores[index])) for index in ranked_indices]


class PgVectorIndex:
    def __init__(
        self,
        conn: psycopg.Connection,
        chunks: Sequence[Chunk],
        model,
        spec: ModelSpec,
    ):
        self.conn = conn
        self.chunk_by_id: Dict[str, Chunk] = {chunk.chunk_id: chunk for chunk in chunks}
        self.model = model
        self.spec = spec
        self.query_latencies_ms: List[float] = []

    def search(self, query: str, limit: int = 10) -> List[Tuple[Chunk, float]]:
        started = time.perf_counter()
        query_embedding = encode_query(self.model, self.spec, query)
        self.query_latencies_ms.append((time.perf_counter() - started) * 1000)
        rows = search_chunk_rows(
            self.conn,
            query_embedding,
            self.spec,
            limit=limit,
            public_only=True,
        )
        return [(self.chunk_by_id[row["chunk_id"]], float(row["score"])) for row in rows]


def encode_query(model, spec: ModelSpec, query: str):
    return model.encode(
        [spec.query_prefix + query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]


def load_model(spec: ModelSpec):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is missing; install spikes/m1_pgvector/requirements.txt"
        ) from exc
    return SentenceTransformer(spec.model_id, revision=spec.revision, device="cpu")


def prepare_corpus(knowledge_path: Path, max_chars: int, model, spec: ModelSpec):
    documents = load_published_documents(knowledge_path)
    chunks = [chunk for document in documents for chunk in chunk_document(document, max_chars)]
    passages = [spec.passage_prefix + chunk.search_text for chunk in chunks]
    started = time.perf_counter()
    embeddings = model.encode(
        passages,
        batch_size=16,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    corpus_encode_seconds = time.perf_counter() - started
    dimension = int(embeddings.shape[1])
    if dimension != EMBEDDING_DIMENSION:
        raise PgVectorSpikeError(f"expected {EMBEDDING_DIMENSION} dimensions, got {dimension}")
    return documents, chunks, embeddings, corpus_encode_seconds


def reset_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("drop table if exists m1_chunk_embeddings")
        cur.execute("drop table if exists m1_chunks")
        cur.execute("drop table if exists m1_documents")
    conn.commit()


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def import_corpus(
    conn: psycopg.Connection,
    documents: Sequence[KnowledgeDocument],
    chunks: Sequence[Chunk],
    embeddings,
    spec: ModelSpec,
) -> None:
    document_by_id = {document.metadata.document_id: document for document in documents}
    with conn.cursor() as cur:
        for document in documents:
            metadata = document.metadata
            cur.execute(
                """
                insert into m1_documents (
                    document_id, source_path, title, category, project_id,
                    visibility, status, updated_at, content_hash
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                """,
                (
                    metadata.document_id,
                    str(document.path),
                    metadata.title,
                    metadata.category,
                    metadata.project_id,
                    metadata.visibility,
                    metadata.status,
                    metadata.updated_at,
                    document.content_hash,
                ),
            )

        for chunk, embedding in zip(chunks, embeddings):
            document = document_by_id[chunk.document_id]
            cur.execute(
                """
                insert into m1_chunks (
                    chunk_id, document_id, project_id, document_title, heading_path,
                    ordinal, content, search_text, content_hash,
                    previous_chunk_id, next_chunk_id
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                """,
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.project_id,
                    chunk.document_title,
                    list(chunk.heading_path),
                    chunk.ordinal,
                    chunk.content,
                    chunk.search_text,
                    chunk.content_hash,
                    chunk.previous_chunk_id,
                    chunk.next_chunk_id,
                ),
            )
            cur.execute(
                """
                insert into m1_chunk_embeddings (
                    chunk_id, embedding_model, embedding_revision,
                    embedding_dimension, embedding
                )
                values (%s, %s, %s, %s, %s::vector)
                on conflict (chunk_id, embedding_model, embedding_revision) do update set
                    embedding_dimension = excluded.embedding_dimension,
                    embedding = excluded.embedding,
                    refreshed_at = now()
                """,
                (
                    chunk.chunk_id,
                    spec.name,
                    spec.revision,
                    EMBEDDING_DIMENSION,
                    vector_literal(embedding),
                ),
            )
    conn.commit()


def insert_probe_document(
    conn: psycopg.Connection,
    metadata: DocumentMetadata,
    chunk_id: str,
    content: str,
    embedding,
    spec: ModelSpec,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into m1_documents (
                document_id, source_path, title, category, project_id,
                visibility, status, updated_at, content_hash
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (document_id) do update set
                visibility = excluded.visibility,
                status = excluded.status,
                refreshed_at = now()
            """,
            (
                metadata.document_id,
                "probe/private.md",
                metadata.title,
                metadata.category,
                metadata.project_id,
                metadata.visibility,
                metadata.status,
                metadata.updated_at,
                "probe-document-hash",
            ),
        )
        cur.execute(
            """
            insert into m1_chunks (
                chunk_id, document_id, project_id, document_title, heading_path,
                ordinal, content, search_text, content_hash
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (chunk_id) do update set
                content = excluded.content,
                search_text = excluded.search_text,
                refreshed_at = now()
            """,
            (
                chunk_id,
                metadata.document_id,
                metadata.project_id,
                metadata.title,
                [],
                1,
                content,
                f"{metadata.title} {content}",
                "probe-chunk-hash",
            ),
        )
        cur.execute(
            """
            insert into m1_chunk_embeddings (
                chunk_id, embedding_model, embedding_revision,
                embedding_dimension, embedding
            )
            values (%s, %s, %s, %s, %s::vector)
            on conflict (chunk_id, embedding_model, embedding_revision) do update set
                embedding = excluded.embedding,
                refreshed_at = now()
            """,
            (chunk_id, spec.name, spec.revision, EMBEDDING_DIMENSION, vector_literal(embedding)),
        )
    conn.commit()


def insert_alternate_embedding(
    conn: psycopg.Connection,
    chunk_id: str,
    revision: str,
    embedding,
    spec: ModelSpec,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into m1_chunk_embeddings (
                chunk_id, embedding_model, embedding_revision,
                embedding_dimension, embedding
            )
            values (%s, %s, %s, %s, %s::vector)
            on conflict (chunk_id, embedding_model, embedding_revision) do update set
                embedding = excluded.embedding,
                refreshed_at = now()
            """,
            (chunk_id, spec.name, revision, EMBEDDING_DIMENSION, vector_literal(embedding)),
        )
    conn.commit()


def count_rows(conn: psycopg.Connection, table_name: str) -> int:
    if table_name not in {"m1_documents", "m1_chunks", "m1_chunk_embeddings"}:
        raise ValueError(f"unsupported table name: {table_name}")
    with conn.cursor() as cur:
        cur.execute(f"select count(*) from {table_name}")
        return int(cur.fetchone()[0])


def count_embeddings(conn: psycopg.Connection, spec: ModelSpec, revision: str = "") -> int:
    embedding_revision = revision or spec.revision
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*)
            from m1_chunk_embeddings
            where embedding_model = %s
              and embedding_revision = %s
            """,
            (spec.name, embedding_revision),
        )
        return int(cur.fetchone()[0])


def search_chunk_rows(
    conn: psycopg.Connection,
    query_embedding,
    spec: ModelSpec,
    limit: int,
    public_only: bool,
    revision: str = "",
) -> List[dict]:
    visibility_sql = "and d.visibility = 'public' and d.status = 'published'" if public_only else ""
    embedding_revision = revision or spec.revision
    sql = f"""
        select
            c.chunk_id,
            c.document_id,
            1 - (e.embedding <=> %s::vector) as score
        from m1_chunk_embeddings e
        join m1_chunks c on c.chunk_id = e.chunk_id
        join m1_documents d on d.document_id = c.document_id
        where e.embedding_model = %s
          and e.embedding_revision = %s
          and e.embedding_dimension = %s
          {visibility_sql}
        order by e.embedding <=> %s::vector, c.chunk_id
        limit %s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        vector = vector_literal(query_embedding)
        cur.execute(sql, (vector, spec.name, embedding_revision, EMBEDDING_DIMENSION, vector, limit))
        return list(cur.fetchall())


def ranked_chunk_ids(rows_or_pairs: Sequence) -> List[str]:
    result: List[str] = []
    for item in rows_or_pairs:
        if isinstance(item, tuple):
            result.append(item[0].chunk_id)
        else:
            result.append(item["chunk_id"])
    return result


def verify_pg_matches_memory(
    conn: psycopg.Connection,
    cases: Sequence[EvaluationCase],
    memory_index: InMemoryDenseIndex,
    model,
    spec: ModelSpec,
) -> List[dict]:
    mismatches = []
    for case in cases:
        memory_ids = ranked_chunk_ids(memory_index.search(case.question, limit=5))
        query_embedding = encode_query(model, spec, case.question)
        pg_ids = ranked_chunk_ids(
            search_chunk_rows(conn, query_embedding, spec, limit=5, public_only=True)
        )
        if memory_ids != pg_ids:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "memory_top5": memory_ids,
                    "pgvector_top5": pg_ids,
                }
            )
    return mismatches


def run_private_filter_check(conn: psycopg.Connection, model, spec: ModelSpec) -> dict:
    query = "private visibility probe unique phrase"
    query_embedding = encode_query(model, spec, query)
    chunk_id = "m1-private-probe--root--001"
    metadata = DocumentMetadata(
        document_id="m1-private-probe",
        title="Private Probe",
        category="probe",
        project_id=None,
        visibility="private",
        status="published",
        updated_at="2026-07-17",
    )
    insert_probe_document(
        conn,
        metadata,
        chunk_id,
        "private visibility probe unique phrase",
        query_embedding,
        spec,
    )
    unsafe_ids = ranked_chunk_ids(
        search_chunk_rows(conn, query_embedding, spec, limit=3, public_only=False)
    )
    safe_ids = ranked_chunk_ids(
        search_chunk_rows(conn, query_embedding, spec, limit=10, public_only=True)
    )
    return {
        "unsafe_top_is_private": bool(unsafe_ids and unsafe_ids[0] == chunk_id),
        "safe_excludes_private": chunk_id not in safe_ids,
        "unsafe_top3": unsafe_ids,
        "safe_top10": safe_ids,
    }


def run_embedding_version_check(
    conn: psycopg.Connection,
    chunks: Sequence[Chunk],
    model,
    spec: ModelSpec,
) -> dict:
    query = "embedding revision isolation probe"
    query_embedding = encode_query(model, spec, query)
    alternate_revision = spec.revision + "-probe"
    probe_chunk_id = chunks[0].chunk_id
    insert_alternate_embedding(conn, probe_chunk_id, alternate_revision, query_embedding, spec)
    alternate_ids = ranked_chunk_ids(
        search_chunk_rows(
            conn,
            query_embedding,
            spec,
            limit=3,
            public_only=True,
            revision=alternate_revision,
        )
    )
    real_count = count_embeddings(conn, spec)
    alternate_count = count_embeddings(conn, spec, revision=alternate_revision)
    return {
        "real_revision_embedding_count": real_count,
        "alternate_revision_embedding_count": alternate_count,
        "alternate_revision_top_is_probe_chunk": bool(
            alternate_ids and alternate_ids[0] == probe_chunk_id
        ),
        "alternate_revision": alternate_revision,
        "alternate_top3": alternate_ids,
    }


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def summarize_latencies(latencies: Sequence[float]) -> dict:
    return {
        "mean": round(statistics.mean(latencies), 4) if latencies else 0.0,
        "p50": round(statistics.median(latencies), 4) if latencies else 0.0,
        "p95": round(percentile(latencies, 0.95), 4) if latencies else 0.0,
        "sample_count": len(latencies),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M1 PostgreSQL + pgvector spike")
    parser.add_argument("--database-url", default=os.environ.get("PGVECTOR_DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--knowledge", type=Path, default=Path("knowledge"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/mvp-v1.jsonl"))
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--reset", action="store_true", help="drop M1 spike tables before import")
    args = parser.parse_args()

    spec = MODEL_SPECS[EMBEDDING_NAME]
    load_started = time.perf_counter()
    model = load_model(spec)
    load_seconds = time.perf_counter() - load_started
    documents, chunks, embeddings, corpus_encode_seconds = prepare_corpus(
        args.knowledge,
        args.max_chars,
        model,
        spec,
    )
    cases = load_enabled_cases(args.dataset)

    with psycopg.connect(args.database_url) as conn:
        if args.reset:
            reset_schema(conn)
        ensure_schema(conn)
        import_corpus(conn, documents, chunks, embeddings, spec)
        import_corpus(conn, documents, chunks, embeddings, spec)
        idempotency = {
            "document_count": count_rows(conn, "m1_documents"),
            "chunk_count": count_rows(conn, "m1_chunks"),
            "real_revision_embedding_count": count_embeddings(conn, spec),
        }
        memory_index = InMemoryDenseIndex(chunks, embeddings, model, spec)
        pg_index = PgVectorIndex(conn, chunks, model, spec)
        # Warm up once so the 16 measured queries do not include first-call setup.
        pg_index.search("预热查询", limit=1)
        pg_index.query_latencies_ms.clear()
        evaluation = evaluate(pg_index, cases)
        mismatches = verify_pg_matches_memory(conn, cases, memory_index, model, spec)
        embedding_version = run_embedding_version_check(conn, chunks, model, spec)
        private_filter = run_private_filter_check(conn, model, spec)

    validations = {
        "idempotent_import": idempotency == {
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "real_revision_embedding_count": len(chunks),
        },
        "pgvector_matches_in_memory_top5": not mismatches,
        "private_document_filter": private_filter["unsafe_top_is_private"]
        and private_filter["safe_excludes_private"],
        "embedding_version_isolation": embedding_version["real_revision_embedding_count"] == len(chunks)
        and embedding_version["alternate_revision_embedding_count"] == 1
        and embedding_version["alternate_revision_top_is_probe_chunk"],
    }
    output = {
        "environment": {
            "database_url": args.database_url,
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "case_count": len(cases),
            "max_chars": args.max_chars,
        },
        "embedding": {
            "configuration": spec.name,
            "model_id": spec.model_id,
            "model_revision": spec.revision,
            "dimension": EMBEDDING_DIMENSION,
            "distance": "cosine via pgvector <=> on L2-normalized embeddings",
            "load_seconds": round(load_seconds, 4),
            "corpus_encode_seconds": round(corpus_encode_seconds, 4),
            "query_latency_ms": summarize_latencies(pg_index.query_latencies_ms),
        },
        "evaluation": {
            "case_count": evaluation["case_count"],
            "summary": evaluation["summary"],
        },
        "validations": validations,
        "details": {
            "idempotency": idempotency,
            "ranking_mismatches": mismatches[:3],
            "private_filter": private_filter,
            "embedding_version": embedding_version,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
