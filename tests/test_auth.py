"""Тесты валидации initData и сессионных токенов (app.api.auth)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.api.auth import (
    issue_session_token,
    validate_init_data,
    verify_session_token,
)

BOT_TOKEN = "7000000001:AA-test-token-for-unit-tests"


def make_init_data(bot_token: str, params: dict[str, str]) -> str:
    """Подписывает параметры так же, как это делает Telegram:
    секрет = HMAC_SHA256(key='WebAppData', msg=токен)."""
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(list(params.items()) + [("hash", digest)])


def user_param() -> str:
    return json.dumps({"id": 424242, "first_name": "Тест", "username": "t_est"})


class TestValidateInitData:
    def test_valid(self) -> None:
        init_data = make_init_data(
            BOT_TOKEN, {"user": user_param(), "auth_date": str(int(time.time()))}
        )
        pairs = validate_init_data(init_data, BOT_TOKEN)
        assert pairs is not None
        assert json.loads(pairs["user"])["id"] == 424242

    def test_signed_with_wrong_token(self) -> None:
        init_data = make_init_data(
            "999:another-token", {"user": user_param(), "auth_date": str(int(time.time()))}
        )
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_tampered_payload(self) -> None:
        init_data = make_init_data(
            BOT_TOKEN, {"user": user_param(), "auth_date": str(int(time.time()))}
        )
        tampered = init_data.replace("424242", "111111")
        assert validate_init_data(tampered, BOT_TOKEN) is None

    def test_signature_field_included(self) -> None:
        # Telegram присылает поле signature (Ed25519) в общем наборе полей —
        # оно входит в data-check-string как любое другое.
        init_data = make_init_data(
            BOT_TOKEN,
            {
                "query_id": "AAF14D8qAAAA",
                "user": user_param(),
                "signature": "A" * 171,
                "auth_date": str(int(time.time())),
            },
        )
        pairs = validate_init_data(init_data, BOT_TOKEN)
        assert pairs is not None
        assert json.loads(pairs["user"])["id"] == 424242

    def test_missing_hash(self) -> None:
        assert validate_init_data("user=x&auth_date=123", BOT_TOKEN) is None

    def test_expired(self) -> None:
        old = str(int(time.time()) - 10 * 24 * 3600)
        init_data = make_init_data(BOT_TOKEN, {"user": user_param(), "auth_date": old})
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_empty_inputs(self) -> None:
        assert validate_init_data("", BOT_TOKEN) is None
        assert validate_init_data("hash=abc", "") is None


class TestSessionToken:
    def test_roundtrip(self) -> None:
        token = issue_session_token(424242, BOT_TOKEN)
        assert verify_session_token(token, BOT_TOKEN) == 424242

    def test_wrong_key(self) -> None:
        token = issue_session_token(424242, BOT_TOKEN)
        assert verify_session_token(token, "999:another") is None

    def test_tampered_body(self) -> None:
        token = issue_session_token(424242, BOT_TOKEN)
        body, sig = token.split(".")
        flipped = body[:-1] + ("A" if body[-1] != "A" else "B")
        assert verify_session_token(f"{flipped}.{sig}", BOT_TOKEN) is None

    def test_expired_token(self) -> None:
        payload = json.dumps({"uid": 1, "exp": time.time() - 1}, separators=(",", ":"))
        body = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
        key = hashlib.sha256(BOT_TOKEN.encode() + b":session").digest()
        sig = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
        assert verify_session_token(f"{body}.{sig}", BOT_TOKEN) is None
