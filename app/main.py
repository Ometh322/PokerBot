"""Точка входа: бот (long polling) и API/Mini App (uvicorn) в одном процессе."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.api.app import create_app
from app.bot import sender
from app.bot.info import set_bot_username
from app.bot.router import router as bot_router
from app.config import get_settings


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(), host=settings.host, port=settings.port, log_level="warning"
        )
    )

    if not settings.bot_token:
        logging.warning(
            "BOT_TOKEN не задан: работаем в режиме «только API», "
            "бот и уведомления отключены"
        )
        await server.serve()
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(bot_router)

    # Имя бота нужно для сборки invite-ссылок Mini App (t.me/<bot>?startapp=…),
    # сам бот — для уведомлений «твой ход» (см. app.bot.sender).
    set_bot_username((await bot.me()).username)
    sender.set_bot(bot)

    # Снимаем возможный вебхук и стартуем polling вместе с веб-сервером.
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.gather(dp.start_polling(bot), server.serve())
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
