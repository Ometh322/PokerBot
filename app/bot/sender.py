"""Отправка личных сообщений ботом (уведомления о ходе).

Бот регистрируется в main.py; если бота нет (режим «только API»)
или пользователь его заблокировал — молча пропускаем.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def set_bot(bot: Bot | None) -> None:
    global _bot
    _bot = bot


def get_bot() -> Bot | None:
    return _bot


async def pm(
    user_id: int,
    text: str,
    *,
    button_text: str | None = None,
    button_url: str | None = None,
) -> None:
    bot = _bot
    if bot is None:
        return
    reply_markup = None
    if button_url:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=button_text or "Открыть",
                        web_app=WebAppInfo(url=button_url),
                    )
                ]
            ]
        )
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    except Exception:  # noqa: BLE001 — не роняем игру из-за уведомления
        logger.debug("не доставлено личное сообщение игроку %s", user_id)
