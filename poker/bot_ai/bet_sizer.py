"""Street-Aware Bet Sizing for the Advanced Bot AI.

Provides context-dependent bet sizing that varies by street, board texture,
range advantage, polarization, and bot personality. Includes noise injection
for exploitability reduction.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from poker.bot_ai.models import BoardTexture, RangeAdvantage
from poker.bot_ai.personality_engine import PokerPersonality


@dataclass
class SizingContext:
    """All context needed for computing a bet size."""

    street: str  # "preflop", "flop", "turn", "river"
    board_texture: BoardTexture
    range_advantage: RangeAdvantage
    pot: int
    is_value_bet: bool
    is_polarized: bool  # River with nuts-or-air range
    personality: PokerPersonality


def compute_bet_size(ctx: SizingContext, min_raise: int, max_raise: int) -> int:
    """Compute a bet size based on street, board texture, range advantage, and polarization.

    Priority order:
      1. Nut advantage → overbet (110%-130% pot)
      2. Polarized river → 75%-150% pot
      3. Flop/turn dry board → 25%-40% pot
      4. Flop/turn wet board → 55%-75% pot
      5. Default → ~50% pot

    The personality's aggression parameter (0.0-1.0) interpolates within each range:
    higher aggression → larger sizing within the allowed band.

    The result is clamped to [min_raise, max_raise].

    Req 8.1: Dry board cbet → 25%-40% pot
    Req 8.2: Wet board cbet → 55%-75% pot
    Req 8.3: Polarized river → 75%-150% pot
    Req 8.4: Nut advantage → >100% pot (overbet)
    """
    aggression = ctx.personality.aggression

    # 1. Nut advantage → overbet (110%-130% pot)
    if ctx.range_advantage.nut_advantage:
        low, high = 1.10, 1.30
        pct = low + aggression * (high - low)

    # 2. Polarized river → 75%-150% pot
    elif ctx.is_polarized and ctx.street == "river":
        low, high = 0.75, 1.50
        pct = low + aggression * (high - low)

    # 3. Flop/turn dry board cbet → 25%-40% pot
    elif ctx.street in ("flop", "turn") and ctx.board_texture.is_dry:
        low, high = 0.25, 0.40
        pct = low + aggression * (high - low)

    # 4. Flop/turn wet board cbet → 55%-75% pot
    elif ctx.street in ("flop", "turn") and ctx.board_texture.is_wet:
        low, high = 0.55, 0.75
        pct = low + aggression * (high - low)

    # 5. Default → ~50% pot
    else:
        pct = 0.50

    amount = int(pct * ctx.pot)

    # Clamp to [min_raise, max_raise]
    amount = max(min_raise, min(amount, max_raise))

    return amount


def compute_bet_size_with_equity_cap(
    ctx: SizingContext, min_raise: int, max_raise: int, equity: float
) -> int:
    """Compute bet size with equity-based pot cap.

    Delegates to compute_bet_size for the base calculation.
    When equity < 0.70, the result is capped at ctx.pot (the current pot size).
    If ctx.pot < min_raise, the cap is clamped up to min_raise.

    The final result is always within [min_raise, max_raise].

    Req 2.2: Cap raise amount at pot size when equity < 70%.
    """
    base = compute_bet_size(ctx, min_raise, max_raise)

    if equity < 0.70:
        # Cap at pot size, but never below min_raise
        cap = max(ctx.pot, min_raise)
        base = min(base, cap)

    # Ensure final clamp to [min_raise, max_raise]
    return max(min_raise, min(base, max_raise))


def add_sizing_noise(base_size: int, noise_pct: float = 0.10) -> int:
    """Add random noise within ±noise_pct of the base size.

    Returns an integer value guaranteed to be within [base_size * (1 - noise_pct),
    base_size * (1 + noise_pct)].

    Req 8.5: Produces value within ±10% of base size.
    """
    lower = base_size * (1.0 - noise_pct)
    upper = base_size * (1.0 + noise_pct)
    noisy = random.uniform(lower, upper)
    return int(round(noisy))
