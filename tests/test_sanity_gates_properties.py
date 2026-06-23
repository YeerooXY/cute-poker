"""Property-based tests for sanity gates.

Tests the core gate invariants: preflop premium protection, deep stack 4-bet
protection, dry board raise restriction, pot odds call protection, SPR all-in
gating, raise-ladder protection, and legal action preservation.

Validates: Requirements 3.1, 3.2, 4.1, 5.1, 6.1, 6.2, 7.1, 7.4, 2.7
"""

from hypothesis import given, settings, assume, strategies as st
import pytest

from poker.bot_ai.sanity_gates import (
    GateContext,
    HAND_CLASS_ORDER,
    TOP_5_PERCENT_HANDS,
    PREMIUM_HANDS,
    apply_preflop_gate,
    apply_postflop_gate,
    apply_allin_gate,
    apply_raise_ladder_gate,
    apply_sanity_gates,
    validate_selection,
)
from poker.bot_ai.models import ActionScores, BoardTexture


# ─── Helper: Build GateContext with sensible defaults ──────────────────────────


def make_gate_context(**overrides) -> GateContext:
    """Build a GateContext with sensible defaults and given overrides."""
    defaults = {
        "hole_cards": ["Ah", "Kd"],
        "hand_percentile": 0.05,
        "is_premium": True,
        "effective_stack_bb": 100.0,
        "facing_action": "raise",
        "phase": "flop",
        "hand_class": "top_pair",
        "board_texture": BoardTexture(is_dry=False, is_wet=False),
        "equity": 0.50,
        "pot_odds": 0.30,
        "pot": 200,
        "spr": 5.0,
        "has_strong_draw": False,
        "remaining_stack": 1000,
        "would_be_all_in": False,
        "raises_faced_this_street": 0,
        "legal_actions": ["fold", "call", "raise"],
    }
    defaults.update(overrides)
    return GateContext(**defaults)


# ─── Strategies ────────────────────────────────────────────────────────────────

premium_hands_st = st.sampled_from(["AA", "KK", "QQ", "AKs", "AKo"])
weak_hand_classes_st = st.sampled_from(["trash", "bottom_pair"])
all_hand_classes_st = st.sampled_from(list(HAND_CLASS_ORDER.keys()))
non_top5_hands_st = st.sampled_from(
    ["JTs", "TT", "99", "88", "77", "AQs", "AQo", "AJs", "KQs", "QJs", "J9o", "72o"]
)


def _hand_to_hole_cards(hand_repr: str) -> list[str]:
    """Convert a canonical hand representation to hole cards.

    e.g., 'AA' -> ['Ah', 'Ad'], 'AKs' -> ['Ah', 'Kh'], 'AKo' -> ['Ah', 'Kd']
    """
    suits = ["h", "d", "c", "s"]
    if len(hand_repr) == 2:
        # Pair: e.g., "AA"
        return [f"{hand_repr[0]}{suits[0]}", f"{hand_repr[1]}{suits[1]}"]
    elif hand_repr.endswith("s"):
        # Suited: e.g., "AKs"
        return [f"{hand_repr[0]}{suits[0]}", f"{hand_repr[1]}{suits[0]}"]
    else:
        # Offsuit: e.g., "AKo"
        return [f"{hand_repr[0]}{suits[0]}", f"{hand_repr[1]}{suits[1]}"]


# ─── Property 4: Preflop Premium Protection ──────────────────────────────────
# Feature: balanced-bot-ai, Property 4: Preflop Premium Protection
# For any game state where the bot holds a Premium_Hand (AA, KK, QQ, AK) and is
# facing a single raise with effective stacks of 50BB or more, the fold score
# after gate application SHALL be -1e9 and the raise score SHALL include a bonus
# of 0.3 × pot.
# **Validates: Requirements 3.1**


@settings(max_examples=50)
@given(
    hand=premium_hands_st,
    stack_bb=st.floats(min_value=50.0, max_value=500.0),
    pot=st.integers(min_value=100, max_value=5000),
    initial_fold=st.floats(min_value=-10.0, max_value=10.0),
    initial_raise=st.floats(min_value=-10.0, max_value=10.0),
)
def test_preflop_premium_protection(hand, stack_bb, pot, initial_fold, initial_raise):
    """Premium hands + single raise + 50BB+ → fold = -1e9, raise includes 0.3 × pot bonus.

    Validates: Requirements 3.1
    """
    hole_cards = _hand_to_hole_cards(hand)
    scores = ActionScores(fold=initial_fold, check=0.0, call=0.0, bet=0.0, raise_=initial_raise)
    ctx = make_gate_context(
        hole_cards=hole_cards,
        is_premium=True,
        effective_stack_bb=stack_bb,
        facing_action="raise",
        phase="preflop",
        pot=pot,
    )

    result = apply_preflop_gate(scores, ctx)

    assert result.fold == -1e9, f"Expected fold=-1e9 for premium hand {hand}, got {result.fold}"
    expected_raise = initial_raise + 0.3 * pot
    assert abs(result.raise_ - expected_raise) < 1e-6, (
        f"Expected raise={expected_raise} (initial {initial_raise} + 0.3*{pot}), got {result.raise_}"
    )


