"""Расчёт итогов сессии: ledger → чистые итоги и минимальные переводы.

Деньги считаются в копейках (целые), чтобы не ловить погрешности float.
Переводы сворачиваются жадно: наибольший должник платит наибольшему
кредитору — не больше n−1 переводов.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.bot import sender
from app.models.orm import Hand, User
from app.tables import service
from app.tables.settings import TableSettings


def minimal_transfers(net_cents: dict[int, int]) -> list[dict[str, int]]:
    """Свёртка долгов: [{from_user_id, to_user_id, cents}], сумма = нулю."""
    debtors = sorted(((amount, uid) for uid, amount in net_cents.items() if amount < 0))
    creditors = sorted(
        ((amount, uid) for uid, amount in net_cents.items() if amount > 0),
        reverse=True,
    )
    transfers: list[dict[str, int]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debt, debtor = debtors[i]
        credit, creditor = creditors[j]
        pay = min(-debt, credit)
        if pay > 0:
            transfers.append(
                {"from_user_id": debtor, "to_user_id": creditor, "cents": pay}
            )
        debtors[i] = (debt + pay, debtor)
        creditors[j] = (credit - pay, creditor)
        if debtors[i][0] == 0:
            i += 1
        if creditors[j][0] == 0:
            j += 1
    return transfers


def format_cents(cents: int) -> str:
    """1150 → «11,5 ₽», 1100 → «11 ₽», -1050 → «-10,5 ₽»."""
    if cents % 100 == 0:
        return f"{cents // 100} ₽"
    return f"{cents / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " ₽"


def _signed_cents(cents: int) -> str:
    return f"+{format_cents(cents)}" if cents > 0 else format_cents(cents)


def _duration_human(created_at, finished_at) -> str:
    if created_at is None or finished_at is None:
        return ""
    total = int((finished_at - created_at).total_seconds())
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours} ч {minutes} мин"
    if hours:
        return f"{hours} ч"
    return f"{minutes} мин"


async def build_settlement(session, table) -> dict[str, Any]:
    """Полный расчёт по ledger: итоги игроков, переводы, метаданные."""
    summary = await service.ledger_summary(session, table.code)
    settings = TableSettings.model_validate_json(table.settings_json)

    uids = [row["user_id"] for row in summary]
    names: dict[int, str] = {}
    if uids:
        users = (
            await session.execute(select(User).where(User.tg_id.in_(uids)))
        ).scalars().all()
        names = {u.tg_id: service.display_name(u) for u in users}

    hands_played = (
        await session.scalar(
            select(func.count()).select_from(Hand).where(Hand.table_code == table.code)
        )
        or 0
    )

    players: list[dict[str, Any]] = []
    net_cents: dict[int, int] = {}
    for row in summary:
        net_chips = row["net"]
        cents = round(net_chips * settings.chip_value * 100) if settings.chip_value else 0
        net_cents[row["user_id"]] = cents
        players.append(
            {
                "user_id": row["user_id"],
                "name": names.get(row["user_id"], f"Игрок {row['user_id']}"),
                "bought": row["bought"],
                "cashed_out": row["cashed_out"],
                "net_chips": net_chips,
                "net_cents": cents,
            }
        )

    transfers = minimal_transfers(net_cents) if settings.chip_value else []
    return {
        "table": {
            "code": table.code,
            "name": table.name,
            "chip_value": settings.chip_value,
            "created_at": table.created_at.isoformat() if table.created_at else None,
            "finished_at": table.finished_at.isoformat() if table.finished_at else None,
            "duration": _duration_human(table.created_at, table.finished_at),
        },
        "hands_played": hands_played,
        "players": players,
        "transfers": transfers,
    }


async def notify_table_finished(session, table) -> None:
    """Сводка сессии каждому участнику личным сообщением бота."""
    settlement = await build_settlement(session, table)
    if not settlement["players"]:
        return

    chip_value = settlement["table"]["chip_value"]
    meta = f"раздач: {settlement['hands_played']}"
    if settlement["table"]["duration"]:
        meta += f", время: {settlement['table']['duration']}"

    lines = [f"🏁 «{table.name}» — игра завершена", meta, ""]
    if chip_value:
        lines.append(f"Итоги (фишка = {format_cents(round(chip_value * 100))}):")
    else:
        lines.append("Итоги (в фишках):")
    for player in sorted(settlement["players"], key=lambda p: -p["net_chips"]):
        if chip_value:
            lines.append(f"{player['name']}: {_signed_cents(player['net_cents'])}")
        else:
            net = player["net_chips"]
            lines.append(f"{player['name']}: {'+' if net > 0 else ''}{net}")

    if settlement["transfers"]:
        by_id = {p["user_id"]: p["name"] for p in settlement["players"]}
        lines.append("")
        lines.append("Расчёты:")
        for transfer in settlement["transfers"]:
            lines.append(
                f"{by_id[transfer['from_user_id']]} → "
                f"{by_id[transfer['to_user_id']]} "
                f"{format_cents(transfer['cents'])}"
            )

    text = "\n".join(lines)
    for player in settlement["players"]:
        await sender.pm(player["user_id"], text)
