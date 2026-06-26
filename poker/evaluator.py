from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import List, Tuple


RANK_VALUE = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

CATEGORY_NAME = {
    8: "Royal flush / straight flush",
    7: "Four of a kind",
    6: "Full house",
    5: "Flush",
    4: "Straight",
    3: "Three of a kind",
    2: "Two pair",
    1: "One pair",
    0: "High card",
}


def straight_high(values: list[int]) -> int | None:
    unique = sorted(set(values), reverse=True)

    # A-5 wheel straight.
    if {14, 5, 4, 3, 2}.issubset(set(unique)):
        return 5

    for i in range(len(unique) - 4):
        window = unique[i:i + 5]
        if window[0] - window[4] == 4:
            return window[0]

    return None


def evaluate_5(cards: tuple[str, ...]) -> tuple[tuple[int, list[int]], str]:
    values = [RANK_VALUE[c[0]] for c in cards]
    suits = [c[1] for c in cards]
    counts = Counter(values)

    is_flush = len(set(suits)) == 1
    s_high = straight_high(values)

    if is_flush and s_high:
        if s_high == 14:
            return (8, [14]), "Royal flush"
        return (8, [s_high]), "Straight flush"

    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)

    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(v for v in values if v != quad)
        return (7, [quad, kicker]), "Four of a kind"

    if groups[0][1] == 3 and groups[1][1] == 2:
        return (6, [groups[0][0], groups[1][0]]), "Full house"

    if is_flush:
        return (5, sorted(values, reverse=True)), "Flush"

    if s_high:
        return (4, [s_high]), "Straight"

    if groups[0][1] == 3:
        trip = groups[0][0]
        kickers = sorted([v for v in values if v != trip], reverse=True)
        return (3, [trip] + kickers), "Three of a kind"

    if groups[0][1] == 2 and groups[1][1] == 2:
        pairs = sorted([g[0] for g in groups if g[1] == 2], reverse=True)
        kicker = max(v for v in values if v not in pairs)
        return (2, pairs + [kicker]), "Two pair"

    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = sorted([v for v in values if v != pair], reverse=True)
        return (1, [pair] + kickers), "One pair"

    return (0, sorted(values, reverse=True)), "High card"


def evaluate_7(cards: List[str]) -> tuple[tuple[int, list[int]], str, list[str]]:
    if len(cards) < 5:
        raise ValueError("At least five cards are required.")

    best_score: tuple[int, list[int]] | None = None
    best_name = ""
    best_cards: tuple[str, ...] | None = None

    for combo in combinations(cards, 5):
        score, name = evaluate_5(combo)
        if best_score is None or score > best_score:
            best_score = score
            best_name = name
            best_cards = combo

    assert best_score is not None
    assert best_cards is not None

    return best_score, best_name, list(best_cards)


# ─── Human-readable hand detail (for kicker explanations) ───────────────────────

VALUE_NAME = {
    14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "Ten",
    9: "Nine", 8: "Eight", 7: "Seven", 6: "Six", 5: "Five",
    4: "Four", 3: "Three", 2: "Two",
}

VALUE_NAME_PLURAL = {
    14: "Aces", 13: "Kings", 12: "Queens", 11: "Jacks", 10: "Tens",
    9: "Nines", 8: "Eights", 7: "Sevens", 6: "Sixes", 5: "Fives",
    4: "Fours", 3: "Threes", 2: "Twos",
}


def describe_hand(score: tuple[int, list[int]], hand_name: str) -> str:
    """Generate a detailed human-readable description of a hand including kickers.
    
    Examples:
        "Flush, Ace-high"
        "Two pair, Kings and Tens, Ace kicker"
        "One pair, Aces, King kicker"
        "Full house, Queens full of Sevens"
        "Straight, King-high"
    """
    category = score[0]
    kickers = score[1]

    if category == 8:  # Straight flush / Royal flush
        return hand_name

    if category == 7:  # Four of a kind
        quad = VALUE_NAME.get(kickers[0], "?")
        kicker = VALUE_NAME.get(kickers[1], "?") if len(kickers) > 1 else ""
        return f"Four of a kind, {VALUE_NAME_PLURAL.get(kickers[0], quad)}" + (f", {kicker} kicker" if kicker else "")

    if category == 6:  # Full house
        trips = VALUE_NAME_PLURAL.get(kickers[0], "?")
        pair = VALUE_NAME_PLURAL.get(kickers[1], "?")
        return f"Full house, {trips} full of {pair}"

    if category == 5:  # Flush
        high = VALUE_NAME.get(kickers[0], "?") if kickers else "?"
        return f"Flush, {high}-high"

    if category == 4:  # Straight
        high = VALUE_NAME.get(kickers[0], "?") if kickers else "?"
        return f"Straight, {high}-high"

    if category == 3:  # Three of a kind
        trip = VALUE_NAME_PLURAL.get(kickers[0], "?")
        return f"Three of a kind, {trip}"

    if category == 2:  # Two pair
        high_pair = VALUE_NAME_PLURAL.get(kickers[0], "?")
        low_pair = VALUE_NAME_PLURAL.get(kickers[1], "?")
        kicker = VALUE_NAME.get(kickers[2], "") if len(kickers) > 2 else ""
        result = f"Two pair, {high_pair} and {low_pair}"
        if kicker:
            result += f", {kicker} kicker"
        return result

    if category == 1:  # One pair
        pair = VALUE_NAME_PLURAL.get(kickers[0], "?")
        kicker = VALUE_NAME.get(kickers[1], "") if len(kickers) > 1 else ""
        result = f"One pair, {pair}"
        if kicker:
            result += f", {kicker} kicker"
        return result

    # category == 0: High card
    high = VALUE_NAME.get(kickers[0], "?") if kickers else "?"
    return f"High card, {high}"
