"""Авторизация Mini App: валидация initData и сессионные токены.

Схема стандартная для Telegram Mini Apps:
1. клиент присылает строку initData (подписана HMAC-SHA256 с токеном бота);
2. сервер проверяет подпись и свежесть auth_date;
3. сервер выдаёт собственный подписанный сессионный токен, который клиент
   использует в последующих REST-запросах и при открытии WebSocket.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60
SESSION_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60


def validate_init_data(
    init_data: str, bot_token: str, *, max_age: int = DEFAULT_MAX_AGE_SECONDS
) -> dict[str, str] | None:
    """Проверяет подпись initData. Возвращает параметры или None, если данные плохие."""
    if not init_data or not bot_token:
        logger.warning("initData отклонён: пустая строка или токен")
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        logger.warning("initData отклонён: не разбирается как query-строка")
        return None

    received_hash = pairs.pop("hash", "")
    if not received_hash:
        logger.warning("initData отклонён: нет поля hash (поля: %s)", sorted(pairs))
        return None

    age: float | None = None
    if "auth_date" in pairs:
        try:
            age = time.time() - int(pairs["auth_date"])
        except ValueError:
            logger.warning("initData отклонён: auth_date не число")
            return None
        if age < -max_age or age > max_age:
            logger.warning(
                "initData отклонён: auth_date вне окна (age=%.1f сек)", age
            )
            return None

    # Контрольная строка: все поля кроме hash (включая signature), по алфавиту.
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    # Секрет: HMAC_SHA256 с ключом "WebAppData" и сообщением = токен бота
    # (да, именно так — ключ и сообщение не перепутать, см. docs/aiogram).
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        logger.warning(
            "initData отклонён: подпись не совпала (age=%s, поля: %s, "
            "наш хэш %.8s…, их хэш %.8s…)",
            f"{age:.1f}" if age is not None else "нет",
            sorted(pairs),
            calculated,
            received_hash,
        )
        return None
    return pairs


def parse_user(pairs: dict[str, str]) -> dict[str, Any] | None:
    """Достаёт объект пользователя из уже провалидированных параметров."""
    raw = pairs.get("user")
    if not raw:
        return None
    try:
        user = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


def _session_key(bot_token: str) -> bytes:
    return hashlib.sha256(bot_token.encode() + b":session").digest()


def issue_session_token(user_id: int, bot_token: str) -> str:
    """Подписанный токен сессии вида <payload>.<hmac>, без состояния на сервере."""
    payload = json.dumps(
        {"uid": user_id, "exp": time.time() + SESSION_TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    )
    body = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    sig = hmac.new(_session_key(bot_token), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_session_token(token: str, bot_token: str) -> int | None:
    """Возвращает user_id для валидного непросроченного токена, иначе None."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_session_key(bot_token), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    uid = payload.get("uid")
    exp = payload.get("exp")
    if not isinstance(uid, int) or not isinstance(exp, (int, float)):
        return None
    if exp < time.time():
        return None
    return uid
