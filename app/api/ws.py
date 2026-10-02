"""WebSocket стола: авторизация, приём действий/лобби-команд, рассылка.

Маршрутизация сообщений:
- «action» и «stand_up» в активной игре уходят в runtime (сам берёт лок
  и сам рассылает снапшоты);
- остальные команды (sit/kick/transfer_host/start/end) — сервис лобби
  под локом комнаты; старт и финиш дополнительно включают/останавливают
  runtime уже вне лока.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.auth import verify_session_token
from app.config import get_settings
from app.db import SessionLocal
from app.tables import service
from app.tables.rooms import room_manager
from app.tables.runtime import (
    broadcast_state,
    ensure_started,
    get_runtime,
    send_initial,
    stop_runtime,
)
from app.tables.service import TableError

logger = logging.getLogger(__name__)

ws_router = APIRouter()

LOBBY_ACTIONS = {"sit", "kick", "transfer_host", "start_game", "end_game"}
GAME_ACTIONS = {"fold", "check", "call", "bet", "raise"}


def _int_field(message: dict, key: str) -> int:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"поле «{key}» должно быть целым числом")
    return value


async def _apply(user_id: int, code: str, message: dict) -> None:
    mtype = message.get("type")

    # ── Игровые действия ────────────────────────────────────
    if mtype == "action":
        runtime = get_runtime(code)
        if runtime is None:
            raise TableError("сейчас нет активной раздачи")
        action = message.get("action")
        if action not in GAME_ACTIONS:
            raise TableError("неизвестное действие")
        amount = message.get("amount")
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, int)
        ):
            raise TableError("размер должен быть целым числом")
        await runtime.act(user_id, str(action), amount)
        return  # runtime сам рассылает снапшоты

    if mtype == "stand_up":
        runtime = get_runtime(code)
        if runtime is not None:
            await runtime.stand_up(user_id)  # активная игра — между раздачами
            return
        async with room_manager.get_room(code).lock:
            async with SessionLocal() as session:
                table = await service.get_table(session, code)
                if table is None:
                    raise TableError("стол не найден", status=404)
                await service.stand_up(session, table, user_id)
                await session.commit()
        await broadcast_state(code)
        return

    # ── Команды лобби ───────────────────────────────────────
    if mtype not in LOBBY_ACTIONS:
        raise TableError("неизвестный тип сообщения")

    started = False
    ended = False
    async with room_manager.get_room(code).lock:
        async with SessionLocal() as session:
            table = await service.get_table(session, code)
            if table is None:
                raise TableError("стол не найден", status=404)
            if mtype == "sit":
                await service.sit(session, table, user_id, _int_field(message, "seat"))
            elif mtype == "kick":
                await service.kick(
                    session, table, user_id, _int_field(message, "user_id")
                )
            elif mtype == "transfer_host":
                await service.transfer_host(
                    session, table, user_id, _int_field(message, "user_id")
                )
            elif mtype == "start_game":
                await service.start_game(session, table, user_id)
                started = True
            else:  # end_game
                await service.end_game(session, table, user_id)
                ended = True
            await session.commit()

    if started:
        # Создаём runtime и планируем первую раздачу (вне лока комнаты).
        await ensure_started(code)
        return
    if ended:
        await stop_runtime(code)
        await broadcast_state(code)
        return
    await broadcast_state(code)


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

    # Восстановление после рестарта процесса: стол активен, runtime нет.
    if get_runtime(code) is None:
        await ensure_started(code)

    room = room_manager.get_room(code)
    room.add(user_id, websocket)
    try:
        await send_initial(websocket, code, user_id)
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
