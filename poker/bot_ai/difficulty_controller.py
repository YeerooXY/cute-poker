"""Difficulty Controller for the Advanced Bot AI.

Gates AI subsystem activation based on difficulty level and configures
equity error bounds appropriate to each level. Lower difficulties use
fewer subsystems and larger equity errors, while higher difficulties
unlock the full AI pipeline with near-perfect equity estimation.

Req 9.1: DifficultyConfig with three fields: level, equity_error_max, active_subsystems
Req 9.2: Easy equity_error_max = 0.15
Req 9.3: Medium equity_error_max = 0.08
Req 9.4: Hard equity_error_max = 0.04
Req 9.5: Expert equity_error_max = 0.02
Req 9.6: Monotonic subsystem inclusion across difficulty levels
"""

from __future__ import annotations

import math
import random

from poker.bot_ai.models import ActiveSubsystems, DifficultyConfig, DifficultyLevel


# Exploitability ranges per difficulty level (min, max)
_EXPLOITABILITY_RANGES: dict[DifficultyLevel, tuple[float, float]] = {
    DifficultyLevel.EASY: (0.40, 0.45),
    DifficultyLevel.MEDIUM: (0.20, 0.35),
    DifficultyLevel.HARD: (0.10, 0.20),
    DifficultyLevel.EXPERT: (0.03, 0.05),
}


# ─── Public API ────────────────────────────────────────────────────────────────



def apply_equity_error(true_equity: float, equity_error_max: float) -> float:
    """Apply uniform random error to equity, clamped to [0.0, 1.0].

    If equity_error_max is negative or NaN, treat as 0.0 (no error applied).

    Req 8.1-8.5: Equity error bounded by difficulty, clamped to valid range.
    """
    if math.isnan(equity_error_max) or equity_error_max <= 0.0:
        return true_equity
    error = random.uniform(-equity_error_max, equity_error_max)
    return max(0.0, min(1.0, true_equity + error))


def get_active_subsystems(level: DifficultyLevel) -> ActiveSubsystems:
    """Return which AI subsystems are active at a given difficulty level.

    Key property: monotonic subsystem inclusion — each higher level enables ALL
    subsystems from the level below plus additional ones.

    - Easy: hand_strength + pot_odds (defaults, always active)
    - Medium: + preflop_charts + bet_sizing
    - Hard: + range_tracking + board_texture + opponent_modeling + bluff_calculator
    - Expert: + dynamic_adjustment + full_action_scoring (all True)
    """
    if level == DifficultyLevel.EASY:
        return ActiveSubsystems(
            hand_strength=True,
            pot_odds=True,
            preflop_charts=False,
            bet_sizing=False,
            range_tracking=False,
            board_texture=False,
            opponent_modeling=False,
            bluff_calculator=False,
            dynamic_adjustment=False,
            full_action_scoring=False,
        )

    if level == DifficultyLevel.MEDIUM:
        return ActiveSubsystems(
            hand_strength=True,
            pot_odds=True,
            preflop_charts=True,
            bet_sizing=True,
            range_tracking=False,
            board_texture=False,
            opponent_modeling=False,
            bluff_calculator=False,
            dynamic_adjustment=False,
            full_action_scoring=False,
        )

    if level == DifficultyLevel.HARD:
        return ActiveSubsystems(
            hand_strength=True,
            pot_odds=True,
            preflop_charts=True,
            bet_sizing=True,
            range_tracking=True,
            board_texture=True,
            opponent_modeling=True,
            bluff_calculator=True,
            dynamic_adjustment=False,
            full_action_scoring=False,
        )

    # EXPERT — all subsystems active
    return ActiveSubsystems(
        hand_strength=True,
        pot_odds=True,
        preflop_charts=True,
        bet_sizing=True,
        range_tracking=True,
        board_texture=True,
        opponent_modeling=True,
        bluff_calculator=True,
        dynamic_adjustment=True,
        full_action_scoring=True,
    )


def get_difficulty_config(level: DifficultyLevel) -> DifficultyConfig:
    """Return the preset DifficultyConfig for a given difficulty level.

    Each level defines:
    - equity_error_max: maximum magnitude of equity estimation error
    - active_subsystems: which AI subsystems are enabled

    The configs enforce monotonic subsystem inclusion — each higher level
    includes all subsystems from the level below plus additional ones.
    """
    return _DIFFICULTY_CONFIGS[level]


# ─── Preset difficulty configurations ─────────────────────────────────────────

_DIFFICULTY_CONFIGS: dict[DifficultyLevel, DifficultyConfig] = {
    DifficultyLevel.EASY: DifficultyConfig(
        level=DifficultyLevel.EASY,
        equity_error_max=0.15,
        active_subsystems=get_active_subsystems(DifficultyLevel.EASY),
    ),
    DifficultyLevel.MEDIUM: DifficultyConfig(
        level=DifficultyLevel.MEDIUM,
        equity_error_max=0.08,
        active_subsystems=get_active_subsystems(DifficultyLevel.MEDIUM),
    ),
    DifficultyLevel.HARD: DifficultyConfig(
        level=DifficultyLevel.HARD,
        equity_error_max=0.04,
        active_subsystems=get_active_subsystems(DifficultyLevel.HARD),
    ),
    DifficultyLevel.EXPERT: DifficultyConfig(
        level=DifficultyLevel.EXPERT,
        equity_error_max=0.02,
        active_subsystems=get_active_subsystems(DifficultyLevel.EXPERT),
    ),
}


# ─── Equity error ──────────────────────────────────────────────────────────────


def apply_equity_error(true_equity: float, equity_error_max: float) -> float:
    """Apply uniform random error to equity, clamped to [0.0, 1.0].

    Implementation:
        error = random.uniform(-equity_error_max, equity_error_max)
        return clamp(true_equity + error, 0.0, 1.0)

    Edge cases:
        - If equity_error_max is negative or NaN, treat as 0.0 (no error applied).

    Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
    """
    if math.isnan(equity_error_max) or equity_error_max <= 0.0:
        return true_equity
    error = random.uniform(-equity_error_max, equity_error_max)
    return max(0.0, min(1.0, true_equity + error))


# ─── Private helpers ───────────────────────────────────────────────────────────


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to [minimum, maximum]."""
    return max(minimum, min(maximum, value))
