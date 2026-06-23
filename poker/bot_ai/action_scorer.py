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
    ActionModifiers,
    ActionScores,
    ScoringContext,
)
from poker.bot_ai.personality_engine import PokerPersonality, get_action_multipliers


# Score assigned to illegal actions so they are never selected
_ILLEGAL_SCORE = -1e9


def compute_ev_scores(
    equity: float,
    pot: int,
    call_amount: int,
    bet_amount: int,
    raise_amount: int,
    fold_probability: float,
    legal_actions: list[str],
    num_opponents: int = 1,
) -> ActionScores:
    """Compute Expected Value scores for each legal action.

    Pure function implementing EV formulas:
      - fold:  EV = 0.0 (baseline — surrendering costs nothing more)
      - check: EV = 0.0 (no cost, no immediate gain)
      - call:  EV = equity × final_pot − call_amount
               where final_pot = pot + call_amount
      - bet:   EV = fold_prob × pot + (1 − fold_prob) × (equity × final_pot_if_called − bet_cost)
               where final_pot_if_called = pot + bet_amount + bet_amount (hero bet + opponent call)
      - raise: same semi-bluff formula as bet with raise amounts substituted

    For multiway pots (num_opponents > 1):
      - combined_fold_prob = fold_probability ^ num_opponents
      - final_pot_if_called uses num_opponents × call amount for optimistic case

    Actions not in legal_actions receive _ILLEGAL_SCORE (-1e9).

    **Validates: Requirements 1.1, 2.1, 3.1, 4.1, 6.1**
    """
    scores = ActionScores(
        fold=_ILLEGAL_SCORE,
        check=_ILLEGAL_SCORE,
        call=_ILLEGAL_SCORE,
        bet=_ILLEGAL_SCORE,
        raise_=_ILLEGAL_SCORE,
    )

    # Clamp inputs to valid ranges for safety
    equity = max(0.0, min(1.0, equity))
    fold_probability = max(0.0, min(1.0, fold_probability))
    pot = max(0, pot)
    call_amount = max(0, call_amount)
    bet_amount = max(0, bet_amount)
    raise_amount = max(0, raise_amount)
    num_opponents = max(1, num_opponents)

    # Multiway pot approximation (Req 6.1):
    # Assumes independent fold decisions across opponents.
    # combined_fold_prob = fold_prob_per_opponent ^ num_opponents
    # This is an acceptable approximation — exact game-theoretic multiway EV is NOT required.
    combined_fold_prob = fold_probability ** num_opponents

    # ─── Fold ──────────────────────────────────────────────────────────────
    if "fold" in legal_actions:
        scores.fold = 0.0

    # ─── Check ─────────────────────────────────────────────────────────────
    if "check" in legal_actions:
        scores.check = 0.0

    # ─── Call ──────────────────────────────────────────────────────────────
    if "call" in legal_actions:
        # final_pot = current_pot + call_amount
        final_pot = pot + call_amount
        # call_ev = equity × final_pot − call_amount
        scores.call = equity * final_pot - call_amount

    # ─── Bet ───────────────────────────────────────────────────────────────
    if "bet" in legal_actions:
        if bet_amount > 0:
            # Multiway pot approximation (Req 6.3):
            # final_pot_if_called = current_pot + hero_bet + (num_opponents × call_amount_per_opponent)
            # Optimistic assumption: all opponents who don't fold will call the full bet.
            final_pot_if_called = pot + bet_amount + (num_opponents * bet_amount)
            bet_cost = bet_amount
            # Semi-bluff EV:
            # fold_prob × pot + (1 − fold_prob) × (equity × final_pot_if_called − bet_cost)
            scores.bet = (
                combined_fold_prob * pot
                + (1 - combined_fold_prob) * (equity * final_pot_if_called - bet_cost)
            )
        else:
            # bet_amount = 0 means bet is not meaningful; treat as 0 EV
            scores.bet = 0.0

    # ─── Raise ─────────────────────────────────────────────────────────────
    if "raise" in legal_actions:
        if raise_amount > 0:
            # Multiway pot approximation (Req 6.3):
            # final_pot_if_called = current_pot + hero_raise + (num_opponents × call_amount_per_opponent)
            # Opponent's call_of_raise ≈ raise_amount (simplified; they match the raise).
            final_pot_if_called = pot + raise_amount + (num_opponents * raise_amount)
            raise_cost = raise_amount
            # Semi-bluff EV (same structure as bet):
            # fold_prob × pot + (1 − fold_prob) × (equity × final_pot_if_called − raise_cost)
            scores.raise_ = (
                combined_fold_prob * pot
                + (1 - combined_fold_prob) * (equity * final_pot_if_called - raise_cost)
            )
        else:
            # raise_amount = 0 means raise is not meaningful; treat as 0 EV
            scores.raise_ = 0.0

    return scores


