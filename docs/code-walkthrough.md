# RAG NoteBook — Complete Code Walkthrough

This document explains every file in the project: what it does, why it's
written the way it is, and how it connects to everything else. It's meant
to be read once end-to-end, then used as a reference. `docs/architecture.md`
covers the same system at a higher level (data model, swap points); this
document goes down to the line level.

---

## Part 1 — Two full request traces

Reading files in isolation makes it hard to see how they connect. Before
the file-by-file breakdown, here's exactly what happens, step by step,
for the two core actions in the app.

### Trace A: uploading a document

1. **Frontend** (`UploadPanel.jsx`): user picks a file. `handleFileChange`
   wraps it in a `FormData` object and calls `api.uploadDocument`.
2. **API client** (`api/client.js`): `uploadDocument` POSTs the form data to
   `/api/notebooks/{notebook_id}/documents`. Because the body is
   `FormData`, `client.js` deliberately skips setting a `Content-Type`
   header — the browser sets the correct multipart boundary itself.
3. **Router** (`routers/documents.py`, `upload_document`): validates the
   notebook exists and the file extension is supported, generates a new
   `document_id`, saves the raw file to disk via `storage/local_files.py`,
   inserts a `documents` row with `status='processing'`, and — critically —
   schedules the actual processing as a **background task** rather than
   doing it inline. This is why the endpoint returns almost instantly even
   though embedding a large PDF can take several seconds: the HTTP
   response goes out immediately with `status: "processing"`, and
   `_process_document` keeps running after the response is sent.
4. **`_process_document`** (still in `documents.py`): calls
   `extract_text` (`ingestion/extractors.py`) to get `(page, text)` pairs,
   then `chunk_pages` (`ingestion/chunker.py`) to split those into
   token-windowed chunks with overlap. Each chunk's raw text is inserted
   into the `chunks` SQLite table (this is the permanent, verbatim copy
   used later for citations). Then `add_chunks` (`vectorstore/chroma_store.py`)
   embeds every chunk's text via `embeddings/local_embedder.py` and stores
   the vectors in that notebook's Chroma collection. Finally the
   `documents` row is updated to `status='ready'` (or `'failed'` with an
   error message, if anything threw).
5. **Frontend polling**: `UploadPanel.jsx` polls `GET .../documents` every
   3 seconds and re-renders the status badge, so "processing" flips to
   "ready" without the user refreshing.

### Trace B: asking a question

1. **Frontend** (`ChatPanel.jsx`): `handleSend` calls `api.chat(notebookId, question)`.
2. **Router** (`routers/chat.py`, `chat`): confirms the notebook exists,
   then calls `vector_query` (`chroma_store.py`) with the question text.
3. **Retrieval** (`chroma_store.py`, `query`): embeds the question (one
   vector) via `local_embedder.py`, then asks Chroma for the `top_k`
   nearest chunk vectors **within that notebook's collection only** —
   this is the actual mechanism behind "questions are scoped to their
   notebook": each notebook is a physically separate Chroma collection
   (`notebook_<id>`), so cross-notebook retrieval is structurally
   impossible, not just filtered out after the fact.
4. **Back in `chat.py`**: the retrieved chunks are numbered `[S1]..[S5]`
   and formatted into `context_blocks`, each labeled with filename and
   page. Each also becomes a `Citation` object (document_id, filename,
   page, chunk_id, full text, relevance score).
5. **Generation** (`llm/factory.py` → `llm/groq_provider.py`): the
   configured provider (Groq, by default) gets the question plus all
   `context_blocks` and is instructed (via its system prompt) to answer
   only from those excerpts and cite them inline as `[S1]`, `[S2]`, etc.
   Any failure here (bad API key, model error, network issue) is caught
   and re-raised as an `HTTPException(502, detail=...)` with the real
   error message, rather than a bare 500.
6. **Response**: `chat.py` saves both the question and answer to
   `chat_messages`, then returns `{answer, citations}` to the frontend.
7. **Frontend rendering** (`ChatPanel.jsx`): `renderAnswer` scans the
   answer text for `[S<n>]` tokens and replaces each with a clickable
   `CitationChip` wired to `citations[n-1]`. Separately, `RetrievedSources`
   renders *all* returned citations (not just the ones the model chose to
   cite), so you can inspect retrieval quality independently of what the
   model did with it.
