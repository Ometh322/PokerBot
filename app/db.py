"""Движок и сессии SQLAlchemy (async, aiosqlite).

Для файловой SQLite используем NullPool: каждое подключение живёт
в текущем event loop — это важно для тестов, где приложение
поднимается в разных loop'ах. Для :memory: нужен StaticPool,
иначе каждая сессия получала бы собственную пустую базу.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings


def _create_engine(url: str):
    if ":memory:" in url:
        return create_async_engine(url, poolclass=StaticPool)
    return create_async_engine(url, poolclass=NullPool)


engine = _create_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from app.models.orm import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