def compute_personality_ev_modifiers(
    personality_name: str,
    ev_scores: ActionScores,
    fold_probability: float,
    pot: int,
    equity: float,
    bet_amount: int,
    raise_amount: int,
    num_opponents: int,
    legal_actions: list[str],
) -> ActionModifiers:
    """Compute personality-specific EV modifiers for key personality archetypes.

    These modifiers are ADDED to the generic personality modifiers (from get_action_multipliers)
    and represent how each personality type biases EV-based decisions:

      - TAG: Increases weight of highest-EV action (+0.05×pot), decreases modifiers
              for marginal-EV actions (-0.03×pot)
      - LAG: Recomputes bet/raise EV with fold_prob × 1.2 (capped at 1.0),
              returns the DIFFERENCE as modifier
      - Nit: When any action's EV is within ±0.1×pot of zero, subtracts 0.08×pot
              from call and raise
      - Maniac: Recomputes bet/raise EV with fold_prob × 1.4 (capped at 1.0),
                plus adds flat +0.05×pot to bet and raise
      - Calling_Station: Adds +0.1×pot to call, subtracts 0.05×pot from fold

    All results are clamped to [-0.3×pot, +0.3×pot].

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
    """
    pot = max(1, pot)
    bound = 0.3 * pot

    mods = {"fold": 0.0, "check": 0.0, "call": 0.0, "bet": 0.0, "raise": 0.0}

    fold_probability = max(0.0, min(1.0, fold_probability))
    equity = max(0.0, min(1.0, equity))
    bet_amount = max(0, bet_amount)
    raise_amount = max(0, raise_amount)
    num_opponents = max(1, num_opponents)

    if personality_name == "TAG":
        # Identify highest EV among legal actions
        ev_map = {
            "fold": ev_scores.fold if "fold" in legal_actions else _ILLEGAL_SCORE,
            "check": ev_scores.check if "check" in legal_actions else _ILLEGAL_SCORE,
            "call": ev_scores.call if "call" in legal_actions else _ILLEGAL_SCORE,
            "bet": ev_scores.bet if "bet" in legal_actions else _ILLEGAL_SCORE,
            "raise": ev_scores.raise_ if "raise" in legal_actions else _ILLEGAL_SCORE,
        }
        legal_evs = {k: v for k, v in ev_map.items() if v > _ILLEGAL_SCORE}
        if legal_evs:
            best_action = max(legal_evs, key=legal_evs.get)
            # Boost the best EV action
            mods[best_action] += 0.05 * pot
            # Penalize marginal-EV actions (within ±0.1×pot of zero)
            for action, ev in legal_evs.items():
                if action != best_action and abs(ev) <= 0.1 * pot:
                    mods[action] -= 0.03 * pot

    elif personality_name == "LAG":
        # Recompute bet/raise EV with fold_prob × 1.2 (capped at 1.0)
        adjusted_fold_prob = min(1.0, fold_probability * 1.2)
        combined_adjusted = adjusted_fold_prob ** num_opponents

        if "bet" in legal_actions and bet_amount > 0:
            final_pot_if_called = pot + bet_amount + (num_opponents * bet_amount)
            new_bet_ev = (
                combined_adjusted * pot
                + (1 - combined_adjusted) * (equity * final_pot_if_called - bet_amount)
            )
            # Original bet EV
            combined_orig = (fold_probability ** num_opponents)
            orig_bet_ev = (
                combined_orig * pot
                + (1 - combined_orig) * (equity * final_pot_if_called - bet_amount)
            )
            mods["bet"] += new_bet_ev - orig_bet_ev

        if "raise" in legal_actions and raise_amount > 0:
            final_pot_if_called = pot + raise_amount + (num_opponents * raise_amount)
            new_raise_ev = (
                combined_adjusted * pot
                + (1 - combined_adjusted) * (equity * final_pot_if_called - raise_amount)
            )
            combined_orig = (fold_probability ** num_opponents)
            orig_raise_ev = (
                combined_orig * pot
                + (1 - combined_orig) * (equity * final_pot_if_called - raise_amount)
            )
            mods["raise"] += new_raise_ev - orig_raise_ev

    elif personality_name == "Nit":
        # When any action's EV is within ±0.1×pot of zero, subtract 0.08×pot from call and raise
        ev_map = {
            "fold": ev_scores.fold if "fold" in legal_actions else _ILLEGAL_SCORE,
            "check": ev_scores.check if "check" in legal_actions else _ILLEGAL_SCORE,
            "call": ev_scores.call if "call" in legal_actions else _ILLEGAL_SCORE,
            "bet": ev_scores.bet if "bet" in legal_actions else _ILLEGAL_SCORE,
            "raise": ev_scores.raise_ if "raise" in legal_actions else _ILLEGAL_SCORE,
        }
        legal_evs = {k: v for k, v in ev_map.items() if v > _ILLEGAL_SCORE}
        marginal_threshold = 0.1 * pot
        has_marginal = any(abs(ev) <= marginal_threshold for ev in legal_evs.values())
        if has_marginal:
            if "call" in legal_actions:
                mods["call"] -= 0.08 * pot
            if "raise" in legal_actions:
                mods["raise"] -= 0.08 * pot

    elif personality_name == "Maniac":
        # Recompute bet/raise EV with fold_prob × 1.4 (capped at 1.0) + flat bonus
        adjusted_fold_prob = min(1.0, fold_probability * 1.4)
        combined_adjusted = adjusted_fold_prob ** num_opponents

        if "bet" in legal_actions and bet_amount > 0:
            final_pot_if_called = pot + bet_amount + (num_opponents * bet_amount)
            new_bet_ev = (
                combined_adjusted * pot
                + (1 - combined_adjusted) * (equity * final_pot_if_called - bet_amount)
            )
            combined_orig = (fold_probability ** num_opponents)
            orig_bet_ev = (
                combined_orig * pot
                + (1 - combined_orig) * (equity * final_pot_if_called - bet_amount)
            )
            mods["bet"] += (new_bet_ev - orig_bet_ev) + 0.05 * pot

        if "raise" in legal_actions and raise_amount > 0:
            final_pot_if_called = pot + raise_amount + (num_opponents * raise_amount)
            new_raise_ev = (
                combined_adjusted * pot
                + (1 - combined_adjusted) * (equity * final_pot_if_called - raise_amount)
            )
            combined_orig = (fold_probability ** num_opponents)
            orig_raise_ev = (
                combined_orig * pot
                + (1 - combined_orig) * (equity * final_pot_if_called - raise_amount)
            )
            mods["raise"] += (new_raise_ev - orig_raise_ev) + 0.05 * pot

    elif personality_name == "Calling_Station":
        # Boost call regardless of EV sign, penalize fold
        if "call" in legal_actions:
            mods["call"] += 0.1 * pot
        if "fold" in legal_actions:
            mods["fold"] -= 0.05 * pot

    # Clamp all modifiers to [-0.3×pot, +0.3×pot]
    for action in mods:
        mods[action] = max(-bound, min(bound, mods[action]))

    # Zero out modifiers for illegal actions
    if "fold" not in legal_actions:
        mods["fold"] = 0.0
    if "check" not in legal_actions:
        mods["check"] = 0.0
    if "call" not in legal_actions:
        mods["call"] = 0.0
    if "bet" not in legal_actions:
        mods["bet"] = 0.0
    if "raise" not in legal_actions:
        mods["raise"] = 0.0

    return ActionModifiers(
        fold=mods["fold"],
        check=mods["check"],
        call=mods["call"],
        bet=mods["bet"],
        raise_=mods["raise"],
    )


