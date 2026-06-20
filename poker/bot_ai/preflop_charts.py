"""Positional preflop charts for the Advanced Bot AI.

Defines position-specific opening, 3-bet, 4-bet, and calling ranges.
Provides lookup-based preflop decisions adjusted by personality parameters.

Hand notation:
- "AA", "KK" — pocket pairs
- "AKs" — suited (lowercase 's')
- "AKo" — offsuit (lowercase 'o')
"""

from __future__ import annotations

from dataclasses import dataclass, field

from poker.bot_ai.personality_engine import PokerPersonality


@dataclass
class PositionRange:
    """Position-specific hand ranges for preflop decisions."""

    open_range: set[str] = field(default_factory=set)
    three_bet_value: set[str] = field(default_factory=set)
    three_bet_bluff: set[str] = field(default_factory=set)
    four_bet_range: set[str] = field(default_factory=set)
    call_range: set[str] = field(default_factory=set)


# ─── Hand category definitions ─────────────────────────────────────────────────

PREMIUM_HANDS = {"AA", "KK", "QQ", "AKs"}

STRONG_HANDS = {"JJ", "TT", "AQs", "AJs", "ATs", "KQs", "AKo"}

PLAYABLE_HANDS = {
    "99", "88", "77", "KJs", "KTs", "QJs", "QTs", "JTs",
    "AQo", "AJo", "A9s", "A8s", "A7s", "A6s", "A5s",
}

MARGINAL_HANDS = {
    "66", "55", "44", "33", "22", "T9s", "98s", "87s", "76s",
    "65s", "54s", "KQo", "KJo", "QJo", "JTo", "A4s", "A3s", "A2s",
}

SPECULATIVE_HANDS = {
    "K9s", "K8s", "K7s", "Q9s", "J9s", "T8s", "97s", "86s",
    "75s", "64s", "53s", "43s", "ATo", "A9o", "KTo", "QTo",
    "J9o", "T9o",
}

# ─── All possible hand notations (for expansion logic) ──────────────────────────

ALL_HANDS = PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS | MARGINAL_HANDS | SPECULATIVE_HANDS

# ─── Expansion order for personality adjustments ────────────────────────────────
# Ordered from tightest to widest — used to expand/contract ranges.

HAND_TIERS = [
    PREMIUM_HANDS,
    STRONG_HANDS,
    PLAYABLE_HANDS,
    MARGINAL_HANDS,
    SPECULATIVE_HANDS,
]

# Flat ordered list for expansion/contraction
_EXPANSION_ORDER: list[str] = []
for _tier in HAND_TIERS:
    for _hand in sorted(_tier):
        if _hand not in _EXPANSION_ORDER:
            _EXPANSION_ORDER.append(_hand)

# ─── Position charts ────────────────────────────────────────────────────────────
# UTG: ~12% open range (tightest)
# UTG1: ~14%
# MP: ~18%
# HJ: ~22%
# CO: ~28%
# BTN: ~40% (widest open)
# SB: ~35% (slightly tighter than BTN, out of position)
# BB: defense range (mostly calls)

