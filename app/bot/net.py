"""Сетевая обвязка бота: aiohttp-сессия с опциями доступа к api.telegram.org.

Порядок приоритета:
1. PROXY_URL (http://… или socks5://…) — если задан, работаем через прокси;
2. TELEGRAM_API_IP — пиннинг официальных IP для хоста API (через запятую
   можно перечислить несколько — aiohttp пробует по очереди). Полезно,
   когда локальный DNS отдаёт недоступный адрес;
3. обычный DNS.

Официальные адреса: https://core.telegram.org/api/bots/api
"""

from __future__ import annotations

import socket
from typing import Any

from aiohttp.resolver import ThreadedResolver
from aiogram.client.session.aiohttp import AiohttpSession

API_HOST = "api.telegram.org"


class PinnedResolver(ThreadedResolver):
    """Резолвер, который для api.telegram.org возвращает заданные IP."""

    def __init__(self, api_ips: list[str]) -> None:
        super().__init__()
        self._api_ips = api_ips

    async def resolve(  # type: ignore[override]
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[dict[str, Any]]:
        if host == API_HOST and self._api_ips:
            return [
                {
                    "hostname": host,
                    "host": ip,
                    "port": port or 443,
                    "family": family,
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST,
                }
                for ip in self._api_ips
            ]
        return await super().resolve(host, port, family)


def make_bot_session(
    *, proxy: str | None = None, api_ips: str | None = None
) -> AiohttpSession:
    """Сессия бота: прокси приоритетнее, иначе пиннинг IP (если задан)."""
    session = AiohttpSession(proxy=proxy)
    candidates = [ip.strip() for ip in (api_ips or "").split(",") if ip.strip()]
    if not proxy and candidates:
        # aiogram собирает коннектор из этого словаря при первом запросе.
        session._connector_init["resolver"] = PinnedResolver(candidates)  # noqa: SLF001
    return session
