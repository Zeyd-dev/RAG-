"""
Pydantic schemas used across API request/response bodies.
Persistence itself lives in db.py (plain sqlite3, no ORM needed
at this scale) and vectorstore/chroma_store.py.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotebookCreate(BaseModel):
    name: str
    description: Optional[str] = None


class Notebook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime


class DocumentMeta(BaseModel):
    id: str
    notebook_id: str
    filename: str
    file_type: str
    page_count: Optional[int] = None
    uploaded_at: datetime
    status: str = "processing"  # processing | ready | failed
    error: Optional[str] = None


class ChatRequest(BaseModel):
    notebook_id: str
    question: str


class DriveImportRequest(BaseModel):
    drive_url: str


class DriveImportedFile(BaseModel):
    id: str
    filename: str


class DriveImportResponse(BaseModel):
    imported: list[DriveImportedFile]
    skipped: int


class Citation(BaseModel):
    document_id: str
    filename: str
    page: Optional[int] = None
    chunk_id: str
    text: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


class ExportRequest(BaseModel):
    """Body for POST /{notebook_id}/chat/export -- the frontend sends back
    exactly what it already has in state (the assistant message's content
    and citations) rather than the backend re-fetching anything, since the
    chat_messages row already has this same data."""

    content: str
    citations: list[Citation] = []
    title: Optional[str] = None
