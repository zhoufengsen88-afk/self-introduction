create extension if not exists vector;

create table if not exists m1_documents (
    document_id text primary key,
    source_path text not null,
    title text not null,
    category text not null,
    project_id text,
    visibility text not null check (visibility in ('public', 'private')),
    status text not null check (status in ('draft', 'published')),
    updated_at date not null,
    content_hash text not null,
    imported_at timestamptz not null default now(),
    refreshed_at timestamptz not null default now()
);

create table if not exists m1_chunks (
    chunk_id text primary key,
    document_id text not null references m1_documents(document_id) on delete cascade,
    project_id text,
    document_title text not null,
    heading_path text[] not null,
    ordinal integer not null,
    content text not null,
    search_text text not null,
    content_hash text not null,
    previous_chunk_id text,
    next_chunk_id text,
    imported_at timestamptz not null default now(),
    refreshed_at timestamptz not null default now()
);

create table if not exists m1_chunk_embeddings (
    chunk_id text not null references m1_chunks(chunk_id) on delete cascade,
    embedding_model text not null,
    embedding_revision text not null,
    embedding_dimension integer not null check (embedding_dimension = 384),
    embedding vector(384) not null,
    imported_at timestamptz not null default now(),
    refreshed_at timestamptz not null default now(),
    primary key (chunk_id, embedding_model, embedding_revision)
);

create index if not exists m1_documents_visibility_status_idx
    on m1_documents (visibility, status);

create index if not exists m1_chunks_document_id_idx
    on m1_chunks (document_id);

create index if not exists m1_chunk_embeddings_model_revision_idx
    on m1_chunk_embeddings (embedding_model, embedding_revision);
