"""Оценка рук: лучшие 5 из 7 карт и человеческие названия комбинаций.

Оценка — кортеж (категория, кикеры...), сравнение кортежей напрямую.
Категории: 0 старшая … 8 стрит-флеш. Для наших объёмов (один шоудаун
на раздачу) перебора 21 комбинации более чем достаточно.
"""

from __future__ import annotations

import itertools

from app.game.cards import Card

RANK_LABELS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def evaluate5(cards: list[Card]) -> tuple[int, ...]:
    ranks = sorted((c.rank for c in cards), reverse=True)
    flush = len({c.suit for c in cards}) == 1

    straight_high: int | None = None
    uniq = sorted(set(ranks), reverse=True)
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [12, 3, 2, 1, 0]:
            straight_high = 3  # колесо A-5-4-3-2: старшая — пятёрка

    counts: dict[int, int] = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))

    if straight_high is not None and flush:
        return (8, straight_high)
    if groups[0][1] == 4:
        return (7, groups[0][0], groups[1][0])
    if groups[0][1] == 3 and groups[1][1] == 2:
        return (6, groups[0][0], groups[1][0])
    if flush:
        return (5, *ranks)
    if straight_high is not None:
        return (4, straight_high)
    if groups[0][1] == 3:
        return (3, groups[0][0], groups[1][0], groups[2][0])
    if groups[0][1] == 2 and groups[1][1] == 2:
        return (2, groups[0][0], groups[1][0], groups[2][0])
    if groups[0][1] == 2:
        return (1, groups[0][0], groups[1][0], groups[2][0], groups[3][0])
    return (0, *ranks)


def best_hand(cards: list[Card]) -> tuple[tuple[int, ...], tuple[Card, ...]]:
    """Лучшие 5 из набора (5–7 карт): (оценка, комбинация)."""
    best_score: tuple[int, ...] | None = None
    best_combo: tuple[Card, ...] | None = None
    for combo in itertools.combinations(cards, 5):
        score = evaluate5(list(combo))
        if best_score is None or score > best_score:
            best_score, best_combo = score, combo
    assert best_score is not None and best_combo is not None
    return best_score, best_combo


def hand_name(score: tuple[int, ...]) -> str:
    label = lambda r: RANK_LABELS[r]  # noqa: E731 — компактный алиас
    cat = score[0]
    if cat == 8:
        return "флеш-рояль" if score[1] == 12 else f"стрит-флеш до {label(score[1])}"
    if cat == 7:
        return f"каре {label(score[1])}"
    if cat == 6:
        return f"фулл-хаус {label(score[1])} на {label(score[2])}"
    if cat == 5:
        return f"флеш до {label(score[1])}"
    if cat == 4:
        return f"стрит до {label(score[1])}"
    if cat == 3:
        return f"сет {label(score[1])}"
    if cat == 2:
        return f"две пары {label(score[1])} и {label(score[2])}"
    if cat == 1:
        return f"пара {label(score[1])}"
    return f"старшая {label(score[1])}"


def preflop_name(cards: list[Card]) -> str:
    """Подсказка для двух карманных карт (до выхода борда)."""
    if len(cards) != 2:
        return ""
    hi, lo = sorted(cards, key=lambda c: c.rank, reverse=True)
    name_hi, name_lo = RANK_LABELS[hi.rank], RANK_LABELS[lo.rank]
    if hi.rank == lo.rank:
        return f"карманная пара {name_hi}"
    if hi.suit == lo.suit:
        return f"{name_hi}{name_lo} одномастные"
    return f"{name_hi}{name_lo} разномастные"
