"""Тесты расчёта итогов: переводы, формат денег, build_settlement, сводка."""

from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.orm import Base, TablePlayer
from app.tables import service, settlement
from app.tables.settings import TableSettings


class TestMinimalTransfers:
    def test_one_debtor_two_creditors(self) -> None:
        result = settlement.minimal_transfers({1: -30, 2: 20, 3: 10})
        assert result == [
            {"from_user_id": 1, "to_user_id": 2, "cents": 20},
            {"from_user_id": 1, "to_user_id": 3, "cents": 10},
        ]

    def test_two_debtors_one_creditor(self) -> None:
        result = settlement.minimal_transfers({1: -10, 2: -20, 3: 30})
        assert result == [
            {"from_user_id": 2, "to_user_id": 3, "cents": 20},
            {"from_user_id": 1, "to_user_id": 3, "cents": 10},
        ]

    def test_zero_and_empty(self) -> None:
        assert settlement.minimal_transfers({}) == []
        assert settlement.minimal_transfers({1: 0, 2: 0}) == []


class TestFormatCents:
    def test_formats(self) -> None:
        assert settlement.format_cents(0) == "0 ₽"
        assert settlement.format_cents(1100) == "11 ₽"
        assert settlement.format_cents(1150) == "11,5 ₽"
        assert settlement.format_cents(105) == "1,05 ₽"
        assert settlement.format_cents(-1500) == "-15 ₽"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def _finished_table(session, chip_value: float):
    for uid, name in ((1, "Аня"), (2, "Боря")):
        await service.upsert_user(session, user_id=uid, first_name=name)
    table = await service.create_table(
        session, host_id=1, name="Тест", settings=TableSettings(chip_value=chip_value)
    )
    await service.sit(session, table, 2, seat=1)
    await service.start_game(session, table, 1)
    # Аня удвоилась, Боря проигрался.
    await session.execute(
        update(TablePlayer)
        .where(TablePlayer.table_code == table.code, TablePlayer.user_id == 1)
        .values(stack=1300)
    )
    await session.execute(
        update(TablePlayer)
        .where(TablePlayer.table_code == table.code, TablePlayer.user_id == 2)
        .values(stack=700)
    )
    await service.end_game(session, table, 1)
    await session.commit()
    return table


async def test_build_settlement_with_money(session) -> None:
    table = await _finished_table(session, chip_value=0.5)
    data = await settlement.build_settlement(session, table)
    assert data["hands_played"] == 0
    nets = {p["user_id"]: p["net_chips"] for p in data["players"]}
    assert nets == {1: 300, 2: -300}
    cents = {p["user_id"]: p["net_cents"] for p in data["players"]}
    assert cents == {1: 15000, 2: -15000}
    assert data["transfers"] == [
        {"from_user_id": 2, "to_user_id": 1, "cents": 15000}
    ]
    names = {p["user_id"]: p["name"] for p in data["players"]}
    assert names[1] == "Аня" and names[2] == "Боря"


async def test_build_settlement_without_money(session) -> None:
    table = await _finished_table(session, chip_value=0)
    data = await settlement.build_settlement(session, table)
    assert all(p["net_cents"] == 0 for p in data["players"])
    assert data["transfers"] == []


async def test_notify_without_bot_is_noop(session) -> None:
    table = await _finished_table(session, chip_value=1)
    # Бот не зарегистрирован — сводка не должна падать.
    await settlement.notify_table_finished(session, table)
