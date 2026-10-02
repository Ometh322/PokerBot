"""Маршруты бота: /start, deep links, кнопка открытия Mini App."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import get_settings

router = Router(name="main")


def open_club_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎰 Открыть покер-клуб",
                    web_app=WebAppInfo(url=settings.base_url),
                )
            ]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    payload = (command.args or "").strip()

    # Deep link вида t.me/<bot>?start=tbl_<code> — приглашение за стол.
    if payload.startswith("tbl_"):
        code = payload.removeprefix("tbl_")
        settings = get_settings()
        url = f"{settings.base_url.rstrip('/')}/?table={code}"
        await message.answer(
            "Тебя ждут за игровым столом 🂠\n\nЖми кнопку — сядешь за него.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🂡 Сесть за стол",
                            web_app=WebAppInfo(url=url),
                        )
                    ]
                ]
            ),
        )
        return

    await message.answer(
        "Привет! Это покер-клуб для своих: безлимитный Холдем "
        "на условные фишки.\n\n"
        "Жми кнопку — откроется клуб.",
        reply_markup=open_club_keyboard(),
    )
