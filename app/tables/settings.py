"""Валидация настроек стола (правила — PLAN.md, раздел 5)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RebuyMode = Literal["off", "busted", "anytime"]


class TableSettings(BaseModel):
    starting_stack: int = Field(default=1000, ge=100, le=1_000_000)
    small_blind: int = Field(default=5, ge=1, le=10_000)
    big_blind: int = Field(default=10, ge=2, le=20_000)
    rebuy_mode: RebuyMode = "busted"
    # Условная цена фишки: 0 = «играем просто так».
    chip_value: float = Field(default=1.0, ge=0, le=10_000)
    max_seats: int = Field(default=6, ge=2, le=9)
    # Таймер хода в секундах; None — играть без таймера.
    action_timeout: int | None = Field(default=60, ge=10, le=300)

    @model_validator(mode="after")
    def _check_blinds(self) -> "TableSettings":
        if self.big_blind <= self.small_blind:
            raise ValueError("блайнды: BB должен быть больше SB")
        if self.big_blind % self.small_blind != 0:
            raise ValueError("блайнды: BB должен быть кратен SB")
        if self.big_blind > self.starting_stack:
            raise ValueError("блайнды: BB не может превышать стартовый стек")
        return self
