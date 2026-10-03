"""Перевязка старых /start-кнопок на новый адрес туннеля.

Telegram «зашивает» URL web_app-кнопки в момент отправки — когда туннель
меняется, все ранее отправленные сообщения ведут в пустоту. Запоминаем
последнее сообщение каждому игроку и при ротации редактируем его кнопку.
"""

from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

from app.bot import sender
from app.db import SessionLocal
from app.models.orm import StartButtonMessage

log = logging.getLogger(__name__)

# user_id -> (chat_id, message_id, table_code | None)
_known: dict[int, tuple[int, int, str | None]] = {}


def _keyboard(base_url: str, table_code: str | None) -> InlineKeyboardMarkup:
    if table_code:
        button = InlineKeyboardButton(
            text="🂡 Сесть за стол",
            web_app=WebAppInfo(url=f"{base_url}/?table={table_code}"),
        )
    else:
        button = InlineKeyboardButton(
            text="🎰 Открыть покер-клуб",
            web_app=WebAppInfo(url=base_url),
        )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def load() -> None:
    """Восстанавливает список сообщений после рестарта процесса."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(StartButtonMessage))
        ).scalars().all()
    _known.clear()
    for row in rows:
        _known[row.user_id] = (row.chat_id, row.message_id, row.table_code)


async def remember(
    user_id: int,
    chat_id: int,
    message_id: int,
    *,
    table_code: str | None = None,
) -> None:
    _known[user_id] = (chat_id, message_id, table_code)
    async with SessionLocal() as session:
        row = await session.get(StartButtonMessage, user_id)
        if row is None:
            session.add(
                StartButtonMessage(
                    user_id=user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    table_code=table_code,
                )
            )
        else:
            row.chat_id = chat_id
            row.message_id = message_id
            row.table_code = table_code
        await session.commit()


async def rebind_all(base_url: str) -> None:
    """Редактирует кнопки всех отправленных сообщений на новый адрес."""
    bot = sender.get_bot()
    if bot is None:
        return
    base = base_url.rstrip("/")
    for user_id, (chat_id, message_id, table_code) in list(_known.items()):
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=_keyboard(base, table_code),
            )
        except Exception:  # noqa: BLE001 — сообщение могло быть удалено
            log.debug("не удалось перевязать кнопку игрока %s", user_id)
