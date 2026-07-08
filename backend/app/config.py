"""
Centralized app configuration, loaded from environment variables / .env.
Keeping all tunables here makes it easy to swap providers later
(embedding model, vector store path, LLM provider, storage backend).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the project root (one level above backend/), so it's an
# obvious place for the docker-compose.yml (also at the root) to read too.
# Anchor the path to this file's location rather than a relative ".env" --
# a relative path resolves against the current working directory, which
# breaks depending on whether you launch uvicorn from the repo root or
# from backend/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # --- Auth (simple shared login, no OAuth/SSO) ---
    APP_USERNAME: str = "admin"
    APP_PASSWORD: str = "changeme"
    SESSION_SECRET: str = "dev-secret-change-me"

    # --- Storage ---
    DATA_DIR: str = "data"
    UPLOAD_DIR: str = "data/uploads"

    # --- Metadata DB ---
    DATABASE_URL: str = "sqlite:///./data/notebook.db"

    # --- Vector store (ChromaDB, embedded/local mode) ---
    CHROMA_DIR: str = "data/chroma"

    # --- Supabase (optional alternate backend) ---
    # Unset by default, which is what keeps a fresh `git clone` + run fully
    # local and account-free: DATABASE_URL stays "sqlite:///..." and
    # SUPABASE_URL/SUPABASE_KEY stay empty, so db.py and storage/factory.py
    # both fall back to sqlite + local disk.
    #
    # To opt in (e.g. for a Hugging Face Spaces deploy that needs real
    # persistent storage): create a free project at supabase.com, run
    # docs/supabase_schema.sql once in its SQL editor, then set:
    #   DATABASE_URL=postgresql://...   (Supabase's "Connection string", replacing the sqlite default)
    #   SUPABASE_URL=https://<project>.supabase.co
    #   SUPABASE_KEY=<service_role key, from Project Settings -> API>
    # No code change needed -- both the metadata DB and the vector store
    # (db.py / vectorstore/factory.py) switch to Postgres+pgvector, and
    # document storage (storage/factory.py) switches to Supabase Storage,
    # purely based on these values being set.
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_BUCKET: str = "documents"

    # --- Embeddings (local, no external API calls) ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Chunking ---
    CHUNK_SIZE_TOKENS: int = 800
    CHUNK_OVERLAP_TOKENS: int = 150

    # --- Retrieval ---
    TOP_K: int = 5

    # --- LLM provider (swappable: "groq" today, could add "anthropic" later) ---
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Google Drive import (optional) ---
    # Free API key from https://console.cloud.google.com with the Drive API
    # enabled. Only works for folders shared as "Anyone with the link can
    # view" -- private folders would need a full OAuth flow, out of scope
    # for this simple import feature.
    GOOGLE_API_KEY: str = ""

    # --- CORS ---
    FRONTEND_ORIGIN: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
