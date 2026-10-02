"""Тесты валидации настроек стола (app.tables.settings)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tables.settings import TableSettings


def test_defaults() -> None:
    s = TableSettings()
    assert s.starting_stack == 1000
    assert (s.small_blind, s.big_blind) == (5, 10)
    assert s.rebuy_mode == "busted"
    assert s.chip_value == 1.0
    assert s.max_seats == 6
    assert s.action_timeout == 60


def test_bb_must_exceed_sb() -> None:
    with pytest.raises(ValidationError, match="больше SB"):
        TableSettings(small_blind=10, big_blind=10)


def test_bb_must_be_multiple_of_sb() -> None:
    with pytest.raises(ValidationError, match="кратен"):
        TableSettings(small_blind=3, big_blind=10)


def test_bb_cannot_exceed_stack() -> None:
    with pytest.raises(ValidationError, match="стартовый стек"):
        TableSettings(starting_stack=100, small_blind=100, big_blind=200)


def test_no_timeout_allowed() -> None:
    s = TableSettings(action_timeout=None)
    assert s.action_timeout is None


def test_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        TableSettings(action_timeout=5)
    with pytest.raises(ValidationError):
        TableSettings(action_timeout=301)


def test_chip_value_bounds() -> None:
    assert TableSettings(chip_value=0).chip_value == 0
    with pytest.raises(ValidationError):
        TableSettings(chip_value=-1)
    with pytest.raises(ValidationError):
        TableSettings(chip_value=100_001)


def test_seats_bounds() -> None:
    assert TableSettings(max_seats=2).max_seats == 2
    assert TableSettings(max_seats=9).max_seats == 9
    with pytest.raises(ValidationError):
        TableSettings(max_seats=1)
    with pytest.raises(ValidationError):
        TableSettings(max_seats=10)


def test_json_roundtrip() -> None:
    s = TableSettings(action_timeout=None, chip_value=0)
    restored = TableSettings.model_validate_json(s.model_dump_json())
    assert restored == s