POSITION_CHARTS: dict[str, PositionRange] = {
    "UTG": PositionRange(
        open_range=PREMIUM_HANDS | STRONG_HANDS | {"99", "88", "AQo"},
        three_bet_value={"AA", "KK", "QQ", "AKs", "AKo"},
        three_bet_bluff={"A5s", "A4s"},
        four_bet_range={"AA", "KK", "QQ", "AKs"},
        call_range={"JJ", "TT", "AQs", "AJs", "KQs"},
    ),
    "UTG1": PositionRange(
        open_range=PREMIUM_HANDS | STRONG_HANDS | {"99", "88", "77", "AQo", "KJs"},
        three_bet_value={"AA", "KK", "QQ", "AKs", "AKo", "JJ"},
        three_bet_bluff={"A5s", "A4s", "A3s"},
        four_bet_range={"AA", "KK", "QQ", "AKs"},
        call_range={"TT", "99", "AQs", "AJs", "ATs", "KQs", "KJs"},
    ),
    "MP": PositionRange(
        open_range=(
            PREMIUM_HANDS | STRONG_HANDS
            | {"99", "88", "77", "KJs", "KTs", "QJs", "AQo", "AJo", "A9s", "A8s"}
        ),
        three_bet_value={"AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        three_bet_bluff={"A5s", "A4s", "A3s", "76s"},
        four_bet_range={"AA", "KK", "QQ", "AKs", "AKo"},
        call_range={"TT", "99", "88", "AJs", "ATs", "KQs", "KJs", "KTs", "QJs"},
    ),
    "HJ": PositionRange(
        open_range=(
            PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS
            | {"KQo", "KJo", "T9s", "98s", "87s"}
        ),
        three_bet_value={"AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs", "AQo"},
        three_bet_bluff={"A5s", "A4s", "A3s", "76s", "65s", "54s"},
        four_bet_range={"AA", "KK", "QQ", "JJ", "AKs", "AKo"},
        call_range={
            "TT", "99", "88", "77", "AJs", "ATs", "KQs", "KJs",
            "KTs", "QJs", "QTs", "JTs",
        },
    ),
    "CO": PositionRange(
        open_range=(
            PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS | MARGINAL_HANDS
            | {"K9s", "Q9s", "J9s", "T8s", "97s", "ATo"}
        ),
        three_bet_value={
            "AA", "KK", "QQ", "JJ", "TT", "99",
            "AKs", "AKo", "AQs", "AQo", "AJs",
        },
        three_bet_bluff={"A5s", "A4s", "A3s", "A2s", "76s", "65s", "54s", "87s"},
        four_bet_range={"AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        call_range={
            "TT", "99", "88", "77", "66", "AJs", "ATs", "A9s",
            "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s",
        },
    ),
    "BTN": PositionRange(
        open_range=(
            PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS
            | MARGINAL_HANDS | SPECULATIVE_HANDS
        ),
        three_bet_value={
            "AA", "KK", "QQ", "JJ", "TT", "99",
            "AKs", "AKo", "AQs", "AQo", "AJs", "AJo", "KQs",
        },
        three_bet_bluff={
            "A5s", "A4s", "A3s", "A2s", "76s", "65s", "54s",
            "87s", "98s", "K9s", "Q9s",
        },
        four_bet_range={"AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs"},
        call_range={
            "99", "88", "77", "66", "55", "ATs", "A9s", "A8s",
            "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s",
            "87s", "76s", "65s",
        },
    ),
    "SB": PositionRange(
        open_range=(
            PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS | MARGINAL_HANDS
            | {"K9s", "K8s", "Q9s", "J9s", "T8s", "97s", "86s", "ATo", "A9o", "KTo"}
        ),
        three_bet_value={
            "AA", "KK", "QQ", "JJ", "TT", "99",
            "AKs", "AKo", "AQs", "AQo", "AJs", "KQs",
        },
        three_bet_bluff={
            "A5s", "A4s", "A3s", "A2s", "76s", "65s",
            "54s", "87s", "98s",
        },
        four_bet_range={"AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        call_range={
            "TT", "99", "88", "77", "66", "55", "ATs", "A9s",
            "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s", "87s",
        },
    ),
    "BB": PositionRange(
        open_range=set(),  # BB doesn't open (already has blind posted)
        three_bet_value={
            "AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs", "AQo",
        },
        three_bet_bluff={
            "A5s", "A4s", "A3s", "A2s", "76s", "65s", "54s",
            "87s", "98s", "K9s",
        },
        four_bet_range={"AA", "KK", "QQ", "AKs", "AKo"},
        call_range=(
            PREMIUM_HANDS | STRONG_HANDS | PLAYABLE_HANDS | MARGINAL_HANDS
            | {"K9s", "Q9s", "J9s", "T8s", "97s"}
        ),
    ),
}


# ─── Helper: Convert hole cards to hand notation ────────────────────────────────

_RANK_ORDER = "AKQJT98765432"


def _cards_to_hand_notation(hole_cards: list[str]) -> str:
    """Convert two cards like ['AH', 'KH'] to notation like 'AKs'.

    Cards are formatted as rank + suit (e.g., 'AS', 'KH', 'TD').
    Returns:
      - "AA" for pocket pairs
      - "AKs" for suited hands
      - "AKo" for offsuit hands
    Higher rank always comes first.
    """
    if len(hole_cards) != 2:
        return ""

    card1, card2 = hole_cards[0], hole_cards[1]
    rank1, suit1 = card1[0], card1[1]
    rank2, suit2 = card2[0], card2[1]

    # Order by rank (higher rank first)
    idx1 = _RANK_ORDER.index(rank1)
    idx2 = _RANK_ORDER.index(rank2)
    if idx1 > idx2:
        rank1, rank2 = rank2, rank1
        suit1, suit2 = suit2, suit1

    # Pocket pair
    if rank1 == rank2:
        return f"{rank1}{rank2}"

    # Suited or offsuit
    if suit1 == suit2:
        return f"{rank1}{rank2}s"
    else:
        return f"{rank1}{rank2}o"


# ─── Personality range adjustment ───────────────────────────────────────────────

# Baseline vpip/pfr values (TAG-like) used as the neutral reference point.
_BASELINE_VPIP = 0.22
_BASELINE_PFR = 0.18


def adjust_ranges_for_personality(
    base_range: PositionRange,
    personality: PokerPersonality,
) -> PositionRange:
    """Expand or contract ranges based on personality vpip and pfr.

    Higher vpip → wider open_range and call_range.
    Higher pfr → wider three_bet and four_bet ranges.
    Lower vpip/pfr → contract ranges.

    Returns a new PositionRange with adjusted sets.
    """
    # Compute expansion factors relative to baseline
    vpip_factor = personality.vpip / _BASELINE_VPIP  # >1 = expand, <1 = contract
    pfr_factor = personality.pfr / _BASELINE_PFR

    open_range = _adjust_set(base_range.open_range, vpip_factor)
    call_range = _adjust_set(base_range.call_range, vpip_factor)
    three_bet_value = _adjust_set(base_range.three_bet_value, pfr_factor)
    three_bet_bluff = _adjust_set(base_range.three_bet_bluff, pfr_factor)
    four_bet_range = _adjust_set(base_range.four_bet_range, pfr_factor)

    return PositionRange(
        open_range=open_range,
        three_bet_value=three_bet_value,
        three_bet_bluff=three_bet_bluff,
        four_bet_range=four_bet_range,
        call_range=call_range,
    )


def _adjust_set(base_set: set[str], factor: float) -> set[str]:
    """Expand or contract a hand set based on a factor.

    factor > 1.0: add hands from the expansion order that aren't already included.
    factor < 1.0: remove hands from the end of the expansion order.
    factor == 1.0: no change.
    """
    if not base_set:
        return set(base_set)

    # Find indices of all base hands in the expansion order
    base_indices = []
    for i, hand in enumerate(_EXPANSION_ORDER):
        if hand in base_set:
            base_indices.append(i)

    if not base_indices:
        return set(base_set)

    # Target size based on factor
    current_size = len(base_set)
    target_size = max(1, int(round(current_size * factor)))

    if factor >= 1.0:
        # Expand: add hands from expansion order that follow existing ones
        result = set(base_set)
        max_idx = max(base_indices)
        idx = max_idx + 1
        while len(result) < target_size and idx < len(_EXPANSION_ORDER):
            result.add(_EXPANSION_ORDER[idx])
            idx += 1
        return result
    else:
        # Contract: keep only the top N hands by expansion order priority
        ordered_hands = [
            h for h in _EXPANSION_ORDER if h in base_set
        ]
        # Also include any hands from base_set not in expansion order
        extra = base_set - set(_EXPANSION_ORDER)
        kept = set(ordered_hands[:target_size]) | extra
        return kept


# ─── Main preflop decision function ────────────────────────────────────────────


def get_preflop_decision(
    hole_cards: list[str],
    position: str,
    personality: PokerPersonality,
    facing_action: str,
    big_blind: int,
) -> tuple[str, dict]:
    """Return a preflop action based on chart lookup and personality.

    Args:
        hole_cards: Two cards like ["AH", "KH"].
        position: One of "UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB".
        personality: The bot's PokerPersonality.
        facing_action: One of "unopened", "raise", "3bet", "4bet".
        big_blind: The current big blind amount.

    Returns:
        (action, payload) tuple:
          - ("raise", {"amount": int}) for opens, 3-bets, 4-bets
          - ("call", {}) for calling
          - ("fold", {}) for folding
    """
    hand = _cards_to_hand_notation(hole_cards)
    if not hand:
        return ("fold", {})

    # Get the base position range (default to BB if position unknown)
    base_range = POSITION_CHARTS.get(position, POSITION_CHARTS["BB"])

    # Adjust for personality
    adjusted = adjust_ranges_for_personality(base_range, personality)

    return _decide_action(hand, adjusted, facing_action, big_blind)


def _decide_action(
    hand: str,
    ranges: PositionRange,
    facing_action: str,
    big_blind: int,
) -> tuple[str, dict]:
    """Decide action based on hand, adjusted ranges, and facing action."""

    if facing_action == "unopened":
        if hand in ranges.open_range:
            # Standard open raise: 2.5x big blind
            return ("raise", {"amount": int(big_blind * 2.5)})
        return ("fold", {})

    elif facing_action == "raise":
        # Facing a raise: 3-bet for value, 3-bet as bluff, or call
        if hand in ranges.three_bet_value:
            # 3-bet sizing: ~3x the open raise (roughly 7-8 BB)
            return ("raise", {"amount": big_blind * 3})
        if hand in ranges.three_bet_bluff:
            return ("raise", {"amount": big_blind * 3})
        if hand in ranges.call_range:
            return ("call", {})
        return ("fold", {})

    elif facing_action == "3bet":
        # Facing a 3-bet: 4-bet or call
        if hand in ranges.four_bet_range:
            # 4-bet sizing: ~2.5x the 3-bet (roughly 20 BB)
            return ("raise", {"amount": big_blind * 8})
        if hand in ranges.call_range:
            return ("call", {})
        return ("fold", {})

    elif facing_action == "4bet":
        # Facing a 4-bet: only continue with top of 4-bet range
        if hand in ranges.four_bet_range:
            # 5-bet / all-in territory
            return ("raise", {"amount": big_blind * 20})
        return ("fold", {})

    # Unknown facing action: fold as default
    return ("fold", {})
