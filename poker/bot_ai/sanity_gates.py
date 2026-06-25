"""Sanity gates module for Balanced Bot AI (Patch 1).

Sanity gates are score masks applied to ActionScores after EV scoring and
before action selection. They prevent fundamental poker logic violations by
modifying scores:
  - Forbidden: score = -1e9
  - Discouraged: score -= penalty
  - Protected: score += bonus

Gate functions (apply_preflop_gate, apply_postflop_gate, apply_allin_gate,
apply_raise_ladder_gate) and the orchestrator (apply_sanity_gates) plus
validate_selection are implemented in later tasks (4.2-4.6).
"""

import logging
from dataclasses import dataclass

from poker.bot_ai.models import ActionScores, BoardTexture

logger = logging.getLogger(__name__)


@dataclass
class GateContext:
    """All context needed by all gates in a single object."""

    # Preflop gate context
    hole_cards: list[str]
    hand_percentile: float  # 0.0 = best (AA), 1.0 = worst
    is_premium: bool  # AA, KK, QQ, AK
    effective_stack_bb: float
    facing_action: str  # "unopened", "raise", "3bet", "4bet"
    phase: str  # "preflop", "flop", "turn", "river"

    # Postflop gate context
    hand_class: str  # "trash", "bottom_pair", "middle_pair", "top_pair", etc.
    board_texture: BoardTexture
    equity: float
    pot_odds: float
    pot: int

    # All-in gate context
    spr: float
    has_strong_draw: bool  # flush draw + pair, or OESFD
    remaining_stack: int
    would_be_all_in: bool  # pre-computed: True if the proposed raise commits all remaining chips

    # Raise-ladder context
    raises_faced_this_street: int

    # Legal actions
    legal_actions: list[str]


HAND_CLASS_ORDER: dict[str, int] = {
    "trash": 0,
    "bottom_pair": 1,
    "middle_pair": 2,
    "top_pair": 3,
    "overpair": 4,
    "two_pair": 5,
    "set": 6,
    "straight": 7,
    "flush": 8,
    "full_house": 9,
    "quads": 10,
    "straight_flush": 11,
}

TOP_5_PERCENT_HANDS: set[str] = {"AA", "KK", "QQ", "AKs", "AKo", "JJ"}

PREMIUM_HANDS: set[str] = {"AA", "KK", "QQ", "AKs", "AKo"}


def apply_raise_ladder_gate(scores: ActionScores, ctx: GateContext) -> ActionScores:
    """Raise-ladder protection against repeated raise-bluffing exploits.

    Rules:
      - 2+ raises + equity < 45%: raise = -1e9
      - 2+ raises + one pair (HAND_CLASS_ORDER <= 3) + SPR > 2.0 + would_be_all_in: raise = -1e9
      - 2+ raises + hand < two pair (HAND_CLASS_ORDER < 5) + no strong draw: raise -= 0.25 × pot
      - 3+ raises + equity < 60%: raise = -1e9, call -= 0.15 × pot
    """
    if ctx.raises_faced_this_street < 2:
        return scores  # Gate only activates with 2+ raises faced

    hand_rank = HAND_CLASS_ORDER.get(ctx.hand_class, -1)

    # 2+ raises + low equity -> block raise
    if ctx.equity < 0.45:
        scores.raise_ = -1e9
        logger.info(
            f"Raise-ladder gate: raise -> -1e9 (equity={ctx.equity} < 0.45, "
            f"raises={ctx.raises_faced_this_street})"
        )

    # 2+ raises + one pair + high SPR + would be all-in -> block all-in raise
    if hand_rank <= 3 and ctx.spr > 2.0 and ctx.would_be_all_in:
        scores.raise_ = -1e9
        logger.info(
            f"Raise-ladder gate: raise -> -1e9 (one pair, SPR={ctx.spr} > 2.0, all-in)"
        )

    # 2+ raises + below two pair + no strong draw -> discourage raise
    if hand_rank < 5 and not ctx.has_strong_draw:
        scores.raise_ -= 0.25 * ctx.pot
        logger.info(
            f"Raise-ladder gate: raise -= {0.25 * ctx.pot} (hand < two_pair, no draw)"
        )

    # 3+ raises + equity < 60% -> block raise and penalize call
    if ctx.raises_faced_this_street >= 3 and ctx.equity < 0.60:
        scores.raise_ = -1e9
        scores.call -= 0.15 * ctx.pot
        logger.info(
            f"Raise-ladder gate: raise -> -1e9, call -= {0.15 * ctx.pot} "
            f"(3+ raises, equity={ctx.equity})"
        )

    return scores


