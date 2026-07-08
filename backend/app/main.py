"""
FastAPI application entrypoint.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    verify_credentials,
)
from .config import get_settings
from .db import init_db
from .routers import chat, documents, notebooks

settings = get_settings()

app = FastAPI(title="RAG NoteBook", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session_token(body.username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        # SameSite=None (+ the Secure flag it requires) rather than Lax:
        # Hugging Face Spaces normally shows the app embedded in an
        # iframe on huggingface.co, which makes every request from that
        # iframe to the app's own *.hf.space origin "cross-site" from the
        # browser's point of view -- a Lax cookie is silently dropped in
        # that context, so login appears to succeed (200 response, cookie
        # set) but the cookie never actually comes back on the next
        # request, and every API call then 401s as "Not authenticated".
        # Secure cookies still work for local dev over plain http, since
        # Chrome/Firefox both special-case localhost/127.0.0.1 as a
        # secure context.
        samesite="none",
        secure=True,
    )
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="none", secure=True)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(notebooks.router, prefix="/api/notebooks", tags=["notebooks"])
app.include_router(documents.router, prefix="/api/notebooks", tags=["documents"])
app.include_router(chat.router, prefix="/api/notebooks", tags=["chat"])


# Optional single-container mode: if a built frontend was copied in at
# backend/app/static (see the root Dockerfile used for Hugging Face
# Spaces), serve it directly from this same FastAPI process instead of
# needing a separate nginx/Vite server. Local dev is unaffected since this
# directory never exists there. Registered last on purpose: must never
# shadow the /api/* routes above, and route matching order is registration
# order.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    _ASSETS_DIR = _STATIC_DIR / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # Client-side route (e.g. /notebooks/<id>) or the root path --
        # hand back index.html and let React Router take over in-browser.
        return FileResponse(_STATIC_DIR / "index.html")
