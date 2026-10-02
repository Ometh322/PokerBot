"""Карты и колода. Ранги 0..12 (двойка..туз), масти 0..3 (♠ ♥ ♦ ♣)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "shdc"


@dataclass(frozen=True)
class Card:
    rank: int
    suit: int

    @property
    def code(self) -> str:
        """Двухсимвольный код для клиента/сериализации: 'As', 'Td', '2c'."""
        return RANKS[self.rank] + SUITS[self.suit]


def card(code: str) -> Card:
    return Card(RANKS.index(code[0]), SUITS.index(code[1]))


def all_cards() -> list[Card]:
    return [Card(rank, suit) for rank in range(13) for suit in range(4)]


class Deck:
    """Колода с криптостойким перемешиванием (системный генератор ОС)."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        self._cards = list(cards) if cards is not None else all_cards()

    def __len__(self) -> int:
        return len(self._cards)

    def shuffle(self) -> None:
        secrets.SystemRandom().shuffle(self._cards)

    def deal(self, n: int) -> list[Card]:
        if len(self._cards) < n:
            raise RuntimeError("в колоде не хватает карт")
        dealt = self._cards[:n]
        del self._cards[:n]
        return dealt
