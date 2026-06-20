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
