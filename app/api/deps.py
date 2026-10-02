"""Зависимости FastAPI: текущий пользователь по сессионному токену."""

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.auth import verify_session_token
from app.config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="нужен Authorization: Bearer")
    user_id = verify_session_token(credentials.credentials, get_settings().bot_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="сессия недействительна")
    return user_id
