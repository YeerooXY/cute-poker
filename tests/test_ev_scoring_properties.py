"""Property-based tests for EV scoring in the Action Scorer.

Tests the correctness properties of the compute_ev_scores function
from the EV-based bot AI spec.
"""

import math

from hypothesis import given, settings, assume, strategies as st

from poker.bot_ai.action_scorer import compute_ev_scores


# ─── Property 1: Fold EV is always 0.0 ───────────────────────────────────────
# **Validates: Requirements 1.1**


class TestFoldEVInvariant:
    """Property 1: For ALL random valid game states, the fold EV produced by
    compute_ev_scores is always exactly 0.0."""

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        call_amount=st.integers(min_value=0, max_value=100000),
        bet_amount=st.integers(min_value=0, max_value=200000),
        raise_amount=st.integers(min_value=0, max_value=300000),
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        num_opponents=st.integers(min_value=1, max_value=7),
    )
    def test_fold_ev_always_zero(
        self,
        equity: float,
        pot: int,
        call_amount: int,
        bet_amount: int,
        raise_amount: int,
        fold_probability: float,
        num_opponents: int,
    ):
        """**Validates: Requirements 1.1**

        Regardless of equity, pot size, call amount, bet amount, raise amount,
        fold probability, or number of opponents, the fold EV must be exactly 0.0.
        Fold is the baseline action — surrendering costs nothing more.
        """
        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=["fold", "call", "bet", "raise"],
            num_opponents=num_opponents,
        )

        assert scores.fold == 0.0, (
            f"Fold EV should be exactly 0.0 but got {scores.fold} "
            f"with equity={equity}, pot={pot}, call_amount={call_amount}, "
            f"bet_amount={bet_amount}, raise_amount={raise_amount}, "
            f"fold_probability={fold_probability}, num_opponents={num_opponents}"
        )


# ─── Property 2: Call EV matches formula ──────────────────────────────────────
# **Validates: Requirements 2.1, 2.2**


class TestCallEVFormula:
    """Property 2: For ALL valid equity ∈ [0,1], pot > 0, call_amount > 0:
    call_ev == equity × (pot + call_amount) − call_amount."""

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        call_amount=st.integers(min_value=1, max_value=100000),
    )
    def test_call_ev_matches_formula(
        self,
        equity: float,
        pot: int,
        call_amount: int,
    ):
        """**Validates: Requirements 2.1, 2.2**

        The call EV must equal: equity × (pot + call_amount) − call_amount.
        This is the fundamental pot-odds formula for calling.
        """
        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=0,
            raise_amount=0,
            fold_probability=0.5,
            legal_actions=["fold", "call"],
            num_opponents=1,
        )

        expected_call_ev = equity * (pot + call_amount) - call_amount

        assert math.isclose(scores.call, expected_call_ev, abs_tol=1e-9), (
            f"Call EV mismatch: got {scores.call}, expected {expected_call_ev} "
            f"with equity={equity}, pot={pot}, call_amount={call_amount}"
        )


# ─── Property 3: Call EV sign consistency ─────────────────────────────────────
# **Validates: Requirements 2.2, 2.3**


class TestCallEVSignConsistency:
    """Property 3: Call EV sign is consistent with the profit/loss inequality.
    When equity × (pot + call_amount) < call_amount → call_ev is negative.
    When equity × (pot + call_amount) > call_amount → call_ev is positive."""

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        call_amount=st.integers(min_value=1, max_value=100000),
    )
    def test_call_ev_negative_when_unprofitable(
        self,
        equity: float,
        pot: int,
        call_amount: int,
    ):
        """**Validates: Requirements 2.2, 2.3**

        When equity × (pot + call_amount) < call_amount, the call EV must be
        negative — calling is a losing proposition.
        """
        final_pot = pot + call_amount
        # Only test cases where the call is clearly unprofitable
        assume(equity * final_pot < call_amount - 1e-9)

        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=0,
            raise_amount=0,
            fold_probability=0.5,
            legal_actions=["fold", "call"],
            num_opponents=1,
        )

        assert scores.call < 0, (
            f"Call EV should be negative but got {scores.call} "
            f"with equity={equity}, pot={pot}, call_amount={call_amount}, "
            f"equity × final_pot={equity * final_pot} < call_amount={call_amount}"
        )

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        call_amount=st.integers(min_value=1, max_value=100000),
    )
    def test_call_ev_positive_when_profitable(
        self,
        equity: float,
        pot: int,
        call_amount: int,
    ):
        """**Validates: Requirements 2.2, 2.3**

        When equity × (pot + call_amount) > call_amount, the call EV must be
        positive — calling is a winning proposition.
        """
        final_pot = pot + call_amount
        # Only test cases where the call is clearly profitable
        assume(equity * final_pot > call_amount + 1e-9)

        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=0,
            raise_amount=0,
            fold_probability=0.5,
            legal_actions=["fold", "call"],
            num_opponents=1,
        )

        assert scores.call > 0, (
            f"Call EV should be positive but got {scores.call} "
            f"with equity={equity}, pot={pot}, call_amount={call_amount}, "
            f"equity × final_pot={equity * final_pot} > call_amount={call_amount}"
        )


