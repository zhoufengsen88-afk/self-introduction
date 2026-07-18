"""create knowledge tables

Revision ID: 0001_create_knowledge_tables
Revises:
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_create_knowledge_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("document_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.CheckConstraint("visibility in ('public', 'private')", name="document_visibility_check"),
        sa.CheckConstraint("status in ('draft', 'published')", name="document_status_check"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("knowledge_documents.document_id")),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
    )
    op.execute(
        """
        create table if not exists chunk_embeddings (
            chunk_id text not null references knowledge_chunks(chunk_id) on delete cascade,
            embedding_model text not null,
            embedding_revision text not null,
            embedding_dimension integer not null check (embedding_dimension = 384),
            embedding vector(384) not null,
            primary key (chunk_id, embedding_model, embedding_revision)
        )
        """
    )
    op.create_index(
        "knowledge_documents_visibility_status_idx",
        "knowledge_documents",
        ["visibility", "status"],
    )


def downgrade() -> None:
    op.drop_index("knowledge_documents_visibility_status_idx", table_name="knowledge_documents")
    op.drop_table("chunk_embeddings")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
