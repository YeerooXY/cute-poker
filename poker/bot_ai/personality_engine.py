"""Unified Personality Engine for the Advanced Bot AI.

Defines bot personalities as parameter vectors and provides action multipliers
that influence the action scoring system. Each personality profile encodes a
distinct playing style through 10 tunable parameters.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PokerPersonality:
    """A complete bot personality defined by 10 behavioral parameters.

    All parameters are floats in the range [0.0, 1.0].
    """

    name: str
    vpip: float  # Willingness to enter pots
    pfr: float  # Preflop raise frequency
    three_bet: float  # 3-bet frequency
    aggression: float  # Postflop aggression
    bluff_frequency: float  # Bluff propensity
    call_down_looseness: float  # Willingness to call down
    trap_frequency: float  # Slow-play frequency
    tilt_factor: float  # Emotional reactivity
    position_awareness: float  # How much position matters
    exploitability: float  # Randomness/noise in decisions


# ─── Predefined personality profiles ───────────────────────────────────────────

PREDEFINED_PROFILES: dict[str, PokerPersonality] = {
    "TAG": PokerPersonality(
        name="TAG",
        vpip=0.22,
        pfr=0.18,
        three_bet=0.08,
        aggression=0.70,
        bluff_frequency=0.20,
        call_down_looseness=0.30,
        trap_frequency=0.15,
        tilt_factor=0.10,
        position_awareness=0.85,
        exploitability=0.15,
    ),
    "LAG": PokerPersonality(
        name="LAG",
        vpip=0.35,
        pfr=0.28,
        three_bet=0.12,
        aggression=0.80,
        bluff_frequency=0.35,
        call_down_looseness=0.40,
        trap_frequency=0.10,
        tilt_factor=0.20,
        position_awareness=0.75,
        exploitability=0.20,
    ),
    "Nit": PokerPersonality(
        name="Nit",
        vpip=0.12,
        pfr=0.10,
        three_bet=0.04,
        aggression=0.55,
        bluff_frequency=0.05,
        call_down_looseness=0.15,
        trap_frequency=0.25,
        tilt_factor=0.05,
        position_awareness=0.90,
        exploitability=0.10,
    ),
    "Calling_Station": PokerPersonality(
        name="Calling_Station",
        vpip=0.55,
        pfr=0.08,
        three_bet=0.03,
        aggression=0.20,
        bluff_frequency=0.05,
        call_down_looseness=0.85,
        trap_frequency=0.05,
        tilt_factor=0.15,
        position_awareness=0.30,
        exploitability=0.40,
    ),
    "Maniac": PokerPersonality(
        name="Maniac",
        vpip=0.60,
        pfr=0.45,
        three_bet=0.20,
        aggression=0.95,
        bluff_frequency=0.50,
        call_down_looseness=0.60,
        trap_frequency=0.05,
        tilt_factor=0.40,
        position_awareness=0.20,
        exploitability=0.45,
    ),
    "Trapper": PokerPersonality(
        name="Trapper",
        vpip=0.25,
        pfr=0.15,
        three_bet=0.06,
        aggression=0.40,
        bluff_frequency=0.10,
        call_down_looseness=0.50,
        trap_frequency=0.55,
        tilt_factor=0.10,
        position_awareness=0.70,
        exploitability=0.20,
    ),
    "GTO_ish": PokerPersonality(
        name="GTO_ish",
        vpip=0.27,
        pfr=0.22,
        three_bet=0.09,
        aggression=0.65,
        bluff_frequency=0.25,
        call_down_looseness=0.35,
        trap_frequency=0.15,
        tilt_factor=0.05,
        position_awareness=0.90,
        exploitability=0.08,
    ),
    "Exploitative_Shark": PokerPersonality(
        name="Exploitative_Shark",
        vpip=0.28,
        pfr=0.23,
        three_bet=0.10,
        aggression=0.72,
        bluff_frequency=0.28,
        call_down_looseness=0.38,
        trap_frequency=0.18,
        tilt_factor=0.08,
        position_awareness=0.88,
        exploitability=0.12,
    ),
}


# ─── Balanced profile for normal gameplay (Patch 1) ────────────────────────────

BALANCED_PROFILE = PokerPersonality(
    name="Balanced",
    vpip=0.27,
    pfr=0.22,
    three_bet=0.09,
    aggression=0.65,
    bluff_frequency=0.25,
    call_down_looseness=0.35,
    trap_frequency=0.15,
    tilt_factor=0.05,
    position_awareness=0.90,
    exploitability=0.08,
)


# ─── Backward compatibility mapping ───────────────────────────────────────────

STYLE_MAPPING: dict[str, str] = {
    "tight_aggressive": "TAG",
    "loose_aggressive": "LAG",
    "calling_station": "Calling_Station",
    "maniac": "Maniac",
}


# ─── Public API ────────────────────────────────────────────────────────────────


def get_personality(style: str) -> PokerPersonality:
    """Return the PokerPersonality for a given style string.

    Accepts both new profile names (e.g., "TAG", "GTO_ish") and legacy style
    strings (e.g., "tight_aggressive"). Falls back to TAG if style is unknown.
    """
    # Check if it's a legacy style that needs mapping
    profile_name = STYLE_MAPPING.get(style, style)

    # Look up in predefined profiles, defaulting to TAG
    return PREDEFINED_PROFILES.get(profile_name, PREDEFINED_PROFILES["TAG"])


def get_action_multipliers(personality: PokerPersonality) -> dict[str, float]:
    """Derive action multipliers from a personality's parameters.

    Returns a dict mapping action names to multiplier floats:
      - "raise": boosted by aggression and bluff_frequency
      - "bet": boosted by aggression and bluff_frequency
      - "call": boosted by call_down_looseness
      - "check": boosted by trap_frequency (for slow-playing)
      - "fold": inversely related to call_down_looseness

    Multipliers are centered around 1.0 (neutral). Values > 1.0 boost the
    action score; values < 1.0 suppress it.

    Req 6.4: personality multipliers SHALL increase raise/bet score proportional
    to aggression, increase call score proportional to call_down_looseness.
    """
    # Raise/bet: boosted proportionally by aggression and bluff_frequency.
    # Base of 1.0 + contribution from aggression (weighted 0.7) and bluff (weighted 0.3)
    aggression_boost = personality.aggression * 0.7 + personality.bluff_frequency * 0.3
    raise_multiplier = 1.0 + aggression_boost
    bet_multiplier = 1.0 + aggression_boost

    # Call: boosted proportionally by call_down_looseness
    call_multiplier = 1.0 + personality.call_down_looseness

    # Check: boosted by trap_frequency (slow-playing strong hands)
    check_multiplier = 1.0 + personality.trap_frequency

    # Fold: inversely related to call_down_looseness — looser callers fold less
    fold_multiplier = 1.0 + (1.0 - personality.call_down_looseness) * 0.5

    return {
        "fold": fold_multiplier,
        "check": check_multiplier,
        "call": call_multiplier,
        "bet": bet_multiplier,
        "raise": raise_multiplier,
    }
