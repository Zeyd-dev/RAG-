"""
ChromaDB wrapper running in local/embedded (PersistentClient) mode:
file-based storage under CHROMA_DIR, no server process, no account,
no cost. One Chroma collection per notebook keeps retrieval scoped
to the active notebook, per the multi-notebook requirement.
"""
from pathlib import Path

import chromadb

from ..config import get_settings
from ..embeddings.local_embedder import embed_query, embed_texts

settings = get_settings()

_client = None


def get_client():
    global _client
    if _client is None:
        Path(settings.CHROMA_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
    return _client


def _collection_name(notebook_id: str) -> str:
    return f"notebook_{notebook_id}"


def get_or_create_collection(notebook_id: str):
    client = get_client()
    # Explicit cosine space so "distance" is a well-defined 0-2 value
    # (1 - cosine_similarity) rather than Chroma's default squared-L2,
    # which ranking-wise gives the same order (since embeddings are
    # normalized) but makes the "relevance score" shown in the UI
    # (score = 1 - distance) meaningless as a number. This setting only
    # applies to collections created from now on -- existing notebooks
    # created before this change keep their original (L2) space.
    return client.get_or_create_collection(
        name=_collection_name(notebook_id),
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(
    notebook_id: str,
    chunk_ids: list[str],
    texts: list[str],
    metadatas: list[dict],
) -> None:
    if not texts:
        return
    collection = get_or_create_collection(notebook_id)
    embeddings = embed_texts(texts)
    collection.add(ids=chunk_ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def query(notebook_id: str, question: str, top_k: int = 5) -> dict:
    collection = get_or_create_collection(notebook_id)
    query_embedding = embed_query(question)
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )


def delete_document_chunks(notebook_id: str, document_id: str) -> None:
    collection = get_or_create_collection(notebook_id)
    collection.delete(where={"document_id": document_id})


def delete_notebook(notebook_id: str) -> None:
    client = get_client()
    try:
        client.delete_collection(_collection_name(notebook_id))
    except Exception:
        pass
