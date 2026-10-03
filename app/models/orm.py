"""ORM-модели хранения (схема — PLAN.md, раздел 8)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
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
    # waiting | left
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    stack: Mapped[int] = mapped_column(Integer, default=0)
    total_bought: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LedgerEntry(Base):
    """Движение фишек за сессию: buyin / rebuy на вход, cashout на выход.

    Инвариант закрытого стола: сумма buyin+rebuy равна сумме cashout.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("poker_tables.code"), index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16))  # buyin | rebuy | cashout
    chips: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Hand(Base):
    """История раздачи: борд, банк, победители (для разбора и статистики)."""

    __tablename__ = "hands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("poker_tables.code"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    dealer_seat: Mapped[int | None] = mapped_column(Integer)
    board_json: Mapped[str] = mapped_column(Text)
    pot_total: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HandPlayerRow(Base):
    """Участник раздачи: карты (хранятся, наружу отдаются только showed)."""

    __tablename__ = "hand_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hands.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger)
    seat: Mapped[int | None] = mapped_column(Integer)
    hole_cards_json: Mapped[str] = mapped_column(Text)
    start_stack: Mapped[int] = mapped_column(Integer)
    end_stack: Mapped[int] = mapped_column(Integer)
    contributed: Mapped[int] = mapped_column(Integer)
    folded: Mapped[bool] = mapped_column(Boolean, default=False)
    showed: Mapped[bool] = mapped_column(Boolean, default=False)


class StartButtonMessage(Base):
    """Последнее /start-сообщение бота с кнопкой Mini App.

    Telegram «зашивает» URL кнопки в момент отправки; при ротации туннеля
    редактируем сообщение, чтобы старые кнопки не вели на мёртвый адрес.
    """

    __tablename__ = "start_button_messages"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    table_code: Mapped[str | None] = mapped_column(String(8))
