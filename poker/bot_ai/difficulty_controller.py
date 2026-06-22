"""Difficulty Controller for the Advanced Bot AI.

Gates AI subsystem activation based on difficulty level and configures
personality profiles appropriate to each level. Lower difficulties use
fewer subsystems and higher-exploitability profiles, while higher difficulties
unlock the full AI pipeline with near-GTO play.

Req 10.1: Four difficulty levels: Easy, Medium, Hard, Expert
Req 10.2: Easy = hand strength + pot odds only
Req 10.3: Medium = Easy + preflop charts + bet sizing
Req 10.4: Hard = Medium + range tracking, board texture, opponent modeling, bluff calculator
Req 10.5: Expert = all subsystems active
Req 10.6: Lower difficulty → higher exploitability in personality profiles
"""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

from poker.bot_ai.models import ActiveSubsystems
from poker.bot_ai.personality_engine import (
    PREDEFINED_PROFILES,
    PokerPersonality,
    get_personality,
)


class DifficultyLevel(Enum):
    """Four difficulty levels for bot AI."""

    EASY = 1
    MEDIUM = 2
    HARD = 3
    EXPERT = 4


# ─── Personality pools per difficulty level ────────────────────────────────────

_DIFFICULTY_PERSONALITY_POOLS: dict[DifficultyLevel, list[str]] = {
    DifficultyLevel.EASY: ["Calling_Station", "Maniac"],
    DifficultyLevel.MEDIUM: ["TAG", "LAG", "Calling_Station", "Maniac"],
    DifficultyLevel.HARD: ["TAG", "LAG", "Nit", "Trapper"],
    DifficultyLevel.EXPERT: ["GTO_ish", "Exploitative_Shark"],
}

# Exploitability ranges per difficulty level (min, max)
_EXPLOITABILITY_RANGES: dict[DifficultyLevel, tuple[float, float]] = {
    DifficultyLevel.EASY: (0.40, 0.45),
    DifficultyLevel.MEDIUM: (0.20, 0.35),
    DifficultyLevel.HARD: (0.10, 0.20),
    DifficultyLevel.EXPERT: (0.03, 0.05),
}


# ─── Public API ────────────────────────────────────────────────────────────────


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


def get_personality_for_difficulty(
    level: DifficultyLevel, style: str
) -> PokerPersonality:
    """Return a personality profile appropriate for the given difficulty level.

    Uses `get_personality(style)` as the base, then adjusts exploitability
    based on the difficulty level.

    Key design principle: the personality (playing style) is determined by the
    user-requested style parameter. Difficulty only affects:
    1. Exploitability (noise/randomness in decisions)
    2. Which AI subsystems are active (handled by get_active_subsystems)

    This ensures that "expert tight_aggressive" plays a disciplined TAG style
    with all subsystems active, rather than switching to a different profile.

    Exploitability ranges:
    - Easy: 0.40-0.45 (very exploitable/random)
    - Medium: 0.20-0.35 (moderately exploitable)
    - Hard: 0.10-0.20 (low exploitability)
    - Expert: 0.05-0.10 (near-GTO precision)
    """
    exploit_min, exploit_max = _EXPLOITABILITY_RANGES[level]

    # Get the base personality for the requested style
    base = get_personality(style)

    # Override exploitability to fit the difficulty range
    clamped_exploitability = _clamp(base.exploitability, exploit_min, exploit_max)

    return replace(base, exploitability=clamped_exploitability)


# ─── Private helpers ───────────────────────────────────────────────────────────


def _find_closest_profile(target: PokerPersonality, pool: list[str]) -> PokerPersonality:
    """Find the profile in the pool most similar to the target.

    Similarity is measured by Euclidean distance over the core behavioral
    parameters (excluding name and exploitability, since exploitability will
    be overridden anyway).
    """
    best_profile: PokerPersonality | None = None
    best_distance = float("inf")

    for profile_name in pool:
        candidate = PREDEFINED_PROFILES[profile_name]
        distance = _personality_distance(target, candidate)
        if distance < best_distance:
            best_distance = distance
            best_profile = candidate

    # Should always find at least one, but guard defensively
    assert best_profile is not None
    return best_profile


def _personality_distance(a: PokerPersonality, b: PokerPersonality) -> float:
    """Euclidean distance between two personalities over behavioral parameters."""
    return (
        (a.vpip - b.vpip) ** 2
        + (a.pfr - b.pfr) ** 2
        + (a.three_bet - b.three_bet) ** 2
        + (a.aggression - b.aggression) ** 2
        + (a.bluff_frequency - b.bluff_frequency) ** 2
        + (a.call_down_looseness - b.call_down_looseness) ** 2
        + (a.trap_frequency - b.trap_frequency) ** 2
        + (a.tilt_factor - b.tilt_factor) ** 2
        + (a.position_awareness - b.position_awareness) ** 2
    ) ** 0.5


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to [minimum, maximum]."""
    return max(minimum, min(maximum, value))
