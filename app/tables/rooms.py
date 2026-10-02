"""Realtime-комнаты столов: держат WebSocket-подключения и рассылают снапшоты.

Комната — только связи и рассылка; авторитетное состояние живёт в БД.
Мутации стола выполняются под room.lock (один игрок — одно действие),
рассылка идёт уже после снятия блокировки.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from app.db import SessionLocal
from app.tables import service

logger = logging.getLogger(__name__)


class Room:
    def __init__(self, code: str) -> None:
        self.code = code
        self.connections: dict[int, list[WebSocket]] = {}
        self.lock = asyncio.Lock()

    def add(self, user_id: int, ws: WebSocket) -> None:
        self.connections.setdefault(user_id, []).append(ws)

    def remove(self, user_id: int, ws: WebSocket) -> None:
        sockets = self.connections.get(user_id)
        if sockets is None:
            return
        if ws in sockets:
            sockets.remove(ws)
        if not sockets:
            self.connections.pop(user_id, None)

    def all_sockets(self) -> list[WebSocket]:
        return [ws for sockets in self.connections.values() for ws in sockets]


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def get_room(self, code: str) -> Room:
        room = self._rooms.get(code)
        if room is None:
            room = Room(code)
            self._rooms[code] = room
        return room

    def peek(self, code: str) -> Room | None:
        return self._rooms.get(code)

    def drop_if_empty(self, code: str) -> None:
        room = self._rooms.get(code)
        if room is not None and not room.connections:
            self._rooms.pop(code, None)

    def drop(self, code: str) -> None:
        self._rooms.pop(code, None)


room_manager = RoomManager()


async def send_state(ws: WebSocket, code: str, viewer_id: int) -> None:
    """Личный снапшот одному подключению (используется при подключении)."""
    async with SessionLocal() as session:
        table = await service.get_table(session, code)
        if table is None:
            await ws.send_json({"type": "error", "message": "стол не найден"})
            await ws.close()
            return
        snapshot = await service.build_snapshot(session, table, viewer_id)
    await ws.send_json({"type": "state", "state": snapshot})


async def broadcast_state(code: str) -> None:
    """Снапшит состояние каждому подключённому (в M3 в нём появятся карты)."""
    room = room_manager.peek(code)
    if room is None or not room.connections:
        return
    async with SessionLocal() as session:
        table = await service.get_table(session, code)
        if table is None:
            for ws in room.all_sockets():
                try:
                    await ws.close()
                except Exception:  # noqa: BLE001 — сокет мог уже закрыться
                    pass
            room_manager.drop(code)
            return
        for user_id in list(room.connections):
            snapshot = await service.build_snapshot(session, table, user_id)
            for ws in list(room.connections[user_id]):
                try:
                    await ws.send_json({"type": "state", "state": snapshot})
                except Exception:  # noqa: BLE001 — мёртвый сокет убираем
                    room.remove(user_id, ws)