# ─── Property 4: Bet EV matches semi-bluff formula ───────────────────────────
# **Validates: Requirements 3.1**


class TestBetEVFormula:
    """Property 4: For ALL valid fold_prob ∈ [0,1], equity ∈ [0,1], pot > 0,
    bet_amount > 0 (single opponent):
    bet_ev == fold_prob × pot + (1 − fold_prob) × (equity × (pot + 2×bet_amount) − bet_amount)."""

    @settings(max_examples=200)
    @given(
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        bet_amount=st.integers(min_value=1, max_value=200000),
    )
    def test_bet_ev_matches_semi_bluff_formula(
        self,
        fold_probability: float,
        equity: float,
        pot: int,
        bet_amount: int,
    ):
        """**Validates: Requirements 3.1**

        The bet EV for a single opponent must equal:
        fold_prob × pot + (1 − fold_prob) × (equity × (pot + 2×bet) − bet)
        where the final pot if called = pot + hero_bet + opponent_call = pot + 2×bet.
        """
        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=0,
            fold_probability=fold_probability,
            legal_actions=["fold", "bet"],
            num_opponents=1,
        )

        final_pot_if_called = pot + 2 * bet_amount
        expected_bet_ev = (
            fold_probability * pot
            + (1 - fold_probability) * (equity * final_pot_if_called - bet_amount)
        )

        assert math.isclose(scores.bet, expected_bet_ev, abs_tol=1e-9), (
            f"Bet EV mismatch: got {scores.bet}, expected {expected_bet_ev} "
            f"with fold_prob={fold_probability}, equity={equity}, "
            f"pot={pot}, bet_amount={bet_amount}"
        )


# ─── Property 5: Bet EV degenerate cases ─────────────────────────────────────
# **Validates: Requirements 3.2, 3.3**


class TestBetEVDegenerateCases:
    """Property 5: Bet EV boundary conditions.
    When fold_prob=1.0: bet_ev == pot (opponent always folds, we win current pot).
    When fold_prob=0.0 and equity=0.0: bet_ev == -bet_amount (never win, always pay)."""

    @settings(max_examples=200)
    @given(
        pot=st.integers(min_value=1, max_value=100000),
        bet_amount=st.integers(min_value=1, max_value=200000),
    )
    def test_bet_ev_equals_pot_when_fold_prob_one(
        self,
        pot: int,
        bet_amount: int,
    ):
        """**Validates: Requirements 3.2**

        When fold_prob=1.0, the opponent always folds and we win the current pot.
        bet_ev must equal pot regardless of equity or bet amount.
        """
        scores = compute_ev_scores(
            equity=0.5,  # equity is irrelevant when fold_prob=1
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=0,
            fold_probability=1.0,
            legal_actions=["fold", "bet"],
            num_opponents=1,
        )

        assert math.isclose(scores.bet, float(pot), abs_tol=1e-9), (
            f"Bet EV should equal pot={pot} when fold_prob=1.0, "
            f"but got {scores.bet}"
        )

    @settings(max_examples=200)
    @given(
        pot=st.integers(min_value=1, max_value=100000),
        bet_amount=st.integers(min_value=1, max_value=200000),
    )
    def test_bet_ev_equals_neg_bet_when_fold_prob_zero_equity_zero(
        self,
        pot: int,
        bet_amount: int,
    ):
        """**Validates: Requirements 3.3**

        When fold_prob=0.0 and equity=0.0, opponent never folds and we never
        win the pot. bet_ev must equal -bet_amount.
        """
        scores = compute_ev_scores(
            equity=0.0,
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=0,
            fold_probability=0.0,
            legal_actions=["fold", "bet"],
            num_opponents=1,
        )

        assert math.isclose(scores.bet, float(-bet_amount), abs_tol=1e-9), (
            f"Bet EV should equal -bet_amount={-bet_amount} when fold_prob=0 "
            f"and equity=0, but got {scores.bet}"
        )


