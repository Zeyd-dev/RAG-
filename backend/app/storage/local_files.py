"""
Local filesystem storage for uploaded documents. Isolated behind a
small functional interface so a cloud backend (S3, GCS, etc.) could be
swapped in later without touching routers or ingestion code -- see
storage/supabase_storage.py for that swap and storage/factory.py for
how the active backend is picked.
"""
import shutil
from contextlib import contextmanager
from pathlib import Path

from ..config import get_settings

settings = get_settings()


def notebook_dir(notebook_id: str) -> Path:
    d = Path(settings.UPLOAD_DIR) / notebook_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(notebook_id: str, document_id: str, filename: str, fileobj) -> str:
    suffix = Path(filename).suffix
    dest = notebook_dir(notebook_id) / f"{document_id}{suffix}"
    with open(dest, "wb") as out:
        shutil.copyfileobj(fileobj, out)
    return str(dest)


def delete_file(path: str) -> None:
    p = Path(path)
    if p.exists():
        p.unlink()


def read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


@contextmanager
def local_path_for(path: str):
    """The local backend already stores a real filesystem path, so
    there's nothing to stage -- just hand it back unchanged. Matches
    supabase_storage.local_path_for()'s signature (a context manager)
    so callers (ingestion, the file-viewer endpoint) don't need to know
    or care which backend is active."""
    yield path
