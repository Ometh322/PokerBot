"""Сценарные тесты раздачи (HandRunner) + генеративная проверка инвариантов."""

from __future__ import annotations

import random

import pytest

from app.game.cards import card
from app.game.hand import EngineError, HandPlayer, HandRunner


def make(players_specs: list[int], *, button: int = 0, sb: int = 5, bb: int = 10) -> HandRunner:
    players = [HandPlayer(user_id=uid, stack=stack) for uid, stack in players_specs]
    return HandRunner(players, button=button, small_blind=sb, big_blind=bb)


def uid(runner: HandRunner) -> int:
    assert runner.to_act is not None
    return runner.players[runner.to_act].user_id


class TestBasics:
    def test_blinds_and_first_to_act_three_handed(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        # кнопка 1 → SB 2, BB 3, префлоп первым действует 1 (UTG)
        assert uid(runner) == 1
        bets = {p.user_id: p.bet for p in runner.players}
        assert bets == {1: 0, 2: 5, 3: 10}
        assert runner.current_bet == 10

    def test_heads_up_button_is_sb_and_acts_first(self) -> None:
        runner = make([(1, 1000), (2, 1000)], button=0)
        assert uid(runner) == 1
        assert runner.players[0].bet == 5  # кнопка — SB

    def test_everyone_folds_bb_wins_blinds(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "fold")
        runner.act(2, "fold")
        assert runner.result is not None
        assert runner.result["type"] == "uncontested"
        assert runner.result["winners"] == [
            {"user_id": 3, "amount": 15, "hand": None}
        ]
        # BB никого не показывал — карты скрыты
        assert runner.revealed == {}

    def test_out_of_turn_rejected(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        with pytest.raises(EngineError, match="не твой ход"):
            runner.act(2, "call")

    def test_check_rejected_facing_bet(self) -> None:
        runner = make([(1, 1000), (2, 1000)], button=0)
        with pytest.raises(EngineError, match="чек невозможен"):
            runner.act(1, "check")

    def test_min_raise_enforced(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        legal = runner.legal_actions()
        assert legal["raise_to"] == [20, 1000]
        with pytest.raises(EngineError, match="от 20"):
            runner.act(1, "raise", 15)

    def test_act_after_finish_rejected(self) -> None:
        runner = make([(1, 1000), (2, 1000)], button=0)
        runner.act(1, "fold")
        with pytest.raises(EngineError, match="завершена"):
            runner.act(2, "check")


class TestStreets:
    def test_bb_option_then_flop_order(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "call")   # UTG лимп
        runner.act(2, "call")   # SB дополняет
        assert uid(runner) == 3  # опция BB
        runner.act(3, "check")
        assert runner.street == "flop"
        assert len(runner.board) == 3
        assert uid(runner) == 2  # постфлоп первым SB
        assert runner.legal_actions() == {
            "fold": True, "check": True, "raise_to": [10, 990],
        }

    def test_postflop_bet_and_raises(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "call")   # UTG лимп
        runner.act(2, "call")   # SB дополняет
        runner.act(3, "check")  # опция BB
        assert runner.street == "flop"
        runner.act(2, "check")
        runner.act(3, "check")
        runner.act(1, "bet", 30)
        legal = runner.legal_actions()
        assert legal["raise_to"] == [60, 990]  # мин-рейз 30 сверх ставки, мак — весь стек
        runner.act(2, "fold")
        runner.act(3, "call")
        assert runner.street == "turn"
        assert len(runner.board) == 4

    def test_all_in_runout_reveals_and_reaches_showdown(self) -> None:
        runner = make([(1, 1000), (2, 1000)], button=0)
        runner.act(1, "raise", 1000)  # олл-ин
        runner.act(2, "call")
        assert runner.result is not None
        assert runner.result["type"] == "showdown"
        assert len(runner.board) == 5
        # оба игрока вскрыты
        assert set(runner.revealed) == {1, 2}
        # банк = 2000, целиком у победителя
        assert runner.result["pot_total"] == 2000
        assert sum(w["amount"] for w in runner.result["winners"]) == 2000

    def test_board_visible_marks_runout_start(self) -> None:
        runner = make([(1, 1000), (2, 1000)], button=0)
        runner.act(1, "raise", 1000)  # олл-ин префлоп: борд был пуст
        runner.act(2, "call")
        assert runner.public_view()["board_visible"] == 0
        assert len(runner.board) == 5

    def test_board_visible_river_showdown_full(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "call")
        runner.act(2, "call")
        runner.act(3, "check")
        guard = 0
        while runner.result is None:
            guard += 1
            assert guard < 15
            assert "check" in runner.legal_actions()
            runner.act(uid(runner), "check")
        assert runner.result["type"] == "showdown"
        # дошли до ривера торговыми кругами — борд виден целиком
        assert runner.public_view()["board_visible"] == 5

    def test_short_all_in_does_not_reopen_raising(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 150)], button=0)
        runner.act(1, "raise", 100)   # полное повышение до 100
        runner.act(2, "call")
        # у 3 (BB) стек позволяет только короткий олл-ин в диапазон (100, 190)
        legal3 = runner.legal_actions()
        assert legal3["raise_to"] == [150, 150]
        runner.act(3, "raise", 150)   # короткий олл-ин
        # игрок 1 уже действовал: должен уравнять, но НЕ может ререйзить
        legal1 = runner.legal_actions()
        assert "raise_to" not in legal1
        assert legal1["call"] == 50  # до уровня олл-ина не хватает 50
        runner.act(1, "call")
        runner.act(2, "call")
        # у 1 и 2 остались стеки — сайд-пот разыгрывается чеками до вскрытия
        guard = 0
        while runner.result is None:
            guard += 1
            assert guard < 20
            assert "check" in runner.legal_actions()
            runner.act(uid(runner), "check")
        assert runner.result["pots"] == [
            {"amount": 450, "eligible": [1, 2, 3]}
        ]

    def test_side_pot_split(self) -> None:
        # 1 — короткий олл-ин, 2 и 3 достраивают побочный пот и делят его
        runner = make([(1, 100), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "raise", 100)   # олл-ин 100
        runner.act(2, "raise", 500)   # полный рейз до 500
        runner.act(3, "call")
        # у 2 и 3 остались стеки — торги за сайд-пот; в тесте чекуем до конца
        guard = 0
        while runner.result is None:
            guard += 1
            assert guard < 20
            legal = runner.legal_actions()
            assert "check" in legal
            runner.act(uid(runner), "check")
        pots = runner.result["pots"]
        assert [p["amount"] for p in pots] == [300, 800]
        total = sum(w["amount"] for w in runner.result["winners"])
        assert total == 1100
        # стеки сходятся: старт 2100 = финальные стеки после применения выигрышей
        final = {p.user_id: p.stack for p in runner.players}
        for w in runner.result["winners"]:
            final[w["user_id"]] += w["amount"]
        assert sum(final.values()) == 2100


class TestAuto:
    def test_auto_checks_when_free(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        for u in (1, 2):
            runner.act(u, "call")
        runner.auto_act(3)  # опция BB → чек
        assert runner.street == "flop"

    def test_auto_folds_facing_bet(self) -> None:
        runner = make([(1, 1000), (2, 1000), (3, 1000)], button=0)
        runner.act(1, "raise", 100)
        runner.auto_act(2)
        assert runner.players[1].folded


def test_generative_invariants() -> None:
    """Случайные раздачи: фишки не появляются и не исчезают, пот распределён."""
    rng = random.Random(2026)
    for _ in range(60):
        n = rng.choice([2, 3, 4, 5])
        stacks = [rng.randint(20, 300) for _ in range(n)]
        players = [HandPlayer(user_id=i + 1, stack=s) for i, s in enumerate(stacks)]
        runner = HandRunner(
            players, button=rng.randrange(n), small_blind=5, big_blind=10
        )

        guard = 0
        while runner.result is None:
            guard += 1
            assert guard < 600, "раздача зациклилась"
            legal = runner.legal_actions()
            actor = uid(runner)
            options: list[tuple[str, int | None]] = []
            if legal.get("check"):
                options.append(("check", None))
            if "call" in legal:
                options.append(("call", None))
            if "raise_to" in legal and rng.random() < 0.4:
                lo, hi = legal["raise_to"]
                amount = rng.choice([lo, hi, rng.randint(lo, hi)])
                options.append(("raise", amount))
            if not (legal.get("check") and rng.random() < 0.8):
                options.append(("fold", None))
            action, amount = rng.choice(options)
            runner.act(actor, action, amount)

        assert sum(w["amount"] for w in runner.result["winners"]) == (
            runner.result["pot_total"]
        )
        final = {p.user_id: p.stack for p in players}
        for w in runner.result["winners"]:
            final[w["user_id"]] += w["amount"]
        assert sum(final.values()) == sum(stacks), "фишки потерялись"