8. **Clicking a citation** (`SourceViewer.jsx`): calls
   `GET /notebooks/{id}/documents/{doc_id}/chunks/{chunk_id}`
   (`documents.py`, `get_chunk`) — a direct SQLite row lookup by the exact
   id that was embedded and sent to the LLM. This is why the highlighted
   passage is provably the same text the model saw: nothing is re-derived
   or fuzzy-matched, it's the same row, fetched by id.

---

## Part 2 — Backend, file by file

All backend code lives under `backend/app/`. FastAPI is the web framework;
nothing here talks to a database server or an external vector-DB service —
SQLite and Chroma are both just files on disk under `backend/data/`.

### `config.py`

A single `Settings` class (pydantic-settings `BaseSettings`) holds every
tunable: auth credentials, file paths, the embedding model name, chunk
size/overlap, top-k, and the Groq API key/model. Every other file that
needs configuration calls `get_settings()` rather than reading `os.environ`
directly — one indirection point, easy to see everything configurable in
one place.

One detail worth understanding because it caused a real bug during
testing: `env_file` is resolved to an **absolute path**
(`Path(__file__).resolve().parent.parent.parent / ".env"`), anchored to
this file's own location, not a relative `".env"` string. A relative path
resolves against whatever directory the process happens to be launched
from — since `.env` lives at the project root but `uvicorn` is normally
launched from `backend/`, a relative path would silently fail to find it
and fall back to hardcoded defaults (`admin`/`changeme`), which is exactly
what happened the first time this was set up. Anchoring to `__file__`
makes it work regardless of the current working directory.

`get_settings()` is wrapped in `@lru_cache`, meaning `.env` is read exactly
once per running process. Editing `.env` while the backend is running does
nothing until the process actually restarts — `--reload` only watches
files inside `backend/`, and `.env` lives one level up, so even the
auto-reloader won't catch an `.env` edit. A full manual restart is required.

### `auth.py`

Deliberately minimal: one hardcoded username/password pair (from
`Settings`), no user table, no OAuth. `create_session_token` signs a
payload (`{"username": ...}`) with `itsdangerous.URLSafeTimedSerializer`,
which produces a tamper-evident (not encrypted, but unforgeable-without-the-
secret) token stored in an `httpOnly` cookie. `get_current_user` is a
FastAPI dependency (`CurrentUser = Depends(get_current_user)`) — every
protected route takes `user: str = CurrentUser` as a parameter, and FastAPI
runs this check before the route body executes, raising 401 automatically
if the cookie is missing or the signature doesn't verify or check out
within `SESSION_MAX_AGE_SECONDS` (7 days).

### `models.py`

Pure Pydantic schemas for request/response bodies — `NotebookCreate`,
`Notebook`, `DocumentMeta`, `ChatRequest`, `Citation`, `ChatResponse`. These
have no persistence logic themselves; they're just the shape of data
crossing the API boundary, and FastAPI uses them to auto-validate incoming
JSON and auto-generate the OpenAPI schema (visible at `/docs` when the
backend is running).

### `db.py`

Metadata storage using plain `sqlite3` from the standard library — no ORM.
Given the scale (single internal tool, one shared login), an ORM would add
indirection without real benefit; raw SQL is more transparent for a small
schema. `init_db()` runs `CREATE TABLE IF NOT EXISTS` for four tables:

- `notebooks` — id, name, description, created_at
- `documents` — id, notebook_id (FK), filename, file_type, page_count,
  status, error, storage_path
- `chunks` — id, document_id (FK), notebook_id, chunk_index, page, text
  (this is the verbatim text used for citations)
- `chat_messages` — id, notebook_id (FK), role, content, citations_json,
  created_at

Note that **embeddings themselves are not in this database** — only
metadata and raw text live here. Vectors live in Chroma. `get_conn()` is a
context manager that opens a connection, sets `row_factory = sqlite3.Row`
(so rows can be accessed like dicts), commits on successful exit, and
always closes the connection.

### `main.py`

The FastAPI app object, CORS middleware (allowing the configured
`FRONTEND_ORIGIN`), the `/api/auth/login` and `/api/auth/logout` endpoints
(which just call `verify_credentials` and set/clear the session cookie),
an `/api/health` check, and `app.include_router(...)` calls that wire in
the three routers under `/api/notebooks`. `init_db()` runs once on
`@app.on_event("startup")`.