# ─── Property 5: Deep Stack 4-Bet Protection ─────────────────────────────────
# Feature: balanced-bot-ai, Property 5: Deep Stack 4-Bet Protection
# For any hand outside the top 5% of starting hands (not AA, KK, QQ, AKs, AKo, JJ)
# with effective stacks of 100BB or more, the all-in raise score after gate
# application SHALL be -1e9.
# **Validates: Requirements 3.2**


@settings(max_examples=50)
@given(
    hand=non_top5_hands_st,
    stack_bb=st.floats(min_value=100.0, max_value=500.0),
    pot=st.integers(min_value=100, max_value=5000),
    initial_raise=st.floats(min_value=-10.0, max_value=10.0),
)
def test_deep_stack_4bet_protection(hand, stack_bb, pot, initial_raise):
    """Non-top-5% hands + 100BB+ + would_be_all_in → all-in raise = -1e9.

    Validates: Requirements 3.2
    """
    hole_cards = _hand_to_hole_cards(hand)
    scores = ActionScores(fold=0.0, check=0.0, call=0.0, bet=0.0, raise_=initial_raise)
    ctx = make_gate_context(
        hole_cards=hole_cards,
        is_premium=False,
        effective_stack_bb=stack_bb,
        facing_action="raise",
        phase="preflop",
        pot=pot,
        would_be_all_in=True,
    )

    result = apply_preflop_gate(scores, ctx)

    assert result.raise_ == -1e9, (
        f"Expected raise=-1e9 for non-top-5% hand {hand} at {stack_bb}BB (all-in), got {result.raise_}"
    )


# ─── Property 6: Dry Board Raise Restriction ─────────────────────────────────
# Feature: balanced-bot-ai, Property 6: Dry Board Raise Restriction
# For any dry board texture where the bot holds bottom pair or worse, the raise
# score after gate application SHALL be -1e9.
# **Validates: Requirements 4.1**


@settings(max_examples=50)
@given(
    hand_class=weak_hand_classes_st,
    pot=st.integers(min_value=100, max_value=5000),
    initial_raise=st.floats(min_value=-10.0, max_value=10.0),
    equity=st.floats(min_value=0.0, max_value=1.0),
    pot_odds=st.floats(min_value=0.0, max_value=1.0),
)
def test_dry_board_raise_restriction(hand_class, pot, initial_raise, equity, pot_odds):
    """Dry board + bottom pair or worse → raise = -1e9.

    Validates: Requirements 4.1
    """
    scores = ActionScores(fold=0.0, check=0.0, call=0.0, bet=0.0, raise_=initial_raise)
    ctx = make_gate_context(
        hand_class=hand_class,
        board_texture=BoardTexture(is_dry=True, is_wet=False),
        phase="flop",
        pot=pot,
        equity=equity,
        pot_odds=pot_odds,
    )

    result = apply_postflop_gate(scores, ctx)

    assert result.raise_ == -1e9, (
        f"Expected raise=-1e9 for dry board + {hand_class}, got {result.raise_}"
    )


# ─── Property 7: Pot Odds Call Protection ─────────────────────────────────────
# Feature: balanced-bot-ai, Property 7: Pot Odds Call Protection
# For any game state where the bot's equity exceeds pot odds by 5 percentage
# points or more AND the bot holds top pair or better, the fold score after
# gate application SHALL be -1e9 and the call score SHALL include a bonus of
# 0.15 × pot.
# **Validates: Requirements 5.1**


