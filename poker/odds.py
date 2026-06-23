"""
Hybrid equity calculator with street-specific strategies.

- Preflop: Lookup table (169 canonical hands)
- Flop: Monte Carlo with reduced simulations (300)
- Turn: Exact enumeration (opponent combos × remaining river cards)
- River: Exact enumeration (opponent combos only)

Also provides current_strength and the combined calculate_player_odds for UI.
"""

from __future__ import annotations

import random
from functools import lru_cache
from itertools import combinations
from typing import List, Optional

from poker.evaluator import evaluate_7


SUITS = ["S", "H", "D", "C"]
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
FULL_DECK = [r + s for s in SUITS for r in RANKS]

# Rank ordering for canonical hand notation (higher rank first)
_RANK_ORDER = {r: i for i, r in enumerate(RANKS)}  # A=0, K=1, ..., 2=12


# ─── 169 Hand Classes & Category Mapping ──────────────────────────────────────


def _generate_hand_classes_169() -> list:
    """Generate all 169 canonical hand classes.

    13 pocket pairs + 78 suited combos + 78 offsuit combos = 169 total.
    """
    classes = []
    # Pocket pairs
    for r in RANKS:
        classes.append(r + r)
    # Suited and offsuit combos (higher rank first)
    for i, r1 in enumerate(RANKS):
        for r2 in RANKS[i + 1:]:
            classes.append(r1 + r2 + "s")
            classes.append(r1 + r2 + "o")
    return classes


HAND_CLASSES_169: list = _generate_hand_classes_169()

# Category-to-Hand_Classes mapping (Requirement 8.3)
# Maps the 6 range categories to sets of specific hand classes.
_PREMIUM_HANDS: set = {"AA", "KK", "QQ", "JJ", "AKs", "AKo"}

_STRONG_HANDS: set = {"TT", "99", "AQs", "AQo", "AJs", "KQs"}

_PLAYABLE_HANDS: set = {"88", "77", "ATs", "KJs", "QJs", "JTs", "KQo", "AJo"}

_MARGINAL_HANDS: set = {
    "66", "55",
    "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
    "KTs", "QTs", "J9s", "T9s",
}

_SPECULATIVE_HANDS: set = {
    "44", "33", "22",
    "98s", "87s", "76s", "65s", "54s",
    "97s", "86s", "75s", "64s",
}

# Trash = all remaining 169 hand classes not in any other category
_TRASH_HANDS: set = (
    set(HAND_CLASSES_169)
    - _PREMIUM_HANDS
    - _STRONG_HANDS
    - _PLAYABLE_HANDS
    - _MARGINAL_HANDS
    - _SPECULATIVE_HANDS
)

CATEGORY_TO_HAND_CLASSES: dict = {
    "premium": _PREMIUM_HANDS,
    "strong": _STRONG_HANDS,
    "playable": _PLAYABLE_HANDS,
    "marginal": _MARGINAL_HANDS,
    "speculative": _SPECULATIVE_HANDS,
    "trash": _TRASH_HANDS,
}

# Assertions to verify correctness at import time
assert len(HAND_CLASSES_169) == 169, f"Expected 169 hand classes, got {len(HAND_CLASSES_169)}"
_all_categorized = (
    _PREMIUM_HANDS | _STRONG_HANDS | _PLAYABLE_HANDS
    | _MARGINAL_HANDS | _SPECULATIVE_HANDS | _TRASH_HANDS
)
assert _all_categorized == set(HAND_CLASSES_169), "Categories don't cover all 169 hand classes"
assert (
    len(_PREMIUM_HANDS) + len(_STRONG_HANDS) + len(_PLAYABLE_HANDS)
    + len(_MARGINAL_HANDS) + len(_SPECULATIVE_HANDS) + len(_TRASH_HANDS)
) == 169, "Categories overlap — some hand class appears in multiple categories"


