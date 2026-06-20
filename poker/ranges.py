"""
Professional preflop hand ranges and preflop action logic.

Provides tiered hand classification and style-based preflop decisions
using standard poker hand ranking charts.
"""

from __future__ import annotations

import random
from typing import Literal

HandTier = Literal["premium", "strong", "playable", "marginal", "speculative", "trash"]

# Rank ordering for canonical form (high to low)
RANK_ORDER = "AKQJT98765432"


def _rank_index(rank: str) -> int:
    """Return 0-based index of rank in RANK_ORDER (0=A, 12=2)."""
    try:
        return RANK_ORDER.index(rank)
    except ValueError:
        return -1


def _to_canonical(hole_cards: list[str]) -> str:
    """
    Convert two raw cards (e.g. ["AH", "KS"]) to canonical hand notation.

    Returns:
        "AKs" for suited, "AKo" for offsuit, "TT" for pair.
        Returns "" on invalid input.
    """
    if len(hole_cards) != 2:
        return ""

    card1, card2 = hole_cards[0], hole_cards[1]
    if len(card1) != 2 or len(card2) != 2:
        return ""

    rank1, suit1 = card1[0], card1[1]
    rank2, suit2 = card2[0], card2[1]

    idx1 = _rank_index(rank1)
    idx2 = _rank_index(rank2)

    if idx1 < 0 or idx2 < 0:
        return ""

    # Put higher rank first
    if idx1 > idx2:
        rank1, rank2 = rank2, rank1
        suit1, suit2 = suit2, suit1

    if rank1 == rank2:
        return f"{rank1}{rank2}"
    elif suit1 == suit2:
        return f"{rank1}{rank2}s"
    else:
        return f"{rank1}{rank2}o"


# ─── Hand Tier Definitions ───
# Based on standard poker hand charts, roughly:
#   premium: ~top 5% (4 combos)
#   strong: ~top 15% (next ~14 combos)
#   playable: ~top 30% (next ~30 combos)
#   marginal: ~top 50% (next ~40 combos)
#   speculative: ~top 70% (next ~35 combos)
#   trash: remaining

PREMIUM_HANDS: set[str] = {
    "AA", "KK", "QQ", "AKs",
}

STRONG_HANDS: set[str] = {
    "JJ", "TT", "AQs", "AJs", "KQs", "AKo", "ATs", "KJs", "QJs",
}

PLAYABLE_HANDS: set[str] = {
    "99", "88", "77", "AQo", "AJo", "ATo", "KQo", "KTs", "QTs",
    "JTs", "A9s", "A8s", "A7s", "A6s", "A5s", "KJo", "QJo",
    "K9s", "Q9s", "J9s", "T9s",
}

MARGINAL_HANDS: set[str] = {
    "66", "55", "44", "33", "22",
    "A4s", "A3s", "A2s", "K8s", "K7s", "K6s", "K5s", "K4s",
    "Q8s", "J8s", "T8s", "98s", "87s", "76s", "65s",
    "KTo", "QTo", "JTo", "T9o", "98o",
}

SPECULATIVE_HANDS: set[str] = {
    "K3s", "K2s", "Q7s", "Q6s", "Q5s", "Q4s", "Q3s", "Q2s",
    "J7s", "J6s", "J5s", "J4s", "T7s", "T6s", "97s", "96s",
    "86s", "85s", "75s", "74s", "64s", "54s", "53s", "43s",
    "A9o", "A8o", "A7o", "A6o", "A5o", "A4o", "A3o", "A2o",
    "K9o", "Q9o", "J9o", "87o", "76o", "65o",
}

# Build the full HAND_TIERS dict from the sets
HAND_TIERS: dict[str, HandTier] = {}

for h in PREMIUM_HANDS:
    HAND_TIERS[h] = "premium"
for h in STRONG_HANDS:
    HAND_TIERS[h] = "strong"
for h in PLAYABLE_HANDS:
    HAND_TIERS[h] = "playable"
for h in MARGINAL_HANDS:
    HAND_TIERS[h] = "marginal"
for h in SPECULATIVE_HANDS:
    HAND_TIERS[h] = "speculative"

# Generate all 169 canonical hands and fill remaining as trash
_ALL_HANDS: list[str] = []
for i, r1 in enumerate(RANK_ORDER):
    for j, r2 in enumerate(RANK_ORDER):
        if i == j:
            _ALL_HANDS.append(f"{r1}{r2}")  # pair
        elif i < j:
            _ALL_HANDS.append(f"{r1}{r2}s")  # suited (higher rank first)
            _ALL_HANDS.append(f"{r1}{r2}o")  # offsuit
# Note: the above generates 13 pairs + 78 suited + 78 offsuit = 169 hands

for h in _ALL_HANDS:
    if h not in HAND_TIERS:
        HAND_TIERS[h] = "trash"


# ─── Style-specific range cutoffs ───
# Fraction of total hands that each style will play
STYLE_RANGE_CUTOFF: dict[str, float] = {
    "tight_aggressive": 0.15,
    "loose_aggressive": 0.40,
    "calling_station": 0.50,
    "maniac": 0.50,
}

# Tier ordering for range membership checks
_TIER_ORDER: dict[HandTier, int] = {
    "premium": 0,
    "strong": 1,
    "playable": 2,
    "marginal": 3,
    "speculative": 4,
    "trash": 5,
}

# Which tiers are within each style's playable range based on cutoffs
_STYLE_PLAYABLE_TIERS: dict[str, set[HandTier]] = {
    "tight_aggressive": {"premium", "strong"},           # top ~15%
    "loose_aggressive": {"premium", "strong", "playable", "marginal"},  # top ~50% → approx 40%
    "calling_station": {"premium", "strong", "playable", "marginal"},   # top ~50%
    "maniac": {"premium", "strong", "playable", "marginal"},            # top ~50%
}


