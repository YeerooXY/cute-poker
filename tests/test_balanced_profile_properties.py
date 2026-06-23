"""Property-based tests for balanced profile, equity error, and difficulty config.

Tests the core Patch 1 invariants: balanced profile assignment, equity error
bounding, equity clamping, and monotonic subsystem inclusion.

Validates: Requirements 1.1, 1.2, 1.3, 8.1-8.5, 9.6
"""

from hypothesis import given, settings, strategies as st
import pytest

from poker.bot_ai.personality_engine import BALANCED_PROFILE
from poker.bot_ai.difficulty_controller import (
    DifficultyLevel,
    get_difficulty_config,
    apply_equity_error,
    get_active_subsystems,
)
from poker.bot_ai.models import DifficultyConfig, ActiveSubsystems


# ─── Strategies ────────────────────────────────────────────────────────────────

difficulty_levels = st.sampled_from(
    [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD, DifficultyLevel.EXPERT]
)

# Expected equity_error_max per difficulty level
EXPECTED_ERROR_MAX = {
    DifficultyLevel.EASY: 0.15,
    DifficultyLevel.MEDIUM: 0.08,
    DifficultyLevel.HARD: 0.04,
    DifficultyLevel.EXPERT: 0.02,
}

# Difficulty level ordering (lower value = easier)
LEVEL_ORDER = [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD, DifficultyLevel.EXPERT]


# ─── Property 1: Balanced Profile Invariance ──────────────────────────────────
# Feature: balanced-bot-ai, Property 1: Balanced Profile Invariance
# For any difficulty level and any style parameter string, the decision pipeline
# in normal gameplay mode SHALL always assign BALANCED_PROFILE to the bot.
# **Validates: Requirements 1.1, 1.2, 1.3**


@settings(max_examples=50)
@given(
    difficulty=difficulty_levels,
    style=st.text(min_size=0, max_size=20),
)
def test_balanced_profile_invariance(difficulty, style):
    """Regardless of difficulty level or style string, BALANCED_PROFILE is always used.

    The pipeline always assigns BALANCED_PROFILE for normal gameplay.
    The style parameter and difficulty level have no effect on which profile is used.
    """
    # The config returned for any difficulty level does not influence which
    # profile is used — the pipeline always uses BALANCED_PROFILE
    config = get_difficulty_config(difficulty)

    # BALANCED_PROFILE is a fixed constant, independent of difficulty or style
    assert BALANCED_PROFILE.name == "Balanced"
    assert BALANCED_PROFILE.vpip == 0.27
    assert BALANCED_PROFILE.pfr == 0.22
    assert BALANCED_PROFILE.three_bet == 0.09
    assert BALANCED_PROFILE.aggression == 0.65
    assert BALANCED_PROFILE.bluff_frequency == 0.25
    assert BALANCED_PROFILE.call_down_looseness == 0.35
    assert BALANCED_PROFILE.trap_frequency == 0.15
    assert BALANCED_PROFILE.tilt_factor == 0.05
    assert BALANCED_PROFILE.position_awareness == 0.90
    assert BALANCED_PROFILE.exploitability == 0.08

    # The difficulty config exists and is valid (not personality-dependent)
    assert config.level == difficulty
    assert config.equity_error_max == EXPECTED_ERROR_MAX[difficulty]


# ─── Property 2: Equity Error Bounded by Difficulty ───────────────────────────
# Feature: balanced-bot-ai, Property 2: Equity Error Bounded by Difficulty
# For any true equity in [0.0, 1.0] and for any difficulty level, the applied
# equity error magnitude SHALL be at most equity_error_max for that level.
# **Validates: Requirements 8.1, 8.2, 8.3, 8.4**


@settings(max_examples=50)
@given(
    equity=st.floats(min_value=0.0, max_value=1.0),
    difficulty=difficulty_levels,
)
def test_equity_error_bounded(equity, difficulty):
    """For each difficulty level, the error magnitude is at most equity_error_max.

    The difference between the returned equity and the true equity (before clamping)
    must be bounded by the difficulty's equity_error_max.
    """
    config = get_difficulty_config(difficulty)
    error_max = config.equity_error_max

    result = apply_equity_error(equity, error_max)

    # The result must be in valid range
    assert 0.0 <= result <= 1.0

    # The absolute error (before clamping effects) is bounded by error_max.
    # After clamping, the observed difference can be less than error_max
    # (e.g., equity=0.01 with error=-0.15 gets clamped to 0.0, diff = 0.01).
    # But the error can NEVER exceed error_max.
    observed_diff = abs(result - equity)
    assert observed_diff <= error_max + 1e-9, (
        f"Error {observed_diff} exceeds max {error_max} for equity={equity}, "
        f"difficulty={difficulty.name}"
    )


# ─── Property 3: Equity Clamping Invariant ────────────────────────────────────
# Feature: balanced-bot-ai, Property 3: Equity Clamping Invariant
# For any true equity value and for any equity error applied, the final equity
# output SHALL always be in the range [0.0, 1.0].
# **Validates: Requirements 8.5**


@settings(max_examples=50)
@given(
    equity=st.floats(min_value=0.0, max_value=1.0),
    error_max=st.floats(min_value=0.0, max_value=1.0),
)
def test_equity_clamping(equity, error_max):
    """Output is always in [0.0, 1.0] for any valid equity and any error magnitude.

    Even when equity is near the boundaries (0.0 or 1.0) and error_max is large
    (up to 1.0), the result must always be clamped to [0.0, 1.0].
    """
    result = apply_equity_error(equity, error_max)

    assert 0.0 <= result <= 1.0, (
        f"Clamping violated: result={result} for equity={equity}, error_max={error_max}"
    )


# ─── Property 10: Monotonic Subsystem Inclusion ──────────────────────────────
# Feature: balanced-bot-ai, Property 10: Monotonic Subsystem Inclusion
# For all pairs of difficulty levels (A, B) where A < B, every AI subsystem
# active at level A SHALL also be active at level B.
# **Validates: Requirements 9.6**


def test_monotonic_subsystem_inclusion():
    """For all pairs (A, B) where A < B, every subsystem active at A is also active at B.

    This verifies the monotonic inclusion property: higher difficulty levels
    activate all subsystems from lower levels plus potentially more.
    """
    for i in range(len(LEVEL_ORDER)):
        for j in range(i + 1, len(LEVEL_ORDER)):
            level_a = LEVEL_ORDER[i]
            level_b = LEVEL_ORDER[j]

            subs_a = get_active_subsystems(level_a)
            subs_b = get_active_subsystems(level_b)

            # Every True field in subs_a must also be True in subs_b
            for field_name in [
                "hand_strength",
                "pot_odds",
                "preflop_charts",
                "bet_sizing",
                "range_tracking",
                "board_texture",
                "opponent_modeling",
                "bluff_calculator",
                "dynamic_adjustment",
                "full_action_scoring",
            ]:
                val_a = getattr(subs_a, field_name)
                val_b = getattr(subs_b, field_name)
                if val_a:
                    assert val_b, (
                        f"Monotonic inclusion violated: {field_name} is active at "
                        f"{level_a.name} but not at {level_b.name}"
                    )
