-- One-time setup for the optional Supabase (Postgres + pgvector) backend.
--
-- Run this once in your Supabase project's SQL Editor (Supabase dashboard
-- -> SQL Editor -> New query -> paste this whole file -> Run) before
-- setting DATABASE_URL to your Supabase connection string.
--
-- Not run automatically by the app on startup, on purpose: enabling an
-- extension is the kind of one-time, deliberate step that belongs in your
-- hands, not something the app silently does to your database every time
-- it boots. The app's own init_db() (backend/app/db.py) still creates the
-- plain metadata tables (notebooks/documents/chunks/chat_messages)
-- automatically against either backend -- only this pgvector-specific
-- piece is a manual step.
--
-- Also don't forget: create a Storage bucket named "documents" (Supabase
-- dashboard -> Storage -> New bucket -> name it "documents", or whatever
-- you set SUPABASE_BUCKET to) -- that's a couple of clicks in the UI, not
-- SQL, so it isn't part of this file.

-- 1. Enable the pgvector extension (ships with every Supabase project,
--    just needs turning on).
create extension if not exists vector;

-- 2. The embeddings table -- one row per document chunk. Mirrors what
--    ChromaDB stores per-chunk in the default local backend (see
--    backend/app/vectorstore/chroma_store.py): the chunk text, its
--    embedding, and enough metadata (filename, page, chunk_index) to
--    build a citation without a second query.
--
--    vector(384): 384 is the embedding dimension of the default
--    EMBEDDING_MODEL (all-MiniLM-L6-v2). If you change EMBEDDING_MODEL in
--    .env to a model with a different output size (e.g. bge-small-en is
--    also 384, but bge-base-en is 768), update this column's dimension to
--    match and re-run this file -- embeddings from a different-sized
--    model cannot be stored in a vector(384) column.
create table if not exists embeddings (
    id text primary key,
    notebook_id text not null,
    document_id text not null,
    filename text,
    page integer,
    chunk_index integer,
    text text not null,
    embedding vector(384) not null
);

-- 3. Indexes: one for scoping every query to a single notebook (matches
--    the "questions are scoped to the active notebook only" requirement
--    and the one-Chroma-collection-per-notebook design it mirrors), one
--    approximate-nearest-neighbor index for fast cosine similarity search.
--    ivfflat needs some rows in the table to pick good cluster centers, so
--    it's fine (and normal) for this to be less effective until you've
--    uploaded a handful of documents -- it still works correctly before
--    that, just via a fuller scan.
create index if not exists embeddings_notebook_id_idx on embeddings (notebook_id);

create index if not exists embeddings_vector_idx
    on embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);
