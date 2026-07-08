"""
CRUD for notebooks (projects) that group documents together.
Questions in the chat router are always scoped to a single notebook.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import get_current_user
from ..db import get_conn, new_id, now_iso
from ..models import Notebook, NotebookCreate
from ..vectorstore.factory import delete_notebook as delete_notebook_vectors

router = APIRouter()


@router.get("", response_model=list[Notebook])
def list_notebooks(user: str = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM notebooks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


@router.post("", response_model=Notebook)
def create_notebook(body: NotebookCreate, user: str = Depends(get_current_user)):
    nb_id = new_id()
    created_at = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notebooks (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (nb_id, body.name, body.description, created_at),
        )
    return {"id": nb_id, "name": body.name, "description": body.description, "created_at": created_at}


@router.get("/{notebook_id}", response_model=Notebook)
def get_notebook(notebook_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return dict(row)


@router.delete("/{notebook_id}")
def delete_notebook(notebook_id: str, user: str = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Notebook not found")
        conn.execute("DELETE FROM notebooks WHERE id = ?", (notebook_id,))
    delete_notebook_vectors(notebook_id)
    return {"ok": True}