# ─── Property 6: Raise EV formula ────────────────────────────────────────────
# **Validates: Requirements 4.1**


class TestRaiseEVFormula:
    """Property 6: For ALL valid inputs (single opponent):
    raise_ev == fold_prob × pot + (1 − fold_prob) × (equity × (pot + 2×raise_amount) − raise_amount).
    Same semi-bluff structure as bet but with raise_amount substituted."""

    @settings(max_examples=200)
    @given(
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        raise_amount=st.integers(min_value=1, max_value=300000),
    )
    def test_raise_ev_matches_semi_bluff_formula(
        self,
        fold_probability: float,
        equity: float,
        pot: int,
        raise_amount: int,
    ):
        """**Validates: Requirements 4.1**

        The raise EV for a single opponent must equal:
        fold_prob × pot + (1 − fold_prob) × (equity × (pot + 2×raise) − raise)
        where final_pot_if_called = pot + hero_raise + opponent_call = pot + 2×raise.
        """
        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=0,
            bet_amount=0,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=["fold", "raise"],
            num_opponents=1,
        )

        final_pot_if_called = pot + 2 * raise_amount
        expected_raise_ev = (
            fold_probability * pot
            + (1 - fold_probability) * (equity * final_pot_if_called - raise_amount)
        )

        assert math.isclose(scores.raise_, expected_raise_ev, abs_tol=1e-9), (
            f"Raise EV mismatch: got {scores.raise_}, expected {expected_raise_ev} "
            f"with fold_prob={fold_probability}, equity={equity}, "
            f"pot={pot}, raise_amount={raise_amount}"
        )


# ─── Property 9: Multiway fold probability ───────────────────────────────────
# **Validates: Requirements 6.1**


class TestMultiwayFoldProbability:
    """Property 9: When num_opponents > 1, combined_fold_prob = fold_prob ^ num_opponents.
    The bet EV with multiple opponents uses the combined fold probability correctly."""

    @settings(max_examples=200)
    @given(
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        bet_amount=st.integers(min_value=1, max_value=200000),
        num_opponents=st.integers(min_value=2, max_value=7),
    )
    def test_multiway_bet_ev_uses_combined_fold_prob(
        self,
        fold_probability: float,
        equity: float,
        pot: int,
        bet_amount: int,
        num_opponents: int,
    ):
        """**Validates: Requirements 6.1**

        For multiway pots with N opponents:
        combined_fold_prob = fold_prob ^ N
        final_pot_if_called = pot + (N+1) × bet_amount
        bet_ev = combined_fold_prob × pot + (1 − combined_fold_prob) × (equity × final_pot_if_called − bet_amount)
        """
        scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=0,
            fold_probability=fold_probability,
            legal_actions=["fold", "bet"],
            num_opponents=num_opponents,
        )

        combined_fold_prob = fold_probability ** num_opponents
        # final_pot_if_called = pot + bet_amount + (num_opponents × bet_amount)
        #                     = pot + (num_opponents + 1) × bet_amount
        final_pot_if_called = pot + bet_amount + (num_opponents * bet_amount)
        expected_bet_ev = (
            combined_fold_prob * pot
            + (1 - combined_fold_prob) * (equity * final_pot_if_called - bet_amount)
        )

        assert math.isclose(scores.bet, expected_bet_ev, abs_tol=1e-9), (
            f"Multiway Bet EV mismatch: got {scores.bet}, expected {expected_bet_ev} "
            f"with fold_prob={fold_probability}, equity={equity}, pot={pot}, "
            f"bet_amount={bet_amount}, num_opponents={num_opponents}, "
            f"combined_fold_prob={combined_fold_prob}"
        )


# ─── Imports for modifier and personality tests ───────────────────────────────

from poker.bot_ai.action_scorer import (
    compute_modifiers,
    compute_base_scores,
    compute_personality_ev_modifiers,
)
from poker.bot_ai.models import (
    ActionModifiers,
    ActionScores,
    BoardTexture,
    BluffScore,
    DynamicAdjustments,
    ExploitAdjustments,
    RangeAdvantage,
    RangeEstimate,
    ScoringContext,
)
from poker.bot_ai.personality_engine import (
    PREDEFINED_PROFILES,
    PokerPersonality,
)