# ─── Preflop Lookup Table ──────────────────────────────────────────────────────

# fmt: off
PREFLOP_EQUITY_1OPP = {
    "AA": 0.85, "KK": 0.82, "QQ": 0.80, "JJ": 0.77, "TT": 0.75,
    "99": 0.72, "88": 0.69, "77": 0.66, "66": 0.63, "55": 0.60,
    "44": 0.57, "33": 0.54, "22": 0.50,
    "AKs": 0.67, "AQs": 0.66, "AJs": 0.65, "ATs": 0.64, "A9s": 0.62,
    "A8s": 0.61, "A7s": 0.60, "A6s": 0.59, "A5s": 0.59, "A4s": 0.58,
    "A3s": 0.57, "A2s": 0.56,
    "AKo": 0.65, "AQo": 0.64, "AJo": 0.63, "ATo": 0.62, "A9o": 0.59,
    "A8o": 0.58, "A7o": 0.57, "A6o": 0.56, "A5o": 0.56, "A4o": 0.55,
    "A3o": 0.54, "A2o": 0.53,
    "KQs": 0.63, "KJs": 0.62, "KTs": 0.61, "K9s": 0.59, "K8s": 0.57,
    "K7s": 0.56, "K6s": 0.55, "K5s": 0.54, "K4s": 0.53, "K3s": 0.52, "K2s": 0.51,
    "KQo": 0.61, "KJo": 0.60, "KTo": 0.59, "K9o": 0.56, "K8o": 0.54,
    "K7o": 0.53, "K6o": 0.52, "K5o": 0.51, "K4o": 0.50, "K3o": 0.49, "K2o": 0.48,
    "QJs": 0.60, "QTs": 0.59, "Q9s": 0.57, "Q8s": 0.55, "Q7s": 0.54,
    "Q6s": 0.53, "Q5s": 0.52, "Q4s": 0.51, "Q3s": 0.50, "Q2s": 0.49,
    "QJo": 0.58, "QTo": 0.57, "Q9o": 0.54, "Q8o": 0.52, "Q7o": 0.50,
    "Q6o": 0.49, "Q5o": 0.48, "Q4o": 0.47, "Q3o": 0.46, "Q2o": 0.45,
    "JTs": 0.57, "J9s": 0.55, "J8s": 0.53, "J7s": 0.52, "J6s": 0.50,
    "J5s": 0.49, "J4s": 0.48, "J3s": 0.47, "J2s": 0.46,
    "JTo": 0.55, "J9o": 0.53, "J8o": 0.50, "J7o": 0.48, "J6o": 0.46,
    "J5o": 0.45, "J4o": 0.44, "J3o": 0.43, "J2o": 0.42,
    "T9s": 0.54, "T8s": 0.52, "T7s": 0.50, "T6s": 0.48, "T5s": 0.47,
    "T4s": 0.46, "T3s": 0.45, "T2s": 0.44,
    "T9o": 0.52, "T8o": 0.49, "T7o": 0.47, "T6o": 0.45, "T5o": 0.43,
    "T4o": 0.42, "T3o": 0.41, "T2o": 0.40,
    "98s": 0.51, "97s": 0.49, "96s": 0.47, "95s": 0.45, "94s": 0.43,
    "93s": 0.42, "92s": 0.41,
    "98o": 0.49, "97o": 0.46, "96o": 0.44, "95o": 0.41, "94o": 0.39,
    "93o": 0.38, "92o": 0.37,
    "87s": 0.49, "86s": 0.47, "85s": 0.44, "84s": 0.42, "83s": 0.40, "82s": 0.39,
    "87o": 0.47, "86o": 0.44, "85o": 0.41, "84o": 0.38, "83o": 0.36, "82o": 0.35,
    "76s": 0.47, "75s": 0.45, "74s": 0.42, "73s": 0.40, "72s": 0.38,
    "76o": 0.44, "75o": 0.42, "74o": 0.38, "73o": 0.36, "72o": 0.34,
    "65s": 0.45, "64s": 0.43, "63s": 0.40, "62s": 0.38,
    "65o": 0.43, "64o": 0.39, "63o": 0.36, "62o": 0.34,
    "54s": 0.44, "53s": 0.41, "52s": 0.39,
    "54o": 0.40, "53o": 0.37, "52o": 0.35,
    "43s": 0.40, "42s": 0.38, "43o": 0.36, "42o": 0.34,
    "32s": 0.36, "32o": 0.32,
}
# fmt: on


