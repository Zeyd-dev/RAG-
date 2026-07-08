"""
Document upload, listing, deletion, and content retrieval (for the
source viewer). Upload triggers ingestion (extract -> chunk -> embed ->
store) as a background task so the request returns quickly; status
moves processing -> ready/failed as work completes.
"""
import io
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_conn, new_id, now_iso
from ..ingestion import google_drive
from ..ingestion.chunker import chunk_pages
from ..ingestion.extractors import extract_text, page_count_for
from ..models import DocumentMeta, DriveImportRequest
from ..storage.factory import delete_file, local_path_for, read_bytes, save_upload
from ..vectorstore.factory import add_chunks, delete_document_chunks

router = APIRouter()
settings = get_settings()

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def _process_document(document_id: str, notebook_id: str, storage_path: str, suffix: str) -> None:
    try:
        # local_path_for() is a no-op (yields the path unchanged) on the
        # local filesystem backend, and downloads-to-temp-file-then-
        # cleans-up on the Supabase Storage backend -- either way,
        # extract_text() below always gets a real local path to open,
        # regardless of which storage backend is active.
        with local_path_for(storage_path) as path:
            pages = extract_text(path, suffix)
        page_count = page_count_for(pages)
        chunks = chunk_pages(
            pages,
            chunk_size_tokens=settings.CHUNK_SIZE_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
        )

        chunk_ids = [f"{document_id}_{c.chunk_index}" for c in chunks]
        with get_conn() as conn:
            filename_row = conn.execute(
                "SELECT filename FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            filename = filename_row["filename"] if filename_row else ""
            for cid, c in zip(chunk_ids, chunks):
                conn.execute(
                    "INSERT INTO chunks (id, document_id, notebook_id, chunk_index, page, text) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (cid, document_id, notebook_id, c.chunk_index, c.page, c.text),
                )

        metadatas = [
            {"document_id": document_id, "filename": filename, "page": c.page, "chunk_index": c.chunk_index}
            for c in chunks
        ]
        add_chunks(notebook_id, chunk_ids, [c.text for c in chunks], metadatas)

        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status = 'ready', page_count = ? WHERE id = ?",
                (page_count, document_id),
            )
    except Exception as exc:  # noqa: BLE001 - surface any failure via status
        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status = 'failed', error = ? WHERE id = ?",
                (str(exc), document_id),
            )


@router.post("/{notebook_id}/documents", response_model=DocumentMeta)
def upload_document(
    notebook_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: str = Depends(get_current_user),
):
    with get_conn() as conn:
        nb = conn.execute("SELECT id FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not nb:
            raise HTTPException(status_code=404, detail="Notebook not found")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    document_id = new_id()
    storage_path = save_upload(notebook_id, document_id, file.filename, file.file)
    uploaded_at = now_iso()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents (id, notebook_id, filename, file_type, uploaded_at, status, storage_path) "
            "VALUES (?, ?, ?, ?, ?, 'processing', ?)",
            (document_id, notebook_id, file.filename, suffix.lstrip("."), uploaded_at, storage_path),
        )

    background_tasks.add_task(_process_document, document_id, notebook_id, storage_path, suffix)

    return {
        "id": document_id,
        "notebook_id": notebook_id,
        "filename": file.filename,
        "file_type": suffix.lstrip("."),
        "page_count": None,
        "uploaded_at": uploaded_at,
        "status": "processing",
        "error": None,
    }


@router.post("/{notebook_id}/documents/import-drive")
def import_from_drive(
    notebook_id: str,
    body: DriveImportRequest,
    background_tasks: BackgroundTasks,
    user: str = Depends(get_current_user),
):
    """
    Imports every supported file from a publicly-shared ("Anyone with the
    link can view") Google Drive folder into this notebook, reusing the
    exact same save-row-then-background-process pipeline as a normal
    upload -- each imported file goes through extraction/chunking/
    embedding identically, just sourced from Drive instead of a browser
    file picker.
    """
    with get_conn() as conn:
        nb = conn.execute("SELECT id FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not nb:
            raise HTTPException(status_code=404, detail="Notebook not found")

    try:
        folder_id = google_drive.extract_folder_id(body.drive_url)
        files = google_drive.list_folder_files(folder_id)
    except google_drive.DriveImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not files:
        raise HTTPException(
            status_code=400,
            detail=(
                "No supported files (PDF/DOCX/TXT/MD, or Google Docs) found. "
                "Make sure the folder is shared as 'Anyone with the link can view'."
            ),
        )

    imported = []
    skipped = 0
    for f in files:
        try:
            content, filename, suffix = google_drive.download_file(f["id"], f["mimeType"], f["name"])
        except google_drive.DriveImportError:
            skipped += 1
            continue

        if suffix not in SUPPORTED_SUFFIXES:
            skipped += 1
            continue

        document_id = new_id()
        storage_path = save_upload(notebook_id, document_id, filename, io.BytesIO(content))
        uploaded_at = now_iso()

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO documents (id, notebook_id, filename, file_type, uploaded_at, status, storage_path) "
                "VALUES (?, ?, ?, ?, ?, 'processing', ?)",
                (document_id, notebook_id, filename, suffix.lstrip("."), uploaded_at, storage_path),
            )

        background_tasks.add_task(_process_document, document_id, notebook_id, storage_path, suffix)
        imported.append({"id": document_id, "filename": filename})

    return {"imported": imported, "skipped": skipped}


@router.get("/{notebook_id}/documents", response_model=list[DocumentMeta])
def list_documents(notebook_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, notebook_id, filename, file_type, page_count, uploaded_at, status, error "
            "FROM documents WHERE notebook_id = ? ORDER BY uploaded_at DESC",
            (notebook_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.delete("/{notebook_id}/documents/{document_id}")
def delete_document(notebook_id: str, document_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT storage_path FROM documents WHERE id = ? AND notebook_id = ?",
            (document_id, notebook_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    delete_document_chunks(notebook_id, document_id)
    delete_file(row["storage_path"])
    return {"ok": True}


@router.get("/{notebook_id}/documents/{document_id}/file")
def get_document_file(notebook_id: str, document_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT storage_path, filename FROM documents WHERE id = ? AND notebook_id = ?",
            (document_id, notebook_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        # Reads the raw bytes and returns them directly rather than
        # FileResponse(storage_path) -- FileResponse needs a real,
        # long-lived filesystem path, which only the local backend has.
        # This version works identically for both backends (Supabase
        # Storage has no local path at all), and sidesteps any temp-file
        # lifetime/cleanup-before-it's-sent race that a FileResponse over
        # a downloaded temp file would risk.
        data = read_bytes(row["storage_path"])
        media_type = mimetypes.guess_type(row["filename"])[0] or "application/octet-stream"
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'},
        )


@router.get("/{notebook_id}/documents/{document_id}/chunks/{chunk_id}")
def get_chunk(notebook_id: str, document_id: str, chunk_id: str, user: str = Depends(get_current_user)):
    """
    Returns the exact chunk text plus its page number, used by the
    frontend Source Viewer to highlight the passage a citation came from.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT text, page FROM chunks WHERE id = ? AND document_id = ?",
            (chunk_id, document_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chunk not found")
        return dict(row)
