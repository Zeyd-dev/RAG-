"""
Minimal shared-login auth: one username/password pair from env vars,
backed by a signed session cookie. No OAuth/SSO, no user table —
this app is for internal/private use only.
"""
from itsdangerous import BadSignature, URLSafeTimedSerializer
from fastapi import Depends, HTTPException, Request, status

from .config import get_settings

settings = get_settings()
_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="ragnotebook-session")

SESSION_COOKIE_NAME = "rag_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def create_session_token(username: str) -> str:
    return _serializer.dumps({"username": username})


def verify_credentials(username: str, password: str) -> bool:
    return username == settings.APP_USERNAME and password == settings.APP_PASSWORD


def get_current_user(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return data["username"]


CurrentUser = Depends(get_current_user)
