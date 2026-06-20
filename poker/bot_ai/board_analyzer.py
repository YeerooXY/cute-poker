"""Board texture classification and range advantage computation.

Analyzes community cards to determine board texture (dry, wet, paired,
monotone, connected) and computes which player's range is favored.
"""

from __future__ import annotations

from collections import Counter

from poker.bot_ai.models import BoardTexture, RangeAdvantage
from poker.evaluator import RANK_VALUE


def _rank_value(card: str) -> int:
    """Get numeric rank value from a card string (e.g., 'AH' -> 14)."""
    return RANK_VALUE[card[0]]


def _suit(card: str) -> str:
    """Get suit character from a card string (e.g., 'AH' -> 'H')."""
    return card[1]


def _has_consecutive_ranks(rank_values: list[int], count: int) -> bool:
    """Check if there are `count` or more consecutive ranks among the values.

    Also considers Ace-low (A=1) for wheel sequences.
    """
    if len(rank_values) < count:
        return False

    unique = sorted(set(rank_values))

    # Check standard consecutive sequences
    for i in range(len(unique) - count + 1):
        window = unique[i : i + count]
        if window[-1] - window[0] == count - 1:
            return True

    # Check Ace-low (wheel): treat Ace as 1 as well
    if 14 in unique:
        low_unique = sorted(set([1 if v == 14 else v for v in rank_values]))
        for i in range(len(low_unique) - count + 1):
            window = low_unique[i : i + count]
            if window[-1] - window[0] == count - 1:
                return True

    return False


def _count_straight_draw_combos(rank_values: list[int]) -> int:
    """Count how many distinct straight draw combinations exist.

    A straight draw exists when adding 1 or 2 cards could complete a straight.
    We count how many 5-card straight windows the board cards participate in.
    """
    unique = sorted(set(rank_values))

    # Also consider Ace as 1
    extended = set(unique)
    if 14 in extended:
        extended.add(1)
    extended_sorted = sorted(extended)

    combos = 0
    # Check all possible 5-card straight windows (1-5, 2-6, ..., 10-14)
    for low in range(1, 11):
        window = set(range(low, low + 5))
        cards_in_window = window & extended
        # A draw exists when we have 3 or 4 cards in a 5-card window
        # (need 1-2 more cards to complete)
        if len(cards_in_window) >= 3:
            combos += 1

    return combos


def _flush_draw_possible(suits: list[str]) -> bool:
    """Check if a flush draw is possible (2+ cards of same suit on board with < 5 community)."""
    suit_counts = Counter(suits)
    max_suited = max(suit_counts.values()) if suit_counts else 0
    # Flush draw possible if 2+ suited cards (player could have 2 more)
    # or if 3+ suited cards (flush already possible or draw very strong)
    return max_suited >= 2


def analyze_board(community: list[str]) -> BoardTexture:
    """Classify community cards into board texture categories.

    Args:
        community: List of community card strings (3-5 cards), e.g. ["AH", "KS", "2D"]

    Returns:
        BoardTexture with classification flags set.

    Rules:
        - 3+ cards of same suit → monotone
        - Pair on board → paired
        - 3+ consecutive ranks → connected
        - Wet = flush draw possible OR straight draw possible with multiple combos
        - Dry = NOT (wet OR connected OR monotone)
    """
    if not community:
        return BoardTexture()

    suits = [_suit(c) for c in community]
    rank_values = [_rank_value(c) for c in community]
    suit_counts = Counter(suits)
    rank_counts = Counter(rank_values)

    # High card rank (highest rank on board)
    high_card_rank = max(rank_values)

    # Monotone: 3+ cards of same suit
    max_suited = max(suit_counts.values())
    is_monotone = max_suited >= 3

    # Paired: any rank appears 2+ times
    is_paired = any(count >= 2 for count in rank_counts.values())

    # Connected: 3+ consecutive ranks
    is_connected = _has_consecutive_ranks(rank_values, 3)

    # Flush possible: 3+ same suit means flush already possible
    # (opponent could hold 2 of that suit)
    flush_possible = max_suited >= 3

    # Flush draw possible: 2+ same suit (not yet a made flush on board, but draw exists)
    flush_draw = max_suited >= 2

    # Straight possible: 3+ consecutive already, or can be completed easily
    straight_possible = is_connected

    # Straight draw combos (how many straight windows have 3+ board cards)
    straight_draw_combos = _count_straight_draw_combos(rank_values)

    # Wet: flush draw possible or straight draw possible with multiple combos
    is_wet = flush_draw or straight_draw_combos >= 3

    # Dry: not wet and not connected and not monotone
    is_dry = not is_wet and not is_connected and not is_monotone

    return BoardTexture(
        is_dry=is_dry,
        is_wet=is_wet,
        is_paired=is_paired,
        is_monotone=is_monotone,
        is_connected=is_connected,
        flush_possible=flush_possible,
        straight_possible=straight_possible,
        high_card_rank=high_card_rank,
    )


def compute_range_advantage(
    community: list[str], is_preflop_aggressor: bool
) -> RangeAdvantage:
    """Compute which player's range is favored on this board.

    Args:
        community: List of community card strings (3-5 cards)
        is_preflop_aggressor: Whether we are the preflop aggressor

    Returns:
        RangeAdvantage with aggressor_advantage in [0.0, 1.0] and nut_advantage flag.

    Logic:
        - High cards (A, K, Q heavy boards) favor preflop aggressor → higher advantage
        - Low connected boards favor caller → lower advantage
        - Paired boards slightly favor aggressor
        - Monotone boards slightly favor caller
        - Nut advantage = True when board is high-card heavy AND not too connected
    """
    if not community:
        return RangeAdvantage(aggressor_advantage=0.5, nut_advantage=False)

    texture = analyze_board(community)
    rank_values = [_rank_value(c) for c in community]

    # Start with neutral advantage
    advantage = 0.5

    # High card factor: count cards that are T or higher (value >= 10)
    high_cards = sum(1 for v in rank_values if v >= 10)
    high_card_ratio = high_cards / len(rank_values)

    # High cards favor aggressor (they have more premiums like AK, AQ, KQ, big pairs)
    advantage += high_card_ratio * 0.2

    # Low cards favor caller (they have more suited connectors, small pairs)
    low_cards = sum(1 for v in rank_values if v <= 7)
    low_card_ratio = low_cards / len(rank_values)
    advantage -= low_card_ratio * 0.15

    # Connected boards favor caller slightly (suited connectors hit these)
    if texture.is_connected:
        advantage -= 0.08

    # Paired boards slightly favor aggressor (overpairs more likely in their range)
    if texture.is_paired:
        advantage += 0.05

    # Monotone boards slightly favor caller (they can have more suited hands)
    if texture.is_monotone:
        advantage -= 0.08

    # Clamp to [0.0, 1.0]
    advantage = max(0.0, min(1.0, advantage))

    # Nut advantage: aggressor has more nut combos when board is high-card heavy
    # AND not too connected (so top pair/overpairs dominate rather than straights)
    nut_advantage = high_card_ratio >= 0.6 and not texture.is_connected

    return RangeAdvantage(
        aggressor_advantage=advantage,
        nut_advantage=nut_advantage,
    )