def _cards_to_canonical(hero_cards: List[str]) -> str:
    """Convert two hole cards (e.g. ['AH', 'KS']) to canonical notation (e.g. 'AKo')."""
    r1, s1 = hero_cards[0][0], hero_cards[0][1]
    r2, s2 = hero_cards[1][0], hero_cards[1][1]

    # Order by rank (higher first)
    if _RANK_ORDER[r1] > _RANK_ORDER[r2]:
        r1, r2 = r2, r1
        s1, s2 = s2, s1

    if r1 == r2:
        return r1 + r2  # Pocket pair: "AA", "KK", etc.
    elif s1 == s2:
        return r1 + r2 + "s"  # Suited: "AKs"
    else:
        return r1 + r2 + "o"  # Offsuit: "AKo"


def preflop_equity_lookup(hero_cards: List[str], num_opponents: int) -> dict:
    """
    Instant preflop equity from lookup table.

    Uses exponential decay model for multi-opponent scaling:
    equity_vs_n ≈ equity_vs_1 * (0.92 ^ (n-1))
    """
    canonical = _cards_to_canonical(hero_cards)
    base_equity = PREFLOP_EQUITY_1OPP.get(canonical, 0.45)  # Default to slightly below average

    # Scale for multiple opponents
    if num_opponents > 1:
        equity = base_equity * (0.92 ** (num_opponents - 1))
    else:
        equity = base_equity

    return {
        "win_pct": round(equity * 0.9, 4),  # Approximate: most equity comes from wins
        "tie_pct": round(equity * 0.1, 4),  # Small tie fraction
        "loss_pct": round(1.0 - equity, 4),
        "equity": round(equity, 4),
    }


# ─── Exact Enumeration (River & Turn) ─────────────────────────────────────────


def _eval_score(cards: List[str]) -> tuple:
    """Evaluate the best 5-card hand from available cards (5, 6, or 7)."""
    score, _, _ = evaluate_7(cards)
    return score


@lru_cache(maxsize=256)
def _river_equity_cached(hero_cards: tuple, board: tuple, num_opponents: int) -> tuple:
    """Cached river equity calculation. Returns (equity, win_pct, tie_pct)."""
    hero_cards_list = list(hero_cards)
    board_list = list(board)
    known = set(hero_cards_list + board_list)
    remaining = [c for c in FULL_DECK if c not in known]

    hero_score = _eval_score(hero_cards_list + board_list)

    wins = 0
    ties = 0
    total = 0

    if num_opponents == 1:
        # Simple: compare hero vs each possible opponent hand
        for opp_combo in combinations(remaining, 2):
            opp_score = _eval_score(list(opp_combo) + board_list)
            total += 1
            if hero_score > opp_score:
                wins += 1
            elif hero_score == opp_score:
                ties += 1
    else:
        # Multiple opponents: sample a subset of multi-opponent scenarios
        # For exact multi-opponent we'd need C(45,2) * C(43,2) * ... which is too large
        # Use single-opponent exact as a base and apply scaling
        for opp_combo in combinations(remaining, 2):
            opp_score = _eval_score(list(opp_combo) + board_list)
            total += 1
            if hero_score > opp_score:
                wins += 1
            elif hero_score == opp_score:
                ties += 1

    equity = (wins + ties * 0.5) / total if total > 0 else 0.5

    # Scale for multiple opponents (hero must beat ALL opponents)
    if num_opponents > 1:
        # Approximate: P(beat all n) ≈ P(beat 1)^n (slightly generous, use 0.9 exponent)
        equity = equity ** (1 + 0.4 * (num_opponents - 1))

    return (equity, wins / total if total > 0 else 0.0, ties / total if total > 0 else 0.0)


