"""Бизнес-логика лобби: создание столов, посадка, роли хоста, снапшоты.

Функции мутируют переданную сессию; commit делает вызывающая сторона.
Ошибки бизнеса — TableError(message, http_status).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import info as bot_info
from app.config import get_settings
from app.models.orm import LedgerEntry, PokerTable, TablePlayer, User, utcnow
from app.tables.settings import TableSettings

# Алфавит без похожих символов (0/O, 1/l/I).
CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
CODE_LENGTH = 5
DEFAULT_TABLE_NAME = "Покер с друзьями"


class TableError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def norm_code(code: str) -> str:
    """«tbl_ab12c» и «ab12c» → «ab12c»."""
    return (code or "").strip().removeprefix("tbl_")


def invite_link(code: str) -> str:
    username = bot_info.get_bot_username()
    if username:
        return f"https://t.me/{username}?startapp=tbl_{code}"
    return f"{get_settings().base_url.rstrip('/')}/#tbl_{code}"


def display_name(user: User) -> str:
    name = " ".join(p for p in (user.first_name, user.last_name) if p)
    return name or f"Игрок {user.tg_id}"


async def upsert_user(
    session: AsyncSession,
    *,
    user_id: int,
    first_name: str = "",
    last_name: str | None = None,
    username: str | None = None,
    photo_url: str | None = None,
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        session.add(
            User(
                tg_id=user_id,
                first_name=first_name[:64],
                last_name=last_name,
                username=username,
                photo_url=photo_url,
            )
        )
        return
    if first_name:
        user.first_name = first_name[:64]
    if last_name is not None:
        user.last_name = last_name
    if username is not None:
        user.username = username
    if photo_url is not None:
        user.photo_url = photo_url
    user.last_seen_at = utcnow()


async def _generate_code(session: AsyncSession) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if await session.get(PokerTable, code) is None:
            return code


async def create_table(
    session: AsyncSession, *, host_id: int, name: str, settings: TableSettings
) -> PokerTable:
    clean_name = " ".join((name or "").split())[:32] or DEFAULT_TABLE_NAME
    code = await _generate_code(session)
    table = PokerTable(
        code=code,
        name=clean_name,
        host_user_id=host_id,
        settings_json=settings.model_dump_json(),
    )
    session.add(table)
    await session.flush()
    # Хост сразу садится на нулевое место со стартовым стеком (buy-in в ledger с M4).
    session.add(
        TablePlayer(
            table_code=code,
            user_id=host_id,
            seat=0,
            stack=settings.starting_stack,
            total_bought=settings.starting_stack,
        )
    )
    await session.flush()
    return table


async def get_table(session: AsyncSession, code: str) -> PokerTable | None:
    code = norm_code(code)
    if not code:
        return None
    return await session.get(PokerTable, code)


async def _seated_players(session: AsyncSession, table_code: str) -> list[TablePlayer]:
    result = await session.execute(
        select(TablePlayer)
        .where(TablePlayer.table_code == table_code, TablePlayer.status != "left")
        .order_by(TablePlayer.joined_at, TablePlayer.user_id)
    )
    return list(result.scalars().all())


async def sit(session: AsyncSession, table: PokerTable, user_id: int, seat: int) -> None:
    if table.status == "finished":
        raise TableError("стол уже завершён")
    if table.status == "active":
        # Активной игрой владеет runtime: поздний вход идёт через него.
        raise TableError("стол уже играет — сесть можно между раздачами")
    settings = TableSettings.model_validate_json(table.settings_json)
    if not 0 <= seat < settings.max_seats:
        raise TableError("нет такого места")

    player = await session.get(TablePlayer, (table.code, user_id))
    if player is not None and player.status != "left":
        if player.seat == seat:
            return
        raise TableError("сначала встань с текущего места")

    taken = await session.scalar(
        select(TablePlayer).where(
            TablePlayer.table_code == table.code,
            TablePlayer.seat == seat,
            TablePlayer.status != "left",
        )
    )
    if taken is not None:
        raise TableError("место занято")

    if player is None:
        session.add(
            TablePlayer(
                table_code=table.code,
                user_id=user_id,
                seat=seat,
                stack=settings.starting_stack,
                total_bought=settings.starting_stack,
            )
        )
    else:
        # Возврат после выхода: свежий бай-ин стартовым стеком.
        player.seat = seat
        player.status = "waiting"
        player.left_at = None
        player.stack = settings.starting_stack
        player.total_bought = settings.starting_stack
    await session.flush()


async def stand_up(session: AsyncSession, table: PokerTable, user_id: int) -> None:
    if table.status == "finished":
        raise TableError("стол уже завершён")
    player = await session.get(TablePlayer, (table.code, user_id))
    if player is None or player.status == "left":
        raise TableError("ты не за столом")
    player.status = "left"
    player.left_at = utcnow()
    if table.host_user_id == user_id:
        remaining = await _seated_players(session, table.code)
        if remaining:
            table.host_user_id = remaining[0].user_id
        else:
            table.status = "finished"
            table.finished_at = utcnow()
    await session.flush()


async def kick(
    session: AsyncSession, table: PokerTable, actor_id: int, target_id: int
) -> None:
    if table.status != "lobby":
        raise TableError("исключать игроков можно только в лобби")
    if table.host_user_id != actor_id:
        raise TableError("исключать может только хост", status=403)
    if target_id == actor_id:
        raise TableError("самого себя исключить нельзя — просто встань")
    target = await session.get(TablePlayer, (table.code, target_id))
    if target is None or target.status == "left":
        raise TableError("игрок не за столом", status=404)
    target.status = "left"
    target.left_at = utcnow()
    await session.flush()


async def transfer_host(
    session: AsyncSession, table: PokerTable, actor_id: int, target_id: int
) -> None:
    if table.host_user_id != actor_id:
        raise TableError("передать роль может только хост", status=403)
    target = await session.get(TablePlayer, (table.code, target_id))
    if target is None or target.status == "left":
        raise TableError("игрок не за столом", status=404)
    table.host_user_id = target_id
    await session.flush()


async def start_game(session: AsyncSession, table: PokerTable, actor_id: int) -> None:
    if table.status != "lobby":
        raise TableError("игра уже начата или завершена")
    if table.host_user_id != actor_id:
        raise TableError("начать игру может только хост", status=403)
    seated = await _seated_players(session, table.code)
    if len(seated) < 2:
        raise TableError("нужно минимум 2 игрока за столом")
    table.status = "active"
    for player in seated:
        # Начальный бай-ин каждого участника — в ledger.
        session.add(
            LedgerEntry(
                table_code=table.code,
                user_id=player.user_id,
                kind="buyin",
                chips=player.stack,
            )
        )
    await session.flush()


async def end_game(session: AsyncSession, table: PokerTable, actor_id: int) -> None:
    if table.status == "finished":
        raise TableError("стол уже завершён")
    if table.host_user_id != actor_id:
        raise TableError("завершить игру может только хост", status=403)
    table.status = "finished"
    table.finished_at = utcnow()
    # Финальные кэшауты оставшихся: их стеки покидают игру целиком.
    # Берём стеки из БД (после последней завершённой раздачи) — если хост
    # завершил игру посреди раздачи, её ставки откатываются к её началу.
    for player in await _seated_players(session, table.code):
        if player.stack > 0:
            session.add(
                LedgerEntry(
                    table_code=table.code,
                    user_id=player.user_id,
                    kind="cashout",
                    chips=player.stack,
                )
            )
    await session.flush()


async def ledger_summary(session: AsyncSession, table_code: str) -> list[dict[str, Any]]:
    """Сводка по столу: сколько куплено/выведено и чистый итог в фишках."""
    rows = (
        await session.execute(
            select(LedgerEntry)
            .where(LedgerEntry.table_code == table_code)
            .order_by(LedgerEntry.id)
        )
    ).scalars().all()
    summary: dict[int, dict[str, int]] = {}
    for entry in rows:
        player = summary.setdefault(
            entry.user_id, {"bought": 0, "cashed_out": 0}
        )
        if entry.kind == "cashout":
            player["cashed_out"] += entry.chips
        else:  # buyin | rebuy
            player["bought"] += entry.chips
    return [
        {"user_id": uid, "bought": data["bought"], "cashed_out": data["cashed_out"],
         "net": data["cashed_out"] - data["bought"]}
        for uid, data in sorted(summary.items())
    ]


async def build_snapshot(
    session: AsyncSession, table: PokerTable, viewer_id: int
) -> dict[str, Any]:
    settings = json.loads(table.settings_json)
    rows = (
        await session.execute(
            select(TablePlayer, User)
            .join(User, TablePlayer.user_id == User.tg_id)
            .where(TablePlayer.table_code == table.code, TablePlayer.status != "left")
            .order_by(TablePlayer.seat)
        )
    ).all()
    players = [
        {
            "user_id": player.user_id,
            "name": display_name(user),
            "photo_url": user.photo_url,
            "seat": player.seat,
            "stack": player.stack,
            "status": player.status,
            "total_bought": player.total_bought,
            "is_host": player.user_id == table.host_user_id,
        }
        for player, user in rows
    ]
    me = next((p for p in players if p["user_id"] == viewer_id), None)
    return {
        "code": table.code,
        "name": table.name,
        "status": table.status,
        "settings": settings,
        "host_user_id": table.host_user_id,
        "invite_link": invite_link(table.code),
        "seats_total": settings["max_seats"],
        "created_at": table.created_at.isoformat() if table.created_at else None,
        "players": players,
        "you": {
            "seat": me["seat"] if me else None,
            "is_host": table.host_user_id == viewer_id,
        },
    }


async def list_for_user(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(PokerTable, TablePlayer)
            .join(
                TablePlayer,
                (TablePlayer.table_code == PokerTable.code)
                & (TablePlayer.user_id == user_id),
            )
            .where(TablePlayer.status != "left", PokerTable.status != "finished")
            .order_by(PokerTable.created_at.desc())
        )
    ).all()
    if not rows:
        return []
    counts_rows = (
        await session.execute(
            select(TablePlayer.table_code, func.count())
            .where(
                TablePlayer.status != "left",
                TablePlayer.table_code.in_([t.code for t, _ in rows]),
            )
            .group_by(TablePlayer.table_code)
        )
    ).all()
    counts = dict(counts_rows)
    return [
        {
            "code": table.code,
            "name": table.name,
            "status": table.status,
            "players_count": counts.get(table.code, 0),
            "max_seats": json.loads(table.settings_json)["max_seats"],
            "my_seat": player.seat,
            "is_host": table.host_user_id == user_id,
        }
        for table, player in rows
    ]
