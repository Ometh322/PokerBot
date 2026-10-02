"""REST-маршруты API. В M1: health + авторизация Mini App."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.auth import issue_session_token, parse_user, validate_init_data
from app.config import get_settings

api_router = APIRouter()


class AuthRequest(BaseModel):
    init_data: str


@api_router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@api_router.post("/auth")
async def auth(body: AuthRequest) -> dict:
    settings = get_settings()
    pairs = validate_init_data(body.init_data, settings.bot_token)
    if pairs is None:
        raise HTTPException(status_code=401, detail="invalid init data")

    user = parse_user(pairs)
    if user is None:
        raise HTTPException(status_code=401, detail="no user in init data")

    return {
        "user": {
            "id": user["id"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name"),
            "username": user.get("username"),
            "photo_url": user.get("photo_url"),
        },
        "token": issue_session_token(user["id"], settings.bot_token),
        "start_param": pairs.get("start_param"),
    }
