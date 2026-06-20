"""Blocker-based bluff selection for the Advanced Bot AI system.

Computes bluff viability using blocker scores, fold equity, range advantage,
and backup equity. The bluff_score formula combines these weighted factors
to determine whether a bluff should be attempted.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

from collections import Counter

from poker.bot_ai.models import BluffScore, RangeAdvantage
from poker.bot_ai.opponent_model import PlayerStats
from poker.evaluator import RANK_VALUE


def _rank_value(card: str) -> int:
    """Get numeric rank value from a card string (e.g., 'AH' -> 14)."""
    return RANK_VALUE[card[0]]


def _suit(card: str) -> str:
    """Get suit character from a card string (e.g., 'AH' -> 'H')."""
    return card[1]


def _flush_suit(community: list[str]) -> str | None:
    """Return the suit that makes a flush possible (3+ on board), or None."""
    if not community:
        return None
    suits = [_suit(c) for c in community]
    suit_counts = Counter(suits)
    for suit, count in suit_counts.items():
        if count >= 3:
            return suit
    return None


def _straight_possible(community: list[str]) -> bool:
    """Check if a straight is possible given community cards (3+ consecutive ranks)."""
    if len(community) < 3:
        return False
    rank_values = [_rank_value(c) for c in community]
    unique = sorted(set(rank_values))

    # Check standard consecutive sequences of 3+
    for i in range(len(unique) - 2):
        if unique[i + 2] - unique[i] <= 4:
            # 3 cards within a 5-card window means straight is possible
            return True

    # Check Ace-low (wheel)
    if 14 in unique:
        low_unique = sorted(set([1 if v == 14 else v for v in rank_values]))
        for i in range(len(low_unique) - 2):
            if low_unique[i + 2] - low_unique[i] <= 4:
                return True

    return False


def _nut_straight_ranks(community: list[str]) -> list[int]:
    """Determine ranks that would complete the nut straight.

    Returns rank values that, if held, would block the best possible straight.
    """
    if not community:
        return []

    rank_values = sorted(set(_rank_value(c) for c in community))
    blocking_ranks: list[int] = []

    # Check all possible 5-card straight windows
    # The nut straight needs the highest possible window
    for low in range(10, 0, -1):  # Start from highest window (10-14 = T to A)
        window = set(range(low, low + 5))
        board_in_window = window & set(rank_values)
        if len(board_in_window) >= 3:
            # Cards needed to complete this straight
            needed = window - set(rank_values)
            blocking_ranks.extend(needed)
            break  # Only care about the nut straight

    # Also check ace-low wheel if applicable
    if 14 in rank_values or any(v <= 5 for v in rank_values):
        wheel_window = {14, 2, 3, 4, 5}
        board_in_wheel = wheel_window & set(rank_values)
        if len(board_in_wheel) >= 3:
            needed = wheel_window - set(rank_values)
            blocking_ranks.extend(needed)

    return blocking_ranks


def compute_blocker_score(hole_cards: list[str], community: list[str]) -> float:
    """Compute how much our hole cards block opponent's strong hands.

    Higher score when holding cards that reduce opponent's nut combo count.

    Args:
        hole_cards: Our 2 hole cards, e.g. ["AH", "KD"]
        community: Community cards (3-5), e.g. ["QH", "JH", "TH"]

    Returns:
        Float in [0.0, 1.0] representing blocker strength.

    Logic:
        - Flush possible + we hold Ace of that suit → +0.35
        - Flush possible + we hold King/Queen of that suit → +0.20
        - Flush possible + we hold other card of that suit → +0.10
        - Straight possible + we hold nut straight blocker → +0.20
        - Paired board + we hold one of the paired rank → +0.15 (blocks full house)
    """
    if not hole_cards or not community:
        return 0.0

    score = 0.0

    # --- Flush blockers ---
    flush_suit = _flush_suit(community)
    if flush_suit is not None:
        for card in hole_cards:
            if _suit(card) == flush_suit:
                rank = _rank_value(card)
                if rank == 14:  # Ace of flush suit
                    score += 0.35
                elif rank >= 12:  # King or Queen of flush suit
                    score += 0.20
                else:
                    score += 0.10

    # --- Straight blockers ---
    if _straight_possible(community):
        nut_ranks = _nut_straight_ranks(community)
        for card in hole_cards:
            rank = _rank_value(card)
            if rank in nut_ranks:
                score += 0.20

    # --- Paired board blockers (blocks full house) ---
    if len(community) >= 3:
        comm_ranks = [_rank_value(c) for c in community]
        rank_counts = Counter(comm_ranks)
        paired_ranks = {r for r, cnt in rank_counts.items() if cnt >= 2}

        for card in hole_cards:
            if _rank_value(card) in paired_ranks:
                score += 0.15

    # Clamp to [0.0, 1.0]
    return min(1.0, max(0.0, score))


def compute_fold_equity(
    opponent_stats: PlayerStats, bet_size_ratio: float, street: str
) -> float:
    """Estimate the probability an opponent folds to our bet.

    Args:
        opponent_stats: Statistical profile for the opponent.
        bet_size_ratio: Bet size relative to pot (e.g., 0.75 = 75% pot bet).
        street: Current street ("preflop", "flop", "turn", "river").

    Returns:
        Float in [0.0, 1.0] representing estimated fold probability.

    Logic:
        - Insufficient data (< 10 hands): use default 0.35
        - Base fold equity from opponent tendencies (lower vpip = folds more,
          higher fold_to_3bet/fold_to_cbet = more fold equity)
        - Bet size impact: larger bets → more fold equity
        - Street impact: later streets → less fold equity (committed opponents)
    """
    # Default fold equity when we don't have enough data
    if opponent_stats.hands_observed < 10:
        return 0.35

    # --- Base fold equity from opponent stats ---
    # Lower VPIP means tighter player → more likely to fold
    vpip_factor = 1.0 - opponent_stats.vpip  # High when opponent is tight

    # Direct fold stats give strong signal
    fold_to_3bet = opponent_stats.fold_to_3bet
    fold_to_cbet = opponent_stats.fold_to_cbet

    # Weighted combination of fold indicators
    # vpip_factor is universal, fold_to_3bet/cbet are situational but strong signals
    base_fold_equity = (
        vpip_factor * 0.4
        + fold_to_3bet * 0.3
        + fold_to_cbet * 0.3
    )

    # --- Bet size impact ---
    # Larger bets give opponent worse pot odds → more fold equity
    # A pot-sized bet (ratio=1.0) adds moderate fold equity
    # Overbets (ratio>1.0) add more, small bets (ratio<0.5) add less
    bet_size_bonus = min(0.20, bet_size_ratio * 0.15)

    # --- Street impact ---
    # Later streets → opponents who are still in are more committed
    street_penalty = {
        "preflop": 0.0,
        "flop": 0.0,
        "turn": -0.05,
        "river": -0.10,
    }.get(street, 0.0)

    fold_equity = base_fold_equity + bet_size_bonus + street_penalty

    # Clamp to [0.0, 1.0]
    return min(1.0, max(0.0, fold_equity))


def compute_bluff_score(
    hole_cards: list[str],
    community: list[str],
    opponent_stats: PlayerStats,
    range_advantage: RangeAdvantage,
    equity: float,
    bet_size_ratio: float,
    street: str,
) -> BluffScore:
    """Compute overall bluff viability score.

    Combines blocker score, fold equity, range advantage, and backup equity
    using the weighted formula from Req 4.1:
        total = blocker × 0.3 + fold_equity × 0.3 + range_advantage × 0.2 + backup_equity × 0.2

    Args:
        hole_cards: Our 2 hole cards.
        community: Community cards (3-5).
        opponent_stats: Statistical profile for the opponent.
        range_advantage: Board range advantage assessment.
        equity: Our equity if called (0.0-1.0), used as backup_equity.
        bet_size_ratio: Bet size relative to pot.
        street: Current street.

    Returns:
        BluffScore with all component scores and the weighted total.
    """
    blocker_score = compute_blocker_score(hole_cards, community)
    fold_equity = compute_fold_equity(opponent_stats, bet_size_ratio, street)

    # Range advantage: use the aggressor_advantage directly as our range_advantage score
    range_adv_score = range_advantage.aggressor_advantage

    # Backup equity: our equity if called (how likely we improve even if bluff is called)
    backup_equity = max(0.0, min(1.0, equity))

    # Weighted formula (Req 4.1)
    total_score = (
        blocker_score * 0.3
        + fold_equity * 0.3
        + range_adv_score * 0.2
        + backup_equity * 0.2
    )

    return BluffScore(
        blocker_score=blocker_score,
        fold_equity=fold_equity,
        range_advantage=range_adv_score,
        backup_equity=backup_equity,
        total_score=total_score,
    )
