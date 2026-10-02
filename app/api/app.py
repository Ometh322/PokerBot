"""Фабрика FastAPI: REST, WebSocket (с M2) и статика собранного Mini App."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router

# web/dist относительно app/api/app.py: app/api -> app -> корень репо -> web/dist
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="PokerBot API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # В разработке Mini App может жить на vite-дев-сервере (localhost:5173);
    # в бою запросы идут с того же домена.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    # Собранный Mini App отдаём как статику с корня (index.html на "/").
    if WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app
