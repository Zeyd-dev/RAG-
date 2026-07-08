"""
Picks the active vector store backend based on DATABASE_URL's scheme --
Postgres+pgvector (pgvector_store.py) when it's a "postgresql://" URL,
the default embedded ChromaDB (chroma_store.py) otherwise. documents.py,
notebooks.py, and chat.py import from here instead of a specific backend
module directly, so the backend can be swapped by changing one env var
(DATABASE_URL) -- no other code changes.
"""
from ..config import get_settings

settings = get_settings()

if settings.DATABASE_URL.startswith("postgres"):
    from .pgvector_store import add_chunks, delete_document_chunks, delete_notebook, query
else:
    from .chroma_store import add_chunks, delete_document_chunks, delete_notebook, query

__all__ = ["add_chunks", "delete_document_chunks", "delete_notebook", "query"]
