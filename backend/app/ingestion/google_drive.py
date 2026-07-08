"""
Minimal Google Drive integration: given a folder's shareable link, list
and download its files using the Drive API v3 with just an API key --
no OAuth, no service account, no separate consent flow. This only works
for folders shared as "Anyone with the link can view" (Drive's public
sharing setting), which is the common case for a startup handing over a
folder of documents to a program they're applying to. Private folders
require a full OAuth flow to access on someone's behalf, which is a much
bigger feature than "paste a link and import it" -- explicitly out of
scope here.

Google Docs/Sheets/Slides have no raw downloadable file at all (they're
not stored as PDF/DOCX internally) -- they have to be *exported* to a
real format via a separate Drive API endpoint. Only Google Docs export is
wired up below (to PDF), since that's the common case for shared startup
documents; Sheets/Slides can be added the same way later if needed.
"""
import re

import httpx

from ..config import get_settings

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
REQUEST_TIMEOUT = 30.0

# Google-native formats that have no direct file bytes and must be
# exported instead: mime type -> (export mime type, resulting extension).
_EXPORTABLE_MIME_TYPES = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class DriveImportError(Exception):
    pass


def extract_folder_id(url: str) -> str:
    """
    Accepts the two common shapes of a Drive folder link:
    https://drive.google.com/drive/folders/<id>?usp=sharing
    https://drive.google.com/open?id=<id>
    """
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    raise DriveImportError(
        "Couldn't find a folder id in that link. Expected something like "
        "https://drive.google.com/drive/folders/<id>"
    )


def _require_api_key() -> str:
    settings = get_settings()
    if not settings.GOOGLE_API_KEY:
        raise DriveImportError(
            "GOOGLE_API_KEY is not set. Get a free API key at "
            "https://console.cloud.google.com (enable the 'Google Drive API' "
            "for the project, then create an API key under Credentials) and "
            "add it to .env."
        )
    return settings.GOOGLE_API_KEY


def list_folder_files(folder_id: str) -> list[dict]:
    """
    Returns the subset of files in the folder that we know how to import:
    supported-extension files, plus Google Docs (exportable to PDF).
    Silently skips anything else (images, spreadsheets, subfolders, etc.)
    rather than erroring the whole import over one unsupported file.
    """
    api_key = _require_api_key()
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "key": api_key,
        "fields": "files(id, name, mimeType)",
        "pageSize": 200,
    }
    try:
        resp = httpx.get(f"{DRIVE_API_BASE}/files", params=params, timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:
        raise DriveImportError(f"Couldn't reach Google Drive: {exc}") from exc

    if resp.status_code != 200:
        raise DriveImportError(
            f"Google Drive API error ({resp.status_code}). Make sure the "
            "folder is shared as 'Anyone with the link can view', and that "
            "GOOGLE_API_KEY is valid with the Drive API enabled. "
            f"Details: {resp.text[:300]}"
        )

    files = resp.json().get("files", [])
    importable = []
    for f in files:
        name = f.get("name", "")
        mime = f.get("mimeType", "")
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if suffix in SUPPORTED_EXTENSIONS or mime in _EXPORTABLE_MIME_TYPES:
            importable.append(f)
    return importable


def download_file(file_id: str, mime_type: str, name: str) -> tuple[bytes, str, str]:
    """
    Returns (content_bytes, filename, suffix). Handles both a normal
    downloadable file and a Google-native file that needs exporting.
    """
    api_key = _require_api_key()

    if mime_type in _EXPORTABLE_MIME_TYPES:
        export_mime, suffix = _EXPORTABLE_MIME_TYPES[mime_type]
        url = f"{DRIVE_API_BASE}/files/{file_id}/export"
        params = {"mimeType": export_mime, "key": api_key}
        filename = f"{name}{suffix}"
    else:
        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params = {"alt": "media", "key": api_key}
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        filename = name

    try:
        resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT * 2)
    except httpx.HTTPError as exc:
        raise DriveImportError(f"Couldn't download '{name}': {exc}") from exc

    if resp.status_code != 200:
        raise DriveImportError(f"Couldn't download '{name}' ({resp.status_code}).")

    return resp.content, filename, suffix
