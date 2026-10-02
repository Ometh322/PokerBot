"""WebSocket стола: авторизация по токену, приём действий, рассылка снапшотов."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.auth import verify_session_token
from app.config import get_settings
from app.db import SessionLocal
from app.tables import service
from app.tables.rooms import broadcast_state, room_manager, send_state
from app.tables.service import TableError

logger = logging.getLogger(__name__)

ws_router = APIRouter()


def _int_field(message: dict, key: str) -> int:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"поле «{key}» должно быть целым числом")
    return value


async def _apply(user_id: int, code: str, message: dict) -> None:
    """Применяет действие к столу под блокировкой комнаты."""
    mtype = message.get("type")
    async with room_manager.get_room(code).lock:
        async with SessionLocal() as session:
            table = await service.get_table(session, code)
            if table is None:
                raise TableError("стол не найден", status=404)
            if mtype == "sit":
                await service.sit(session, table, user_id, _int_field(message, "seat"))
            elif mtype == "stand_up":
                await service.stand_up(session, table, user_id)
            elif mtype == "start_game":
                await service.start_game(session, table, user_id)
            elif mtype == "end_game":
                await service.end_game(session, table, user_id)
            elif mtype == "kick":
                await service.kick(session, table, user_id, _int_field(message, "user_id"))
            elif mtype == "transfer_host":
                await service.transfer_host(
                    session, table, user_id, _int_field(message, "user_id")
                )
            else:
                raise TableError("неизвестный тип сообщения")
            await session.commit()


@ws_router.websocket("/ws/table/{code}")
async def ws_table(
    websocket: WebSocket, code: str, token: str = Query(default="")
) -> None:
    code = service.norm_code(code)
    await websocket.accept()

    user_id = verify_session_token(token, get_settings().bot_token)
    if user_id is None:
        await websocket.send_json({"type": "error", "message": "нужна авторизация"})
        await websocket.close(code=4401)
        return

    room = room_manager.get_room(code)
    room.add(user_id, websocket)
    try:
        await send_state(websocket, code, user_id)
        while True:
            try:
                raw = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "неправильное сообщение"}
                )
                continue
            if not isinstance(raw, dict):
                await websocket.send_json(
                    {"type": "error", "message": "неправильное сообщение"}
                )
                continue
            if raw.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            try:
                await _apply(user_id, code, raw)
                await broadcast_state(code)
            except TableError as exc:
                await websocket.send_json({"type": "error", "message": exc.message})
            except (TypeError, ValueError) as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — не роняем процесс из-за одного сокета
        logger.exception("ошибка в ws-подключении к столу %s", code)
    finally:
        room.remove(user_id, websocket)
        room_manager.drop_if_empty(code)
