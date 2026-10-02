"""Сетевая обвязка бота: aiohttp-сессия с опциями доступа к api.telegram.org.

Порядок приоритета:
1. PROXY_URL (http://… или socks5://…) — если задан, работаем через прокси;
2. TELEGRAM_API_IP — пиннинг официального IP для хоста API, полезен когда
   локальный DNS отдаёт недоступный адрес (актуально для некоторых сетей);
3. обычный DNS.

IP можно менять переменной окружения TELEGRAM_API_IP (пустая строка —
отключить пиннинг). Официальные адреса: https://core.telegram.org/api/bots/api
"""

from __future__ import annotations

import socket
from typing import Any

from aiohttp.resolver import ThreadedResolver
from aiogram.client.session.aiohttp import AiohttpSession

API_HOST = "api.telegram.org"


class PinnedResolver(ThreadedResolver):
    """Резолвер, который для api.telegram.org возвращает заданный IP."""

    def __init__(self, api_ip: str) -> None:
        super().__init__()
        self._api_ip = api_ip

    async def resolve(  # type: ignore[override]
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[dict[str, Any]]:
        if host == API_HOST:
            return [
                {
                    "hostname": host,
                    "host": self._api_ip,
                    "port": port or 443,
                    "family": family,
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST,
                }
            ]
        return await super().resolve(host, port, family)


def make_bot_session(
    *, proxy: str | None = None, api_ip: str | None = None
) -> AiohttpSession:
    """Сессия бота: прокси приоритетнее, иначе пиннинг IP (если задан)."""
    session = AiohttpSession(proxy=proxy)
    if not proxy and api_ip:
        # aiogram собирает коннектор из этого словаря при первом запросе.
        session._connector_init["resolver"] = PinnedResolver(api_ip)  # noqa: SLF001
    return session
