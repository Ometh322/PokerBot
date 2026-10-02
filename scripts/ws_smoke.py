"""Е2Е-смоук M3: два игрока через WebSocket играют раздачу до результата.

Запуск: подними сервер с DEV_MODE=1 (python -m app.main), затем
    .venv/Scripts/python scripts/ws_smoke.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random

import httpx
import websockets

BASE = "http://127.0.0.1:8000"


class Player:
    def __init__(self, name: str, token: str) -> None:
        self.name = name
        self.token = token
        self.snapshot: dict | None = None
        self.ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self, code: str) -> None:
        ws_base = BASE.replace("http", "ws", 1)
        self.ws = await websockets.connect(
            f"{ws_base}/ws/table/{code}?token={self.token}"
        )
        asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        assert self.ws is not None
        async for message in self.ws:
            data = json.loads(message)
            if data.get("type") == "state":
                self.snapshot = data["state"]
            elif data.get("type") == "error":
                print(f"  [{self.name}] ошибка от сервера: {data['message']}")


async def main() -> None:
    rng = random.Random(7)

    async with httpx.AsyncClient(base_url=BASE) as http:
        tokens = {}
        for uid, name in ((101, "Аня"), (102, "Боря"), (103, "Вася")):
            res = await http.post(
                "/api/auth/dev", json={"user_id": uid, "first_name": name}
            )
            res.raise_for_status()
            tokens[uid] = res.json()["token"]
        headers = {"Authorization": f"Bearer {tokens[101]}"}
        res = await http.post(
            "/api/tables",
            headers=headers,
            json={"name": "Смоук M4", "settings": {"action_timeout": 10}},
        )
        res.raise_for_status()
        code = res.json()["code"]
    print(f"стол создан: {code}")

    anya = Player("Аня", tokens[101])   # уже сидит на месте 0 (хост)
    borya = Player("Боря", tokens[102])
    await anya.connect(code)
    await borya.connect(code)
    await asyncio.sleep(0.5)

    await borya.ws.send(json.dumps({"type": "sit", "seat": 1}))
    await asyncio.sleep(0.5)
    await anya.ws.send(json.dumps({"type": "start_game"}))
    print("игра начата, ждём первую раздачу…")

    hands_played = 0
    for _ in range(400):  # общий бюджет ~40 секунд
        await asyncio.sleep(0.1)
        for player in (anya, borya):
            snap = player.snapshot
            if snap is None or not snap.get("hand"):
                continue
            hand = snap["hand"]
            you = snap.get("you", {})

            if hand.get("last_result") and hands_played == 0:
                result = hand["last_result"]
                hands_played += 1
                print(
                    f"раздача завершена (банк {result.get('pot_total')}): "
                    f"{result['winners']}"
                )

                # Поздний вход: третий игрок садится между раздачами.
                vasya = Player("Вася", tokens[103])
                await vasya.connect(code)
                await asyncio.sleep(0.5)
                await vasya.ws.send(json.dumps({"type": "sit", "seat": 5}))
                await asyncio.sleep(0.5)
                players = anya.snapshot["players"] if anya.snapshot else []
                print(f"игроков за столом: {len(players)}")
                assert len(players) == 3, "поздний вход не сработал"

                # История рук доступна по REST.
                async with httpx.AsyncClient(
                    base_url=BASE, headers={"Authorization": f"Bearer {tokens[101]}"}
                ) as http:
                    res = await http.get(f"/api/tables/{code}/hands")
                    res.raise_for_status()
                    hands = res.json()
                print(f"история рук: {len(hands)} записей, банк {hands[0]['pot_total']}")
                assert len(hands) >= 1

                await asyncio.sleep(1)
                await anya.ws.send(json.dumps({"type": "end_game"}))
                await asyncio.sleep(1)

                # Расчёт долгов по финальному ledger.
                async with httpx.AsyncClient(
                    base_url=BASE, headers={"Authorization": f"Bearer {tokens[101]}"}
                ) as http:
                    res = await http.get(f"/api/tables/{code}/settlement")
                    res.raise_for_status()
                    s = res.json()
                nets = {p["user_id"]: p["net_chips"] for p in s["players"]}
                print(f"итоги в фишках: {nets}, переводов: {len(s['transfers'])}")
                assert sum(nets.values()) == 0, "итоги не сходятся в ноль"
                assert len(s["transfers"]) >= 1, "переводы не рассчитаны"

                print("SMOKE OK: раздача, поздний вход, история, расчёт, завершение")
                for player_ in (anya, borya, vasya):
                    await player_.ws.close()
                return

            legal = you.get("legal_actions")
            if legal:
                if legal.get("check") and rng.random() < 0.7:
                    action = {"type": "action", "action": "check"}
                elif "call" in legal:
                    action = {"type": "action", "action": "call"}
                elif legal.get("check"):
                    action = {"type": "action", "action": "check"}
                else:
                    action = {"type": "action", "action": "fold"}
                if legal.get("raise_to") and rng.random() < 0.25:
                    lo, hi = legal["raise_to"]
                    action = {
                        "type": "action",
                        "action": "raise",
                        "amount": rng.choice([lo, hi]),
                    }
                await player.ws.send(json.dumps(action))

    raise SystemExit("SMOKE FAILED: раздача не завершилась за отведённое время")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base
    asyncio.run(main())
