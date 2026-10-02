"""Раздача: конечный автомат торгов префлоп→флоп→терн→ривер→вскрытие.

Движок чистый: без Telegram, БД и asyncio. Серверный слой (runtime)
вызывает act()/legal_actions()/auto_act() и читает public_view()/result.

Правила, которые здесь зашиты:
- хедз-ап: дилер = SB и действует первым на префлопе, постфлопом первым BB;
- минимальный рейз — размером последнего полного повышения; короткий
  олл-ин не меняет минимум и не открывает торги заново (нельзя ререйзить);
- при выравнивании олл-инов борд добирается до ривера, карты вскрываются;
- нечётная фишка сплита — первому выигравшему слева от кнопки.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.game import pots as pots_engine
from app.game.cards import Card, Deck
from app.game.evaluator import best_hand, hand_name

NEXT_STREET = {"preflop": "flop", "flop": "turn", "turn": "river"}


class EngineError(Exception):
    """Нелегальное действие или нарушение состояния раздачи."""


@dataclass
class HandPlayer:
    user_id: int
    stack: int
    cards: list[Card] = field(default_factory=list)
    bet: int = 0  # ставка в текущем круге
    total: int = 0  # вклад за раздачу
    folded: bool = False
    all_in: bool = False

    @property
    def in_hand(self) -> bool:
        return not self.folded


class HandRunner:
    def __init__(
        self,
        players: list[HandPlayer],
        *,
        button: int,
        small_blind: int,
        big_blind: int,
        deck: Deck | None = None,
    ) -> None:
        if len(players) < 2:
            raise EngineError("нужно минимум 2 игрока")
        if not 0 <= button < len(players):
            raise EngineError("кнопка вне стола")

        self.players = players  # порядок мест
        self.button = button
        self.sb = small_blind
        self.bb = big_blind
        self.deck = deck if deck is not None else Deck()
        self.deck.shuffle()

        self.board: list[Card] = []
        self.street = "preflop"
        self.current_bet = 0
        self.min_increment = big_blind
        self.pending: set[int] = set()
        self.may_raise: set[int] = set()
        self.to_act: int | None = None
        self.revealed: dict[int, list[Card]] = {}
        self.result: dict | None = None
        # Сколько карт борда было видно, когда торги закончились олл-инами
        # (до ранаута) — нужно для поэтапного вскрытия на клиенте.
        self.board_visible_before_runout: int | None = None

        self._deal()

    # ── Публичный API ────────────────────────────────────────

    @property
    def pot_total(self) -> int:
        return sum(p.total for p in self.players)

    def legal_actions(self) -> dict:
        """Допустимые действия для текущего игрока (сервер — источник правды)."""
        if self.result is not None or self.to_act is None:
            return {}
        idx = self.to_act
        player = self.players[idx]
        out: dict = {"fold": True}
        to_call = self.current_bet - player.bet
        if to_call <= 0:
            out["check"] = True
        else:
            out["call"] = min(to_call, player.stack)
        max_total = player.bet + player.stack
        if idx in self.may_raise and max_total > self.current_bet:
            min_total = min(self.current_bet + self.min_increment, max_total)
            out["raise_to"] = [min_total, max_total]
        return out

    def act(self, user_id: int, action: str, amount: int | None = None) -> None:
        if self.result is not None:
            raise EngineError("раздача уже завершена")
        if self.to_act is None or self.players[self.to_act].user_id != user_id:
            raise EngineError("сейчас не твой ход")

        legal = self.legal_actions()
        idx = self.to_act
        player = self.players[idx]

        if action == "fold":
            player.folded = True
            self.pending.discard(idx)

        elif action == "check":
            if "check" not in legal:
                raise EngineError("чек невозможен: есть ставка")
            self.pending.discard(idx)

        elif action == "call":
            if "call" not in legal:
                raise EngineError("нечего уравнивать")
            pay = legal["call"]
            player.stack -= pay
            player.bet += pay
            player.total += pay
            if player.stack == 0:
                player.all_in = True
            self.pending.discard(idx)

        elif action in ("bet", "raise"):
            rng = legal.get("raise_to")
            if rng is None:
                raise EngineError("рейз невозможен")
            if amount is None:
                raise EngineError("укажи размер ставки")
            if not rng[0] <= amount <= rng[1]:
                raise EngineError(f"размер должен быть от {rng[0]} до {rng[1]}")
            pay = amount - player.bet
            player.stack -= pay
            player.bet = amount
            player.total += pay
            if player.stack == 0:
                player.all_in = True

            increment = amount - self.current_bet
            full = increment >= self.min_increment
            self.current_bet = amount
            able = {i for i, p in enumerate(self.players) if p.in_hand and not p.all_in}
            if full:
                self.min_increment = increment
                # полный рейз открывает торги заново для всех остальных
                self.pending = able - {idx}
                self.may_raise = able - {idx}
            else:
                # короткий олл-ин: остальным остаётся уравнять или сбросить
                self.pending = {
                    i for i in able if self.players[i].bet < amount
                } - {idx}
            self.pending.discard(idx)

        else:
            raise EngineError("неизвестное действие")

        # Действовал — право рейза исчерпано, пока не случится полный рейз.
        self.may_raise.discard(idx)
        self._after_action(idx)

    def auto_act(self, user_id: int) -> None:
        """Действие по таймауту: чек, если нет ставки, иначе фолд."""
        legal = self.legal_actions()
        if legal.get("check"):
            self.act(user_id, "check")
        else:
            self.act(user_id, "fold")

    def public_view(self) -> dict:
        """Публичное состояние раздачи (без закрытых карт)."""
        return {
            "street": self.street,
            "board": [c.code for c in self.board],
            "board_visible": (
                self.board_visible_before_runout
                if self.board_visible_before_runout is not None
                else len(self.board)
            ),
            "pot": self.pot_total,
            "current_bet": self.current_bet,
            "players": [
                {
                    "user_id": p.user_id,
                    "stack": p.stack,
                    "bet": p.bet,
                    "folded": p.folded,
                    "all_in": p.all_in,
                }
                for p in self.players
            ],
            "to_act": (
                self.players[self.to_act].user_id if self.to_act is not None else None
            ),
            "revealed": {
                uid: [c.code for c in cards] for uid, cards in self.revealed.items()
            },
            "result": self.result,
        }

    # ── Внутреннее ───────────────────────────────────────────

    def _next_index(self, i: int) -> int:
        return (i + 1) % len(self.players)

    def _next_alive_with_cards(self, i: int) -> int:
        for _ in range(len(self.players)):
            i = self._next_index(i)
            if self.players[i].in_hand:
                return i
        raise EngineError("не осталось игроков в раздаче")

    def _deal(self) -> None:
        n = len(self.players)
        for player in self.players:
            player.cards = self.deck.deal(2)

        if n == 2:
            sb_idx, bb_idx = self.button, self._next_index(self.button)
        else:
            sb_idx = self._next_index(self.button)
            bb_idx = self._next_index(sb_idx)
        self.sb_index, self.bb_index = sb_idx, bb_idx

        self._post_blind(sb_idx, self.sb)
        self._post_blind(bb_idx, self.bb)
        self.current_bet = self.bb
        self.min_increment = self.bb

        # Префлоп действует первый после BB (в хедз-апе это кнопка/SB).
        self._open_betting(self._next_index(bb_idx), include_matched=True)
        if self.to_act is None:
            self._close_street()

    def _post_blind(self, idx: int, amount: int) -> None:
        player = self.players[idx]
        pay = min(amount, player.stack)
        player.stack -= pay
        player.bet += pay
        player.total += pay
        if player.stack == 0:
            player.all_in = True

    def _open_betting(self, first_idx: int, *, include_matched: bool) -> None:
        able = {i for i, p in enumerate(self.players) if p.in_hand and not p.all_in}
        if include_matched:
            must = set(able)
        else:
            must = {i for i in able if self.players[i].bet < self.current_bet}
            if self.current_bet == 0 and len(able) >= 2:
                must = set(able)
        self.pending = must
        self.may_raise = set(must)
        self.to_act = self._pick_actor(first_idx)

    def _pick_actor(self, from_idx: int) -> int | None:
        if not self.pending:
            return None
        i = from_idx
        for _ in range(len(self.players)):
            if i in self.pending:
                return i
            i = self._next_index(i)
        return None

    def _after_action(self, idx: int) -> None:
        in_hand = [p for p in self.players if p.in_hand]
        if len(in_hand) == 1:
            self._award_uncontested(in_hand[0])
            return
        self.to_act = self._pick_actor(self._next_index(idx))
        if self.to_act is None:
            self._close_street()

    def _close_street(self) -> None:
        self.to_act = None
        self.pending = set()

        in_hand = [p for p in self.players if p.in_hand]
        able = [p for p in in_hand if not p.all_in]
        if len(in_hand) >= 2 and len(able) <= 1:
            # торгов больше не будет — фиксируем видимый борд и вскрываемся
            if self.board_visible_before_runout is None:
                self.board_visible_before_runout = len(self.board)
            for p in in_hand:
                self.revealed.setdefault(p.user_id, list(p.cards))

        if self.street == "river":
            self._showdown()
        else:
            self._start_street(NEXT_STREET[self.street])

    def _start_street(self, street: str) -> None:
        self.street = street
        for p in self.players:
            p.bet = 0
        self.current_bet = 0
        self.min_increment = self.bb
        if street == "flop":
            self.board += self.deck.deal(3)
        elif street in ("turn", "river"):
            self.board += self.deck.deal(1)
        self._open_betting(self._first_to_act_postflop(), include_matched=False)
        if self.to_act is None:
            self._close_street()

    def _first_to_act_postflop(self) -> int:
        return self._next_alive_with_cards(self.button)

    def _showdown(self) -> None:
        contenders = [p for p in self.players if p.in_hand]
        for p in contenders:
            self.revealed.setdefault(p.user_id, list(p.cards))

        pots = pots_engine.build_pots(self.players)
        n = len(self.players)
        odd_order = [
            self.players[(self.button + 1 + k) % n].user_id for k in range(n)
        ]
        winnings = pots_engine.distribute(pots, self.players, self.board, odd_order)
        by_id = {p.user_id: p for p in self.players}

        winners = [
            {
                "user_id": uid,
                "amount": amount,
                "hand": hand_name(
                    best_hand(list(by_id[uid].cards) + self.board)[0]
                ),
            }
            for uid, amount in winnings.items()
            if amount > 0
        ]
        self.street = "showdown"
        self.result = {
            "type": "showdown",
            "board": [c.code for c in self.board],
            "pot_total": self.pot_total,
            "pots": pots,
            "winners": winners,
        }

    def _award_uncontested(self, winner: HandPlayer) -> None:
        self.street = "finished"
        self.result = {
            "type": "uncontested",
            "board": [c.code for c in self.board],
            "pot_total": self.pot_total,
            "pots": [],
            "winners": [
                {"user_id": winner.user_id, "amount": self.pot_total, "hand": None}
            ],
        }
