"""add ingestion metadata

Revision ID: 0002_add_ingestion_metadata
Revises: 0001_create_knowledge_tables
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_ingestion_metadata"
down_revision: str | None = "0001_create_knowledge_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("source_path", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.alter_column("knowledge_documents", "imported_at", nullable=False)
    op.alter_column("knowledge_documents", "refreshed_at", nullable=False)

    op.add_column("knowledge_chunks", sa.Column("project_id", sa.String(), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("document_title", sa.String(), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("previous_chunk_id", sa.String(), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("next_chunk_id", sa.String(), nullable=True))
    op.add_column(
        "knowledge_chunks",
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.alter_column("knowledge_chunks", "imported_at", nullable=False)
    op.alter_column("knowledge_chunks", "refreshed_at", nullable=False)

    op.execute(
        """
        alter table chunk_embeddings
            add column if not exists imported_at timestamptz not null default now(),
            add column if not exists refreshed_at timestamptz not null default now()
        """
    )
    op.create_index(
        "knowledge_chunks_document_id_idx",
        "knowledge_chunks",
        ["document_id"],
    )
    op.create_index(
        "chunk_embeddings_model_revision_idx",
        "chunk_embeddings",
        ["embedding_model", "embedding_revision"],
    )


def downgrade() -> None:
    op.drop_index("chunk_embeddings_model_revision_idx", table_name="chunk_embeddings")
    op.drop_index("knowledge_chunks_document_id_idx", table_name="knowledge_chunks")
    op.execute("alter table chunk_embeddings drop column if exists refreshed_at")
    op.execute("alter table chunk_embeddings drop column if exists imported_at")
    op.drop_column("knowledge_chunks", "refreshed_at")
    op.drop_column("knowledge_chunks", "imported_at")
    op.drop_column("knowledge_chunks", "next_chunk_id")
    op.drop_column("knowledge_chunks", "previous_chunk_id")
    op.drop_column("knowledge_chunks", "document_title")
    op.drop_column("knowledge_chunks", "project_id")
    op.drop_column("knowledge_documents", "refreshed_at")
    op.drop_column("knowledge_documents", "imported_at")
    op.drop_column("knowledge_documents", "source_path")
