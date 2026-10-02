"""ORM-модели хранения (схема — PLAN.md, раздел 8)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64), default="")
    last_name: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PokerTable(Base):
    __tablename__ = "poker_tables"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), default="Покер с друзьями")
    host_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id"), index=True
    )
    # lobby | active | finished
    status: Mapped[str] = mapped_column(String(16), default="lobby", index=True)
    settings_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TablePlayer(Base):
    __tablename__ = "table_players"

    table_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("poker_tables.code"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id"), primary_key=True
    )
    seat: Mapped[int] = mapped_column(Integer)
    # waiting | left (в M3 появятся playing / sitting_out)
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    stack: Mapped[int] = mapped_column(Integer, default=0)
    total_bought: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