def apply_allin_gate(scores: ActionScores, ctx: GateContext) -> ActionScores:
    """SPR-based all-in discipline.

    Uses ctx.would_be_all_in (pre-computed flag) to determine if the proposed
    raise commits all remaining chips. Only masks the raise score when
    would_be_all_in is True; normal-sized raises are not blocked by this gate.

    Rules:
      - SPR > 3.0 + one pair or worse (HAND_CLASS_ORDER <= 3) + no strong draw + would_be_all_in: raise = -1e9
      - SPR > 6.0 + below two pair (HAND_CLASS_ORDER < 5) + equity <= 70% + would_be_all_in: raise = -1e9
      - SPR <= 1.5 + top pair+ (HAND_CLASS_ORDER >= 3) or strong draw + would_be_all_in: raise += 0.2 × pot
    """
    if not ctx.would_be_all_in:
        return scores  # Only apply to all-in raises

    hand_rank = HAND_CLASS_ORDER.get(ctx.hand_class, -1)

    # High SPR + weak hand + no draw -> block all-in
    if ctx.spr > 3.0 and hand_rank <= 3 and not ctx.has_strong_draw:
        scores.raise_ = -1e9
        logger.info(
            f"All-in gate: raise -> -1e9 (SPR={ctx.spr}, hand={ctx.hand_class}, no draw)"
        )

    # Very high SPR + below two pair + not great equity -> block all-in
    if ctx.spr > 6.0 and hand_rank < 5 and ctx.equity <= 0.70:
        scores.raise_ = -1e9
        logger.info(
            f"All-in gate: raise -> -1e9 (SPR={ctx.spr} > 6, hand={ctx.hand_class}, equity={ctx.equity})"
        )

    # Low SPR + strong hand/draw -> encourage all-in
    if ctx.spr <= 1.5 and (hand_rank >= 3 or ctx.has_strong_draw):
        scores.raise_ += 0.2 * ctx.pot
        logger.info(
            f"All-in gate: raise += {0.2 * ctx.pot} (SPR={ctx.spr} <= 1.5, strong hand/draw)"
        )

    return scores


# Rank order for canonical hand representation
_RANK_ORDER = "23456789TJQKA"


def _get_hand_representation(hole_cards: list[str]) -> str:
    """Convert hole cards like ["Ah", "Ks"] to canonical representation like "AKs" or "AKo".

    Returns empty string for invalid/empty inputs.
    Canonical form: higher rank first, followed by 's' (suited) or 'o' (offsuit).
    Pairs are represented as just the rank doubled (e.g., "AA").
    """
    if not hole_cards or len(hole_cards) < 2:
        return ""

    card1, card2 = hole_cards[0], hole_cards[1]

    # Validate card format: at least 2 chars, rank + suit
    if len(card1) < 2 or len(card2) < 2:
        return ""

    rank1, suit1 = card1[0].upper(), card1[1].lower()
    rank2, suit2 = card2[0].upper(), card2[1].lower()

    # Validate ranks
    if rank1 not in _RANK_ORDER or rank2 not in _RANK_ORDER:
        return ""

    # Order by rank (higher first)
    idx1 = _RANK_ORDER.index(rank1)
    idx2 = _RANK_ORDER.index(rank2)

    if idx1 < idx2:
        rank1, rank2 = rank2, rank1
        suit1, suit2 = suit2, suit1

    # Pairs: just two ranks, no suited/offsuit suffix
    if rank1 == rank2:
        return f"{rank1}{rank2}"

    # Suited or offsuit
    suffix = "s" if suit1 == suit2 else "o"
    return f"{rank1}{rank2}{suffix}"


def apply_preflop_gate(scores: ActionScores, ctx: GateContext) -> ActionScores:
    """Preflop premium protection and deep-stack 4-bet restriction.

    Rules:
      - Premium hand (AA/KK/QQ/AK) + single raise + 50BB+:
        fold = -1e9, raise += 0.3 × pot
      - Non-top-5% hand + 100BB+ + would_be_all_in:
        raise = -1e9 (only blocks all-in raises, not normal-sized raises)

    Only activates when phase == "preflop".
    """
    if ctx.phase != "preflop":
        return scores

    # Premium protection
    if ctx.is_premium and ctx.facing_action == "raise" and ctx.effective_stack_bb >= 50:
        original_fold = scores.fold
        original_raise = scores.raise_
        scores.fold = -1e9
        scores.raise_ += 0.3 * ctx.pot
        logger.info(
            f"Preflop premium gate: fold {original_fold} -> -1e9, "
            f"raise {original_raise} -> {scores.raise_}"
        )

    # Deep-stack 4-bet protection (only blocks all-in raises)
    hand_repr = _get_hand_representation(ctx.hole_cards)
    if (
        hand_repr not in TOP_5_PERCENT_HANDS
        and ctx.effective_stack_bb >= 100
        and ctx.would_be_all_in
    ):
        original_raise = scores.raise_
        scores.raise_ = -1e9
        logger.info(
            f"Preflop deep-stack gate: raise {original_raise} -> -1e9 "
            f"(non-top-5%, {ctx.effective_stack_bb}BB, would_be_all_in)"
        )

    return scores