Worth noting: in this project's dev-proxy setup (Vite forwards `/api/*` to
the backend server-side — see the frontend section), the browser only ever
talks to the Vite origin, never directly to port 8000. That means the CORS
configuration here is mostly a safety net / documentation of intent, not
something actively exercised in the default local dev flow — it *would*
matter if the frontend were served from a different origin without a
proxy (e.g., a production build served as static files with no reverse
proxy in front of the backend).

### `ingestion/extractors.py`

Converts a file on disk into a list of `PageText(page, text)` objects.
Four format handlers, dispatched by file extension via the `EXTRACTORS`
dict:

- **`extract_pdf`**: uses `pypdf`'s `PdfReader`, one `PageText` per real
  PDF page (PDFs have genuine page boundaries, unlike DOCX).
- **`extract_docx`**: DOCX has no stored page numbers — pagination is
  computed at print/render time, not saved in the file. This function
  approximates pages by detecting **manual** page breaks: either a
  paragraph's `page_break_before` property, or an explicit
  `<w:br w:type="page"/>` element inside a run (what Word inserts for a
  Ctrl+Enter break). Paragraphs are bucketed into "pages" at each detected
  break. A document with zero manual breaks still comes back as a single
  page — this is a hard limitation of the file format, not something more
  regex could fix; genuinely recovering rendered page numbers would
  require actually laying out the document the way Word does.
- **`extract_txt`** / **`extract_markdown`**: no real pagination concept;
  each returns a single `PageText(page=1, ...)`.

The other piece of real logic here is `_fix_letter_spacing`, applied to
every PDF page's extracted text. Some PDFs — especially ones exported from
slide-deck tools — use letter-spacing/tracking on headings or emphasized
text as a design choice. Each letter is positioned individually in the
PDF's content stream, and `pypdf` reads the visual gap between letters as
a literal space, producing garbage like `"P o t e n t i a l C h a l l e n
g e s"` instead of `"Potential Challenges"`. The fix: a regex
(`_LETTER_SPACED_RUN`) detects runs of single letters each separated by
one space, collapses the spaces, then re-inserts a space at each
lowercase→uppercase boundary in the collapsed blob — which correctly
recovers word breaks for Title Case headings (the common case), since a
new word starting with a capital letter is a reliable signal. It **can't**
recover word breaks in an all-lowercase or ALL-CAPS spaced run (no case
signal exists to split on), so an emphasized mid-sentence phrase like
`"d o e s i t"` may collapse into `"doesit"` rather than `"does it"` —
still far more readable than the letter-by-letter original, just not a
perfect fix in every case. This was found and fixed by actually testing
retrieval quality (see Part 4).

### `ingestion/chunker.py`

Splits each page's text into overlapping token windows using `tiktoken`
(the `cl100k_base` encoding — used here purely as a consistent token
counter, not tied to any specific LLM). The core loop:

```python
step = chunk_size_tokens - overlap_tokens  # default: 800 - 150 = 650
```

Chunk *N+1* starts `step` tokens after chunk *N* started, while chunk *N*
is `chunk_size_tokens` tokens long — so the last `overlap_tokens` tokens of
chunk *N* are deliberately repeated as the first tokens of chunk *N+1*.
This exists so that a sentence or idea that happens to fall right on a
chunk boundary still appears whole in at least one chunk; without overlap,
a fact split across the cut point would be damaged in both halves (one
chunk ending mid-thought, the next starting with a dangling reference).
Chunks never span a page boundary — each chunk is chunked from a single
page's text — so every chunk has one unambiguous page number for citations.

### `embeddings/local_embedder.py`

Wraps `sentence-transformers`. `get_model()` is `@lru_cache`d so the model
(`all-MiniLM-L6-v2` by default) loads from disk once per process, not once
per request. `embed_texts` calls `model.encode(..., normalize_embeddings=True)`
— normalizing every vector to unit length is what makes cosine similarity
and dot-product search equivalent, which is why Chroma can do the cheaper
dot-product computation internally and still get correct cosine-similarity
rankings. `embed_query` is a convenience wrapper for embedding a single
string (the question).

### `vectorstore/chroma_store.py`

Wraps a `chromadb.PersistentClient` (file-based, no server process) with
one collection per notebook, named `notebook_<id>`. This naming is the
entire mechanism behind notebook isolation: a query against notebook A's
collection can't return vectors from notebook B's collection, because
they're different collections entirely — there's no shared index to leak
across.

