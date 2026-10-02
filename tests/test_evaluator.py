"""Тесты оценки рук и названий комбинаций."""

from __future__ import annotations

from app.game.cards import card
from app.game.evaluator import best_hand, evaluate5, hand_name, preflop_name


def cards(codes: str) -> list:
    return [card(code) for code in codes.split()]


def test_category_order() -> None:
    royal = evaluate5(cards("As Ks Qs Js Ts"))
    quads = evaluate5(cards("9c 9d 9h 9s 2c"))
    full = evaluate5(cards("8c 8d 8h 7c 7d"))
    flush = evaluate5(cards("Ac Jc 9c 6c 2c"))
    straight = evaluate5(cards("9c 8d 7h 6s 5c"))
    trips = evaluate5(cards("7c 7d 7h Kc 2c"))
    two_pair = evaluate5(cards("Ac Ad Kh Ks 2c"))
    pair = evaluate5(cards("Ac Ad Kh Qs 2c"))
    high = evaluate5(cards("Ac Jd 9h 6s 2c"))
    assert royal > quads > full > flush > straight > trips > two_pair > pair > high


def test_ace_to_five_straight() -> None:
    wheel = evaluate5(cards("Ac 2d 3h 4s 5c"))
    assert wheel[0] == 4
    assert wheel[1] == 3  # старшая карта колеса — пятёрка
    king_high = evaluate5(cards("Kc Qd Jh Ts 9c"))
    assert king_high[0] == 4 and king_high[1] == 11
    assert king_high > wheel  # колесо — младший из стритов
    assert wheel > evaluate5(cards("Ac Ad Kh Qs Jc"))  # но стрит старше пары


def test_ace_to_five_not_flush_here() -> None:
    score = evaluate5(cards("Ad 2d 3d 4d 5d"))
    assert score[0] == 8  # стрит-флеш (стальное колесо)


def test_kickers_decide() -> None:
    strong = evaluate5(cards("Ac Ad Kh Qs Jc"))
    weak = evaluate5(cards("Ac Ad Kh Qs 9c"))
    assert strong > weak


def test_best7_picks_best_five() -> None:
    score, combo = best_hand(cards("As Ks Qs Js Ts 9s 2c"))
    assert score[0] == 8
    assert {c.code for c in combo} == {"As", "Ks", "Qs", "Js", "Ts"}


def test_best7_pair_on_board_with_kicker() -> None:
    # пара тузов на борде + король в руке против пары на борде с дамой
    score1, _ = best_hand(cards("Ah Ad Kc 7s 7d 2h 3c"))
    score2, _ = best_hand(cards("Ah Ad Qc 7s 7d 2h 3c"))
    assert score1[0] == 2 and score2[0] == 2
    assert score1 > score2


def test_hand_names() -> None:
    assert hand_name(evaluate5(cards("As Ks Qs Js Ts"))) == "флеш-рояль"
    assert hand_name(evaluate5(cards("9c 9d 9h 9s 2c"))) == "каре 9"
    assert hand_name(evaluate5(cards("8c 8d 8h 7c 7d"))) == "фулл-хаус 8 на 7"
    assert hand_name(evaluate5(cards("Ac Jc 9c 6c 2c"))) == "флеш до A"
    assert hand_name(evaluate5(cards("9c 8d 7h 6s 5c"))) == "стрит до 9"
    assert hand_name(evaluate5(cards("7c 7d 7h Kc 2c"))) == "сет 7"
    assert hand_name(evaluate5(cards("Ac Ad Kh Ks 2c"))) == "две пары A и K"
    assert hand_name(evaluate5(cards("Ac Ad Kh Qs 2c"))) == "пара A"
    assert hand_name(evaluate5(cards("Ac Jd 9h 6s 2c"))) == "старшая A"


def test_preflop_names() -> None:
    assert preflop_name(cards("Kh Kd")) == "карманная пара K"
    assert preflop_name(cards("As 2s")) == "A2 одномастные"
    assert preflop_name(cards("Kc Qh")) == "KQ разномастные"
    assert preflop_name(cards("Ah")) == ""