def river_equity_exact(hero_cards: List[str], board: List[str], num_opponents: int) -> dict:
    """Exact equity on the river via full enumeration of opponent hands."""
    equity, win_pct, tie_pct = _river_equity_cached(
        tuple(hero_cards), tuple(board), num_opponents
    )
    return {
        "win_pct": round(win_pct, 4),
        "tie_pct": round(tie_pct, 4),
        "loss_pct": round(1.0 - win_pct - tie_pct, 4),
        "equity": round(equity, 4),
    }


@lru_cache(maxsize=256)
def _turn_equity_cached(hero_cards: tuple, board: tuple, num_opponents: int) -> tuple:
    """Cached turn equity calculation. Returns (equity, win_pct, tie_pct)."""
    hero_cards_list = list(hero_cards)
    board_list = list(board)
    known = set(hero_cards_list + board_list)
    remaining = [c for c in FULL_DECK if c not in known]

    total_equity = 0.0
    total_wins = 0.0
    total_ties = 0.0
    river_count = 0

    for river_card in remaining:
        full_board = board_list + [river_card]
        river_remaining = [c for c in remaining if c != river_card]

        hero_score = _eval_score(hero_cards_list + full_board)

        wins = 0
        ties = 0
        combos = 0

        for opp_combo in combinations(river_remaining, 2):
            opp_score = _eval_score(list(opp_combo) + full_board)
            combos += 1
            if hero_score > opp_score:
                wins += 1
            elif hero_score == opp_score:
                ties += 1

        if combos > 0:
            total_equity += (wins + ties * 0.5) / combos
            total_wins += wins / combos
            total_ties += ties / combos
        river_count += 1

    equity = total_equity / river_count if river_count > 0 else 0.5
    win_pct = total_wins / river_count if river_count > 0 else 0.0
    tie_pct = total_ties / river_count if river_count > 0 else 0.0

    # Scale for multiple opponents
    if num_opponents > 1:
        equity = equity ** (1 + 0.4 * (num_opponents - 1))

    return (equity, win_pct, tie_pct)


def turn_equity_exact(hero_cards: List[str], board: List[str], num_opponents: int) -> dict:
    """Exact equity on the turn via enumeration of river cards × opponent hands."""
    equity, win_pct, tie_pct = _turn_equity_cached(
        tuple(hero_cards), tuple(board), num_opponents
    )
    return {
        "win_pct": round(win_pct, 4),
        "tie_pct": round(tie_pct, 4),
        "loss_pct": round(1.0 - win_pct - tie_pct, 4),
        "equity": round(equity, 4),
    }


# ─── Monte Carlo (Flop fallback) ──────────────────────────────────────────────


def _make_deck_without(exclude: List[str]) -> List[str]:
    """Create a deck without the specified cards."""
    exclude_set = set(exclude)
    return [c for c in FULL_DECK if c not in exclude_set]


