---
title: RAG NoteBook
emoji: 🔴
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# RAG NoteBook

An internal, NotebookLM-style RAG app: upload documents into notebooks, ask
questions, get answers with inline citations that link back to the exact
source passage. Runs fully locally at zero cost.

- Backend: FastAPI (Python)
- Frontend: React + Tailwind (Vite)
- Vector store: ChromaDB, embedded/file-based (no server, no account)
- Embeddings: sentence-transformers, local (no API calls, documents stay private)
- LLM: Groq API, free tier (e.g. Llama 3.3 70B) — swappable, see `docs/architecture.md`
- Auth: shared username/password (env vars), no OAuth/SSO

See `docs/architecture.md` for how the pieces fit together and how to swap
any component later.

## 1. Prerequisites

- Python 3.11+
- Node.js 20+
- A free Groq API key: sign up at https://console.groq.com and create an API key

## 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the env file and fill in your Groq key:

```bash
cd ..
cp .env.example .env
```

Edit `.env`:

```
APP_USERNAME=admin
APP_PASSWORD=choose-a-real-password
SESSION_SECRET=choose-a-long-random-string
GROQ_API_KEY=your-key-from-console.groq.com
```

Run the backend (from the `backend/` directory, with the venv active):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The first request that generates embeddings will download the
`all-MiniLM-L6-v2` model (a few hundred MB) — this happens once and is then
cached locally.

## 3. Frontend setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the `APP_USERNAME` /
`APP_PASSWORD` you set in `.env`.

### Everyday launching (after first-time setup above)

Once the one-time setup (venv, `pip install`, `npm install`, `.env`) is done,
you don't need to repeat it. Three double-clickable scripts are provided at
the project root:

- `start-backend.bat` — activates the venv and starts the backend on :8000
- `start-frontend.bat` — starts the frontend dev server on :5173
- `start-all.bat` — opens both of the above in their own windows at once

Double-click `start-all.bat` (or run it from a terminal) each time you want
to use the app, then open http://localhost:5173. Close both windows (or
Ctrl+C in each) when you're done. These just wrap the manual commands above
— nothing changes about how the app works.

## 4. Using it

1. Create a notebook.
2. Upload PDF, DOCX, TXT, or Markdown files — they're processed in the
   background (status shows "processing" then "ready"). Or click
   "From Drive" and paste a Google Drive folder link to import every
   supported file in that folder at once (requires `GOOGLE_API_KEY` in
   `.env`, and the folder must be shared as "Anyone with the link can
   view" — see `.env.example` for how to get a free key).
3. Ask a question. The answer cites sources inline as small numbered
   markers; click one to see the exact passage it came from.
4. Under each answer, expand "Retrieved sources" to see every chunk that
   was actually retrieved and sent to the model for that question — not
   just the ones the model chose to cite inline. This is the fastest way
   to tell a retrieval problem (right chunk never retrieved) apart from a
   generation problem (right chunk retrieved, but the model answered it
   wrong or ignored it) when evaluating answer quality.
5. Click "Export as Word" under any answer to download it as a `.docx`
   file — the same Markdown formatting (headings, bold, tables) plus a
   "Sources" section listing each cited document and page. Useful for
   report-style questions where you want the answer as a file, not just
   chat text.

If you're compiling something across several similar documents (e.g. an
end-of-year report from multiple years of past reports) and sections go
missing inconsistently between them, that's usually retrieval, not the
model: only the top `TOP_K` chunks (5 by default, in `.env`) are retrieved
per question across the *whole* notebook, so a section present in one
document can lose out to more textually-similar chunks from another.
Two fixes, best used together: upload a reference document showing the
structure/sections you want, and/or raise `TOP_K` in `.env` (e.g. to 10)
so more of the notebook gets considered per question.

## 5. Testing on your own network (optional)

The frontend (`vite.config.js`) and the backend start script
(`start-backend.bat`) are both configured to listen on all network
interfaces, not just `localhost`. That means colleagues on the same
Wi-Fi/office network can reach the app at `http://<your-machine-ip>:5173`
(find your IP with `ipconfig`) while it's running on your machine — no
deployment needed. Windows Firewall will prompt to allow the connection the
first time; allow it for private networks. This is fine for quick internal
testing on a trusted network, but there's no HTTPS here, so don't expose
this beyond a trusted LAN.

