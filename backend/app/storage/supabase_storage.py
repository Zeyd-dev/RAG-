"""
Supabase Storage (S3-compatible object storage) backend -- alternate to
local_files.py, selected automatically (see storage/factory.py) when
SUPABASE_URL and SUPABASE_KEY are both set in .env.

Talks to Supabase's Storage REST API directly over httpx (already a
pinned dependency of this project) instead of pulling in the official
`supabase` Python package -- that package brings its own httpx version
constraint, and this project already had one painful httpx pin conflict
(see the README's note on the `groq` package). Three plain REST calls
avoid a second one entirely, at the cost of a little more code here.

Same functional interface as local_files.py so documents.py never needs
to know which backend is active: save_upload / delete_file / read_bytes
/ local_path_for. The returned "storage_path" is an object key inside
the bucket ("<notebook_id>/<document_id><suffix>"), not a real
filesystem path -- extraction (pypdf/python-docx) and the file-viewer
endpoint both need a real local file, which local_path_for() provides
by downloading to a temp file on demand.
"""
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import httpx

from ..config import get_settings

settings = get_settings()


def _headers(content_type: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "apikey": settings.SUPABASE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _object_url(path: str) -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{settings.SUPABASE_BUCKET}/{path}"


def save_upload(notebook_id: str, document_id: str, filename: str, fileobj) -> str:
    suffix = Path(filename).suffix
    key = f"{notebook_id}/{document_id}{suffix}"
    data = fileobj.read()
    resp = httpx.post(
        _object_url(key),
        headers={**_headers("application/octet-stream"), "x-upsert": "true"},
        content=data,
        timeout=60.0,
    )
    resp.raise_for_status()
    return key


def delete_file(path: str) -> None:
    try:
        resp = httpx.delete(_object_url(path), headers=_headers(), timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        pass  # matches local_files.delete_file: "already gone" is not an error


def read_bytes(path: str) -> bytes:
    resp = httpx.get(_object_url(path), headers=_headers(), timeout=60.0)
    resp.raise_for_status()
    return resp.content


@contextmanager
def local_path_for(path: str):
    """Downloads the object to a temp file for callers (extractors, the
    file-viewer endpoint) that need a real filesystem path, and removes
    it afterwards -- the bucket, not local disk, is the durable copy."""
    suffix = Path(path).suffix
    data = read_bytes(path)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        yield tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)