def estimate_equity(
    hero_cards: List[str],
    board_cards: List[str],
    num_opponents: int = 1,
    simulations: int = 300,
) -> dict:
    """
    Monte Carlo equity calculation.

    Deals out remaining board cards and random opponent hands,
    then evaluates who wins.

    Returns:
        win_pct: fraction of simulations hero wins outright
        tie_pct: fraction where hero ties for best
        loss_pct: fraction where hero loses
        equity: expected share of pot (wins + split ties)
    """
    if num_opponents < 1:
        return {"win_pct": 1.0, "tie_pct": 0.0, "loss_pct": 0.0, "equity": 1.0}

    known = hero_cards + board_cards
    remaining_deck = _make_deck_without(known)
    cards_to_deal = 5 - len(board_cards)  # How many community cards still needed

    wins = 0
    ties = 0
    losses = 0
    equity = 0.0

    for _ in range(simulations):
        deck = remaining_deck[:]
        random.shuffle(deck)

        idx = 0
        # Deal opponent hands
        opponents = []
        for _ in range(num_opponents):
            opponents.append([deck[idx], deck[idx + 1]])
            idx += 2

        # Deal remaining board
        future_board = board_cards[:]
        for _ in range(cards_to_deal):
            future_board.append(deck[idx])
            idx += 1

        # Evaluate
        hero_score = _eval_score(hero_cards + future_board)
        opp_scores = [_eval_score(opp + future_board) for opp in opponents]

        best_opp = max(opp_scores)

        if hero_score > best_opp:
            wins += 1
            equity += 1.0
        elif hero_score == best_opp:
            # Count how many tied at hero's level (hero + tied opponents)
            tied_count = 1 + sum(1 for s in opp_scores if s == hero_score)
            ties += 1
            equity += 1.0 / tied_count
        else:
            losses += 1

    n = simulations
    return {
        "win_pct": round(wins / n, 4),
        "tie_pct": round(ties / n, 4),
        "loss_pct": round(losses / n, 4),
        "equity": round(equity / n, 4),
    }


# ─── Hybrid Entry Point ───────────────────────────────────────────────────────


def calculate_equity_hybrid(hero_cards: List[str], board: List[str], num_opponents: int, simulations: int = 300) -> dict:
    """
    Smart equity calculation using the best method for the current street.

    - Preflop (0 board cards): instant lookup table
    - Flop (3 board cards): Monte Carlo (configurable sims)
    - Turn (4 board cards): exact for heads-up, Monte Carlo for multiway
    - River (5 board cards): exact enumeration
    """
    if num_opponents < 1:
        return {"win_pct": 1.0, "tie_pct": 0.0, "loss_pct": 0.0, "equity": 1.0}

    board_len = len(board)
    if board_len == 0:
        return preflop_equity_lookup(hero_cards, num_opponents)
    elif board_len == 5:
        return river_equity_exact(hero_cards, board, num_opponents)
    elif board_len == 4:
        # Turn: exact for heads-up, Monte Carlo for multiway
        if num_opponents == 1:
            return turn_equity_exact(hero_cards, board, num_opponents)
        return estimate_equity(hero_cards, board, num_opponents, simulations=simulations)
    else:  # flop, 3 cards
        return estimate_equity(hero_cards, board, num_opponents, simulations=simulations)


# ─── Current Strength (unchanged logic) ───────────────────────────────────────


