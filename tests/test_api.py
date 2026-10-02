"""Смоук-тесты REST API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app


def test_health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_rejects_garbage() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/auth", json={"init_data": "user=hacker&hash=deadbeef"}
        )
    assert response.status_code == 401