`get_or_create_collection` passes `metadata={"hnsw:space": "cosine"}` —
this explicitly tells Chroma to use cosine distance rather than its
default (squared Euclidean/L2). This only matters for the *numeric
"relevance" score* shown in the UI; retrieval **ranking** is identical
either way because embeddings are normalized (for unit vectors, L2
distance and cosine distance are monotonically related — same ordering,
different numbers). Without this explicit setting, the "relevance %"
computed as `1 - distance` was a real but meaningless number (this was
caught during live testing — every score showed ~0%, which traced back to
the arithmetic of L2 distance on typical relevant-chunk similarity, not
an actual retrieval failure).

`add_chunks` embeds a batch of chunk texts and stores them with their ids
and metadata (`document_id`, `filename`, `page`, `chunk_index`) in one
`collection.add()` call. `query` embeds the question and asks for the
`top_k` nearest neighbors, returning documents/metadatas/distances/ids in
parallel arrays (Chroma's API shape — index `i` across all four arrays
describes one retrieved chunk). `delete_document_chunks` and
`delete_notebook` clean up Chroma state when the corresponding SQL rows
are deleted.

### `llm/base.py`, `llm/groq_provider.py`, `llm/factory.py`

`base.py` defines `LLMProvider`, an abstract class with one method:
`generate_answer(question, context_blocks) -> str`. This is the entire
contract any generation backend must satisfy.

`groq_provider.py` is the only current implementation. Its `SYSTEM_PROMPT`
is the whole mechanism behind grounded, cited answers: it tells the model
the excerpts are labeled `[S1]`, `[S2]`, etc., to cite them inline when
used, and explicitly not to make things up if the excerpts don't cover the
question. `generate_answer` joins the context blocks, builds a user
message with the question, and calls the Groq chat completions API at
`temperature=0.2` (fairly deterministic — appropriate for a
fact-grounding task, not creative writing).

`factory.py` maps a string (`settings.LLM_PROVIDER`, default `"groq"`) to
a provider class via the `PROVIDERS` dict and instantiates it. Swapping to
a different LLM (Anthropic's API, for instance) means writing one new
class implementing `LLMProvider`, adding one line to `PROVIDERS`, and
changing an env var — no router or retrieval code changes.

### `storage/local_files.py`

Filesystem operations for uploaded documents, isolated behind a small
functional interface (`save_upload`, `delete_file`, `read_bytes`) so a
cloud backend could replace this module later without touching any
router code. Files are stored under `data/uploads/<notebook_id>/<document_id><ext>`
— the original filename isn't used as the on-disk name (avoiding
collisions/path issues), but is remembered in the `documents` table for
display and download.

### `routers/notebooks.py`

Plain CRUD: list, create, get, delete. Deleting a notebook cascades to its
documents/chunks/messages via SQL `ON DELETE CASCADE` foreign keys, and
separately calls `delete_notebook_vectors` to drop the corresponding
Chroma collection (Chroma isn't part of the SQL foreign-key graph, so this
cleanup has to happen explicitly).

### `routers/documents.py`

Covered in detail in Trace A above. Also exposes:
`GET .../documents` (list, used for the polling status display),
`DELETE .../documents/{id}` (removes the SQL row, the Chroma vectors, and
the file on disk), `GET .../documents/{id}/file` (streams the original
file back — used by the "Open original document" link in the Source
Viewer), and `GET .../documents/{id}/chunks/{chunk_id}` (the exact-text
lookup that powers citation trustworthiness, described in Trace B).

### `routers/chat.py`

Covered in detail in Trace B above. One implementation detail worth
calling out: the Groq call is wrapped in `try/except`, and any exception is
re-raised as `HTTPException(502, detail=f"LLM generation failed
({type(exc).__name__}): {exc}")`. Before this was added, any failure here
(invalid API key, a decommissioned model, a network hiccup) surfaced to
the user as a completely generic "Internal Server Error" with no
information — this fix was made specifically because that's exactly what
happened during testing, and the fix immediately revealed the real cause
(an `httpx`/`groq` version mismatch — see Part 4).

---

## Part 3 — Frontend, file by file

React + Vite + Tailwind, no state management library — `useState`/`useEffect`
are sufficient at this scale. All API calls go through one client module.

### `main.jsx` / `App.jsx`