def estimate_current_strength(
    hero_cards: List[str],
    board_cards: List[str],
    num_opponents: int = 1,
    simulations: int = 300,
) -> dict:
    """
    Current hand strength: how often hero is ahead RIGHT NOW.

    Only considers the cards already on the board (no future cards).
    Only meaningful postflop (when board has 3+ cards).

    Returns:
        ahead_pct: fraction hero is currently best
        tied_pct: fraction hero ties
        behind_pct: fraction hero is behind
    """
    if len(board_cards) < 3:
        # Preflop: current strength is meaningless
        return {"ahead_pct": 0.0, "tied_pct": 0.0, "behind_pct": 0.0}

    if num_opponents < 1:
        return {"ahead_pct": 1.0, "tied_pct": 0.0, "behind_pct": 0.0}

    known = hero_cards + board_cards
    remaining_deck = _make_deck_without(known)

    hero_score = _eval_score(hero_cards + board_cards)

    ahead = 0
    tied = 0
    behind = 0

    # For turn/river: enumerate or sample opponent hands
    if len(board_cards) >= 4:
        if num_opponents == 1:
            # Heads-up: exact enumeration of all opponent combos
            for opp_combo in combinations(remaining_deck, 2):
                opp_score = _eval_score(list(opp_combo) + board_cards)
                if hero_score > opp_score:
                    ahead += 1
                elif hero_score == opp_score:
                    tied += 1
                else:
                    behind += 1
            n = ahead + tied + behind
        else:
            # Multiway: Monte Carlo sampling of all opponents
            for _ in range(simulations):
                deck = remaining_deck[:]
                random.shuffle(deck)
                idx = 0
                best_opp_score = None
                for _ in range(num_opponents):
                    if idx + 1 >= len(deck):
                        break
                    opp_cards = [deck[idx], deck[idx + 1]]
                    idx += 2
                    opp_score = _eval_score(opp_cards + board_cards)
                    if best_opp_score is None or opp_score > best_opp_score:
                        best_opp_score = opp_score
                if best_opp_score is None:
                    continue
                if hero_score > best_opp_score:
                    ahead += 1
                elif hero_score == best_opp_score:
                    tied += 1
                else:
                    behind += 1
            n = ahead + tied + behind
    else:
        # Flop: Monte Carlo sampling for current strength
        for _ in range(simulations):
            deck = remaining_deck[:]
            random.shuffle(deck)

            idx = 0
            best_opp_score = None
            for _ in range(num_opponents):
                opp_cards = [deck[idx], deck[idx + 1]]
                idx += 2
                opp_score = _eval_score(opp_cards + board_cards)
                if best_opp_score is None or opp_score > best_opp_score:
                    best_opp_score = opp_score

            if hero_score > best_opp_score:
                ahead += 1
            elif hero_score == best_opp_score:
                tied += 1
            else:
                behind += 1
        n = simulations

    if n == 0:
        return {"ahead_pct": 0.0, "tied_pct": 0.0, "behind_pct": 0.0}

    return {
        "ahead_pct": round(ahead / n, 4),
        "tied_pct": round(tied / n, 4),
        "behind_pct": round(behind / n, 4),
    }


# ─── Range-Aware Equity Calculator ────────────────────────────────────────────


def _normalize_weights(combo_range: dict) -> dict:
    """Normalize combo_range weights so they sum to 1.0.

    Args:
        combo_range: dict mapping hand_class -> weight (any non-negative floats)

    Returns:
        dict with same keys, weights scaled to sum to 1.0.
        If all weights are 0, returns uniform distribution over all entries.
    """
    total = sum(combo_range.values())
    if total <= 0:
        # Uniform distribution
        n = len(combo_range)
        return {k: 1.0 / n for k in combo_range} if n > 0 else {}
    return {k: v / total for k, v in combo_range.items()}


def _range_estimate_to_combo_range(range_estimate) -> dict:
    """Convert a 6-category RangeEstimate into a 169 hand-class combo_range.

    Each hand class receives its category's weight directly. This means a
    premium weight of 0.85 assigns 0.85 to every hand class in the premium
    category. Sampling is later weighted by the number of combos each hand
    class expands to (pairs=6, suited=4, offsuit=12), which naturally handles
    the probability distribution.

    Args:
        range_estimate: A RangeEstimate dataclass with premium, strong, playable,
                        marginal, speculative, and trash float fields (0.0-1.0).

    Returns:
        dict[str, float] with 169 entries mapping each hand class to a weight.
    """
    combo_range = {}
    category_weights = {
        "premium": range_estimate.premium,
        "strong": range_estimate.strong,
        "playable": range_estimate.playable,
        "marginal": range_estimate.marginal,
        "speculative": range_estimate.speculative,
        "trash": range_estimate.trash,
    }
    for category, hand_classes in CATEGORY_TO_HAND_CLASSES.items():
        weight = category_weights[category]
        for hc in hand_classes:
            combo_range[hc] = weight
    return combo_range