def compute_modifiers(
    ctx: ScoringContext,
    legal_actions: list[str],
    use_personality: bool = False,
) -> ActionModifiers:
    """Compute additive modifiers for each action from exploit and board texture.

    When use_personality=True (test/debug mode), also includes personality-based
    modifiers (multiplier-based and EV-specific). In normal gameplay
    (use_personality=False), personality modifiers are excluded entirely.

    Each modifier type is bounded by pot-proportional limits:
      - personality_modifier ∈ [-0.3 × pot, +0.3 × pot]  (only when use_personality=True)
      - exploit_modifier ∈ [-0.2 × pot, +0.2 × pot]
      - board_texture_modifier ∈ [-0.15 × pot, +0.15 × pot]

    The returned ActionModifiers contains the sum of all active modifier types per action.

    **Validates: Requirements 1.4, 1.5, 5.2, 5.3, 5.4**
    """
    # Derive pot size from context for modifier bounding.
    # ScoringContext carries pot directly when available.
    if ctx.pot > 0:
        pot = ctx.pot
    elif ctx.pot_odds > 0 and ctx.call_amount > 0:
        # pot_odds = call_amount / (pot + call_amount) → pot = call_amount/pot_odds - call_amount
        pot = int(ctx.call_amount / ctx.pot_odds - ctx.call_amount)
    elif ctx.bet_amount > 0:
        pot = ctx.bet_amount * 2
    else:
        pot = 100  # Reasonable default

    pot = max(1, pot)  # Ensure pot is at least 1 to avoid zero bounds

    # Bounds
    personality_bound = 0.3 * pot
    exploit_bound = 0.2 * pot
    board_texture_bound = 0.15 * pot

    # ─── 1. Personality Modifier ───────────────────────────────────────────
    # Convert personality multipliers to additive offsets: (multiplier - 1.0) × pot × scaling_factor
    # Only included when use_personality=True (test/debug mode)
    personality_mods = {"fold": 0.0, "check": 0.0, "call": 0.0, "bet": 0.0, "raise": 0.0}
    if use_personality:
        multipliers = get_action_multipliers(ctx.personality)
        # Scaling factor to keep personality modifiers within reasonable range.
        # Multipliers range roughly from 0.7 to 2.0, so (mult - 1.0) ranges from -0.3 to 1.0.
        # We use a scaling factor of 0.3 to bring these into the desired bound range.
        personality_scaling = 0.3

        action_to_key = {"fold": "fold", "check": "check", "call": "call", "bet": "bet", "raise": "raise"}
        for action in ["fold", "check", "call", "bet", "raise"]:
            mult_key = action_to_key[action]
            mult = multipliers.get(mult_key, 1.0)
            raw_mod = (mult - 1.0) * pot * personality_scaling
            personality_mods[action] = max(-personality_bound, min(personality_bound, raw_mod))

    # ─── 2. Exploit Modifier ──────────────────────────────────────────────
    exploit = ctx.exploit_adjustments
    exploit_mods = {"fold": 0.0, "check": 0.0, "call": 0.0, "bet": 0.0, "raise": 0.0}

    if exploit.active:
        # three_bet_bluff_boost → boosts raise
        exploit_mods["raise"] += exploit.three_bet_bluff_boost * pot * 0.5

        # cbet_frequency_boost → boosts bet
        exploit_mods["bet"] += exploit.cbet_frequency_boost * pot * 0.5

        # bluff_frequency_reduction → reduces bet/raise (negative)
        exploit_mods["bet"] -= exploit.bluff_frequency_reduction * pot * 0.4
        exploit_mods["raise"] -= exploit.bluff_frequency_reduction * pot * 0.4

        # value_bet_boost → boosts bet when equity is high
        if ctx.equity > 0.6:
            exploit_mods["bet"] += exploit.value_bet_boost * pot * 0.4

    # Clamp exploit modifiers
    for action in exploit_mods:
        exploit_mods[action] = max(-exploit_bound, min(exploit_bound, exploit_mods[action]))

    # ─── 3. Board Texture Modifier ────────────────────────────────────────
    board = ctx.board_texture
    range_adv = ctx.range_advantage
    board_mods = {"fold": 0.0, "check": 0.0, "call": 0.0, "bet": 0.0, "raise": 0.0}

    # Dry board → small bonus to bet/raise (good for cbets)
    if board.is_dry:
        board_mods["bet"] += 0.05 * pot
        board_mods["raise"] += 0.03 * pot

    # Wet board → penalty to bet/raise when equity is low (danger)
    if board.is_wet and ctx.equity < 0.5:
        board_mods["bet"] -= 0.06 * pot
        board_mods["raise"] -= 0.08 * pot

    # Range advantage: aggressor_advantage > 0.6 → bonus to bet
    if range_adv.aggressor_advantage > 0.6:
        bonus = (range_adv.aggressor_advantage - 0.6) * pot * 0.3
        board_mods["bet"] += bonus

    # Range advantage: aggressor_advantage < 0.4 → penalty to bet, bonus to check
    if range_adv.aggressor_advantage < 0.4:
        penalty = (0.4 - range_adv.aggressor_advantage) * pot * 0.3
        board_mods["bet"] -= penalty
        board_mods["check"] += penalty * 0.5

    # Clamp board texture modifiers
    for action in board_mods:
        board_mods[action] = max(-board_texture_bound, min(board_texture_bound, board_mods[action]))

    # ─── 4. Personality-Specific EV Modifiers ────────────────────────────
    # Only included when use_personality=True (test/debug mode).
    # In normal gameplay (use_personality=False), these modifiers are skipped
    # to prevent personality-driven exploitable patterns.
    if use_personality:
        # Compute EV scores for this context so personality-specific modifiers can
        # reference them (TAG needs to know best EV, Nit checks for marginal EV, etc.)
        ev_scores = compute_ev_scores(
            equity=ctx.equity,
            pot=pot,
            call_amount=ctx.call_amount,
            bet_amount=ctx.bet_amount,
            raise_amount=ctx.raise_amount,
            fold_probability=ctx.fold_probability,
            legal_actions=legal_actions,
            num_opponents=ctx.num_opponents,
        )
        personality_ev_mods = compute_personality_ev_modifiers(
            personality_name=ctx.personality.name,
            ev_scores=ev_scores,
            fold_probability=ctx.fold_probability,
            pot=pot,
            equity=ctx.equity,
            bet_amount=ctx.bet_amount,
            raise_amount=ctx.raise_amount,
            num_opponents=ctx.num_opponents,
            legal_actions=legal_actions,
        )
    else:
        personality_ev_mods = ActionModifiers(fold=0.0, check=0.0, call=0.0, bet=0.0, raise_=0.0)

    # ─── 5. Sum all modifiers per action ──────────────────────────────────
    total_fold = personality_mods["fold"] + exploit_mods["fold"] + board_mods["fold"] + personality_ev_mods.fold
    total_check = personality_mods["check"] + exploit_mods["check"] + board_mods["check"] + personality_ev_mods.check
    total_call = personality_mods["call"] + exploit_mods["call"] + board_mods["call"] + personality_ev_mods.call
    total_bet = personality_mods["bet"] + exploit_mods["bet"] + board_mods["bet"] + personality_ev_mods.bet
    total_raise = personality_mods["raise"] + exploit_mods["raise"] + board_mods["raise"] + personality_ev_mods.raise_

    # Zero out modifiers for actions not in legal_actions
    if "fold" not in legal_actions:
        total_fold = 0.0
    if "check" not in legal_actions:
        total_check = 0.0
    if "call" not in legal_actions:
        total_call = 0.0
    if "bet" not in legal_actions:
        total_bet = 0.0
    if "raise" not in legal_actions:
        total_raise = 0.0

    return ActionModifiers(
        fold=total_fold,
        check=total_check,
        call=total_call,
        bet=total_bet,
        raise_=total_raise,
    )


