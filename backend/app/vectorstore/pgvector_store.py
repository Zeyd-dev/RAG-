"""
Postgres + pgvector vector store -- alternate backend to chroma_store.py,
selected automatically (see vectorstore/factory.py) when DATABASE_URL
points at Postgres. Implements the exact same functions as
chroma_store.py (add_chunks, query, delete_document_chunks,
delete_notebook) with the exact same return shapes, so documents.py and
chat.py never need to know which backend is active.

Requires the one-time schema in docs/supabase_schema.sql to have been
run in the Supabase SQL editor first (creates the pgvector extension and
the `embeddings` table). Uses the `<=>` cosine-distance operator, which
matches chroma_store's explicit "hnsw:space": "cosine" setting -- so
`score = 1 - distance` (used in chat.py to show relevance %) means the
same thing regardless of which backend answered the query.
"""
from ..config import get_settings
from ..embeddings.local_embedder import embed_query, embed_texts

settings = get_settings()


def _conn():
    import psycopg2

    return psycopg2.connect(settings.DATABASE_URL)


def _vec_literal(values) -> str:
    # pgvector accepts a text literal like '[0.1,0.2,...]' for a vector
    # column. Fixed-point formatting avoids repr() ever emitting
    # scientific notation (e.g. "1e-05"), which pgvector's parser is not
    # guaranteed to accept.
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def add_chunks(
    notebook_id: str,
    chunk_ids: list[str],
    texts: list[str],
    metadatas: list[dict],
) -> None:
    if not texts:
        return
    embeddings = embed_texts(texts)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            for cid, text, meta, emb in zip(chunk_ids, texts, metadatas, embeddings):
                cur.execute(
                    """
                    INSERT INTO embeddings
                        (id, notebook_id, document_id, filename, page, chunk_index, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        text = EXCLUDED.text,
                        embedding = EXCLUDED.embedding,
                        filename = EXCLUDED.filename,
                        page = EXCLUDED.page,
                        chunk_index = EXCLUDED.chunk_index
                    """,
                    (
                        cid,
                        notebook_id,
                        meta.get("document_id"),
                        meta.get("filename"),
                        meta.get("page"),
                        meta.get("chunk_index"),
                        text,
                        _vec_literal(emb),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def query(notebook_id: str, question: str, top_k: int = 5) -> dict:
    from psycopg2.extras import RealDictCursor

    query_embedding = _vec_literal(embed_query(question))
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, document_id, filename, page, chunk_index, text,
                       embedding <=> %s AS distance
                FROM embeddings
                WHERE notebook_id = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (query_embedding, notebook_id, query_embedding, top_k),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    # Same nested-list-of-one-query shape chroma_store.query returns
    # (Chroma's API supports batched queries, hence the outer list), so
    # chat.py's `results.get("documents", [[]])[0]` pattern works
    # unchanged regardless of which backend answered the query.
    return {
        "documents": [[r["text"] for r in rows]],
        "metadatas": [
            [
                {
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "page": r["page"],
                    "chunk_index": r["chunk_index"],
                }
                for r in rows
            ]
        ],
        "distances": [[float(r["distance"]) for r in rows]],
        "ids": [[r["id"] for r in rows]],
    }


def delete_document_chunks(notebook_id: str, document_id: str) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM embeddings WHERE notebook_id = %s AND document_id = %s",
                (notebook_id, document_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_notebook(notebook_id: str) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM embeddings WHERE notebook_id = %s", (notebook_id,))
        conn.commit()
    finally:
        conn.close()
