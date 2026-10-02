"""Тесты сервиса лобби (app.tables.service) на временной SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.orm import Base, User
from app.tables import service
from app.tables.service import TableError
from app.tables.settings import TableSettings


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def add_user(session, user_id: int, name: str = "Игрок") -> None:
    await service.upsert_user(session, user_id=user_id, first_name=name)


async def new_table(session, host_id: int = 1):
    await add_user(session, host_id)
    return await service.create_table(
        session, host_id=host_id, name="", settings=TableSettings()
    )


async def test_upsert_user_updates_profile(session) -> None:
    await service.upsert_user(session, user_id=7, first_name="Старое")
    await service.upsert_user(session, user_id=7, first_name="Новое", username="nov")
    user = await session.get(User, 7)
    assert user is not None
    assert user.first_name == "Новое"
    assert user.username == "nov"


async def test_create_table_seats_host(session) -> None:
    table = await new_table(session, host_id=1)
    assert table.status == "lobby"
    assert table.name == service.DEFAULT_TABLE_NAME

    snap = await service.build_snapshot(session, table, viewer_id=1)
    assert len(snap["players"]) == 1
    host = snap["players"][0]
    assert host["user_id"] == 1
    assert host["seat"] == 0
    assert host["stack"] == 1000
    assert host["total_bought"] == 1000
    assert host["is_host"] is True
    assert snap["you"] == {"seat": 0, "is_host": True}


async def test_snapshot_for_viewer_outside(session) -> None:
    table = await new_table(session, host_id=1)
    snap = await service.build_snapshot(session, table, viewer_id=99)
    assert snap["you"] == {"seat": None, "is_host": False}
    assert snap["seats_total"] == snap["settings"]["max_seats"] == 6
    assert table.code in snap["invite_link"]


async def test_sit_and_occupied_seat(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=2)
    await add_user(session, 3)
    with pytest.raises(TableError, match="место занято"):
        await service.sit(session, table, 3, seat=2)


async def test_sit_bad_seat_rejected(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    with pytest.raises(TableError):
        await service.sit(session, table, 2, seat=9)
    with pytest.raises(TableError):
        await service.sit(session, table, 2, seat=-1)


async def test_seated_player_cannot_take_second_seat(session) -> None:
    table = await new_table(session, 1)  # хост уже сидит на месте 0
    with pytest.raises(TableError, match="встань"):
        await service.sit(session, table, 1, seat=4)


async def test_rejoin_resets_seat_and_stack(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)
    await service.stand_up(session, table, 2)
    await service.sit(session, table, 2, seat=4)

    snap = await service.build_snapshot(session, table, viewer_id=2)
    assert snap["you"]["seat"] == 4
    p2 = next(p for p in snap["players"] if p["user_id"] == 2)
    assert p2["seat"] == 4
    assert p2["stack"] == 1000


async def test_stand_up_transfers_host_then_finishes(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)
    await service.stand_up(session, table, 1)
    assert table.host_user_id == 2

    await service.stand_up(session, table, 2)
    assert table.status == "finished"


async def test_start_game_rules(session) -> None:
    table = await new_table(session, 1)
    with pytest.raises(TableError, match="минимум"):
        await service.start_game(session, table, 1)

    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)
    with pytest.raises(TableError, match="хост"):
        await service.start_game(session, table, 2)

    await service.start_game(session, table, 1)
    assert table.status == "active"
    with pytest.raises(TableError):
        await service.start_game(session, table, 1)


async def test_sit_when_active_rejected(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)
    await service.start_game(session, table, 1)
    await add_user(session, 3)
    with pytest.raises(TableError, match="между раздачами"):
        await service.sit(session, table, 3, seat=2)


async def test_kick_and_transfer_host(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)

    with pytest.raises(TableError):
        await service.kick(session, table, 2, 1)

    await service.kick(session, table, 1, 2)
    snap = await service.build_snapshot(session, table, viewer_id=1)
    assert all(p["user_id"] != 2 for p in snap["players"])

    await add_user(session, 3)
    await service.sit(session, table, 3, seat=2)
    await service.transfer_host(session, table, 1, 3)
    assert table.host_user_id == 3


async def test_list_for_user(session) -> None:
    table = await new_table(session, 1)
    await add_user(session, 2)
    await service.sit(session, table, 2, seat=1)

    rows = await service.list_for_user(session, 2)
    assert len(rows) == 1
    assert rows[0]["code"] == table.code
    assert rows[0]["my_seat"] == 1
    assert rows[0]["players_count"] == 2
    assert rows[0]["is_host"] is False

    assert await service.list_for_user(session, 42) == []