def compute_base_scores(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """Compute base action scores using EV + modifier composition.

    Behavior is gated by difficulty_level on the ScoringContext:

      - EASY: Simplified EV only — call EV = equity × final_pot − call_amount,
              bet/raise use a simple heuristic (positive if equity > 0.5 threshold).
              No fold_probability, no modifier systems.
      - MEDIUM: Full EV formulas with all modifiers, but exploit_modifier is
               scaled to 50% of its normal value.
      - HARD/EXPERT/None: Full EV system with all modifiers active, unmodified.

    Noise scaling by difficulty is handled externally in the caller (advanced_bot_decide)
    by adjusting exploitability before passing to apply_noise:
      - EASY: exploitability × 2.0
      - MEDIUM: exploitability × 1.5
      - HARD/EXPERT: exploitability × 1.0 (unchanged)

    This function composes the final score for each action as:
      final_score[action] = ev_score[action] + modifiers[action]

    Where:
      - ev_score comes from compute_ev_scores (pure EV formulas)
      - modifiers come from compute_modifiers (personality + exploit + board texture + personality-specific EV)

    Only actions present in legal_actions receive meaningful scores.
    Actions not in legal_actions are set to _ILLEGAL_SCORE (-1e9).

    **Validates: Requirements 5.1, 5.6, 9.1, 13.1, 13.2, 13.3**
    """
    difficulty = ctx.difficulty_level

    if difficulty == "EASY":
        return _compute_base_scores_easy(ctx, legal_actions)
    elif difficulty == "MEDIUM":
        return _compute_base_scores_medium(ctx, legal_actions)
    else:
        # HARD, EXPERT, or None — full system
        return _compute_base_scores_full(ctx, legal_actions)


def _compute_base_scores_easy(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """EASY difficulty: simplified EV with no fold_probability or modifiers.

    - Fold EV = 0
    - Check EV = 0
    - Call EV = equity × (pot + call_amount) − call_amount
    - Bet: simple heuristic — bet if equity > threshold, score = equity × pot × 0.5
    - Raise: similar heuristic, slightly higher threshold

    No personality/exploit/board_texture modifiers are applied at EASY level.

    **Validates: Requirement 13.1**
    """
    equity = max(0.0, min(1.0, ctx.equity))
    pot = max(0, ctx.pot)
    call_amount = max(0, ctx.call_amount)
    bet_amount = max(0, ctx.bet_amount)
    raise_amount = max(0, ctx.raise_amount)

    scores = ActionScores(
        fold=_ILLEGAL_SCORE,
        check=_ILLEGAL_SCORE,
        call=_ILLEGAL_SCORE,
        bet=_ILLEGAL_SCORE,
        raise_=_ILLEGAL_SCORE,
    )

    # Fold: EV = 0
    if "fold" in legal_actions:
        scores.fold = 0.0

    # Check: EV = 0
    if "check" in legal_actions:
        scores.check = 0.0

    # Call: simplified EV = equity × final_pot − call_amount (no fold_probability)
    if "call" in legal_actions:
        final_pot = pot + call_amount
        scores.call = equity * final_pot - call_amount

    # Bet: simple heuristic — bet when equity is decent
    if "bet" in legal_actions:
        if equity > 0.5 and bet_amount > 0:
            # Simple bet value: expected gain from betting, no fold equity considered
            scores.bet = equity * pot * 0.5
        else:
            # Below threshold, bet has low appeal
            scores.bet = (equity - 0.5) * pot * 0.3

    # Raise: similar to bet but slightly higher threshold
    if "raise" in legal_actions:
        if equity > 0.55 and raise_amount > 0:
            scores.raise_ = equity * pot * 0.4
        else:
            scores.raise_ = (equity - 0.55) * pot * 0.25

    return _ensure_finite(scores)


def _compute_base_scores_medium(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """MEDIUM difficulty: full EV formulas but exploit_modifier scaled to 50%.

    Uses the complete EV calculator and modifier engine, but reduces
    exploit_modifier influence by capping it at 50% of its normal value.

    **Validates: Requirement 13.2**
    """
    # 1. Compute raw EV scores (full formulas)
    ev_scores = compute_ev_scores(
        equity=ctx.equity,
        pot=ctx.pot,
        call_amount=ctx.call_amount,
        bet_amount=ctx.bet_amount,
        raise_amount=ctx.raise_amount,
        fold_probability=ctx.fold_probability,
        legal_actions=legal_actions,
        num_opponents=ctx.num_opponents,
    )

    # 2. Compute modifiers (full system)
    modifiers = compute_modifiers(ctx, legal_actions)

    # 3. Scale down exploit modifier contribution by 50%
    # We need to recompute just the exploit portion to scale it.
    # The modifiers already contain the sum, so we compute exploit separately and adjust.
    exploit_only = _compute_exploit_modifier_only(ctx, legal_actions)

    # Subtract 50% of exploit from the total modifiers (keeping 50% of exploit influence)
    adjusted_mods = ActionModifiers(
        fold=modifiers.fold - exploit_only["fold"] * 0.5,
        check=modifiers.check - exploit_only["check"] * 0.5,
        call=modifiers.call - exploit_only["call"] * 0.5,
        bet=modifiers.bet - exploit_only["bet"] * 0.5,
        raise_=modifiers.raise_ - exploit_only["raise"] * 0.5,
    )

    # 4. Compose final scores = ev + adjusted modifiers
    scores = ActionScores(
        fold=ev_scores.fold + adjusted_mods.fold if "fold" in legal_actions else _ILLEGAL_SCORE,
        check=ev_scores.check + adjusted_mods.check if "check" in legal_actions else _ILLEGAL_SCORE,
        call=ev_scores.call + adjusted_mods.call if "call" in legal_actions else _ILLEGAL_SCORE,
        bet=ev_scores.bet + adjusted_mods.bet if "bet" in legal_actions else _ILLEGAL_SCORE,
        raise_=ev_scores.raise_ + adjusted_mods.raise_ if "raise" in legal_actions else _ILLEGAL_SCORE,
    )

    return _ensure_finite(scores)


def _compute_exploit_modifier_only(ctx: ScoringContext, legal_actions: list[str]) -> dict[str, float]:
    """Compute just the exploit modifier portion for difficulty scaling.

    Returns a dict of action → exploit_modifier_value for use in MEDIUM difficulty
    where exploit modifiers are reduced to 50%.
    """
    pot = max(1, ctx.pot) if ctx.pot > 0 else 100
    exploit_bound = 0.2 * pot

    exploit = ctx.exploit_adjustments
    exploit_mods = {"fold": 0.0, "check": 0.0, "call": 0.0, "bet": 0.0, "raise": 0.0}

    if exploit.active:
        exploit_mods["raise"] += exploit.three_bet_bluff_boost * pot * 0.5
        exploit_mods["bet"] += exploit.cbet_frequency_boost * pot * 0.5
        exploit_mods["bet"] -= exploit.bluff_frequency_reduction * pot * 0.4
        exploit_mods["raise"] -= exploit.bluff_frequency_reduction * pot * 0.4
        if ctx.equity > 0.6:
            exploit_mods["bet"] += exploit.value_bet_boost * pot * 0.4

    for action in exploit_mods:
        exploit_mods[action] = max(-exploit_bound, min(exploit_bound, exploit_mods[action]))

    # Zero out illegal actions
    for action in ["fold", "check", "call", "bet", "raise"]:
        if action not in legal_actions:
            exploit_mods[action] = 0.0

    return exploit_mods


def _compute_base_scores_full(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """HARD/EXPERT difficulty: full EV system with all modifiers active.

    This is the complete pipeline: EV scores + personality + exploit + board_texture
    + personality-specific EV modifiers.

    **Validates: Requirement 13.3**
    """
    # 1. Compute raw EV scores
    ev_scores = compute_ev_scores(
        equity=ctx.equity,
        pot=ctx.pot,
        call_amount=ctx.call_amount,
        bet_amount=ctx.bet_amount,
        raise_amount=ctx.raise_amount,
        fold_probability=ctx.fold_probability,
        legal_actions=legal_actions,
        num_opponents=ctx.num_opponents,
    )

    # 2. Compute modifiers (personality + exploit + board texture + personality-specific EV)
    modifiers = compute_modifiers(ctx, legal_actions)

    # 3. Compose final scores = ev + modifiers
    scores = ActionScores(
        fold=ev_scores.fold + modifiers.fold if "fold" in legal_actions else _ILLEGAL_SCORE,
        check=ev_scores.check + modifiers.check if "check" in legal_actions else _ILLEGAL_SCORE,
        call=ev_scores.call + modifiers.call if "call" in legal_actions else _ILLEGAL_SCORE,
        bet=ev_scores.bet + modifiers.bet if "bet" in legal_actions else _ILLEGAL_SCORE,
        raise_=ev_scores.raise_ + modifiers.raise_ if "raise" in legal_actions else _ILLEGAL_SCORE,
    )

    return _ensure_finite(scores)


def _compute_base_scores_legacy(ctx: ScoringContext, legal_actions: list[str]) -> ActionScores:
    """DEPRECATED: Old heuristic scoring logic. Kept for reference only. See compute_base_scores for the new EV-based implementation.

    This was the original compute_base_scores logic before the EV-based refactor.
    It uses heuristic weights and is no longer called in production code.
    Preserved for comparison and potential rollback during integration testing.

    .. deprecated::
        This function is dead code. Do not call in production.
        Personality, exploit, and board texture are now handled via compute_modifiers().
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
        if equity < 0.25:
            fold_score += (0.25 - equity) * 1.5
        if pot_odds > 0 and equity < pot_odds:
            fold_score += (pot_odds - equity) * 0.8
        scores.fold = fold_score

    # ─── Check ─────────────────────────────────────────────────────────────
    if "check" in legal_actions:
        check_score = 0.4
        if board.is_wet and ctx.is_preflop_aggressor:
            check_score += 0.15
        check_score += personality.trap_frequency * 0.3
        check_score += dynamic.trap_frequency_boost * 0.2
        scores.check = check_score

    # ─── Call ──────────────────────────────────────────────────────────────
    if "call" in legal_actions:
        call_score = 0.2
        if pot_odds > 0 and equity > pot_odds:
            call_score += (equity - pot_odds) * 2.0
        elif pot_odds == 0:
            call_score += equity * 0.5
        if _is_late_position(ctx.position):
            call_score += bluff_total * 0.2
        scores.call = call_score

    # ─── Bet ───────────────────────────────────────────────────────────────
    if "bet" in legal_actions:
        bet_score = 0.2
        bet_score += equity * 1.2
        if board.is_dry:
            bet_score += 0.2
        if ctx.is_preflop_aggressor:
            bet_score += 0.15
        bet_score += bluff_total * 0.4
        bet_score += aggressor_adv * 0.3
        bet_score += position_bonus * 0.15
        bet_score += dynamic.steal_frequency_boost * 0.2
        if exploit.active:
            bet_score += exploit.cbet_frequency_boost * 0.3
        scores.bet = bet_score

    # ─── Raise ─────────────────────────────────────────────────────────────
    if "raise" in legal_actions:
        raise_score = 0.1
        if equity > 0.7:
            raise_score += (equity - 0.7) * 3.0
        raise_score += equity * 0.8
        raise_score += personality.aggression * 0.3
        raise_score += bluff_total * 0.3
        if exploit.active:
            raise_score += exploit.three_bet_bluff_boost * 0.4
            raise_score += exploit.cbet_frequency_boost * 0.2
        raise_score += dynamic.four_bet_frequency_boost * 0.2
        raise_score += position_bonus * 0.1
        scores.raise_ = raise_score

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


def apply_allin_cap(scores: ActionScores, equity: float) -> ActionScores:
    """Cap all-in (raise) score based on equity to prevent marginal shoves.

    When a raise commits the player's entire stack (all-in), the score is
    capped relative to the next-best aggressive action (bet) based on equity:

    - equity >= 0.80: no cap (strong hands may shove freely)
    - equity 0.60-0.80: cap raise_ to 1.5× bet score (value shoves OK)
    - equity 0.40-0.60: cap raise_ to 0.8× bet score (marginal hands rarely shove)
    - equity < 0.40: cap raise_ to 0.3× bet score (bluff shoves very rare)

    This prevents the bot from over-shoving one-pair or marginal hands at
    deep stacks (SPR > 3) while still allowing strong hand shoves and
    occasional well-timed bluff shoves (via noise).

    **Validates: Requirements 2.1, 2.5**
    """
    # No cap for very strong hands
    if equity >= 0.80:
        return scores

    # Only cap if raise_ is a legal action
    if scores.raise_ <= _ILLEGAL_SCORE:
        return scores

    # Find the reference score (bet or call — whichever is highest legal non-raise)
    reference = max(
        scores.bet if scores.bet > _ILLEGAL_SCORE else -1e8,
        scores.call if scores.call > _ILLEGAL_SCORE else -1e8,
        scores.check if scores.check > _ILLEGAL_SCORE else -1e8,
    )

    # If no valid reference, use a small absolute cap
    if reference <= -1e7:
        cap = 0.1
    elif reference <= 0:
        cap = 0.1
    elif equity >= 0.60:
        # Strong value range: allow shoves but cap to 1.5× reference
        cap = 1.5 * reference
    elif equity >= 0.40:
        # Marginal range: shoves heavily discouraged
        cap = 0.8 * reference
    else:
        # Weak range: almost never shove (bluff shoves very rare)
        cap = 0.3 * reference

    if scores.raise_ > cap:
        return ActionScores(
            fold=scores.fold,
            check=scores.check,
            call=scores.call,
            bet=scores.bet,
            raise_=cap,
        )

    return scores


def apply_noise(scores: ActionScores, exploitability: float, pot_size: int = 0) -> ActionScores:
    """Add random noise proportional to exploitability and pot size.

    For each action score that is not illegal, adds gaussian noise with
    mean 0 and standard deviation = exploitability × 0.05 × pot_size.

    When pot_size is 0, no noise is applied (sigma = 0).
    Higher exploitability → greater variance in scores → less predictable play.

    **Validates: Requirements 5.5, 9.3**
    """
    sigma = exploitability * 0.05 * pot_size

    if sigma <= 0:
        return scores

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