`main.jsx` mounts the app inside a `BrowserRouter`. `App.jsx` holds one
piece of top-level state: `loggedIn`, persisted in `sessionStorage` purely
as a client-side UI flag (real auth is the `httpOnly` cookie the backend
set — this flag just decides whether to show the login screen or the app
without a network round-trip on every page load). Two routes: `/` (notebook
list) and `/notebooks/:notebookId` (a single notebook's workspace).

### `api/client.js`

One `request()` helper wraps `fetch` with `credentials: "include"` (so the
session cookie is sent automatically) and normalizes error handling: on a
non-OK response, it tries to parse a JSON `detail` field (what our
`HTTPException`s produce) and falls back to the raw HTTP status text if
the body isn't JSON (which is what a truly unhandled backend exception
produces — plain text, not JSON — explaining why early testing showed the
generic browser-level "Internal Server Error" string rather than a useful
message). Every backend endpoint has a corresponding one-line method here
(`listNotebooks`, `uploadDocument`, `chat`, etc.) — this is the only file
that constructs a URL path, so if a backend route ever moves, this is the
one place to update.

### `pages/Login.jsx`

A controlled form (`username`/`password` state) that calls `api.login`,
and on success calls the `onLogin` callback passed down from `App.jsx`.
Errors from a failed login (bad credentials → backend 401) are caught and
displayed inline.

### `pages/NotebookList.jsx`

Loads notebooks on mount, renders a create form and a list with delete
buttons. Nothing unusual — a template for how every other CRUD list in the
app is structured.

### `pages/NotebookView.jsx`

The workspace for one notebook: a two-column layout, `UploadPanel` on the
left, `ChatPanel` on the right. Reads `notebookId` from the URL via
`useParams()` and passes it down — this one id is the thread tying
together every request made from this page.

### `components/UploadPanel.jsx`

Lists documents for the current notebook and polls every 3 seconds
(`setInterval`) so a document's status visibly flips from "processing" to
"ready" without a manual refresh — this is the frontend half of the
background-task pattern described in Trace A. The file input is hidden
(`className="hidden"`) with a styled `<label>` acting as the visible
button, a standard trick for custom-styling file inputs since the native
control can't be styled directly.

### `components/ChatPanel.jsx`

The most complex frontend file. Three things happen here:

1. **`renderAnswer`**: scans the answer string with the regex
   `/\[S(\d+)\]/g`, and for each match, splices in a `CitationChip`
   component wired to the corresponding entry in the `citations` array
   (by index). If the model cites a number that's out of range (e.g.
   `[S9]` when only 5 chunks were retrieved — a real LLM failure mode,
   since nothing stops the model from hallucinating a label), the
   fallback just renders the literal bracket text rather than crashing.
2. **`RetrievedSources`**: an independent `<details>` disclosure showing
   *every* retrieved citation, regardless of whether the model cited it
   inline. Built specifically to separate "was the right chunk even
   retrieved" from "did the model use it correctly" when evaluating
   answer quality — a wrong answer with the right chunk visible here is a
   generation problem; a wrong answer with the right chunk *absent* here
   is a retrieval problem (chunking, embedding, or top-k might need
   tuning).
3. **`handleSend`**: optimistically appends the user's message to
   `messages` state immediately, then appends the assistant's response
   once the API call resolves — this is why the user's own message
   appears instantly while "Thinking..." shows for the assistant side.

### `components/CitationChip.jsx`

A small button rendering `S<n> · filename · p.<page>`, with the full
chunk text as a `title` attribute (native browser tooltip on hover) and an
`onClick` that bubbles up to `ChatPanel`'s `activeCitation` state.

### `components/SourceViewer.jsx`

A modal triggered by `activeCitation` being non-null. On mount/update, it
fetches the exact chunk by id (`api.getChunk`) — this is the "provably the
same text" mechanism discussed in Trace B: it does not re-extract or
search the document for matching text, it fetches the literal row that
was embedded and sent to the LLM. Also links to the original file via
`api.documentFileUrl` for full context.

### Config files: `vite.config.js`, `tailwind.config.js`, `postcss.config.js`

`vite.config.js` sets up the React plugin, and a dev-server proxy:
requests to `/api/*` are forwarded server-side to `http://localhost:8000`.
This is why the browser never needs CORS handling in normal local dev —
from the browser's perspective, everything (page and API) comes from the
single Vite origin; Vite's Node process does the actual cross-port
forwarding invisibly. `host: true` makes the dev server listen on all
network interfaces (not just `localhost`), which is what allows reaching
the app from another device on the same network at
`http://<your-ip>:5173`. `tailwind.config.js` / `postcss.config.js` are
standard Tailwind v3 setup — `content` tells Tailwind which files to scan
for class names so it only ships the CSS actually used.

