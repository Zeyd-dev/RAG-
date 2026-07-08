"""
Local embedding generation via sentence-transformers. Runs entirely
on-device — no external API calls, no cost, documents never leave
the machine. Swap EMBEDDING_MODEL in config to try a different model
(e.g. BAAI/bge-small-en) without touching any other code.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from ..config import get_settings

settings = get_settings()


@lru_cache
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
