"""Тесты построения сайд-потов и распределения."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.game.cards import Card, card
from app.game.pots import build_pots, distribute


@dataclass
class FakePlayer:
    user_id: int
    total: int
    folded: bool = False
    cards: list[Card] = field(default_factory=list)


def P(uid: int, total: int, folded: bool = False, cards: str = "") -> FakePlayer:
    return FakePlayer(uid, total, folded, [card(c) for c in cards.split()] if cards else [])


def test_single_pot() -> None:
    players = [P(1, 100), P(2, 100), P(3, 100, folded=True)]
    pots = build_pots(players)
    assert pots == [{"amount": 300, "eligible": [1, 2]}]


def test_side_pot_two_levels() -> None:
    # 1 — короткий олл-ин на 40, двое внесли по 100
    players = [P(1, 40), P(2, 100), P(3, 100)]
    pots = build_pots(players)
    assert pots == [
        {"amount": 120, "eligible": [1, 2, 3]},
        {"amount": 120, "eligible": [2, 3]},
    ]


def test_folded_contribution_merges_levels() -> None:
    # сбросивший на 70 создаёт уровень, где претенденты те же — поты сливаются
    players = [P(1, 100), P(2, 100), P(3, 70, folded=True)]
    pots = build_pots(players)
    assert pots == [{"amount": 270, "eligible": [1, 2]}]


def test_three_levels() -> None:
    players = [P(1, 30), P(2, 60), P(3, 100), P(4, 100)]
    pots = build_pots(players)
    assert [p["amount"] for p in pots] == [120, 90, 80]
    assert pots[0]["eligible"] == [1, 2, 3, 4]
    assert pots[1]["eligible"] == [2, 3, 4]
    assert pots[2]["eligible"] == [3, 4]


def test_distribute_split_and_odd_chip() -> None:
    board = [card(c) for c in "Ah Ad Ac 7h 2d".split()]
    players = [
        P(1, 101, cards="Ks Qh"),  # сет A, кикеры K Q
        P(2, 101, folded=True, cards="5h 4h"),
        P(3, 101, cards="Kd Qc"),  # сет A, кикеры K Q — точный сплит
    ]
    pots = build_pots(players)
    # общий банк 303 (вклад сбросившего входит), претенденты 1 и 3
    winnings = distribute(pots, players, board, odd_order=[3, 1, 2])
    # сплит 303/2 = 151.5 → 151 каждому, нечётная фишка первому слева от кнопки (3)
    assert winnings[1] + winnings[3] == 303
    assert winnings[3] == 152
    assert winnings[1] == 151


def test_distribute_side_pots() -> None:
    board = [card(c) for c in "Ah Ad Ac 7h 2d".split()]
    players = [
        P(1, 40, cards="5h 6h"),   # короткий олл-ин, слабее
        P(2, 100, cards="Ks Qh"),  # кикер K
        P(3, 100, cards="Kd Jh"),  # кикер K — делит верхний пот
    ]
    pots = build_pots(players)
    winnings = distribute(pots, players, board, odd_order=[1, 2, 3])
    assert winnings[1] == 0
    assert winnings[2] + winnings[3] == 240