---

## Part 4 — Bugs found during testing, and what each one teaches

These are worth understanding well, not just as fixes but as *why* they
happened — this is the kind of thing worth being able to explain if asked
"what problems did you run into and how did you debug them."

**`.env` silently ignored → login always failed with defaults.** Root
cause: `config.py` originally used a relative `env_file=".env"`, which
resolves against the current working directory, not the project's actual
layout. Since `uvicorn` is launched from `backend/` but `.env` lives at
the project root, the file was never found, and `Settings` silently fell
back to its hardcoded defaults. Fixed by anchoring the path to
`Path(__file__).resolve().parent.parent.parent`. The broader lesson:
relative paths in config loading are a common source of "works on my
machine" bugs, because they depend on an assumption (current working
directory) that isn't guaranteed by anything.

**`Client.__init__() got an unexpected keyword argument 'proxies'`.** Root
cause: `httpx` 0.28 removed a `proxies` constructor argument that older
versions of the `groq` SDK (`0.11.0`, pinned in `requirements.txt`) still
pass internally. Since `httpx` wasn't pinned, `pip install` resolved the
newest available version, which was incompatible. Fixed by pinning
`httpx==0.27.2`. The broader lesson: pinning your direct dependencies
isn't enough if their *transitive* dependencies aren't pinned — a
library two levels away can break your app on a fresh install months
after it worked fine, with no code change on your side at all.

**Generic "Internal Server Error" masked the real cause.** The Groq call
in `chat.py` wasn't originally wrapped in error handling, so any failure
there (including the `httpx` bug above) surfaced as FastAPI's default
unhandled-exception response — plain text, no detail. Fixed by catching
exceptions around the LLM call and re-raising as an `HTTPException` with
the real exception type and message. Lesson: a blanket "it errored"
message is not a debugging tool; surfacing the actual exception (safely,
without leaking secrets) turns a mystery into a two-second diagnosis.

**PDF citations showing letter-spaced garbage text.** Caught by actually
reading the "Retrieved sources" panel rather than just trusting that a
plausible-looking final answer meant everything upstream worked. Root
cause and fix are covered in the `extractors.py` section above. Lesson:
a RAG system's output can look completely reasonable even when an upstream
step (extraction, in this case) is producing damaged data — the LLM is
often good enough to produce a coherent-sounding answer from moderately
garbled context, which is precisely why it's dangerous to evaluate a RAG
system by eyeballing final answers alone.

**Every DOCX citation showing "page 1."** Caught the same way, on a
different (much longer) document. Root cause: DOCX has no stored page
concept the way PDF does. Fixed with best-effort manual-page-break
detection, with the honest limitation documented rather than hidden.

**Relevance scores showing ~0% for obviously-relevant retrieved chunks.**
Root cause: Chroma's default distance metric (squared L2) was used to
compute a number (`1 - distance`) that was only meaningful under cosine
distance; the two metrics rank results identically but produce different
numbers. Fixed by explicitly setting `hnsw:space: "cosine"` at collection
creation. Lesson: a metric can be "not wrong" (ranking was always correct)
while still being "not right" (the displayed number was meaningless) —
worth distinguishing when debugging, since fixing the wrong half wastes
time.

---

## Part 5 — Known limitations (by design, not oversight)

- **Source Viewer shows the matched passage, not a rendered original
  layout.** Building a full in-browser PDF/DOCX renderer with highlight
  overlays is a much larger project; showing the exact text plus a link
  to open the original file was judged the right scope for an internal
  tool.
- **DOCX pagination is best-effort**, as explained above — a fundamental
  limitation of the file format, not something fixable with more code
  without actually rendering the document.
- **The relevance score is a retrieval-strength signal, not an
  answer-correctness score.** A high-relevance chunk can still be
  misread or ignored by the LLM.
- **Docker Compose's frontend container serves a static build**; if
  deployed behind a different origin than the backend, `/api` requests
  need a reverse proxy (e.g. nginx) in front, since the dev-time Vite
  proxy trick only exists in `vite dev`, not in a static production
  build.
- **Single shared login, no per-user history/permissions** — intentional,
  matching the "internal tool, no public signup" requirement. Chat
  history is stored per-notebook in SQL (`chat_messages`) but the current
  UI starts a fresh thread each page load; the `GET .../chat/history`
  endpoint exists and is ready to be wired up if persistent history across
  sessions becomes a requirement.
