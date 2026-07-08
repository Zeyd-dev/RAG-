"""
Token-aware chunking with overlap. Uses tiktoken purely as a token
counter/splitter (not tied to any specific LLM) so chunk sizes are
consistent regardless of which embedding model or LLM is configured.
"""
from dataclasses import dataclass

import tiktoken

from .extractors import PageText

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    page: int
    chunk_index: int


def chunk_pages(
    pages: list[PageText],
    chunk_size_tokens: int = 800,
    overlap_tokens: int = 150,
) -> list[Chunk]:
    """
    Splits each page's text into overlapping token windows. Chunks never
    span page boundaries, so every chunk maps cleanly to one page number
    for citation purposes.
    """
    chunks: list[Chunk] = []
    idx = 0
    step = max(chunk_size_tokens - overlap_tokens, 1)

    for page in pages:
        tokens = _ENCODING.encode(page.text)
        if not tokens:
            continue
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size_tokens, len(tokens))
            piece_tokens = tokens[start:end]
            text = _ENCODING.decode(piece_tokens).strip()
            if text:
                chunks.append(Chunk(text=text, page=page.page, chunk_index=idx))
                idx += 1
            if end == len(tokens):
                break
            start += step

    return chunks