def apply_postflop_gate(scores: ActionScores, ctx: GateContext) -> ActionScores:
    """Dry board raise restriction and pot-odds fold protection.

    Rules:
      - Dry board + bottom pair or worse: raise = -1e9
      - Dry board + middle pair + equity < 40%: raise -= 0.2 × pot
      - Equity > pot_odds + 5% AND top pair+: fold = -1e9, call += 0.15 × pot
      - Equity > pot_odds + 10% (any hand): fold = -1e9

    Only activates when phase != "preflop".
    """
    if ctx.phase == "preflop":
        return scores

    hand_rank = HAND_CLASS_ORDER.get(ctx.hand_class, -1)

    # Dry board raise restriction
    if ctx.board_texture.is_dry:
        if hand_rank != -1 and hand_rank <= 1:  # bottom_pair or worse
            scores.raise_ = -1e9
            logger.info(
                f"Postflop dry board gate: raise -> -1e9 (hand_class={ctx.hand_class})"
            )
        elif ctx.hand_class == "middle_pair" and ctx.equity < 0.40:
            scores.raise_ -= 0.2 * ctx.pot
            logger.info(
                f"Postflop dry board gate: raise -= {0.2 * ctx.pot} "
                f"(middle_pair, equity={ctx.equity})"
            )

    # Pot-odds fold protection
    if ctx.equity > ctx.pot_odds + 0.05 and hand_rank >= 3:  # top_pair or better
        scores.fold = -1e9
        scores.call += 0.15 * ctx.pot
        logger.info(f"Pot-odds gate: fold -> -1e9, call += {0.15 * ctx.pot}")

    if ctx.equity > ctx.pot_odds + 0.10:  # any hand
        scores.fold = -1e9
        logger.info(
            f"Pot-odds gate (strong): fold -> -1e9 "
            f"(equity={ctx.equity}, pot_odds={ctx.pot_odds})"
        )

    return scores


def apply_sanity_gates(scores: ActionScores, ctx: GateContext) -> ActionScores:
    """Apply all gates in sequence: preflop -> postflop -> all-in -> raise-ladder.

    Each gate modifies scores in-place via score masks:
      - Forbidden: score = -1e9
      - Discouraged: score -= penalty
      - Protected: score += bonus

    Returns modified ActionScores.
    """
    scores = apply_preflop_gate(scores, ctx)
    scores = apply_postflop_gate(scores, ctx)
    scores = apply_allin_gate(scores, ctx)
    scores = apply_raise_ladder_gate(scores, ctx)
    return scores


def validate_selection(
    selected_action: str, scores: ActionScores, legal_actions: list[str]
) -> str:
    """Final safety check after select_action().

    If the selected action has score == -1e9 (forbidden by gates), fall back
    to the highest-scoring legal non-forbidden action.

    Guarantees: at least one legal action is always available.
    If all aggressive actions are forbidden, returns check > call > fold.
    """
    # Get the score for the selected action
    action_score_map = {
        "fold": scores.fold,
        "check": scores.check,
        "call": scores.call,
        "bet": scores.bet,
        "raise": scores.raise_,
    }

    selected_score = action_score_map.get(selected_action, 0.0)

    # If selected action is not forbidden, return it
    if selected_score > -1e9:
        return selected_action

    # Fall back to highest-scoring non-forbidden legal action
    best_action = None
    best_score = -float("inf")

    for action in legal_actions:
        score = action_score_map.get(action, 0.0)
        if score > -1e9 and score > best_score:
            best_score = score
            best_action = action

    if best_action is not None:
        return best_action

    # Emergency fallback: all actions are forbidden (should never happen)
    # Guarantee at least one action: check > call > fold
    for fallback in ["check", "call", "fold"]:
        if fallback in legal_actions:
            return fallback

    # Absolute last resort (shouldn't reach here with valid legal_actions)
    return legal_actions[0] if legal_actions else "fold"
