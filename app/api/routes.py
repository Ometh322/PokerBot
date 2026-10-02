"""REST-маршруты API: health, авторизация, столы, история рук."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import issue_session_token, parse_user, validate_init_data
from app.api.deps import current_user_id
from app.config import get_settings
from app.db import SessionLocal
from app.models.orm import Hand, User
from app.tables import service
from app.tables import runtime as table_runtime
from app.tables import settlement as table_settlement
from app.tables.settings import TableSettings

api_router = APIRouter()


class AuthRequest(BaseModel):
    init_data: str


class DevAuthRequest(BaseModel):
    user_id: int = Field(default=999_123, ge=1, le=1_000_000_000)
    first_name: str = Field(default="Гость", max_length=64)


class CreateTableRequest(BaseModel):
    name: str = Field(default="", max_length=64)
    settings: TableSettings = TableSettings()


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

    # Профиль обновляем при каждом входе — имя/аватар из Telegram актуальны.
    async with SessionLocal() as session:
        await service.upsert_user(
            session,
            user_id=user["id"],
            first_name=str(user.get("first_name") or ""),
            last_name=user.get("last_name"),
            username=user.get("username"),
            photo_url=user.get("photo_url"),
        )
        await session.commit()

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


@api_router.post("/auth/dev")
async def auth_dev(body: DevAuthRequest) -> dict:
    """Вход тестовым игроком без Telegram. Доступен только при DEV_MODE=1."""
    settings = get_settings()
    if not settings.dev_mode:
        raise HTTPException(status_code=404, detail="not found")
    async with SessionLocal() as session:
        await service.upsert_user(session, user_id=body.user_id, first_name=body.first_name)
        await session.commit()
    return {
        "user": {
            "id": body.user_id,
            "first_name": body.first_name,
            "last_name": None,
            "username": None,
            "photo_url": None,
        },
        "token": issue_session_token(body.user_id, settings.bot_token),
        "start_param": None,
    }


@api_router.post("/tables", status_code=201)
async def create_table(
    body: CreateTableRequest, user_id: int = Depends(current_user_id)
) -> dict:
    async with SessionLocal() as session:
        table = await service.create_table(
            session, host_id=user_id, name=body.name, settings=body.settings
        )
        await session.commit()
        snapshot = await service.build_snapshot(session, table, user_id)
    return {
        "code": table.code,
        "invite_link": service.invite_link(table.code),
        "snapshot": snapshot,
    }


@api_router.get("/tables")
async def list_tables(user_id: int = Depends(current_user_id)) -> list[dict]:
    async with SessionLocal() as session:
        return await service.list_for_user(session, user_id)


@api_router.get("/tables/{code}/hands")
async def get_table_hands(
    code: str, user_id: int = Depends(current_user_id), limit: int = 20
) -> list[dict]:
    """История раздач; имена победителей подтягиваются из профилей."""
    code = service.norm_code(code)
    limit = max(1, min(limit, 50))
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Hand)
                .where(Hand.table_code == code)
                .order_by(Hand.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        results = [(hand, json.loads(hand.result_json)) for hand in rows]
        uids = {w["user_id"] for _, winners in results for w in winners}
        names: dict[int, str] = {}
        if uids:
            users = (
                await session.execute(select(User).where(User.tg_id.in_(uids)))
            ).scalars().all()
            names = {u.tg_id: service.display_name(u) for u in users}
        return [
            {
                "number": hand.number,
                "dealer_seat": hand.dealer_seat,
                "board": json.loads(hand.board_json),
                "pot_total": hand.pot_total,
                "winners": [
                    {**w, "name": names.get(w["user_id"], f"Игрок {w['user_id']}")}
                    for w in winners
                ],
                "created_at": hand.created_at.isoformat() if hand.created_at else None,
            }
            for hand, winners in results
        ]


@api_router.get("/tables/{code}/settlement")
async def get_settlement(code: str, user_id: int = Depends(current_user_id)) -> dict:
    """Расчёт долгов — после завершения игры."""
    async with SessionLocal() as session:
        table = await service.get_table(session, code)
        if table is None:
            raise HTTPException(status_code=404, detail="стол не найден")
        if table.status != "finished":
            raise HTTPException(
                status_code=400, detail="расчёт доступен после завершения игры"
            )
        return await table_settlement.build_settlement(session, table)


@api_router.get("/tables/{code}")
async def get_table(code: str, user_id: int = Depends(current_user_id)) -> dict:
    # Активная игра: снапшот собирает runtime (живые стеки, карты, действия).
    runtime = table_runtime.get_runtime(service.norm_code(code))
    if runtime is not None:
        return await runtime.build_snapshot(user_id)
    async with SessionLocal() as session:
        table = await service.get_table(session, code)
        if table is None:
            raise HTTPException(status_code=404, detail="стол не найден")
        return await service.build_snapshot(session, table, user_id)