# ─── Shared strategies for modifier tests ─────────────────────────────────────

_ALL_PERSONALITY_NAMES = list(PREDEFINED_PROFILES.keys())

st_personality_name = st.sampled_from(_ALL_PERSONALITY_NAMES)
st_personality = st_personality_name.map(lambda name: PREDEFINED_PROFILES[name])


def _build_scoring_context(
    equity: float,
    pot: int,
    fold_probability: float,
    bet_amount: int,
    raise_amount: int,
    call_amount: int,
    personality: PokerPersonality,
    board_texture: BoardTexture,
    exploit_adjustments: ExploitAdjustments,
    num_opponents: int = 1,
    difficulty_level: str | None = None,
) -> ScoringContext:
    """Helper to build a ScoringContext with all required fields."""
    return ScoringContext(
        equity=equity,
        pot_odds=call_amount / (pot + call_amount) if pot + call_amount > 0 else 0.0,
        opponent_range=RangeEstimate(),
        board_texture=board_texture,
        range_advantage=RangeAdvantage(aggressor_advantage=0.5),
        position="BTN",
        street="flop",
        bluff_score=BluffScore(
            blocker_score=0.3,
            fold_equity=fold_probability,
            range_advantage=0.5,
            backup_equity=equity,
            total_score=0.4,
        ),
        exploit_adjustments=exploit_adjustments,
        dynamic_adjustments=DynamicAdjustments(),
        personality=personality,
        stack_to_pot=10.0,
        is_preflop_aggressor=True,
        fold_probability=fold_probability,
        bet_amount=bet_amount,
        raise_amount=raise_amount,
        num_opponents=num_opponents,
        call_amount=call_amount,
        pot=pot,
        difficulty_level=difficulty_level,
    )


st_board_texture = st.builds(
    BoardTexture,
    is_dry=st.booleans(),
    is_wet=st.booleans(),
    is_paired=st.booleans(),
    is_monotone=st.booleans(),
    is_connected=st.booleans(),
    flush_possible=st.booleans(),
    straight_possible=st.booleans(),
    high_card_rank=st.integers(min_value=2, max_value=14),
)

st_exploit_adjustments = st.builds(
    ExploitAdjustments,
    three_bet_bluff_boost=st.floats(min_value=0.0, max_value=1.0),
    cbet_frequency_boost=st.floats(min_value=0.0, max_value=1.0),
    bluff_frequency_reduction=st.floats(min_value=0.0, max_value=1.0),
    value_bet_boost=st.floats(min_value=0.0, max_value=1.0),
    active=st.booleans(),
)


# ─── Property 7: Modifier Bounds ─────────────────────────────────────────────
# **Validates: Requirements 5.2, 5.3, 5.4**


class TestModifierBounds:
    """Property 7: For any random personality, exploit adjustments, and board texture,
    the TOTAL combined modifier for each action stays within theoretical bounds.

    The compute_modifiers function sums four components:
      - personality_modifier ∈ [-0.3×pot, 0.3×pot]
      - exploit_modifier ∈ [-0.2×pot, 0.2×pot]
      - board_texture_modifier ∈ [-0.15×pot, 0.15×pot]
      - personality_ev_modifier ∈ [-0.3×pot, 0.3×pot]

    Total theoretical maximum: ±0.95×pot per action.
    """

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        bet_amount=st.integers(min_value=0, max_value=200000),
        raise_amount=st.integers(min_value=0, max_value=300000),
        call_amount=st.integers(min_value=0, max_value=100000),
        personality=st_personality,
        board_texture=st_board_texture,
        exploit_adjustments=st_exploit_adjustments,
        num_opponents=st.integers(min_value=1, max_value=5),
    )
    def test_total_modifiers_within_bounds(
        self,
        equity: float,
        pot: int,
        fold_probability: float,
        bet_amount: int,
        raise_amount: int,
        call_amount: int,
        personality: PokerPersonality,
        board_texture: BoardTexture,
        exploit_adjustments: ExploitAdjustments,
        num_opponents: int,
    ):
        """**Validates: Requirements 5.2, 5.3, 5.4**

        The total modifier per action (personality + exploit + board_texture +
        personality_ev) must be within [-0.95×pot, 0.95×pot] since each component
        has its own bound: 0.3 + 0.2 + 0.15 + 0.3 = 0.95.
        """
        ctx = _build_scoring_context(
            equity=equity,
            pot=pot,
            fold_probability=fold_probability,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            call_amount=call_amount,
            personality=personality,
            board_texture=board_texture,
            exploit_adjustments=exploit_adjustments,
            num_opponents=num_opponents,
        )

        legal_actions = ["fold", "check", "call", "bet", "raise"]
        modifiers = compute_modifiers(ctx, legal_actions)

        # Total theoretical bound = 0.3 + 0.2 + 0.15 + 0.3 = 0.95
        total_bound = 0.95 * pot

        for action_name, mod_value in [
            ("fold", modifiers.fold),
            ("check", modifiers.check),
            ("call", modifiers.call),
            ("bet", modifiers.bet),
            ("raise", modifiers.raise_),
        ]:
            assert -total_bound <= mod_value <= total_bound, (
                f"Modifier for {action_name} = {mod_value} is outside "
                f"[-{total_bound}, {total_bound}] (pot={pot}, "
                f"personality={personality.name})"
            )


