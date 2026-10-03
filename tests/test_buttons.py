"""Тесты перевязки /start-кнопок на новый адрес туннеля."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.bot import buttons
from app.models.orm import Base


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(buttons, "SessionLocal", maker)
    yield maker
    await engine.dispose()


async def test_remember_and_load_roundtrip(env) -> None:
    await buttons.remember(1, 10, 100, table_code="ab12c")
    await buttons.remember(2, 20, 200)

    buttons._known.clear()  # noqa: SLF001 — имитируем рестарт процесса
    await buttons.load()

    assert buttons._known[1] == (10, 100, "ab12c")  # noqa: SLF001
    assert buttons._known[2] == (20, 200, None)  # noqa: SLF001


async def test_rebind_without_bot_is_noop(env) -> None:
    # Бот не зарегистрирован (тесты/режим «только API») — не падаем.
    await buttons.remember(1, 10, 100)
    await buttons.rebind_all("https://x.example.com/")


def test_keyboard_urls() -> None:
    plain = buttons._keyboard("https://x.example.com", None)  # noqa: SLF001
    invite = buttons._keyboard("https://x.example.com", "ab12c")  # noqa: SLF001
    assert plain.inline_keyboard[0][0].web_app.url == "https://x.example.com"
    assert (
        invite.inline_keyboard[0][0].web_app.url
        == "https://x.example.com/?table=ab12c"
    )
