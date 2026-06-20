"""
Poker hand terminology labels.

Categorizes hands into human-readable poker terms like:
- "The Nuts" (best possible hand on current board)
- "Set", "Trips", "Overpair", "Top Pair", etc.
- Draw labels: "Nut flush draw", "Open-ended straight draw", "Gutshot"
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import List, Optional, Tuple

from poker.evaluator import evaluate_7, evaluate_5, RANK_VALUE


def classify_hand(
    hole_cards: List[str],
    board_cards: List[str],
) -> dict:
    """
    Classify a player's hand into poker terminology.

    Returns:
        {
            "made_hand": str - description of current made hand
            "draws": list[str] - active draws
            "nuts_rank": int or None - 1 = nuts, 2 = second nuts, etc.
            "is_nuts": bool
        }
    """
    if not hole_cards or len(hole_cards) < 2:
        return {"made_hand": "", "draws": [], "nuts_rank": None, "is_nuts": False}

    all_cards = hole_cards + board_cards

    if len(board_cards) == 0:
        # Preflop: just describe the starting hand
        return {
            "made_hand": _preflop_label(hole_cards),
            "draws": [],
            "nuts_rank": None,
            "is_nuts": False,
        }

    # Get our hand score
    our_score, our_name, our_best = evaluate_7(all_cards)

    # Classify made hand with context
    made_hand = _classify_made_hand(hole_cards, board_cards, our_score, our_name)

    # Find draws (only on flop/turn)
    draws = []
    if len(board_cards) < 5:
        draws = _find_draws(hole_cards, board_cards)

    # Calculate nuts rank
    nuts_rank = _calculate_nuts_rank(hole_cards, board_cards, our_score)

    return {
        "made_hand": made_hand,
        "draws": draws,
        "nuts_rank": nuts_rank,
        "is_nuts": nuts_rank == 1,
    }


def _preflop_label(hole_cards: List[str]) -> str:
    """Label a preflop hand."""
    r1, r2 = hole_cards[0][0], hole_cards[1][0]
    s1, s2 = hole_cards[0][1], hole_cards[1][1]
    suited = s1 == s2

    if r1 == r2:
        name = _rank_name(r1)
        return f"Pocket {name}s"

    high = r1 if RANK_VALUE[r1] > RANK_VALUE[r2] else r2
    low = r2 if high == r1 else r1

    suffix = "suited" if suited else ""
    h_name = _rank_name(high)
    l_name = _rank_name(low)

    # Common nicknames
    if high == "A" and low == "K":
        return "Big Slick" + (" suited" if suited else "")
    if r1 == r2 == "A":
        return "Pocket Rockets"

    return f"{h_name}-{l_name}{' suited' if suited else ''}"


def _rank_name(r: str) -> str:
    names = {"A": "Ace", "K": "King", "Q": "Queen", "J": "Jack", "T": "Ten",
             "9": "Nine", "8": "Eight", "7": "Seven", "6": "Six",
             "5": "Five", "4": "Four", "3": "Three", "2": "Two"}
    return names.get(r, r)


def _classify_made_hand(
    hole_cards: List[str],
    board_cards: List[str],
    score: Tuple[int, List[int]],
    hand_name: str,
) -> str:
    """Provide detailed poker term for the made hand."""
    category = score[0]
    hole_ranks = [c[0] for c in hole_cards]
    board_ranks = [c[0] for c in board_cards]
    board_values = sorted([RANK_VALUE[r] for r in board_ranks], reverse=True)

    if category == 8:
        return "Straight Flush!"
    if category == 7:
        return "Quads"
    if category == 6:
        return "Full House"
    if category == 5:
        # Check if it's a flush using both hole cards, one, or board flush
        hole_suits = [c[1] for c in hole_cards]
        board_suits = [c[1] for c in board_cards]
        flush_suit = Counter(board_suits + hole_suits).most_common(1)[0][0]
        hole_in_flush = sum(1 for s in hole_suits if s == flush_suit)
        if hole_in_flush == 2:
            return "Flush (both cards)"
        elif hole_in_flush == 1:
            return "Flush (one card)"
        return "Board Flush"
    if category == 4:
        return "Straight"
    if category == 3:
        # Three of a kind: is it a set or trips?
        hole_rank_counts = Counter(hole_ranks)
        for rank, count in hole_rank_counts.items():
            if count == 2 and board_ranks.count(rank) >= 1:
                return "Set"  # pocket pair hit the board
        # Check if one hole card matches two on board
        for r in hole_ranks:
            if board_ranks.count(r) == 2:
                return "Trips"
        return "Three of a Kind"
    if category == 2:
        return "Two Pair"
    if category == 1:
        # One pair: categorize it
        pair_value = score[1][0]
        for r in hole_ranks:
            if RANK_VALUE[r] == pair_value:
                # Our hole card makes the pair
                if pair_value > board_values[0]:
                    return "Overpair"
                elif pair_value == board_values[0]:
                    return "Top Pair"
                elif len(board_values) > 1 and pair_value == board_values[1]:
                    return "Middle Pair"
                else:
                    return "Bottom Pair"
        # Pair is on the board
        return "Board Pair"
    if category == 0:
        # High card: check for overcards
        hole_values = [RANK_VALUE[r] for r in hole_ranks]
        overcards = sum(1 for v in hole_values if v > board_values[0])
        if overcards == 2:
            return "Two Overcards"
        elif overcards == 1:
            return "One Overcard"
        return "High Card"

    return hand_name


def _find_draws(hole_cards: List[str], board_cards: List[str]) -> List[str]:
    """Identify active draws."""
    draws = []
    all_cards = hole_cards + board_cards
    hole_suits = [c[1] for c in hole_cards]
    hole_ranks = [c[0] for c in hole_cards]
    all_suits = [c[1] for c in all_cards]
    all_values = [RANK_VALUE[c[0]] for c in all_cards]

    # Flush draw (4 to a flush)
    suit_counts = Counter(all_suits)
    for suit, count in suit_counts.items():
        if count == 4:
            # Check if hole cards contribute
            hole_in_suit = sum(1 for s in hole_suits if s == suit)
            if hole_in_suit > 0:
                # Is it the nut flush draw?
                hole_flush_values = [RANK_VALUE[c[0]] for c in hole_cards if c[1] == suit]
                if hole_flush_values and max(hole_flush_values) == 14:
                    draws.append("Nut flush draw")
                else:
                    draws.append("Flush draw")

    # Straight draws
    unique_vals = sorted(set(all_values))

    # Add ace-low (wheel)
    if 14 in unique_vals:
        unique_vals_with_low = sorted(set(unique_vals + [1]))
    else:
        unique_vals_with_low = unique_vals

    # Open-ended: 4 consecutive with room on both sides
    for i in range(len(unique_vals_with_low) - 3):
        seq = unique_vals_with_low[i:i + 4]
        if seq[-1] - seq[0] == 3:
            # Check both ends are possible (not blocked by board edge)
            above = seq[-1] + 1
            below = seq[0] - 1
            # Need at least one hole card in the sequence
            hole_vals = [RANK_VALUE[r] for r in hole_ranks]
            if 14 in hole_vals:
                hole_vals.append(1)
            if any(v in seq for v in hole_vals):
                if below >= 2 and above <= 14 and "Open-ended straight draw" not in draws:
                    draws.append("Open-ended straight draw")
                elif ("Gutshot" not in draws and
                      "Open-ended straight draw" not in draws):
                    draws.append("Gutshot")

    # Gutshot: 4 out of 5 with one gap
    if "Open-ended straight draw" not in draws:
        for start in range(1, 11):
            window = list(range(start, start + 5))
            have = [v for v in window if v in unique_vals_with_low]
            if len(have) == 4:
                hole_vals = [RANK_VALUE[r] for r in hole_ranks]
                if 14 in hole_vals:
                    hole_vals.append(1)
                if any(v in window for v in hole_vals) and "Gutshot" not in draws:
                    draws.append("Gutshot")
                    break

    return draws


def _calculate_nuts_rank(
    hole_cards: List[str],
    board_cards: List[str],
    our_score: Tuple[int, List[int]],
) -> Optional[int]:
    """
    Calculate where our hand ranks among all possible hands on this board.
    1 = the nuts (best possible), 2 = second nuts, etc.
    Returns None if board is empty or calculation not feasible.
    Only practical on turn/river (fewer combos to check).
    """
    if len(board_cards) < 4:
        # Too many combos on flop, skip
        return None

    # Build remaining deck
    known = set(hole_cards + board_cards)
    remaining = [r + s for s in "SHDC" for r in "AKQJT98765432" if r + s not in known]

    # Find all possible 2-card combos and their scores
    our_score_key = (our_score[0], tuple(our_score[1]))
    scores_better = set()

    better_count = 0
    for c1, c2 in combinations(remaining, 2):
        try:
            score, _, _ = evaluate_7([c1, c2] + board_cards)
            score_key = (score[0], tuple(score[1]))
            if score > our_score:
                if score_key not in scores_better:
                    better_count += 1
                    scores_better.add(score_key)
        except Exception:
            continue

        # Early exit if we're clearly not near the nuts
        if better_count > 10:
            return None

    return better_count + 1  # 1 = nuts, 2 = second nuts, etc.