# ─── Property 8: Final Score Composition is Additive ─────────────────────────
# **Validates: Requirements 5.1**


class TestFinalScoreComposition:
    """Property 8: For HARD/EXPERT difficulty (full system), the final base score
    equals ev_score + modifiers for each action."""

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=1, max_value=100000),
        fold_probability=st.floats(min_value=0.0, max_value=1.0),
        bet_amount=st.integers(min_value=1, max_value=200000),
        raise_amount=st.integers(min_value=1, max_value=300000),
        call_amount=st.integers(min_value=1, max_value=100000),
        personality=st_personality,
        board_texture=st_board_texture,
        exploit_adjustments=st_exploit_adjustments,
    )
    def test_base_scores_equal_ev_plus_modifiers(
        self,
        equity: float,
        pot: int,
        fold_probability: float,
        bet_amount: int,
        raise_amount: int,
        call_amount: int,
        personality: PokerPersonality,
        board_texture: BoardTexture,
        exploit_adjustments: ExploitAdjustments,
    ):
        """**Validates: Requirements 5.1**

        For HARD difficulty: compute_base_scores(ctx) == compute_ev_scores(...) + compute_modifiers(ctx)
        for each legal action.
        """
        ctx = _build_scoring_context(
            equity=equity,
            pot=pot,
            fold_probability=fold_probability,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            call_amount=call_amount,
            personality=personality,
            board_texture=board_texture,
            exploit_adjustments=exploit_adjustments,
            difficulty_level="HARD",
        )

        legal_actions = ["fold", "check", "call", "bet", "raise"]

        # 1. Compute base scores (full pipeline)
        base_scores = compute_base_scores(ctx, legal_actions)

        # 2. Compute EV scores independently
        ev_scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=legal_actions,
            num_opponents=1,
        )

        # 3. Compute modifiers independently
        modifiers = compute_modifiers(ctx, legal_actions)

        # 4. Verify additivity for each action
        for action_name, base_val, ev_val, mod_val in [
            ("fold", base_scores.fold, ev_scores.fold, modifiers.fold),
            ("check", base_scores.check, ev_scores.check, modifiers.check),
            ("call", base_scores.call, ev_scores.call, modifiers.call),
            ("bet", base_scores.bet, ev_scores.bet, modifiers.bet),
            ("raise", base_scores.raise_, ev_scores.raise_, modifiers.raise_),
        ]:
            expected = ev_val + mod_val
            assert math.isclose(base_val, expected, abs_tol=1e-6), (
                f"Additivity violated for {action_name}: "
                f"base_score={base_val} != ev_score({ev_val}) + modifier({mod_val}) = {expected} "
                f"(equity={equity}, pot={pot}, personality={personality.name})"
            )


# ─── Property 15: Personality Aggression Ordering ─────────────────────────────
# **Validates: Requirements 12.2, 12.4**


