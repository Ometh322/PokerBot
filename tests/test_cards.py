"""Тесты карт и колоды."""

from __future__ import annotations

import pytest

from app.game.cards import Card, Deck, all_cards, card


def test_code_roundtrip() -> None:
    for c in all_cards():
        assert card(c.code) == c


def test_deck_deals_all_unique() -> None:
    deck = Deck()
    deck.shuffle()
    dealt = deck.deal(52)
    assert len({c.code for c in dealt}) == 52
    assert len(deck) == 0


def test_deck_raises_when_empty() -> None:
    deck = Deck()
    deck.shuffle()
    deck.deal(52)
    with pytest.raises(RuntimeError):
        deck.deal(1)


def test_deterministic_deck() -> None:
    # Подмена колоды позволяет писать детерминированные тесты раздач.
    cards = [card("As"), card("Kh"), card("Qd"), card("Jc"), card("Ts")]
    deck = Deck(cards)
    assert [c.code for c in deck.deal(3)] == ["As", "Kh", "Qd"]


def test_card_equality() -> None:
    assert Card(12, 0) == card("As")
    assert Card(12, 1) != card("As")
