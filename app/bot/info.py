"""Кэш имени бота: нужен для сборки invite-ссылок Mini App (t.me/<bot>?startapp=…)."""

_bot_username: str | None = None


def set_bot_username(username: str | None) -> None:
    global _bot_username
    _bot_username = username


def get_bot_username() -> str | None:
    return _bot_username