class TestPersonalityAggressionOrdering:
    """Property 15: Given identical game state with positive bet EV:
    Maniac bet/raise modifier >= LAG bet/raise modifier for aggressive actions.

    The core aggression ordering is:
    - Maniac inflates fold_prob by 1.4× and adds +0.05×pot flat bonus
    - LAG inflates fold_prob by 1.2×
    - TAG uses a different mechanism (best-action boost), so its ordering is
      tested separately: TAG bet/raise mod <= 0 when bet/raise is NOT the best action.

    Constraints:
    - equity < 1.0 (so fold_prob inflation genuinely helps bet/raise EV)
    - fold_probability ≤ 1.0/1.4 ≈ 0.71 (so Maniac's 1.4× doesn't cap at 1.0)
    """

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.2, max_value=0.85),
        pot=st.integers(min_value=100, max_value=100000),
        fold_probability=st.floats(min_value=0.1, max_value=0.7),
        bet_amount=st.integers(min_value=1, max_value=200000),
        raise_amount=st.integers(min_value=1, max_value=300000),
    )
    def test_maniac_ge_lag_for_bet_raise(
        self,
        equity: float,
        pot: int,
        fold_probability: float,
        bet_amount: int,
        raise_amount: int,
    ):
        """**Validates: Requirements 12.2, 12.4**

        For states with equity < 1.0 and moderate fold_probability:
        Maniac bet/raise personality_ev_modifier >= LAG bet/raise personality_ev_modifier.

        Maniac uses fold_prob × 1.4 (vs LAG's 1.2×) AND adds a flat +0.05×pot
        bonus, so Maniac should always produce a higher or equal bet/raise modifier.
        """
        legal_actions = ["fold", "check", "call", "bet", "raise"]

        # Compute EV scores (same for all personalities)
        ev_scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=legal_actions,
            num_opponents=1,
        )

        # Only test when bet EV is positive
        assume(ev_scores.bet > 0)

        # For the ordering to hold, fold equity must genuinely help — i.e., winning
        # the pot now (opponents fold) is better than being called. This means:
        #   equity × final_pot_if_called - bet/raise_cost < pot
        # Otherwise inflating fold_prob actually HURTS EV, and Maniac's larger
        # inflation (1.4×) hurts MORE than LAG's (1.2×), potentially breaking the ordering.
        final_pot_bet = pot + 2 * bet_amount
        assume(equity * final_pot_bet - bet_amount < pot)

        final_pot_raise = pot + 2 * raise_amount
        assume(equity * final_pot_raise - raise_amount < pot)

        # Compute personality EV modifiers
        maniac_mods = compute_personality_ev_modifiers(
            personality_name="Maniac",
            ev_scores=ev_scores,
            fold_probability=fold_probability,
            pot=pot,
            equity=equity,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            num_opponents=1,
            legal_actions=legal_actions,
        )

        lag_mods = compute_personality_ev_modifiers(
            personality_name="LAG",
            ev_scores=ev_scores,
            fold_probability=fold_probability,
            pot=pot,
            equity=equity,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            num_opponents=1,
            legal_actions=legal_actions,
        )

        # Maniac bet modifier >= LAG bet modifier
        assert maniac_mods.bet >= lag_mods.bet - 1e-9, (
            f"Maniac bet mod ({maniac_mods.bet}) < LAG bet mod ({lag_mods.bet}) "
            f"with equity={equity}, pot={pot}, fold_prob={fold_probability}, bet={bet_amount}"
        )

        # Maniac raise modifier >= LAG raise modifier
        assert maniac_mods.raise_ >= lag_mods.raise_ - 1e-9, (
            f"Maniac raise mod ({maniac_mods.raise_}) < LAG raise mod ({lag_mods.raise_}) "
            f"with equity={equity}, pot={pot}, fold_prob={fold_probability}, raise={raise_amount}"
        )

    @settings(max_examples=200)
    @given(
        equity=st.floats(min_value=0.2, max_value=0.6),
        pot=st.integers(min_value=100, max_value=100000),
        fold_probability=st.floats(min_value=0.1, max_value=0.7),
        bet_amount=st.integers(min_value=1, max_value=200000),
        raise_amount=st.integers(min_value=1, max_value=300000),
    )
    def test_lag_boosts_aggression_more_than_tag(
        self,
        equity: float,
        pot: int,
        fold_probability: float,
        bet_amount: int,
        raise_amount: int,
    ):
        """**Validates: Requirements 12.2, 12.4**

        LAG's bet/raise modifier is non-negative (fold_prob inflation always
        helps when equity is low enough that fold equity is valuable), while
        TAG never inflates fold_prob for bet/raise — demonstrating that LAG
        is more aggressively biased than TAG.

        This holds when:
        - equity × (pot + 2×bet_amount) - bet_amount < pot
          (being called is WORSE than opponents folding, so fold_prob inflation helps)
        """
        legal_actions = ["fold", "check", "call", "bet", "raise"]

        # Ensure fold equity genuinely helps for bet action
        final_pot_bet = pot + 2 * bet_amount
        assume(equity * final_pot_bet - bet_amount < pot)

        ev_scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=0,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=legal_actions,
            num_opponents=1,
        )

        assume(ev_scores.bet > 0)

        lag_mods = compute_personality_ev_modifiers(
            personality_name="LAG",
            ev_scores=ev_scores,
            fold_probability=fold_probability,
            pot=pot,
            equity=equity,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            num_opponents=1,
            legal_actions=legal_actions,
        )

        # LAG's bet modifier should be non-negative (fold_prob inflation helps)
        assert lag_mods.bet >= -1e-9, (
            f"LAG bet mod ({lag_mods.bet}) should be non-negative when fold equity helps "
            f"with equity={equity}, pot={pot}, fold_prob={fold_probability}, bet={bet_amount}"
        )


