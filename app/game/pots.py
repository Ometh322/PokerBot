"""Сайд-поты: построение по вкладам и распределение с учётом сплитов.

Нечётная фишка при сплите достаётся первому выигравшему слева от кнопки.
"""

from __future__ import annotations

from typing import Iterable

from app.game.cards import Card
from app.game.evaluator import best_hand


def build_pots(players: Iterable) -> list[dict]:
    """Уровни банка по размерам вкладов; у каждого — список претендентов.

    `players` — объекты с полями user_id, total (вклад за раздачу), folded.
    Смежные уровни с одинаковым набором претендентов сливаются в один пот.
    """
    players = list(players)
    contribs = [(p.user_id, p.total) for p in players if p.total > 0]
    levels = sorted({amount for _, amount in contribs})

    pots: list[dict] = []
    prev = 0
    for level in levels:
        amount = sum(min(a, level) - min(a, prev) for _, a in contribs)
        eligible = [p.user_id for p in players if not p.folded and p.total >= level]
        if pots and eligible == pots[-1]["eligible"]:
            pots[-1]["amount"] += amount
        elif eligible:
            pots.append({"amount": amount, "eligible": eligible})
        prev = level
    return pots


def distribute(
    pots: list[dict], players: list, board: list[Card], odd_order: list[int]
) -> dict[int, int]:
    """Распределяет поты; возвращает {user_id: выигрыш}.

    `players` — как в build_pots, плюс поле cards (2 карты).
    `odd_order` — user_id в порядке мест, начиная слева от кнопки.
    """
    by_id = {p.user_id: p for p in players}
    winnings: dict[int, int] = {p.user_id: 0 for p in players}

    for pot in pots:
        contenders = [by_id[uid] for uid in pot["eligible"]]
        if not contenders:
            continue
        scores = {
            p.user_id: best_hand(list(p.cards) + list(board))[0] for p in contenders
        }
        top = max(scores.values())
        winners = [p for p in contenders if scores[p.user_id] == top]

        share = pot["amount"] // len(winners)
        remainder = pot["amount"] - share * len(winners)
        ordered = sorted(
            winners,
            key=lambda p: odd_order.index(p.user_id) if p.user_id in odd_order else len(odd_order),
        )
        for winner in ordered:
            winnings[winner.user_id] += share
        if remainder:
            winnings[ordered[0].user_id] += remainder

    return winnings