## 6. Running with Docker Compose (optional)

Only needed if you want this always-on and reachable by someone (e.g. your
supervisor) without them installing anything or opening a terminal — they
just get a URL to open in a browser and the shared login. For pure local
use by yourself, the two `npm run dev` / `uvicorn --reload` processes above
are simpler.

```bash
docker compose up --build -d
```

Everything is served from **one port, 80** — the frontend container runs
nginx, which serves the built React app and internally forwards `/api/*`
requests to the backend container (`frontend/nginx.conf`). The backend
itself isn't published to the outside world at all, only reachable from
the frontend container. Put your real `.env` file at the repo root before
running this — `docker-compose.yml` reads it for the backend container.

### 6a. Deploying this to a small VPS so someone else can use it

This is the "anyone can open it from their own device, no CMD, no install"
setup. Rough shape of it:

1. Rent a small VPS (Hetzner, DigitalOcean, Contabo, etc. — a few dollars a
   month for a small Ubuntu instance is plenty for this app's size). This
   step needs a real account and payment method, so it has to be done by
   you directly on the provider's site.
2. SSH into the server, install Docker and the Docker Compose plugin
   (`curl -fsSL https://get.docker.com | sh` covers Docker itself on
   Ubuntu; the compose plugin usually comes with it on recent versions).
3. Clone this repo onto the server, add a real `.env` (same variables as
   your local one, with your Groq key etc.) at the repo root.
4. `docker compose up --build -d`
5. Open Windows/your provider's firewall for port 80 if needed, then share
   `http://<server-ip>/` with your supervisor along with the
   `APP_USERNAME`/`APP_PASSWORD` from your `.env`. That link plus that
   login is the entire experience on his end — no terminal, no setup.

Optional polish for later: point a real domain at the server and put
[Caddy](https://caddyserver.com/) in front instead of nginx directly, which
gets you automatic free HTTPS and a proper `https://yourdomain.com` link
instead of a bare IP — worth doing if this moves beyond a quick internal
demo, not required to get it working.

### 6b. Using Supabase for persistent storage (optional)

Everything above (sqlite + ChromaDB + local disk) is the default and needs
no accounts at all. The one gap it has is on hosts with no persistent
disk — a free Hugging Face Space, for instance, loses all notebooks and
documents whenever the container restarts or sleeps. Supabase (a free
Postgres + object storage service) fixes that, as a swap-in alternate
backend, not a rewrite:

- **Metadata + vector store**: `backend/app/db.py` and
  `backend/app/vectorstore/factory.py` switch from sqlite/ChromaDB to
  Postgres + [pgvector](https://github.com/pgvector/pgvector) automatically
  based on `DATABASE_URL`'s scheme.
- **File storage**: `backend/app/storage/factory.py` switches from local
  disk to Supabase Storage automatically based on whether `SUPABASE_URL`
  and `SUPABASE_KEY` are set.

Neither swap touches the local, account-free path — leave `DATABASE_URL`
and the `SUPABASE_*` vars unset (or absent from `.env`) and the app behaves
exactly as described above.

To opt in:

1. Create a free project at [supabase.com](https://supabase.com) (no card
   required on the free tier — 500MB database, 1GB file storage).
2. In the Supabase dashboard, go to **SQL Editor → New query**, paste in
   the contents of `docs/supabase_schema.sql`, and run it once. This
   enables the pgvector extension and creates the `embeddings` table that
   holds chunk text + vectors.
3. In **Storage**, create a new bucket named `documents` (or pick your own
   name and set `SUPABASE_BUCKET` to match).
4. In **Project Settings → API**, copy the Project URL and the
   `service_role` key (not the public `anon` key — the backend needs
   write access). In **Project Settings → Database**, copy the connection
   string (URI format).
5. Add these to `.env` (in addition to the usual variables):

```
DATABASE_URL=postgresql://postgres:[your-db-password]@[your-project-ref].supabase.co:5432/postgres
SUPABASE_URL=https://[your-project-ref].supabase.co
SUPABASE_KEY=[your service_role key]
SUPABASE_BUCKET=documents
```

6. Restart the backend (or rebuild/redeploy your container, e.g. re-push
   to your Hugging Face Space with these as Secrets instead of plain
   variables, since one of them is a service-role key). `init_db()` will
   create the remaining metadata tables in Postgres automatically on
   startup — only the pgvector table from step 2 is a manual one-time step.

This is entirely optional and only worth doing if you're hosting somewhere
without persistent disk. For local use, or a VPS with Docker Compose (where
the container's disk already persists), the default sqlite/Chroma/local-disk
setup is simpler and has one less account involved.

## Notes

- **Groq free-tier rate limits**: if usage grows (more users, more/longer
  documents), you may hit Groq's free-tier request or token-per-minute
  limits. Check current limits at https://console.groq.com. If you need
  more headroom, either request a rate-limit increase or point the app at
  a different provider.
- **`llama-3.3-70b-versatile` is on Groq's deprecation list** (shutdown
  date 08/16/26 per https://console.groq.com/docs/deprecations, checked as
  of writing this). Before that date, change `GROQ_MODEL` in `.env` to
  Groq's recommended replacement (`openai/gpt-oss-120b` or
  `qwen/qwen3.6-27b` as of writing — check the deprecations page for the
  current recommendation, since Groq's model lineup changes over time).
  No code change needed, just the `.env` value.
- **Swapping the LLM provider**: generation logic is isolated in
  `backend/app/llm/`. To use Anthropic's Claude API (or any other
  provider) instead of Groq, add a new class implementing `LLMProvider`
  (see `backend/app/llm/base.py`), register it in `backend/app/llm/factory.py`,
  and set `LLM_PROVIDER` in `.env`. No other code needs to change.
- **Data location**: uploaded files, the sqlite metadata DB, and the Chroma
  vector store all live under `backend/data/` — back this folder up if you
  care about retaining notebooks. (This only applies to the default local
  setup — see "6b. Using Supabase for persistent storage" if you've
  switched `DATABASE_URL`/`SUPABASE_*` to the Postgres+Supabase backend,
  where the data lives in your Supabase project instead.)
- **Swapping the metadata DB, vector store, or file storage backend**:
  same pattern as the LLM provider above — `backend/app/db.py`,
  `backend/app/vectorstore/factory.py`, and `backend/app/storage/factory.py`
  each pick their backend from env vars (`DATABASE_URL`, `SUPABASE_URL`/
  `SUPABASE_KEY`) with no other code changes. sqlite+ChromaDB+local disk is
  the zero-account default; Postgres+pgvector+Supabase Storage is the
  built-in alternate (see "6b." above). A third backend (e.g. plain S3, or
  a different Postgres host) would follow the same shape: implement the
  same functions the current backend exposes, then add one more branch to
  the relevant `factory.py`.
- **`httpx` is pinned to `0.27.2`** in `requirements.txt`. The installed
  `groq==0.11.0` SDK still passes a `proxies` argument to `httpx.Client`
  internally, which `httpx>=0.28` removed — if you ever see
  `Client.__init__() got an unexpected keyword argument 'proxies'`, it
  means something reinstalled a newer `httpx`; run
  `pip install httpx==0.27.2` to fix it.
- **Known extraction limitations**, both addressed with best-effort fixes
  rather than perfect solutions (see `docs/code-walkthrough.md` for the
  full explanation of each): PDFs with letter-spaced/tracked headings
  (common in slide-deck-style exports) are automatically de-spaced during
  extraction, but an ALL-CAPS or all-lowercase spaced run can't always be
  perfectly re-segmented into separate words. DOCX files don't store page
  numbers the way PDFs do; citations use manually-inserted page breaks
  (Ctrl+Enter, or a paragraph's "page break before" property) where
  present, but a document with zero manual breaks will show every
  citation as page 1.
- **Citation relevance score**: the `~XX% relevance` shown per source in
  the "Retrieved sources" panel is the embedding cosine similarity between
  the question and that chunk. It's a rough signal of retrieval strength,
  not a calibrated confidence score for the answer's correctness — a high
  relevance chunk can still be misread or ignored by the LLM (that's a
  generation problem, not a retrieval problem; see item 4 in "Using it").