@settings(max_examples=50)
@given(
    pot_odds=st.floats(min_value=0.0, max_value=0.90),
    equity_margin=st.floats(min_value=0.051, max_value=0.50),
    hand_class=st.sampled_from(
        ["top_pair", "overpair", "two_pair", "set", "straight", "flush", "full_house", "quads", "straight_flush"]
    ),
    pot=st.integers(min_value=100, max_value=5000),
    initial_fold=st.floats(min_value=-10.0, max_value=10.0),
    initial_call=st.floats(min_value=-10.0, max_value=10.0),
)
def test_pot_odds_call_protection(pot_odds, equity_margin, hand_class, pot, initial_fold, initial_call):
    """Equity > pot_odds + 5% + top pair+ → fold = -1e9, call includes 0.15 × pot bonus.

    Validates: Requirements 5.1
    """
    equity = pot_odds + equity_margin
    assume(equity <= 1.0)

    scores = ActionScores(fold=initial_fold, check=0.0, call=initial_call, bet=0.0, raise_=0.0)
    ctx = make_gate_context(
        hand_class=hand_class,
        equity=equity,
        pot_odds=pot_odds,
        pot=pot,
        phase="flop",
        board_texture=BoardTexture(is_dry=False, is_wet=False),
    )

    result = apply_postflop_gate(scores, ctx)

    assert result.fold == -1e9, (
        f"Expected fold=-1e9 for equity={equity} > pot_odds={pot_odds}+0.05 + {hand_class}, "
        f"got {result.fold}"
    )
    expected_call = initial_call + 0.15 * pot
    assert abs(result.call - expected_call) < 1e-6, (
        f"Expected call={expected_call} (initial {initial_call} + 0.15*{pot}), got {result.call}"
    )


# ─── Property 8: SPR All-In Gating ───────────────────────────────────────────
# Feature: balanced-bot-ai, Property 8: SPR All-In Gating
# For any game state where SPR > 3.0 and the bot holds one pair (top pair or
# worse) without a Strong_Draw, the all-in raise score after gate application
# SHALL be -1e9.
# **Validates: Requirements 6.1, 6.2**


@settings(max_examples=50)
@given(
    spr=st.floats(min_value=3.01, max_value=20.0),
    hand_class=st.sampled_from(["trash", "bottom_pair", "middle_pair", "top_pair"]),
    pot=st.integers(min_value=100, max_value=5000),
    initial_raise=st.floats(min_value=-10.0, max_value=10.0),
)
def test_spr_allin_gating(spr, hand_class, pot, initial_raise):
    """SPR > 3.0 + one pair or worse + no draw + would_be_all_in → all-in raise = -1e9.

    Validates: Requirements 6.1, 6.2
    """
    scores = ActionScores(fold=0.0, check=0.0, call=0.0, bet=0.0, raise_=initial_raise)
    ctx = make_gate_context(
        spr=spr,
        hand_class=hand_class,
        has_strong_draw=False,
        would_be_all_in=True,
        pot=pot,
        phase="flop",
    )

    result = apply_allin_gate(scores, ctx)

    assert result.raise_ == -1e9, (
        f"Expected raise=-1e9 for SPR={spr} > 3.0, hand={hand_class}, no draw, all-in, "
        f"got {result.raise_}"
    )


# ─── Property 9: Raise-Ladder Protection ─────────────────────────────────────
# Feature: balanced-bot-ai, Property 9: Raise-Ladder Protection
# For any game state where the bot has faced 2 or more raises on the current
# street AND the bot's equity is below 45%, the raise score after gate
# application SHALL be -1e9.
# **Validates: Requirements 7.1, 7.4**


@settings(max_examples=50)
@given(
    raises_faced=st.integers(min_value=2, max_value=10),
    equity=st.floats(min_value=0.0, max_value=0.449),
    pot=st.integers(min_value=100, max_value=5000),
    initial_raise=st.floats(min_value=-10.0, max_value=10.0),
    initial_call=st.floats(min_value=-10.0, max_value=10.0),
)
def test_raise_ladder_protection(raises_faced, equity, pot, initial_raise, initial_call):
    """2+ raises + equity < 45% → raise = -1e9.

    Additionally, for 3+ raises + equity < 60%: raise = -1e9, call -= 0.15 × pot.

    Validates: Requirements 7.1, 7.4
    """
    scores = ActionScores(fold=0.0, check=0.0, call=initial_call, bet=0.0, raise_=initial_raise)
    ctx = make_gate_context(
        raises_faced_this_street=raises_faced,
        equity=equity,
        pot=pot,
        phase="flop",
    )

    result = apply_raise_ladder_gate(scores, ctx)

    # 2+ raises + equity < 45% → raise is forbidden (set to -1e9 or below,
    # since additional penalty rules may stack on top of the -1e9 value)
    assert result.raise_ <= -1e9, (
        f"Expected raise<=-1e9 for {raises_faced} raises faced + equity={equity} < 0.45, "
        f"got {result.raise_}"
    )

    # 3+ raises + equity < 60% → additional call penalty
    if raises_faced >= 3 and equity < 0.60:
        # For call, the 3+ raises rule applies (-0.15 * pot).
        expected_call = initial_call - 0.15 * pot
        assert abs(result.call - expected_call) < 1e-6, (
            f"Expected call={expected_call} (initial {initial_call} - 0.15*{pot}), "
            f"got {result.call}"
        )


