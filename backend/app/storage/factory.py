"""
Picks the active document-storage backend based on whether Supabase
credentials are configured -- Supabase Storage (supabase_storage.py)
when SUPABASE_URL and SUPABASE_KEY are both set, the local filesystem
(local_files.py) otherwise, which is the zero-account default for a
plain `git clone` + run. documents.py imports from here instead of a
specific backend module directly, so the backend can be swapped by
changing two env vars -- no other code changes.
"""
from ..config import get_settings

settings = get_settings()

if settings.SUPABASE_URL and settings.SUPABASE_KEY:
    from .supabase_storage import delete_file, local_path_for, read_bytes, save_upload
else:
    from .local_files import delete_file, local_path_for, read_bytes, save_upload

__all__ = ["save_upload", "delete_file", "read_bytes", "local_path_for"]
