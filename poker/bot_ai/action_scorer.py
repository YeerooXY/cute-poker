"""Action Scoring System for the Advanced Bot AI.

Central decision system that scores all legal actions and selects the best one.
Scores are computed based on equity, pot odds, opponent range, board texture,
position, and bluff viability. Personality multipliers and noise are applied
before final selection.

Req 9.1: Compute finite scores for every legal action
Req 9.2: Apply personality multipliers to modify action scores
Req 9.3: Add random noise proportional to exploitability parameter
Req 9.4: When bet/raise selected, produce valid amount via bet_sizer
Req 9.5: If two or more actions within 5% of max score → random weighted selection
"""

from __future__ import annotations

import math
import random

from poker.bot_ai.models import (
    ActionScores,
    ScoringContext,
)
from poker.bot_ai.personality_engine import PokerPersonality, get_action_multipliers


# Score assigned to illegal actions so they are never selected
_ILLEGAL_SCORE = -1e9

# Base noise scale factor; actual noise = exploitability * _BASE_NOISE_SCALE
_BASE_NOISE_SCALE = 0.1


def compute_base_scores(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """Compute base action scores from game context.

    Only actions present in legal_actions receive meaningful scores.
    Actions not in legal_actions are set to a very negative value so they
    are never selected.

    Scoring logic:
      - fold: small base; boosted when equity is low and pot odds are bad
      - check: base when no bet required; boosted on wet boards for pot control;
               boosted with trap_frequency
      - call: boosted when equity > pot_odds; boosted with bluff_score in position
      - bet: boosted with high equity, dry boards, preflop aggressor status,
             bluff_score, and range_advantage
      - raise_: boosted with very high equity (>0.7), aggression, and exploit
                adjustments (3bet bluff boost, cbet boost)

    Returns ActionScores with finite (non-NaN, non-infinite) values for all
    legal actions.

    **Validates: Requirements 9.1**
    """
    scores = ActionScores(
        fold=_ILLEGAL_SCORE,
        check=_ILLEGAL_SCORE,
        call=_ILLEGAL_SCORE,
        bet=_ILLEGAL_SCORE,
        raise_=_ILLEGAL_SCORE,
    )

    # Precompute useful values
    equity = ctx.equity
    pot_odds = ctx.pot_odds
    bluff_total = ctx.bluff_score.total_score
    aggressor_adv = ctx.range_advantage.aggressor_advantage
    personality = ctx.personality
    board = ctx.board_texture
    exploit = ctx.exploit_adjustments
    dynamic = ctx.dynamic_adjustments

    # Position bonus: later positions get a small bonus for aggression
    position_bonus = _position_bonus(ctx.position, personality.position_awareness)

    # ─── Fold ──────────────────────────────────────────────────────────────
    if "fold" in legal_actions:
        fold_score = 0.1
        # Boost fold when equity is very low and pot odds are bad
        if equity < 0.25:
            fold_score += (0.25 - equity) * 1.5
        if pot_odds > 0 and equity < pot_odds:
            fold_score += (pot_odds - equity) * 0.8
        scores.fold = fold_score

    # ─── Check ─────────────────────────────────────────────────────────────
    if "check" in legal_actions:
        check_score = 0.4  # Reasonable base — checking is free
        # Boost on wet boards when aggressor (pot control)
        if board.is_wet and ctx.is_preflop_aggressor:
            check_score += 0.15
        # Boost with trap_frequency (slow-play strong hands)
        check_score += personality.trap_frequency * 0.3
        # Boost from dynamic trap adjustment
        check_score += dynamic.trap_frequency_boost * 0.2
        scores.check = check_score

    # ─── Call ──────────────────────────────────────────────────────────────
    if "call" in legal_actions:
        call_score = 0.2
        # Profitable call: equity exceeds pot odds
        if pot_odds > 0 and equity > pot_odds:
            call_score += (equity - pot_odds) * 2.0
        elif pot_odds == 0:
            # No bet to call — rare edge case, still give equity-based score
            call_score += equity * 0.5
        # Boost when in position with bluff catching potential
        if _is_late_position(ctx.position):
            call_score += bluff_total * 0.2
        # Call-down looseness influence (via personality, applied later in apply_personality)
        scores.call = call_score

    # ─── Bet ───────────────────────────────────────────────────────────────
    if "bet" in legal_actions:
        bet_score = 0.2
        # High equity → strong value bet
        bet_score += equity * 1.2
        # Dry board bonus for cbets
        if board.is_dry:
            bet_score += 0.2
        # Preflop aggressor cbet bonus
        if ctx.is_preflop_aggressor:
            bet_score += 0.15
        # Bluff score contribution
        bet_score += bluff_total * 0.4
        # Range advantage
        bet_score += aggressor_adv * 0.3
        # Position bonus for betting
        bet_score += position_bonus * 0.15
        # Dynamic steal boost
        bet_score += dynamic.steal_frequency_boost * 0.2
        # Exploit cbet boost
        if exploit.active:
            bet_score += exploit.cbet_frequency_boost * 0.3
        scores.bet = bet_score

    # ─── Raise ─────────────────────────────────────────────────────────────
    if "raise" in legal_actions:
        raise_score = 0.1
        # Very high equity → strong raise
        if equity > 0.7:
            raise_score += (equity - 0.7) * 3.0
        # General equity contribution
        raise_score += equity * 0.8
        # Aggression personality influence (applied later, but give base)
        raise_score += personality.aggression * 0.3
        # Bluff score for semi-bluff raises
        raise_score += bluff_total * 0.3
        # Exploit: 3bet bluff boost
        if exploit.active:
            raise_score += exploit.three_bet_bluff_boost * 0.4
            raise_score += exploit.cbet_frequency_boost * 0.2
        # Dynamic adjustments
        raise_score += dynamic.four_bet_frequency_boost * 0.2
        # Position bonus
        raise_score += position_bonus * 0.1
        scores.raise_ = raise_score

    # Final safety: ensure all scores are finite
    scores = _ensure_finite(scores)

    return scores


def apply_personality(scores: ActionScores, personality: PokerPersonality) -> ActionScores:
    """Apply personality-based multipliers to action scores.

    Uses get_action_multipliers() from personality_engine to derive multiplier
    values, then multiplies each action score by the corresponding multiplier.
    Only applies to non-illegal scores (scores > _ILLEGAL_SCORE).

    **Validates: Requirements 9.2**
    """
    multipliers = get_action_multipliers(personality)

    new_scores = ActionScores(
        fold=scores.fold * multipliers["fold"] if scores.fold > _ILLEGAL_SCORE else scores.fold,
        check=scores.check * multipliers["check"] if scores.check > _ILLEGAL_SCORE else scores.check,
        call=scores.call * multipliers["call"] if scores.call > _ILLEGAL_SCORE else scores.call,
        bet=scores.bet * multipliers["bet"] if scores.bet > _ILLEGAL_SCORE else scores.bet,
        raise_=scores.raise_ * multipliers["raise"] if scores.raise_ > _ILLEGAL_SCORE else scores.raise_,
    )

    return _ensure_finite(new_scores)


def apply_noise(scores: ActionScores, exploitability: float) -> ActionScores:
    """Add random noise proportional to exploitability.

    For each action score that is not illegal, adds gaussian noise with
    mean 0 and standard deviation = exploitability * _BASE_NOISE_SCALE.

    Higher exploitability → greater variance in scores → less predictable play.

    **Validates: Requirements 9.3**
    """
    sigma = exploitability * _BASE_NOISE_SCALE

    new_scores = ActionScores(
        fold=scores.fold + random.gauss(0, sigma) if scores.fold > _ILLEGAL_SCORE else scores.fold,
        check=scores.check + random.gauss(0, sigma) if scores.check > _ILLEGAL_SCORE else scores.check,
        call=scores.call + random.gauss(0, sigma) if scores.call > _ILLEGAL_SCORE else scores.call,
        bet=scores.bet + random.gauss(0, sigma) if scores.bet > _ILLEGAL_SCORE else scores.bet,
        raise_=scores.raise_ + random.gauss(0, sigma) if scores.raise_ > _ILLEGAL_SCORE else scores.raise_,
    )

    return _ensure_finite(new_scores)


def select_action(scores: ActionScores) -> str:
    """Select the best action based on scores.

    Finds the maximum score among all actions. If multiple actions are within
    5% of the maximum, performs weighted random selection among them (weighted
    by their scores). Otherwise returns the single highest-scoring action.

    **Validates: Requirements 9.5**
    """
    action_map = {
        "fold": scores.fold,
        "check": scores.check,
        "call": scores.call,
        "bet": scores.bet,
        "raise": scores.raise_,
    }

    # Filter out illegal actions
    legal = {k: v for k, v in action_map.items() if v > _ILLEGAL_SCORE}

    if not legal:
        # Fallback: if somehow all actions are illegal, fold
        return "fold"

    max_score = max(legal.values())

    # Threshold: within 5% of max
    # Handle edge case where max_score could be 0 or negative
    if max_score > 0:
        threshold = max_score * 0.95
    elif max_score == 0:
        threshold = -0.05
    else:
        # max_score is negative — 5% means closer to zero
        threshold = max_score * 1.05

    tied_actions = {k: v for k, v in legal.items() if v >= threshold}

    if len(tied_actions) == 1:
        return next(iter(tied_actions))

    # Weighted random selection among tied actions
    # Shift scores to be positive for weighting
    min_tied = min(tied_actions.values())
    shift = abs(min_tied) + 0.01 if min_tied <= 0 else 0.0
    weights = [v + shift for v in tied_actions.values()]
    actions = list(tied_actions.keys())

    chosen = random.choices(actions, weights=weights, k=1)[0]
    return chosen


# ─── Private helpers ───────────────────────────────────────────────────────────


def _position_bonus(position: str, position_awareness: float) -> float:
    """Return a bonus [0, 1] based on position (later = higher) scaled by awareness."""
    position_order = {
        "UTG": 0.0,
        "UTG1": 0.1,
        "MP": 0.2,
        "HJ": 0.4,
        "CO": 0.6,
        "BTN": 0.9,
        "SB": 0.3,
        "BB": 0.2,
    }
    raw = position_order.get(position, 0.3)
    return raw * position_awareness


def _is_late_position(position: str) -> bool:
    """Return True if position is considered late (CO, BTN)."""
    return position in ("CO", "BTN")


def _ensure_finite(scores: ActionScores) -> ActionScores:
    """Replace any NaN or infinite values with _ILLEGAL_SCORE."""
    def _safe(v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            return _ILLEGAL_SCORE
        return v

    return ActionScores(
        fold=_safe(scores.fold),
        check=_safe(scores.check),
        call=_safe(scores.call),
        bet=_safe(scores.bet),
        raise_=_safe(scores.raise_),
    )
