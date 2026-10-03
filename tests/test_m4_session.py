"""Тесты сессии кэш-игры (M4): ребай, поздний вход, кэшауты, ledger, история.

Runtime работает со «своим» SessionLocal — в тестах подменяем его на фабрику
с временной файловой базой (NullPool, отдельные подключения).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.game.hand import HandPlayer, HandRunner
from app.models.orm import Base, Hand, HandPlayerRow, LedgerEntry
from app.tables import runtime as runtime_module
from app.tables import service
from app.tables.runtime import TableRuntime
from app.tables.service import TableError
from app.tables.settings import TableSettings


@pytest.fixture
async def env(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/m4.db"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(runtime_module, "SessionLocal", maker)

    async with maker() as session:
        for uid, name in ((1, "Аня"), (2, "Боря")):
            await service.upsert_user(session, user_id=uid, first_name=name)
        table = await service.create_table(
            session, host_id=1, name="", settings=TableSettings()
        )
        await service.sit(session, table, 2, seat=1)
        await service.start_game(session, table, 1)
        await session.commit()
        code = table.code

    rt = TableRuntime(code, TableSettings())
    await rt.load_from_db()
    yield rt, maker
    rt.stop()
    await engine.dispose()


async def ledger_rows(maker, code: str) -> list[LedgerEntry]:
    async with maker() as session:
        rows = (
            await session.execute(
                select(LedgerEntry).where(LedgerEntry.table_code == code)
            )
        ).scalars().all()
    return list(rows)


class TestRebuy:
    async def test_busted_mode(self, env) -> None:
        rt, maker = env
        with pytest.raises(TableError, match="при стеке 0"):
            await rt.rebuy(1)  # стек 1000 — рано
        rt.players[0].stack = 0
        await rt.rebuy(1)
        assert rt.players[0].stack == 1000
        assert rt.players[0].total_bought == 2000
        entries = [e for e in await ledger_rows(maker, rt.code) if e.kind == "rebuy"]
        assert len(entries) == 1 and entries[0].chips == 1000

    async def test_off_mode(self, env) -> None:
        rt, _ = env
        rt.settings = TableSettings(rebuy_mode="off")
        rt.players[0].stack = 0
        with pytest.raises(TableError, match="выключен"):
            await rt.rebuy(1)

    async def test_anytime_mode(self, env) -> None:
        rt, _ = env
        rt.settings = TableSettings(rebuy_mode="anytime")
        await rt.rebuy(2)
        assert rt.players[1].stack == 2000


class TestLateJoin:
    async def test_sit_anytime_waits_for_next_hand(self, env) -> None:
        rt, maker = env
        rt.runner = object()  # «идёт раздача» — садиться можно уже сейчас

        async with maker() as session:
            await service.upsert_user(session, user_id=3, first_name="Вася")
            await session.commit()

        await rt.sit(3, seat=2)
        assert [p.user_id for p in rt.players if not p.left] == [1, 2, 3]
        entries = [e for e in await ledger_rows(maker, rt.code) if e.user_id == 3]
        assert [e.kind for e in entries] == ["buyin"]
        assert entries[0].chips == 1000
        # Раздача не пострадала: следующий старт включит новичка.
        rt.runner = None

        with pytest.raises(TableError, match="занято"):
            await rt.sit(4, seat=2)

    async def test_waiting_player_enters_next_hand(self, env) -> None:
        rt, maker = env
        async with maker() as session:
            await service.upsert_user(session, user_id=3, first_name="Вася")
            await session.commit()
        rt.settings = TableSettings(action_timeout=None)

        # Первая раздача без Васи.
        await rt._start_hand_locked()  # noqa: SLF001
        first_hand_players = {p.user_id for p in rt.runner.players}
        assert first_hand_players == {1, 2}

        # Во время раздачи садится третий.
        await rt.sit(3, seat=2)

        # Доигрываем раздачу движком (авто-чеки) и применяем результат.
        while rt.runner.result is None:
            actor = rt.runner.players[rt.runner.to_act]
            rt.runner.auto_act(actor.user_id)
        await rt._apply_hand_result_locked()  # noqa: SLF001
        rt._showdown = None  # noqa: SLF001
        rt.next_hand_at = None

        await rt._start_hand_locked()  # noqa: SLF001
        assert {p.user_id for p in rt.runner.players} == {1, 2, 3}

    async def test_returning_player_gets_new_buyin(self, env) -> None:
        rt, maker = env
        rt.players[0].stack = 700
        await rt.stand_up(1)
        await rt.sit(1, seat=4)
        player = next(p for p in rt.players if p.user_id == 1)
        assert player.stack == 1000
        assert player.total_bought == 2000
        mine = [e for e in await ledger_rows(maker, rt.code) if e.user_id == 1]
        assert [e.kind for e in mine] == ["buyin", "cashout", "buyin"]


class TestStandUpCashout:
    async def test_cashout_recorded(self, env) -> None:
        rt, maker = env
        rt.players[1].stack = 1300
        await rt.stand_up(2)
        entries = [e for e in await ledger_rows(maker, rt.code) if e.user_id == 2]
        assert [(e.kind, e.chips) for e in entries] == [("buyin", 1000), ("cashout", 1300)]


class TestHandHistory:
    async def test_hand_recorded_after_finish(self, env) -> None:
        rt, maker = env
        rt.hand_number = 1
        rt.button_seat = 0
        rt._hand_start = {p.user_id: p.stack for p in rt.players}
        runner = HandRunner(
            [HandPlayer(user_id=p.user_id, stack=p.stack) for p in rt.players],
            button=0,
            small_blind=5,
            big_blind=10,
        )
        rt.runner = runner

        first = runner.players[runner.to_act]
        runner.act(first.user_id, "raise", first.bet + first.stack)  # олл-ин
        second = runner.players[runner.to_act]
        runner.act(second.user_id, "call")
        assert runner.result is not None

        await rt._apply_hand_result_locked()

        async with maker() as session:
            hands = (await session.execute(select(Hand))).scalars().all()
            rows = (await session.execute(select(HandPlayerRow))).scalars().all()
        assert len(hands) == 1
        assert hands[0].pot_total == 2000
        # победителей может быть двое — колода случайная, возможен сплит
        assert 1 <= len(json_loads(hands[0].result_json)) <= 2
        assert len(rows) == 2
        assert all(r.showed for r in rows)  # олл-ин — вскрытие обоих
        # фишки сохранились: 2000 у победителя, 0 у проигравшего
        assert sum(r.end_stack for r in rows) == 2000


def json_loads(text: str):
    import json

    return json.loads(text)


class TestLedgerBalance:
    async def test_session_balance(self, env) -> None:
        rt, maker = env
        # Аня проигрывает всё Боре, делает ребай, Боря уходит с выигрышем,
        # затем хост завершает игру.
        rt.players[0].stack = 0
        rt.players[1].stack = 2000
        await rt.rebuy(1)  # Аня: +1000
        await rt.stand_up(2)  # Боря: кэшаут 2000

        async with maker() as session:
            table = await service.get_table(session, rt.code)
            await service.end_game(session, table, actor_id=1)
            await session.commit()

        entries = await ledger_rows(maker, rt.code)
        bought = sum(e.chips for e in entries if e.kind in ("buyin", "rebuy"))
        cashed = sum(e.chips for e in entries if e.kind == "cashout")
        assert bought == 3000  # 2×1000 на старте + ребай
        assert cashed == 3000  # 2000 (выход) + 1000 (финал)


class TestTurnTimers:
    async def test_stale_timer_cancelled_on_new_turn(self, env) -> None:
        """Протухший таймер не должен автофолдить следующего игрока."""
        rt, _ = env
        rt.settings = TableSettings(action_timeout=30)
        rt.hand_number = 0
        await rt._start_hand_locked()  # noqa: SLF001 — тестируем таймеры напрямую

        stale = rt._timer_task  # noqa: SLF001
        assert stale is not None and not stale.done()
        actor = rt.runner.players[rt.runner.to_act]
        await rt.act(actor.user_id, "call")
        await asyncio.sleep(0)  # тик цикла — доставка CancelledError

        assert stale.cancelled() or stale.done()
        assert rt._timer_task is not stale  # noqa: SLF001 — новый ход = новый таймер

    async def test_timer_ignores_foreign_deadline(self, env) -> None:
        """Таймер с чужим (старым) дедлайном ничего не делает."""
        rt, _ = env
        rt.settings = TableSettings(action_timeout=30)
        rt.hand_number = 0
        await rt._start_hand_locked()  # noqa: SLF001

        runner = rt.runner
        to_act = runner.to_act
        # Симулируем срабатывание таймера с чужим дедлайном.
        await rt._timeout(0.0, deadline=12345.0)  # noqa: SLF001

        assert runner.to_act == to_act  # никто не автофолднулся
        assert not runner.players[to_act].folded
