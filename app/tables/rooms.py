"""Realtime-комнаты столов: связи WebSocket-подключений.

Комната — только связи и блокировка; авторитетное состояние живёт
в БД (лобби) и в runtime (раздачи). Рассылка снапшотов — в runtime.py.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket


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

    def has_user(self, user_id: int) -> bool:
        return bool(self.connections.get(user_id))

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