def classify_preflop_hand(hole_cards: list[str]) -> HandTier:
    """
    Classify a 2-card hand into a tier based on standard poker charts.

    Converts raw card notation (e.g. ["AH", "KS"]) to canonical form
    and returns the tier. Returns "trash" for invalid input.
    """
    canonical = _to_canonical(hole_cards)
    if not canonical:
        return "trash"
    return HAND_TIERS.get(canonical, "trash")


def _is_in_range(tier: HandTier, style: str) -> bool:
    """Check if a hand tier is within the style's playable range."""
    playable_tiers = _STYLE_PLAYABLE_TIERS.get(style, {"premium", "strong"})
    return tier in playable_tiers


def get_preflop_action(
    hole_cards: list[str],
    style: str,
    facing_raise: bool,
    position: str,
    big_blind: int,
) -> tuple[str, dict]:
    """
    Return (action, extras) for preflop decisions based on hand tier and style.

    Args:
        hole_cards: Two cards in raw notation, e.g. ["AH", "KS"]
        style: Bot style - "tight_aggressive", "loose_aggressive",
               "calling_station", "maniac"
        facing_raise: Whether there's already a raise to respond to
        position: "early", "middle", "late", "blind"
        big_blind: Current big blind amount

    Returns:
        Tuple of (action, extras):
        - ("fold", {})
        - ("check_call", {})
        - ("bet_raise", {"amount": int})
    """
    tier = classify_preflop_hand(hole_cards)

    # Check if hand is within our playable range
    in_range = _is_in_range(tier, style)

    if not in_range:
        # Hand outside playable range: fold if facing any bet
        if facing_raise:
            return ("fold", {})
        # If we're in the blind and no raise, we can check
        return ("fold", {})

    # Hand is in range — decide action
    if facing_raise:
        return _facing_raise_action(tier, style, position, big_blind)
    else:
        return _opening_action(tier, style, position, big_blind)


def _facing_raise_action(
    tier: HandTier,
    style: str,
    position: str,
    big_blind: int,
) -> tuple[str, dict]:
    """Decide action when facing a raise with an in-range hand."""

    # 3-bet logic: premium hands facing a raise → re-raise at least 60%
    # for aggressive styles
    aggressive_styles = {"tight_aggressive", "loose_aggressive", "maniac"}

    if tier == "premium":
        if style in aggressive_styles:
            # 3-bet at least 60% of the time
            if random.random() < 0.70:
                raise_amount = _calculate_raise_size(tier, position, big_blind)
                return ("bet_raise", {"amount": raise_amount})
        else:
            # calling_station: still re-raise sometimes with premium
            if random.random() < 0.35:
                raise_amount = _calculate_raise_size(tier, position, big_blind)
                return ("bet_raise", {"amount": raise_amount})
        return ("check_call", {})

    if tier == "strong":
        # Strong hands: raise sometimes based on style aggression
        raise_chance = 0.45 if style in aggressive_styles else 0.15
        if random.random() < raise_chance:
            raise_amount = _calculate_raise_size(tier, position, big_blind)
            return ("bet_raise", {"amount": raise_amount})
        return ("check_call", {})

    # Playable and marginal hands facing a raise: usually call
    if tier in ("playable", "marginal"):
        # Maniacs still raise with marginal hands sometimes
        if style == "maniac" and random.random() < 0.30:
            raise_amount = _calculate_raise_size(tier, position, big_blind)
            return ("bet_raise", {"amount": raise_amount})
        return ("check_call", {})

    # Speculative (shouldn't get here unless range expanded, but safe fallback)
    return ("check_call", {})


def _opening_action(
    tier: HandTier,
    style: str,
    position: str,
    big_blind: int,
) -> tuple[str, dict]:
    """Decide opening action (no raise to face) with an in-range hand."""

    # With in-range hands, we always open-raise (no limping for aggressive styles)
    aggressive_styles = {"tight_aggressive", "loose_aggressive", "maniac"}

    if style in aggressive_styles:
        # Always raise when opening with an in-range hand
        raise_amount = _calculate_raise_size(tier, position, big_blind)
        return ("bet_raise", {"amount": raise_amount})

    # Calling station: sometimes limps instead of raising
    if style == "calling_station":
        if tier in ("premium", "strong"):
            # Even calling stations raise with strong hands
            if random.random() < 0.60:
                raise_amount = _calculate_raise_size(tier, position, big_blind)
                return ("bet_raise", {"amount": raise_amount})
        return ("check_call", {})

    # Default: raise
    raise_amount = _calculate_raise_size(tier, position, big_blind)
    return ("bet_raise", {"amount": raise_amount})


def _calculate_raise_size(tier: HandTier, position: str, big_blind: int) -> int:
    """
    Calculate raise amount between 2.2x and 3.5x big blind.

    Higher tiers and earlier positions use larger sizing.
    """
    # Base multiplier based on hand tier
    if tier == "premium":
        base_mult = random.uniform(2.8, 3.5)
    elif tier == "strong":
        base_mult = random.uniform(2.5, 3.2)
    elif tier == "playable":
        base_mult = random.uniform(2.3, 2.9)
    else:
        # marginal/speculative
        base_mult = random.uniform(2.2, 2.7)

    # Position adjustment: early position raises slightly more
    if position == "early":
        base_mult = min(3.5, base_mult + 0.2)
    elif position == "late":
        base_mult = max(2.2, base_mult - 0.1)

    # Clamp to valid range
    base_mult = max(2.2, min(3.5, base_mult))

    return int(base_mult * big_blind)