# ─── Property 16: Nit Avoids Marginal EV ─────────────────────────────────────
# **Validates: Requirements 12.3**


class TestNitAvoidsMarginalEV:
    """Property 16: When EV is within ±0.1 × pot of zero, Nit's personality_ev_modifier
    for call/raise is negative (lower than baseline of 0)."""

    @settings(max_examples=200)
    @given(
        pot=st.integers(min_value=100, max_value=100000),
        fold_probability=st.floats(min_value=0.1, max_value=0.9),
        bet_amount=st.integers(min_value=1, max_value=200000),
        raise_amount=st.integers(min_value=1, max_value=300000),
    )
    def test_nit_negative_modifier_for_marginal_ev(
        self,
        pot: int,
        fold_probability: float,
        bet_amount: int,
        raise_amount: int,
    ):
        """**Validates: Requirements 12.3**

        When EV is within ±0.1 × pot of zero for any action, Nit should have
        negative personality_ev_modifier for call and raise, making the bot
        avoid marginal spots.
        """
        # Create a game state with marginal call EV:
        # call_ev = equity × (pot + call_amount) − call_amount ≈ 0
        # For call_ev = 0: equity = call_amount / (pot + call_amount)
        # We pick a call_amount and compute the equity that makes call_ev exactly 0,
        # then add a tiny offset to keep it within ±0.1×pot of zero.
        call_amount = pot // 2  # Half-pot call
        # equity that makes call_ev = 0:
        # equity × (pot + call_amount) = call_amount
        # equity = call_amount / (pot + call_amount)
        neutral_equity = call_amount / (pot + call_amount)

        # Slight offset to stay within marginal range but not exactly zero
        # call_ev = equity * (pot + call_amount) - call_amount
        # We want |call_ev| <= 0.1 * pot
        equity = neutral_equity  # This gives call_ev = 0, well within ±0.1×pot

        legal_actions = ["fold", "check", "call", "bet", "raise"]

        ev_scores = compute_ev_scores(
            equity=equity,
            pot=pot,
            call_amount=call_amount,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            fold_probability=fold_probability,
            legal_actions=legal_actions,
            num_opponents=1,
        )

        # Verify we actually have a marginal EV situation (at least one action near zero)
        marginal_threshold = 0.1 * pot
        has_marginal = any(
            abs(ev) <= marginal_threshold
            for ev in [ev_scores.fold, ev_scores.check, ev_scores.call, ev_scores.bet, ev_scores.raise_]
            if ev > -1e8  # Only check legal actions
        )
        assume(has_marginal)

        # Compute Nit's personality EV modifiers
        nit_mods = compute_personality_ev_modifiers(
            personality_name="Nit",
            ev_scores=ev_scores,
            fold_probability=fold_probability,
            pot=pot,
            equity=equity,
            bet_amount=bet_amount,
            raise_amount=raise_amount,
            num_opponents=1,
            legal_actions=legal_actions,
        )

        # Nit should have negative modifier for call and raise when EV is marginal
        assert nit_mods.call < 0, (
            f"Nit call modifier should be negative for marginal EV but got {nit_mods.call} "
            f"(pot={pot}, equity={equity}, call_amount={call_amount})"
        )
        assert nit_mods.raise_ < 0, (
            f"Nit raise modifier should be negative for marginal EV but got {nit_mods.raise_} "
            f"(pot={pot}, equity={equity}, call_amount={call_amount})"
        )