def _hand_class_to_combos(hand_class: str) -> List[tuple]:
    """Expand a canonical hand class (e.g., 'AKs', 'AA', '72o') into all specific card combos.

    Returns a list of tuples, each containing two card strings (e.g., ('AH', 'KH')).

    - Pocket pairs (e.g., "AA") → 6 combos (4 choose 2 suits)
    - Suited hands (e.g., "AKs") → 4 combos (one per suit)
    - Offsuit hands (e.g., "AKo") → 12 combos (4×3 suit pairs where suits differ)
    """
    # Parse the hand class
    if len(hand_class) == 2:
        # Pocket pair: e.g., "AA"
        rank = hand_class[0]
        combos = []
        for i, s1 in enumerate(SUITS):
            for s2 in SUITS[i + 1:]:
                combos.append((rank + s1, rank + s2))
        return combos
    elif len(hand_class) == 3:
        r1 = hand_class[0]
        r2 = hand_class[1]
        suited = hand_class[2] == "s"

        combos = []
        if suited:
            # Same suit combos
            for s in SUITS:
                combos.append((r1 + s, r2 + s))
        else:
            # Different suit combos
            for s1 in SUITS:
                for s2 in SUITS:
                    if s1 != s2:
                        combos.append((r1 + s1, r2 + s2))
        return combos
    else:
        return []


def _sample_hand_from_range(
    combo_range: dict,
    known_cards: set,
    max_retries: int = 10,
) -> List[str]:
    """Sample a hand from a weighted combo_range distribution, applying blocker filtering.

    Pre-builds all valid (unblocked) combos with their weights, then samples
    directly from the valid set. No random fallback pollution.

    Args:
        combo_range: dict mapping hand_class -> weight (0.0 to 1.0)
        known_cards: set of cards that cannot appear in sampled hands (hero + board + other opps)
        max_retries: unused (kept for API compatibility)

    Returns:
        A list of 2 card strings representing the sampled hand.
        Falls back to a random unseen hand only if NO valid combos exist at all.
    """
    # Pre-build all valid combos with their weights
    valid_combos = []
    valid_weights = []
    for hc, w in combo_range.items():
        if w <= 0.0:
            continue
        for combo in _hand_class_to_combos(hc):
            if combo[0] not in known_cards and combo[1] not in known_cards:
                valid_combos.append(combo)
                valid_weights.append(w)

    if valid_combos and sum(valid_weights) > 0:
        [chosen] = random.choices(valid_combos, weights=valid_weights, k=1)
        return list(chosen)

    # Absolute fallback: no valid combos from range (all blocked)
    remaining = [c for c in FULL_DECK if c not in known_cards]
    if len(remaining) < 2:
        return remaining[:2] if remaining else []
    random.shuffle(remaining)
    return remaining[:2]


