# Architecture

## Overview

RAG NoteBook is a small internal Retrieval-Augmented Generation app, modeled
after Google's NotebookLM. It lets a team upload documents into "notebooks",
asks questions scoped to a notebook, and get answers with inline citations
that link back to the exact source passage.

```
 Upload ──► Extract text ──► Chunk (token-aware, overlap) ──► Embed (local)
                                                                   │
                                                                   ▼
                                                          ChromaDB (per-notebook
                                                           collection, on disk)
                                                                   │
 Question ──► Embed query ──► Similarity search ─────────────────┘
                                       │
                                       ▼
                         Top-k chunks + question ──► LLM (Groq) ──► Answer + citations
```

## Modularity / swap points

Every "free tier now, swap later" requirement maps to one isolated module:

| Concern            | Module                                  | Swap by                                   |
|---------------------|------------------------------------------|--------------------------------------------|
| Embeddings          | `backend/app/embeddings/local_embedder.py` | Changing `EMBEDDING_MODEL` in `.env`      |
| Vector store        | `backend/app/vectorstore/chroma_store.py`  | Replacing with another store's client      |
| LLM provider        | `backend/app/llm/*`                        | Add a class implementing `LLMProvider`, register in `factory.py`, set `LLM_PROVIDER` |
| File storage        | `backend/app/storage/local_files.py`       | Replace functions with cloud SDK calls     |
| Metadata DB         | `backend/app/db.py` (sqlite3)              | Point `DATABASE_URL` at another engine + adjust queries |

## Data model

- **notebooks** — id, name, description, created_at
- **documents** — id, notebook_id, filename, file_type, page_count, status (processing/ready/failed), storage_path
- **chunks** — id, document_id, notebook_id, chunk_index, page, text (raw text kept here so citations can show/highlight the exact passage without re-parsing the source file)
- **chat_messages** — id, notebook_id, role, content, citations_json, created_at

Vector embeddings themselves live in ChromaDB (one collection per notebook,
named `notebook_<id>`), not in sqlite — sqlite only holds metadata + raw text.

## Citations

Each retrieved chunk becomes a labeled source block (`[S1]`, `[S2]`, ...) in
the prompt sent to the LLM. The system prompt instructs the model to cite
inline using those labels. The frontend parses `[S1]`-style tokens out of the
answer text and renders them as clickable chips; clicking one opens the
Source Viewer, which fetches the exact chunk text by id and highlights it.

## Auth

Single shared username/password pair from environment variables, backed by a
signed, httpOnly session cookie (`itsdangerous`). No user table, no OAuth —
appropriate for an internal tool with no public signup.

## Known limitations (MVP)

- Source Viewer shows the exact matched passage (with page number), not a
  rendered original-layout PDF/DOCX view. Opening the original file is one
  click away.
- Docker Compose's frontend serves a static build; if deployed behind a
  different origin, add a reverse proxy (e.g. nginx) to route `/api` to the
  backend container, or set an explicit `VITE_API_BASE` and rebuild.
- Chat history is stored per-notebook but the UI currently starts a fresh
  thread per page load (history endpoint exists at `GET /chat/history` for
  future use).
