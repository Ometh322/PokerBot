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
from app.bot.net import make_bot_session
from app.bot.router import router as bot_router
from app.config import get_settings

log = logging.getLogger(__name__)

_USERNAME_ATTEMPTS = 8
_USERNAME_PAUSE = 3.0
_BACKGROUND_USERNAME_RETRY = 60.0


async def _startup_prepare(bot: Bot) -> None:
    """Готовим бота к polling, переживая рваную связь с API (DPI)."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as exc:  # noqa: BLE001 — вебхук не критичен
        log.warning("не удалось снять вебхук (продолжаем): %s", exc)

    for attempt in range(1, _USERNAME_ATTEMPTS + 1):
        try:
            set_bot_username((await bot.me()).username)
            log.info("имя бота получено (попытка %d)", attempt)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "не удалось получить имя бота (попытка %d/%d): %s",
                attempt,
                _USERNAME_ATTEMPTS,
                exc,
            )
            await asyncio.sleep(_USERNAME_PAUSE)

    # Работаем без имени: invite-ссылки временно через BASE_URL.
    # Поллинг у aiogram свой с ретраями, имя доопределим в фоне.
    log.warning("продолжаем без имени бота — ссылки-приглашения через BASE_URL")

    async def _retry_username() -> None:
        while True:
            await asyncio.sleep(_BACKGROUND_USERNAME_RETRY)
            try:
                set_bot_username((await bot.me()).username)
                log.info("имя бота получено фоновой попыткой")
                return
            except Exception:  # noqa: BLE001
                continue

    asyncio.create_task(_retry_username())


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
        session=make_bot_session(
            proxy=settings.proxy_url or None,
            api_ips=settings.telegram_api_ip or None,
        ),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    sender.set_bot(bot)
    dp = Dispatcher()
    dp.include_router(bot_router)

    async def _polling_forever() -> None:
        """Polling переживает волны DPI: стартовый запрос может упасть
        до внутреннего цикла ретраев aiogram — тогда просто пробуем снова."""
        while True:
            try:
                await dp.start_polling(bot)
                return  # штатное завершение (остановка процесса)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "polling упал (%s) — перезапуск через 5 с", type(exc).__name__
                )
                await asyncio.sleep(5)

    # Сервер стартует сразу, параллельно с подготовкой бота: если Telegram
    # недоступен (DPI-волны), Mini App и API всё равно работают, а бот
    # дождётся окна связи сам.
    prepare = asyncio.create_task(_startup_prepare(bot))
    try:
        await asyncio.gather(_polling_forever(), prepare, server.serve())
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