def estimate_equity_vs_range(
    hero_cards: List[str],
    board_cards: List[str],
    combo_range: dict,
    num_opponents: int = 1,
    simulations: int = 300,
) -> dict:
    """
    Range-aware Monte Carlo equity calculation.

    Samples opponent hands from the combo_range distribution (weighted by hand class)
    instead of uniformly from all unseen hands. Applies blocker filtering to exclude
    hands containing known cards.

    Args:
        hero_cards: Hero's 2 hole cards (e.g., ['AH', 'KS'])
        board_cards: Community cards (0-5 cards)
        combo_range: dict mapping hand_class (str) -> weight (float, 0.0-1.0)
                     169 entries for canonical hand classes (e.g., "AA", "AKs", "72o")
        num_opponents: Number of opponents (default 1)
        simulations: Number of Monte Carlo simulations (default 300)

    Returns:
        dict with keys: win_pct, tie_pct, loss_pct, equity
        Same format as estimate_equity for backward compatibility.
    """
    if num_opponents < 1:
        return {"win_pct": 1.0, "tie_pct": 0.0, "loss_pct": 0.0, "equity": 1.0}

    # Normalize weights to sum to 1.0 before sampling (Requirement 8.4)
    combo_range = _normalize_weights(combo_range)

    known_base = set(hero_cards + board_cards)
    remaining_deck_base = [c for c in FULL_DECK if c not in known_base]
    cards_to_deal = 5 - len(board_cards)  # Community cards still needed

    wins = 0
    ties = 0
    losses = 0
    equity = 0.0

    for _ in range(simulations):
        known = set(known_base)  # Copy for this simulation
        opponents = []

        # Deal opponent hands from the range distribution
        for _ in range(num_opponents):
            opp_hand = _sample_hand_from_range(combo_range, known)
            if len(opp_hand) == 2:
                opponents.append(opp_hand)
                known.add(opp_hand[0])
                known.add(opp_hand[1])
            else:
                # Shouldn't happen, but safeguard with random hand
                remaining = [c for c in FULL_DECK if c not in known]
                random.shuffle(remaining)
                opp_hand = remaining[:2]
                opponents.append(opp_hand)
                known.add(opp_hand[0])
                known.add(opp_hand[1])

        # Deal remaining community cards from the remaining deck
        remaining = [c for c in FULL_DECK if c not in known]
        random.shuffle(remaining)

        future_board = list(board_cards)
        for i in range(cards_to_deal):
            future_board.append(remaining[i])

        # Evaluate hero vs all opponents
        hero_score = _eval_score(hero_cards + future_board)
        opp_scores = [_eval_score(opp + future_board) for opp in opponents]

        best_opp = max(opp_scores)

        if hero_score > best_opp:
            wins += 1
            equity += 1.0
        elif hero_score == best_opp:
            # Count how many tied at hero's level (hero + tied opponents)
            tied_count = 1 + sum(1 for s in opp_scores if s == hero_score)
            ties += 1
            equity += 1.0 / tied_count
        else:
            losses += 1

    n = simulations
    return {
        "win_pct": round(wins / n, 4),
        "tie_pct": round(ties / n, 4),
        "loss_pct": round(losses / n, 4),
        "equity": round(equity / n, 4),
    }


# ─── Combined UI Calculation ──────────────────────────────────────────────────


def calculate_player_odds(
    hero_cards: List[str],
    board_cards: List[str],
    num_opponents: int = 1,
    simulations: int = 500,
) -> Optional[dict]:
    """
    Combined calculation for display in the UI.

    Uses the hybrid calculator internally for speed.

    Returns a dict with:
        equity: win probability through to river (0-100)
        current_ahead: % currently ahead (postflop only)
        phase_note: contextual label
    """
    if not hero_cards or len(hero_cards) < 2:
        return None

    board_len = len(board_cards)

    if board_len == 0:
        # Preflop: instant lookup
        eq = calculate_equity_hybrid(hero_cards, board_cards, num_opponents, simulations=simulations)
        return {
            "equity": round(eq["equity"] * 100),
            "current_ahead": None,
            "phase_note": "preflop equity",
        }
    else:
        # Postflop: use hybrid for equity
        eq = calculate_equity_hybrid(hero_cards, board_cards, num_opponents, simulations=simulations)

        if board_len == 5:
            # River: equity IS current strength (no future cards)
            cs = estimate_current_strength(hero_cards, board_cards, num_opponents, simulations=simulations)
            return {
                "equity": round(cs["ahead_pct"] * 100 + cs["tied_pct"] * 50),
                "current_ahead": round(cs["ahead_pct"] * 100),
                "phase_note": "river",
            }
        else:
            cs = estimate_current_strength(hero_cards, board_cards, num_opponents, simulations=simulations)
            return {
                "equity": round(eq["equity"] * 100),
                "current_ahead": round(cs["ahead_pct"] * 100),
                "phase_note": "flop" if board_len == 3 else "turn",
            }
