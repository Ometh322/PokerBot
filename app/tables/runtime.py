"""Runtime активного стола: цикл раздач, таймеры, уведомления, синк с БД.

Модель ответственности:
- лобби — авторитет в БД (service);
- активная игра — авторитет в памяти (TableRuntime), стеки синхронизируются
  в БД после каждой раздачи;
- рассылка — персональные снапшоты каждому подключению (карты приходят
  только владельцу).

Блокировка: мутации раздачи выполняются под room.lock; публичные методы
runtime сами берут лок, вызывающим из WS вкладываться в него не нужно.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select, update

from app.bot import sender
from app.config import get_settings
from app.db import SessionLocal
from app.game.hand import EngineError, HandPlayer, HandRunner
from app.models.orm import PokerTable, TablePlayer, User, utcnow
from app.tables import service
from app.tables.rooms import room_manager
from app.tables.service import TableError
from app.tables.settings import TableSettings

logger = logging.getLogger(__name__)

# Паузы: после старта и между раздачами — увидеть результат, отдышаться.
FIRST_HAND_DELAY = 3.0
NEXT_HAND_DELAY = 7.0


@dataclass
class RuntimePlayer:
    user_id: int
    name: str
    photo_url: str | None
    seat: int
    stack: int
    total_bought: int
    left: bool = False
    cards: list = field(default_factory=list)


class TableRuntime:
    def __init__(self, code: str, settings: TableSettings) -> None:
        self.code = code
        self.settings = settings
        self.players: list[RuntimePlayer] = []
        self._host_user_id = 0
        self.button_seat: int | None = None
        self.hand_number = 0
        self.runner: HandRunner | None = None
        self.last_result: dict | None = None
        self.next_hand_at: float | None = None
        self.turn_deadline: float | None = None
        self.waiting_for_players = False
        self._stopped = False
        self._tasks: set[asyncio.Task] = set()
        self._notified_key: tuple | None = None

    # ── Загрузка и lifecycle ─────────────────────────────────

    async def load_from_db(self) -> None:
        async with SessionLocal() as session:
            table = await service.get_table(session, self.code)
            if table is None:
                raise TableError("стол не найден", status=404)
            self.settings = TableSettings.model_validate_json(table.settings_json)
            rows = (
                await session.execute(
                    select(TablePlayer, User)
                    .join(User, TablePlayer.user_id == User.tg_id)
                    .where(TablePlayer.table_code == self.code)
                    .order_by(TablePlayer.seat)
                )
            ).all()
            host_user_id = table.host_user_id
        self._host_user_id = host_user_id
        self.players = [
            RuntimePlayer(
                user_id=player.user_id,
                name=_display_name(user),
                photo_url=user.photo_url,
                seat=player.seat,
                stack=player.stack,
                total_bought=player.total_bought,
                left=player.status == "left",
            )
            for player, user in rows
        ]

    @property
    def host_user_id(self) -> int:
        return self._host_user_id

    def schedule_next_hand(self, delay: float) -> None:
        self.next_hand_at = time.time() + delay
        self._spawn(self._delayed_hand(delay))

    def stop(self) -> None:
        self._stopped = True
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _delayed_hand(self, delay: float) -> None:
        await asyncio.sleep(delay)
        self.next_hand_at = None
        async with self.lock():
            if self._stopped:
                return
            await self._start_hand_locked()

    def lock(self):
        return room_manager.get_room(self.code).lock

    # ── Игровые действия ─────────────────────────────────────

    async def act(self, user_id: int, action: str, amount: int | None = None) -> None:
        async with self.lock():
            runner = self.runner
            if runner is None:
                raise TableError("сейчас нет активной раздачи")
            if runner.to_act is None or runner.players[runner.to_act].user_id != user_id:
                raise TableError("сейчас не твой ход")
            try:
                runner.act(user_id, action, amount)
            except EngineError as exc:
                raise TableError(str(exc))
            await self._post_action_locked()

    async def stand_up(self, user_id: int) -> None:
        """Выход из-за стола в активной игре — только между раздачами."""
        async with self.lock():
            if self.runner is not None:
                raise TableError("дождись конца раздачи, чтобы встать")
            player = next((p for p in self.players if p.user_id == user_id), None)
            if player is None or player.left:
                raise TableError("ты не за столом")
            player.left = True
            async with SessionLocal() as session:
                await session.execute(
                    update(TablePlayer)
                    .where(
                        TablePlayer.table_code == self.code,
                        TablePlayer.user_id == user_id,
                    )
                    .values(status="left", left_at=utcnow())
                )
                await session.commit()
            await self._reassign_host_after_leave(user_id)
            await broadcast_state(self.code)

    async def _reassign_host_after_leave(self, leaving_user_id: int) -> None:
        """Хост вышел в активной игре: передаём роль или завершаем стол."""
        remaining = [
            p for p in self.players if not p.left and p.user_id != leaving_user_id
        ]
        remaining.sort(key=lambda p: p.seat)
        async with SessionLocal() as session:
            table = await service.get_table(session, self.code)
            if table is None:
                return
            if remaining:
                table.host_user_id = remaining[0].user_id
                self._host_user_id = remaining[0].user_id
            else:
                table.status = "finished"
                table.finished_at = utcnow()
                self._stopped = True
            await session.commit()

    # ── Внутреннее: ход раздачи ──────────────────────────────

    async def _start_hand_locked(self) -> None:
        eligible = [p for p in self.players if not p.left and p.stack > 0]
        if len(eligible) < 2:
            self.waiting_for_players = True
            await broadcast_state(self.code)
            return
        self.waiting_for_players = False
        self._advance_button(eligible)
        button_idx = next(
            i for i, p in enumerate(eligible) if p.seat == self.button_seat
        )
        hand_players = [
            HandPlayer(user_id=p.user_id, stack=p.stack) for p in eligible
        ]
        self.runner = HandRunner(
            hand_players,
            button=button_idx,
            small_blind=self.settings.small_blind,
            big_blind=self.settings.big_blind,
        )
        self.hand_number += 1
        self.last_result = None
        self._set_deadline()
        await self._notify_turn_locked()
        await broadcast_state(self.code)

    def _advance_button(self, eligible: list[RuntimePlayer]) -> None:
        seats = sorted(p.seat for p in eligible)
        if self.button_seat is None:
            self.button_seat = seats[0]
            return
        for seat in seats:
            if seat > self.button_seat:
                self.button_seat = seat
                return
        self.button_seat = seats[0]

    async def _post_action_locked(self) -> None:
        if self.runner is not None and self.runner.result is not None:
            await self._finish_hand_locked()
        else:
            self._set_deadline()
            await self._notify_turn_locked()
        await broadcast_state(self.code)

    async def _finish_hand_locked(self) -> None:
        result = self.runner.result
        assert result is not None
        hand_by_id = {p.user_id: p for p in self.runner.players}

        for player in self.players:
            hand_player = hand_by_id.get(player.user_id)
            if hand_player is not None:
                player.stack = hand_player.stack
        for winner in result["winners"]:
            for player in self.players:
                if player.user_id == winner["user_id"]:
                    player.stack += winner["amount"]

        self.last_result = result
        self.runner = None
        self.turn_deadline = None
        await self._persist_stacks()
        self.schedule_next_hand(NEXT_HAND_DELAY)

    async def _persist_stacks(self) -> None:
        async with SessionLocal() as session:
            for player in self.players:
                if player.left:
                    continue
                await session.execute(
                    update(TablePlayer)
                    .where(
                        TablePlayer.table_code == self.code,
                        TablePlayer.user_id == player.user_id,
                    )
                    .values(stack=player.stack)
                )
            await session.commit()

    # ── Таймеры и уведомления ────────────────────────────────

    def _set_deadline(self) -> None:
        if self.runner is None or self.runner.to_act is None:
            self.turn_deadline = None
            return
        if self.settings.action_timeout is None:
            self.turn_deadline = None
            return
        self.turn_deadline = time.time() + self.settings.action_timeout
        self._arm_timer()

    def _arm_timer(self) -> None:
        if self.turn_deadline is None:
            return
        delay = max(0.2, self.turn_deadline - time.time())
        self._spawn(self._timeout(delay))

    async def _timeout(self, delay: float) -> None:
        await asyncio.sleep(delay)
        async with self.lock():
            runner = self.runner
            if self._stopped or runner is None or runner.to_act is None:
                return
            user_id = runner.players[runner.to_act].user_id
            runner.auto_act(user_id)
            await self._post_action_locked()

    async def _notify_turn_locked(self) -> None:
        """Личное сообщение ботом, если игрок не в аппе."""
        runner = self.runner
        if runner is None or runner.to_act is None:
            return
        user_id = runner.players[runner.to_act].user_id
        room = room_manager.peek(self.code)
        if room is not None and room.has_user(user_id):
            return  # онлайн — увидит ход в аппе
        key = (self.hand_number, user_id, runner.street, runner.current_bet)
        if self._notified_key == key:
            return
        self._notified_key = key
        settings = get_settings()
        url = f"{settings.base_url.rstrip('/')}/#tbl_{self.code}"
        await sender.pm(
            user_id,
            f"🎰 Твой ход — раздача #{self.hand_number}, банк {runner.pot_total}.\n"
            f"Не успеешь за таймер — автоматически чек или фолд.",
            button_text="За стол",
            button_url=url,
        )

    # ── Снапшоты ─────────────────────────────────────────────

    async def build_snapshot(self, viewer_id: int) -> dict:
        async with SessionLocal() as session:
            table = await service.get_table(session, self.code)
            if table is None:
                raise TableError("стол не найден", status=404)
            base = await service.build_snapshot(session, table, viewer_id)

        base["players"] = [
            {
                "user_id": p.user_id,
                "name": p.name,
                "photo_url": p.photo_url,
                "seat": p.seat,
                "stack": p.stack,
                "status": "playing",
                "total_bought": p.total_bought,
                "is_host": p.user_id == self.host_user_id,
            }
            for p in self.players
            if not p.left
        ]
        base["hand"] = self.hand_view()

        runner = self.runner
        if runner is not None:
            hand_player = next(
                (p for p in runner.players if p.user_id == viewer_id), None
            )
            if hand_player is not None:
                base["you"]["cards"] = [c.code for c in hand_player.cards]
                if (
                    runner.to_act is not None
                    and runner.players[runner.to_act].user_id == viewer_id
                ):
                    base["you"]["legal_actions"] = runner.legal_actions()
        return base

    def hand_view(self) -> dict:
        view: dict = {
            "number": self.hand_number,
            "street": None,
            "board": [],
            "pot": 0,
            "current_bet": 0,
            "dealer_seat": self.button_seat,
            "players": [],
            "to_act": None,
            "deadline": None,
            "next_hand_at": self.next_hand_at,
            "waiting": self.waiting_for_players,
            "revealed": {},
            "last_result": self.last_result,
        }
        if self.runner is not None:
            public = self.runner.public_view()
            for key in ("street", "board", "pot", "current_bet", "players", "to_act", "revealed"):
                view[key] = public[key]
            view["deadline"] = self.turn_deadline
        return view


def _display_name(user: User) -> str:
    name = " ".join(p for p in (user.first_name, user.last_name) if p)
    return name or f"Игрок {user.tg_id}"


# ── Менеджер runtime'ов ──────────────────────────────────────

_runtimes: dict[str, TableRuntime] = {}


def get_runtime(code: str) -> TableRuntime | None:
    return _runtimes.get(code)


async def ensure_started(code: str) -> TableRuntime | None:
    """Создаёт runtime для активного стола (старт или восстановление)."""
    existing = _runtimes.get(code)
    if existing is not None:
        return existing
    async with SessionLocal() as session:
        table = await session.get(PokerTable, code)
        if table is None or table.status != "active":
            return None
    runtime = TableRuntime(code, TableSettings())
    _runtimes[code] = runtime  # занимает слот до await — защита от гонки
    try:
        await runtime.load_from_db()
    except Exception:
        _runtimes.pop(code, None)
        raise
    runtime.schedule_next_hand(FIRST_HAND_DELAY)
    return runtime


async def stop_runtime(code: str) -> None:
    runtime = _runtimes.pop(code, None)
    if runtime is not None:
        runtime.stop()


# ── Рассылка снапшотов ───────────────────────────────────────

async def broadcast_state(code: str) -> None:
    """Персональный снапшот каждому подключённому к столу."""
    room = room_manager.peek(code)
    if room is None or not room.connections:
        return
    runtime = get_runtime(code)
    if runtime is None:
        async with SessionLocal() as session:
            table = await service.get_table(session, code)
            if table is None:
                for ws in room.all_sockets():
                    try:
                        await ws.close()
                    except Exception:  # noqa: BLE001
                        pass
                room_manager.drop(code)
                return
            for user_id in list(room.connections):
                snapshot = await service.build_snapshot(session, table, user_id)
                for ws in list(room.connections[user_id]):
                    await _send(ws, {"type": "state", "state": snapshot})
        return
    for user_id in list(room.connections):
        try:
            snapshot = await runtime.build_snapshot(user_id)
        except TableError:
            continue
        for ws in list(room.connections[user_id]):
            await _send(ws, {"type": "state", "state": snapshot})


async def send_initial(ws, code: str, viewer_id: int) -> None:
    """Первый снапшот при подключении к сокету."""
    runtime = get_runtime(code)
    if runtime is not None:
        await _send(ws, {"type": "state", "state": await runtime.build_snapshot(viewer_id)})
        return
    async with SessionLocal() as session:
        table = await service.get_table(session, code)
        if table is None:
            await _send(ws, {"type": "error", "message": "стол не найден"})
            await ws.close()
            return
        snapshot = await service.build_snapshot(session, table, viewer_id)
    await _send(ws, {"type": "state", "state": snapshot})


async def _send(ws, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:  # noqa: BLE001 — мёртвый сокет уберёт ws-цикл
        pass
