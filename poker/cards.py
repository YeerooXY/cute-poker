from __future__ import annotations

import secrets
from typing import List


SUITS = ["S", "H", "D", "C"]
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

SUIT_SYMBOLS = {
    "S": "♠",
    "H": "♥",
    "D": "♦",
    "C": "♣",
}

RANK_DISPLAY = {
    "T": "10",
    "J": "J",
    "Q": "Q",
    "K": "K",
    "A": "A",
    "9": "9",
    "8": "8",
    "7": "7",
    "6": "6",
    "5": "5",
    "4": "4",
    "3": "3",
    "2": "2",
}


def new_deck() -> List[str]:
    deck = [rank + suit for suit in SUITS for rank in RANKS]
    secure_shuffle(deck)
    return deck


def secure_shuffle(deck: List[str]) -> None:
    # Fisher-Yates shuffle using cryptographic randomness.
    for i in range(len(deck) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        deck[i], deck[j] = deck[j], deck[i]


def display_card(card: str) -> str:
    if card == "BACK":
        return "🂠"
    rank = card[0]
    suit = card[1]
    return f"{RANK_DISPLAY[rank]}{SUIT_SYMBOLS[suit]}"


def display_cards(cards: list[str]) -> list[str]:
    return [display_card(c) for c in cards]
