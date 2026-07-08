"""
Chat endpoint: retrieves top-k relevant chunks from the active
notebook's Chroma collection, passes them + the question to the
configured LLM provider, and returns an answer with citations
(document, page, chunk id, matched text, similarity score).
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_conn, new_id, now_iso
from ..export.markdown_to_docx import render_markdown_to_docx
from ..export.markdown_to_pdf import render_markdown_to_pdf
from ..llm.base import LLMTemporarilyUnavailableError
from ..llm.factory import get_llm_provider
from ..models import ChatRequest, ChatResponse, Citation, ExportRequest
from ..vectorstore.factory import query as vector_query

router = APIRouter()
settings = get_settings()


@router.post("/{notebook_id}/chat", response_model=ChatResponse)
def chat(notebook_id: str, body: ChatRequest, user: str = Depends(get_current_user)):
    if notebook_id != body.notebook_id:
        raise HTTPException(status_code=400, detail="notebook_id mismatch")

    with get_conn() as conn:
        nb = conn.execute("SELECT id FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not nb:
            raise HTTPException(status_code=404, detail="Notebook not found")

    results = vector_query(notebook_id, body.question, top_k=settings.TOP_K)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if not documents:
        answer = (
            "I don't have any relevant information in this notebook to answer that. "
            "Try uploading a document first."
        )
        return {"answer": answer, "citations": []}

    context_blocks = []
    citations: list[Citation] = []
    for i, (doc_text, meta, dist, chunk_id) in enumerate(zip(documents, metadatas, distances, ids), start=1):
        context_blocks.append(f"[S{i}] (source: {meta.get('filename')}, page {meta.get('page')})\n{doc_text}")
        citations.append(
            Citation(
                document_id=meta.get("document_id", ""),
                filename=meta.get("filename", ""),
                page=meta.get("page"),
                chunk_id=chunk_id,
                text=doc_text,
                score=1 - dist if dist is not None else 0.0,
            )
        )

    try:
        provider = get_llm_provider()
        answer = provider.generate_answer(body.question, context_blocks)
    except LLMTemporarilyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface the real cause instead of a bare 500
        raise HTTPException(
            status_code=502,
            detail=f"LLM generation failed ({type(exc).__name__}): {exc}",
        ) from exc

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, notebook_id, role, content, citations_json, created_at) "
            "VALUES (?, ?, 'user', ?, NULL, ?)",
            (new_id(), notebook_id, body.question, now_iso()),
        )
        conn.execute(
            "INSERT INTO chat_messages (id, notebook_id, role, content, citations_json, created_at) "
            "VALUES (?, ?, 'assistant', ?, ?, ?)",
            (new_id(), notebook_id, answer, ChatResponse(answer=answer, citations=citations).model_dump_json(), now_iso()),
        )

    return {"answer": answer, "citations": [c.model_dump() for c in citations]}


@router.post("/{notebook_id}/chat/export")
def export_answer(notebook_id: str, body: ExportRequest, user: str = Depends(get_current_user)):
    """Turns one assistant answer into a downloadable .docx -- this is the
    "generate a report file" ask: the app already produces Markdown-formatted
    answers (tables, headings, bold), so exporting is just rendering that
    same content into a Word document instead of a chat bubble, with a
    Sources section listing the filename/page of each citation."""
    with get_conn() as conn:
        nb = conn.execute("SELECT name FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not nb:
            raise HTTPException(status_code=404, detail="Notebook not found")

    title = body.title or nb["name"]
    buffer = render_markdown_to_docx(
        body.content,
        citations=[c.model_dump() for c in body.citations],
        title=title,
    )
    safe_name = re.sub(r"[^\w\-]+", "_", title).strip("_") or "report"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )


@router.post("/{notebook_id}/report")
def generate_notebook_report(notebook_id: str, user: str = Depends(get_current_user)):
    """
    Summarizes every ready document in a notebook into a single downloadable
    PDF report -- one subsection per document plus a cross-document themes
    section, reusing the same LLM provider as the chat export (PDF rather
    than Word here since a whole-notebook report reads more like a
    document to skim/print than something you'd keep editing).

    Each document's chunks are joined and capped at PER_DOC_CHAR_BUDGET
    characters before being sent to the model. That's a simple truncation,
    not a map-reduce summarizer -- fine for the notebook sizes this app
    targets, but a very large/many-document notebook could lose content
    past the cap. Revisit with a two-pass (summarize-then-summarize)
    approach if that becomes a real problem.
    """
    PER_DOC_CHAR_BUDGET = 6000

    with get_conn() as conn:
        nb = conn.execute("SELECT name FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not nb:
            raise HTTPException(status_code=404, detail="Notebook not found")

        docs = conn.execute(
            "SELECT id, filename FROM documents WHERE notebook_id = ? AND status = 'ready' "
            "ORDER BY uploaded_at ASC",
            (notebook_id,),
        ).fetchall()
        if not docs:
            raise HTTPException(
                status_code=400,
                detail="No ready documents in this notebook yet -- upload something first.",
            )

        context_blocks = []
        for doc in docs:
            chunk_rows = conn.execute(
                "SELECT text FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC",
                (doc["id"],),
            ).fetchall()
            text = "\n\n".join(r["text"] for r in chunk_rows)
            truncated = len(text) > PER_DOC_CHAR_BUDGET
            text = text[:PER_DOC_CHAR_BUDGET]
            block = f"[Document: {doc['filename']}]\n{text}"
            if truncated:
                block += "\n[...truncated for length...]"
            context_blocks.append(block)

    doc_list = ", ".join(f'"{d["filename"]}"' for d in docs)
    instruction = (
        f'Write a structured internal summary report covering every document below from the '
        f'notebook "{nb["name"]}" ({doc_list}). Start with a short 2-3 sentence overview of what '
        f"this notebook contains as a whole. Then add one subsection per document, using its exact "
        f"filename as a level-2 Markdown heading, with 3-6 bullet points covering that document's "
        f"key content. "
        + (
            "Since there is more than one document, close with a level-2 'Key themes across "
            "documents' section noting anything shared, overlapping, or inconsistent between them. "
            if len(docs) > 1
            else ""
        )
        + "Use Markdown formatting throughout."
    )

    try:
        provider = get_llm_provider()
        content = provider.generate_answer(instruction, context_blocks, max_tokens=3000)
    except LLMTemporarilyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface the real cause instead of a bare 500
        raise HTTPException(
            status_code=502,
            detail=f"LLM generation failed ({type(exc).__name__}): {exc}",
        ) from exc

    buffer = render_markdown_to_pdf(content, title=f'{nb["name"]} — Summary Report')
    safe_name = re.sub(r"[^\w\-]+", "_", nb["name"]).strip("_") or "notebook"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_report.pdf"'},
    )


@router.get("/{notebook_id}/chat/history")
def chat_history(notebook_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, citations_json, created_at FROM chat_messages "
            "WHERE notebook_id = ? ORDER BY created_at ASC",
            (notebook_id,),
        ).fetchall()
        return [dict(r) for r in rows]
