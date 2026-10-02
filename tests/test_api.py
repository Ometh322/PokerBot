"""Смоук- и интеграционные тесты REST API (через дев-вход)."""

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


def test_tables_require_auth() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/tables").status_code == 401
        assert client.post("/api/tables", json={}).status_code == 401


def test_dev_auth_and_tables_flow() -> None:
    with TestClient(create_app()) as client:
        auth = client.post(
            "/api/auth/dev", json={"user_id": 42, "first_name": "Аня"}
        ).json()
        headers = {"Authorization": f"Bearer {auth['token']}"}
        assert auth["user"]["id"] == 42

        created = client.post(
            "/api/tables", headers=headers, json={"name": "Тест", "settings": {}}
        )
        assert created.status_code == 201
        body = created.json()
        code = body["code"]
        assert body["snapshot"]["players"][0]["user_id"] == 42
        assert body["snapshot"]["you"]["is_host"] is True
        assert code in body["invite_link"]

        listed = client.get("/api/tables", headers=headers).json()
        assert [t["code"] for t in listed] == [code]
        assert listed[0]["players_count"] == 1

        fetched = client.get(f"/api/tables/{code}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["you"]["seat"] == 0

        bad = client.post(
            "/api/tables",
            headers=headers,
            json={"settings": {"small_blind": 10, "big_blind": 10}},
        )
        assert bad.status_code == 422

        missing = client.get("/api/tables/nope1", headers=headers)
        assert missing.status_code == 404
