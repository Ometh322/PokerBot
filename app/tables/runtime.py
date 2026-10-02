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
import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select, update

from app.bot import sender
from app.config import get_settings
from app.db import SessionLocal
from app.game.cards import card as card_from_code
from app.game.evaluator import best_hand, hand_name, preflop_name
from app.game.hand import EngineError, HandPlayer, HandRunner
from app.models.orm import (
    Hand,
    HandPlayerRow,
    LedgerEntry,
    PokerTable,
    TablePlayer,
    User,
    utcnow,
)
from app.tables import service
from app.tables import settlement
from app.tables.rooms import room_manager
from app.tables.service import TableError
from app.tables.settings import TableSettings

logger = logging.getLogger(__name__)

# Паузы: после старта и между раздачами — увидеть результат, отдышаться.
FIRST_HAND_DELAY = 3.0
NEXT_HAND_DELAY = 7.0
# Режиссура вскрытия: пауза между картами борда/игроков и до результата.
SHOWDOWN_STEP = 1.4
SHOWDOWN_RESULT_DELAY = 1.0


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
        self._hand_start: dict[int, int] = {}
        # Режиссируемое вскрытие: прогресс открытия карт до результата.
        self._showdown: dict | None = None

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
        """Выход из-за стола в активной игре — между раздачами; стек = кэшаут."""
        async with self.lock():
            if self.runner is not None:
                raise TableError("дождись конца раздачи, чтобы встать")
            player = next((p for p in self.players if p.user_id == user_id), None)
            if player is None or player.left:
                raise TableError("ты не за столом")
            cashout = player.stack
            player.left = True
            async with SessionLocal() as session:
                if cashout > 0:
                    session.add(
                        LedgerEntry(
                            table_code=self.code,
                            user_id=user_id,
                            kind="cashout",
                            chips=cashout,
                        )
                    )
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

    async def rebuy(self, user_id: int) -> None:
        """Ребай стартовым стеком по режиму настроек, между раздачами."""
        async with self.lock():
            if self.runner is not None:
                raise TableError("ребай — только между раздачами")
            player = next((p for p in self.players if p.user_id == user_id), None)
            if player is None or player.left:
                raise TableError("ты не за столом")
            mode = self.settings.rebuy_mode
            if mode == "off":
                raise TableError("ребай выключен настройками стола")
            if mode == "busted" and player.stack > 0:
                raise TableError("ребай доступен при стеке 0")

            amount = self.settings.starting_stack
            player.stack += amount
            player.total_bought += amount
            async with SessionLocal() as session:
                await session.execute(
                    update(TablePlayer)
                    .where(
                        TablePlayer.table_code == self.code,
                        TablePlayer.user_id == user_id,
                    )
                    .values(stack=player.stack, total_bought=player.total_bought)
                )
                session.add(
                    LedgerEntry(
                        table_code=self.code,
                        user_id=user_id,
                        kind="rebuy",
                        chips=amount,
                    )
                )
                await session.commit()
            if self.waiting_for_players:
                self.waiting_for_players = False
                self.schedule_next_hand(1.0)
            await broadcast_state(self.code)

    async def sit(self, user_id: int, seat: int) -> None:
        """Поздний вход в активную игру: стартовый стек, между раздачами."""
        async with self.lock():
            if self.runner is not None:
                raise TableError("дождись конца раздачи, чтобы сесть")
            if not 0 <= seat < self.settings.max_seats:
                raise TableError("нет такого места")
            if any(not p.left and p.seat == seat for p in self.players):
                raise TableError("место занято")
            mine = next((p for p in self.players if p.user_id == user_id), None)
            if mine is not None and not mine.left:
                raise TableError("ты уже за столом")

            buyin = self.settings.starting_stack
            async with SessionLocal() as session:
                user = await session.get(User, user_id)
                if user is None:
                    user = User(tg_id=user_id, first_name=f"Игрок {user_id}")
                    session.add(user)
                    await session.flush()
                if mine is not None:  # вернулся после выхода
                    mine.left = False
                    mine.seat = seat
                    mine.stack = buyin
                    mine.total_bought += buyin
                else:
                    self.players.append(
                        RuntimePlayer(
                            user_id=user_id,
                            name=service.display_name(user),
                            photo_url=user.photo_url,
                            seat=seat,
                            stack=buyin,
                            total_bought=buyin,
                        )
                    )
                    self.players.sort(key=lambda p: p.seat)
                row = await session.get(TablePlayer, (self.code, user_id))
                if row is None:
                    session.add(
                        TablePlayer(
                            table_code=self.code,
                            user_id=user_id,
                            seat=seat,
                            stack=buyin,
                            total_bought=buyin,
                        )
                    )
                else:
                    row.seat = seat
                    row.status = "waiting"
                    row.left_at = None
                    row.stack = buyin
                    row.total_bought += buyin
                session.add(
                    LedgerEntry(
                        table_code=self.code, user_id=user_id, kind="buyin", chips=buyin
                    )
                )
                await session.commit()
            if self.waiting_for_players:
                self.waiting_for_players = False
                self.schedule_next_hand(1.0)
            await broadcast_state(self.code)

    async def _reassign_host_after_leave(self, leaving_user_id: int) -> None:
        """Хост вышел в активной игре: передаём роль или завершаем стол."""
        remaining = [
            p for p in self.players if not p.left and p.user_id != leaving_user_id
        ]
        remaining.sort(key=lambda p: p.seat)
        finished_now = False
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
                finished_now = True
            await session.commit()
        if finished_now:
            # Стол опустел — тоже шлём сводку по итогам сессии.
            async with SessionLocal() as session:
                fresh = await service.get_table(session, self.code)
                if fresh is not None:
                    await settlement.notify_table_finished(session, fresh)

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
        self._showdown = None
        self._hand_start = {p.user_id: p.stack for p in eligible}
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
            await self._begin_showdown_locked()
        else:
            self._set_deadline()
            await self._notify_turn_locked()
        await broadcast_state(self.code)

    async def _begin_showdown_locked(self) -> None:
        """Финал раздачи: вскрытие поэтапно или мгновенный результат без показа."""
        runner = self.runner
        result = runner.result
        assert result is not None

        if result["type"] == "uncontested" or not runner.revealed:
            await self._apply_hand_result_locked()
            self.schedule_next_hand(NEXT_HAND_DELAY)
            return

        public = runner.public_view()
        n = len(runner.players)
        # Вскрываем по местам, начиная слева от кнопки.
        order = sorted(
            runner.revealed.keys(),
            key=lambda uid: next(
                (i - runner.button) % n
                for i, p in enumerate(runner.players)
                if p.user_id == uid
            ),
        )
        self._showdown = {
            "board": [c.code for c in runner.board],
            "visible_board": public["board_visible"],
            "pot": public["pot"],
            "players": public["players"],
            "cards": {
                uid: [c.code for c in cards] for uid, cards in runner.revealed.items()
            },
            # Карты всех участников — для личных снапшотов (свои карты видны всегда).
            "all_cards": {
                p.user_id: [c.code for c in p.cards] for p in runner.players
            },
            "revealed": [],
            "result": result,
            "result_visible": False,
        }
        self._spawn(self._showdown_timeline(order))

    async def _showdown_timeline(self, reveal_order: list[int]) -> None:
        """Добираем скрытый борд, вскрываем игроков по одному, затем результат."""
        sd = self._showdown
        while sd["visible_board"] < len(sd["board"]):
            await asyncio.sleep(SHOWDOWN_STEP)
            async with self.lock():
                if self._showdown is not sd or self._stopped:
                    return
                sd["visible_board"] += 1
                await broadcast_state(self.code)

        for user_id in reveal_order:
            await asyncio.sleep(SHOWDOWN_STEP)
            async with self.lock():
                if self._showdown is not sd or self._stopped:
                    return
                sd["revealed"].append(user_id)
                await broadcast_state(self.code)

        await asyncio.sleep(SHOWDOWN_RESULT_DELAY)
        async with self.lock():
            if self._showdown is not sd or self._stopped:
                return
            await self._apply_hand_result_locked()
            sd["result_visible"] = True
            # В замороженный вид — уже обновлённые стеки.
            stacks = {p.user_id: p.stack for p in self.players}
            for player in sd["players"]:
                player["stack"] = stacks.get(player["user_id"], player["stack"])
            await broadcast_state(self.code)

        await asyncio.sleep(0.5)
        async with self.lock():
            if self._showdown is not sd or self._stopped:
                return
            self.schedule_next_hand(NEXT_HAND_DELAY)

    async def _apply_hand_result_locked(self) -> None:
        """Применяет результат раздачи: стеки, история, персист в БД."""
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

        await self._record_hand(result)
        self.last_result = result
        self.turn_deadline = None
        await self._persist_stacks()
        # Раздача сыграна: открываем окно для позднего входа/ребая/выхода,
        # а показ вскрытия живёт в self._showdown до следующей раздачи.
        self.runner = None

    async def _record_hand(self, result: dict) -> None:
        """История рук: борд, банк, победители и вклад каждого игрока.

        Карты хранятся у всех, но наружу (REST) отдаются только вскрытые.
        """
        runner = self.runner
        assert runner is not None
        seat_by_id = {p.user_id: p.seat for p in self.players}
        # Стеки уже финализированы вызывающим кодом (выигрыши применены).
        end_stack = {p.user_id: p.stack for p in self.players}
        async with SessionLocal() as session:
            hand_row = Hand(
                table_code=self.code,
                number=self.hand_number,
                dealer_seat=self.button_seat,
                board_json=json.dumps(result["board"]),
                pot_total=result["pot_total"],
                result_json=json.dumps(result["winners"]),
            )
            session.add(hand_row)
            await session.flush()
            for hp in runner.players:
                session.add(
                    HandPlayerRow(
                        hand_id=hand_row.id,
                        user_id=hp.user_id,
                        seat=seat_by_id.get(hp.user_id),
                        hole_cards_json=json.dumps([c.code for c in hp.cards]),
                        start_stack=self._hand_start.get(hp.user_id, 0),
                        end_stack=end_stack.get(hp.user_id, hp.stack),
                        contributed=hp.total,
                        folded=hp.folded,
                        showed=hp.user_id in runner.revealed,
                    )
                )
            await session.commit()

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
        url = f"{settings.base_url.rstrip('/')}/?table={self.code}"
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

        if self._showdown is not None:
            # Идёт вскрытие: свои карты и подсказка — по видимому борду.
            sd = self._showdown
            mine = sd["all_cards"].get(viewer_id)
            if mine is not None:
                base["you"]["cards"] = mine
                combined = [card_from_code(c) for c in mine] + [
                    card_from_code(c) for c in sd["board"][: sd["visible_board"]]
                ]
                if len(combined) >= 5:
                    base["you"]["hand_hint"] = hand_name(best_hand(combined)[0])
                else:
                    base["you"]["hand_hint"] = preflop_name(combined[:2])
        else:
            runner = self.runner
            if runner is not None:
                hand_player = next(
                    (p for p in runner.players if p.user_id == viewer_id), None
                )
                if hand_player is not None:
                    base["you"]["cards"] = [c.code for c in hand_player.cards]
                    combined = hand_player.cards + runner.board
                    if len(combined) >= 5:
                        base["you"]["hand_hint"] = hand_name(best_hand(combined)[0])
                    else:
                        base["you"]["hand_hint"] = preflop_name(hand_player.cards)
                    if (
                        runner.to_act is not None
                        and runner.players[runner.to_act].user_id == viewer_id
                    ):
                        base["you"]["legal_actions"] = runner.legal_actions()

        # Доступен ли ребай прямо сейчас (между раздачами).
        me = next(
            (p for p in self.players if p.user_id == viewer_id and not p.left), None
        )
        rebuy_available = False
        if me is not None and self.runner is None:
            mode = self.settings.rebuy_mode
            rebuy_available = mode == "anytime" or (mode == "busted" and me.stack == 0)
        base["you"]["rebuy_available"] = rebuy_available
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
        if self._showdown is not None:
            sd = self._showdown
            view.update(
                {
                    "street": "showdown",
                    "board": sd["board"][: sd["visible_board"]],
                    "pot": sd["pot"],
                    "players": sd["players"],
                    "revealed": {
                        str(uid): sd["cards"][uid] for uid in sd["revealed"]
                    },
                    "last_result": sd["result"] if sd["result_visible"] else None,
                }
            )
            return view
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
