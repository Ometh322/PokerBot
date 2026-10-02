"""Настройки процесса. Читаются из окружения и файла .env (см. .env.example)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Токен от @BotFather. Пустой — режим «только API» (бот отключён).
    bot_token: str = ""

    # Публичный HTTPS-адрес, по которому доступны Mini App и API.
    # В разработке — адрес туннеля (cloudflared/ngrok), в проде — домен.
    base_url: str = "http://localhost:8000"

    host: str = "0.0.0.0"
    port: int = 8000

    # SQLite через aiosqlite; схема рассчитана на переезд на Postgres.
    database_url: str = "sqlite+aiosqlite:///./pokerbot.db"

    # Дев-вход без Telegram (POST /api/auth/dev) — только для разработки.
    dev_mode: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