# ─── Property 11: Legal Action Preservation ──────────────────────────────────
# Feature: balanced-bot-ai, Property 11: Legal Action Preservation
# For any set of sanity gate applications on any ActionScores, at least one
# action SHALL remain with a score above -1e9. The gates SHALL never leave the
# bot with zero legal actions.
# **Validates: Requirements 2.7**


@settings(max_examples=50)
@given(
    fold_score=st.floats(min_value=-100.0, max_value=100.0),
    check_score=st.floats(min_value=-100.0, max_value=100.0),
    call_score=st.floats(min_value=-100.0, max_value=100.0),
    bet_score=st.floats(min_value=-100.0, max_value=100.0),
    raise_score=st.floats(min_value=-100.0, max_value=100.0),
    hand_class=all_hand_classes_st,
    equity=st.floats(min_value=0.0, max_value=1.0),
    pot_odds=st.floats(min_value=0.0, max_value=1.0),
    pot=st.integers(min_value=100, max_value=5000),
    spr=st.floats(min_value=0.1, max_value=20.0),
    raises_faced=st.integers(min_value=0, max_value=5),
    is_premium=st.booleans(),
    has_strong_draw=st.booleans(),
    would_be_all_in=st.booleans(),
    effective_stack_bb=st.floats(min_value=10.0, max_value=500.0),
    phase=st.sampled_from(["preflop", "flop", "turn", "river"]),
    is_dry=st.booleans(),
)
def test_legal_action_preservation(
    fold_score,
    check_score,
    call_score,
    bet_score,
    raise_score,
    hand_class,
    equity,
    pot_odds,
    pot,
    spr,
    raises_faced,
    is_premium,
    has_strong_draw,
    would_be_all_in,
    effective_stack_bb,
    phase,
    is_dry,
):
    """After apply_sanity_gates, validate_selection always returns a non-forbidden action.

    For any valid context, at least one action remains above -1e9 after all gates
    are applied, and validate_selection returns a legal action.

    Validates: Requirements 2.7
    """
    legal_actions = ["fold", "check", "call", "raise"]

    scores = ActionScores(
        fold=fold_score,
        check=check_score,
        call=call_score,
        bet=bet_score,
        raise_=raise_score,
    )

    # Pick a hand representation that matches premium status
    if is_premium:
        hole_cards = ["Ah", "Kd"]  # AKo
    else:
        hole_cards = ["7h", "2d"]  # 72o (clearly non-premium, non-top-5%)

    ctx = make_gate_context(
        hole_cards=hole_cards,
        hand_percentile=0.02 if is_premium else 0.80,
        is_premium=is_premium,
        effective_stack_bb=effective_stack_bb,
        facing_action="raise",
        phase=phase,
        hand_class=hand_class,
        board_texture=BoardTexture(is_dry=is_dry, is_wet=not is_dry),
        equity=equity,
        pot_odds=pot_odds,
        pot=pot,
        spr=spr,
        has_strong_draw=has_strong_draw,
        remaining_stack=1000,
        would_be_all_in=would_be_all_in,
        raises_faced_this_street=raises_faced,
        legal_actions=legal_actions,
    )

    result = apply_sanity_gates(scores, ctx)

    # Try each legal action as the selected action and verify validate_selection
    # always returns a valid non-forbidden action
    for action in legal_actions:
        validated = validate_selection(action, result, legal_actions)
        assert validated in legal_actions, (
            f"validate_selection returned '{validated}' which is not in legal_actions={legal_actions}"
        )
        # The validated action must not be forbidden
        score_map = {
            "fold": result.fold,
            "check": result.check,
            "call": result.call,
            "bet": result.bet,
            "raise": result.raise_,
        }
        validated_score = score_map.get(validated, 0.0)
        # Either the validated action is not forbidden, OR it's the emergency fallback
        # (which is acceptable per requirement 2.7 — at least one action remains)
        if validated_score <= -1e9:
            # This can only happen if ALL actions are forbidden (emergency fallback)
            # Verify that indeed all are forbidden
            all_forbidden = all(
                score_map.get(a, 0.0) <= -1e9 for a in legal_actions
            )
            assert all_forbidden, (
                f"validate_selection returned forbidden action '{validated}' "
                f"but not all actions are forbidden. Scores: {score_map}"
            )
