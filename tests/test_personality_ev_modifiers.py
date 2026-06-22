"""Unit tests for compute_personality_ev_modifiers in action_scorer.

Tests cover each personality archetype's modifier behavior:
- TAG: Boosts best EV action, penalizes marginal-EV actions
- LAG: Adds positive modifier to bet/raise via 1.2× fold_prob
- Nit: Penalizes call/raise when EV is marginal (within ±0.1×pot)
- Maniac: Adds larger modifier to bet/raise via 1.4× fold_prob + flat bonus
- Calling_Station: Boosts call, penalizes fold

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
"""

from __future__ import annotations

import pytest

from poker.bot_ai.action_scorer import (
    ActionModifiers,
    ActionScores,
    compute_personality_ev_modifiers,
    compute_ev_scores,
    _ILLEGAL_SCORE,
)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _default_ev_scores(pot: int = 100) -> ActionScores:
    """Create EV scores with typical values for testing."""
    return compute_ev_scores(
        equity=0.5,
        pot=pot,
        call_amount=50,
        bet_amount=75,
        raise_amount=150,
        fold_probability=0.35,
        legal_actions=["fold", "call", "bet", "raise"],
        num_opponents=1,
    )


# ─── TAG Tests ─────────────────────────────────────────────────────────────────

class TestTAGModifiers:
    """TAG increases weight of highest-EV action, decreases for marginal."""

    def test_tag_boosts_best_ev_action(self):
        """TAG should add +0.05×pot to the highest EV action."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="TAG",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        # The best action gets a positive boost
        all_mods = [mods.fold, mods.call, mods.bet, mods.raise_]
        assert max(all_mods) == pytest.approx(0.05 * pot, abs=0.01)

    def test_tag_penalizes_marginal_ev_actions(self):
        """TAG should penalize actions with EV within ±0.1×pot of zero."""
        pot = 100
        # Use fold EV = 0 (always marginal), and make other EVs non-marginal
        ev_scores = compute_ev_scores(
            equity=0.8,
            pot=pot,
            call_amount=20,
            bet_amount=50,
            raise_amount=100,
            fold_probability=0.5,
            legal_actions=["fold", "call", "bet", "raise"],
            num_opponents=1,
        )
        mods = compute_personality_ev_modifiers(
            personality_name="TAG",
            ev_scores=ev_scores,
            fold_probability=0.5,
            pot=pot,
            equity=0.8,
            bet_amount=50,
            raise_amount=100,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        # Fold EV is 0, which is within ±0.1×pot → should be penalized
        # (unless fold is the best action, which it won't be with equity=0.8)
        assert mods.fold < 0

    def test_tag_returns_zero_for_unlisted_personality(self):
        """Non-archetype personalities get zero personality EV modifiers."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="GTO_ish",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.fold == 0.0
        assert mods.check == 0.0
        assert mods.call == 0.0
        assert mods.bet == 0.0
        assert mods.raise_ == 0.0


# ─── LAG Tests ─────────────────────────────────────────────────────────────────

class TestLAGModifiers:
    """LAG overweights fold_probability by 1.2× in bet/raise EV."""

    def test_lag_positive_modifier_for_bet(self):
        """LAG should produce a positive bet modifier (sees higher fold prob)."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="LAG",
            ev_scores=ev_scores,
            fold_probability=0.4,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        # Higher fold prob → higher EV → positive diff
        assert mods.bet > 0
        assert mods.raise_ > 0

    def test_lag_no_modifier_when_fold_prob_already_high(self):
        """When fold_prob×1.2 > 1.0, it gets capped; modifier still non-negative."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="LAG",
            ev_scores=ev_scores,
            fold_probability=0.9,  # 0.9 × 1.2 = 1.08 → capped to 1.0
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.bet >= 0
        assert mods.raise_ >= 0

    def test_lag_does_not_affect_call_or_fold(self):
        """LAG modifier only applies to bet/raise, not call/fold."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="LAG",
            ev_scores=ev_scores,
            fold_probability=0.4,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.fold == 0.0
        assert mods.call == 0.0


# ─── Nit Tests ─────────────────────────────────────────────────────────────────

class TestNitModifiers:
    """Nit applies negative modifier to call/raise when EV is near zero."""

    def test_nit_penalizes_when_marginal_ev_exists(self):
        """Nit should penalize call/raise when any action has marginal EV."""
        pot = 100
        # Fold EV = 0 (always within ±0.1×pot), so nit should trigger
        ev_scores = compute_ev_scores(
            equity=0.5,
            pot=pot,
            call_amount=50,
            bet_amount=75,
            raise_amount=150,
            fold_probability=0.35,
            legal_actions=["fold", "call", "bet", "raise"],
            num_opponents=1,
        )
        mods = compute_personality_ev_modifiers(
            personality_name="Nit",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        # Should penalize call and raise by -0.08×pot
        assert mods.call == pytest.approx(-0.08 * pot)
        assert mods.raise_ == pytest.approx(-0.08 * pot)

    def test_nit_no_penalty_when_no_marginal_ev(self):
        """Nit should not penalize when all actions have EV far from zero."""
        pot = 100
        # Very high equity → all EVs far from zero
        ev_scores = compute_ev_scores(
            equity=0.95,
            pot=pot,
            call_amount=10,
            bet_amount=50,
            raise_amount=100,
            fold_probability=0.8,
            legal_actions=["call", "bet", "raise"],
            num_opponents=1,
        )
        mods = compute_personality_ev_modifiers(
            personality_name="Nit",
            ev_scores=ev_scores,
            fold_probability=0.8,
            pot=pot,
            equity=0.95,
            bet_amount=50,
            raise_amount=100,
            num_opponents=1,
            legal_actions=["call", "bet", "raise"],
        )
        # With such high equity and fold prob, EVs are all well above 0.1×pot
        # call_ev = 0.95 × 110 - 10 = 94.5 (far from 0)
        # so no penalty should apply
        assert mods.call == 0.0
        assert mods.raise_ == 0.0


# ─── Maniac Tests ──────────────────────────────────────────────────────────────

class TestManiacModifiers:
    """Maniac uses 1.4× fold_prob + flat bonus on aggressive actions."""

    def test_maniac_larger_modifier_than_lag(self):
        """Maniac should produce larger bet/raise modifiers than LAG."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        kwargs = dict(
            ev_scores=ev_scores,
            fold_probability=0.4,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        lag_mods = compute_personality_ev_modifiers(personality_name="LAG", **kwargs)
        maniac_mods = compute_personality_ev_modifiers(personality_name="Maniac", **kwargs)

        assert maniac_mods.bet > lag_mods.bet
        assert maniac_mods.raise_ > lag_mods.raise_

    def test_maniac_includes_flat_bonus(self):
        """Maniac adds a flat +0.05×pot to bet and raise on top of fold prob boost."""
        pot = 100
        # Even with fold_prob=0 (no fold prob boost), Maniac still gets flat bonus
        ev_scores = compute_ev_scores(
            equity=0.5,
            pot=pot,
            call_amount=50,
            bet_amount=75,
            raise_amount=150,
            fold_probability=0.0,  # No fold probability
            legal_actions=["fold", "call", "bet", "raise"],
            num_opponents=1,
        )
        mods = compute_personality_ev_modifiers(
            personality_name="Maniac",
            ev_scores=ev_scores,
            fold_probability=0.0,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        # With fold_prob=0, 1.4×0=0, so the fold_prob difference is 0.
        # Only the flat bonus remains: +0.05×pot = 5
        assert mods.bet == pytest.approx(0.05 * pot)
        assert mods.raise_ == pytest.approx(0.05 * pot)


# ─── Calling Station Tests ─────────────────────────────────────────────────────

class TestCallingStationModifiers:
    """Calling_Station boosts call, penalizes fold."""

    def test_calling_station_boosts_call(self):
        """Calling_Station adds +0.1×pot to call."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="Calling_Station",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.call == pytest.approx(0.1 * pot)

    def test_calling_station_penalizes_fold(self):
        """Calling_Station subtracts -0.05×pot from fold."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="Calling_Station",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.fold == pytest.approx(-0.05 * pot)

    def test_calling_station_no_effect_on_bet_raise(self):
        """Calling_Station does not modify bet/raise."""
        pot = 100
        ev_scores = _default_ev_scores(pot)
        mods = compute_personality_ev_modifiers(
            personality_name="Calling_Station",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=150,
            num_opponents=1,
            legal_actions=["fold", "call", "bet", "raise"],
        )
        assert mods.bet == 0.0
        assert mods.raise_ == 0.0


# ─── Clamping Tests ────────────────────────────────────────────────────────────

class TestModifierClamping:
    """All personality EV modifiers are clamped to [-0.3×pot, +0.3×pot]."""

    def test_modifiers_within_bounds(self):
        """No modifier should exceed ±0.3×pot."""
        pot = 100
        bound = 0.3 * pot
        ev_scores = _default_ev_scores(pot)
        for personality in ["TAG", "LAG", "Nit", "Maniac", "Calling_Station"]:
            mods = compute_personality_ev_modifiers(
                personality_name=personality,
                ev_scores=ev_scores,
                fold_probability=0.5,
                pot=pot,
                equity=0.5,
                bet_amount=75,
                raise_amount=150,
                num_opponents=1,
                legal_actions=["fold", "call", "bet", "raise"],
            )
            assert -bound <= mods.fold <= bound, f"{personality} fold out of bounds"
            assert -bound <= mods.check <= bound, f"{personality} check out of bounds"
            assert -bound <= mods.call <= bound, f"{personality} call out of bounds"
            assert -bound <= mods.bet <= bound, f"{personality} bet out of bounds"
            assert -bound <= mods.raise_ <= bound, f"{personality} raise out of bounds"

    def test_illegal_actions_get_zero_modifier(self):
        """Actions not in legal_actions should have zero modifier."""
        pot = 100
        ev_scores = compute_ev_scores(
            equity=0.5,
            pot=pot,
            call_amount=50,
            bet_amount=75,
            raise_amount=0,
            fold_probability=0.35,
            legal_actions=["fold", "call", "bet"],
            num_opponents=1,
        )
        mods = compute_personality_ev_modifiers(
            personality_name="Maniac",
            ev_scores=ev_scores,
            fold_probability=0.35,
            pot=pot,
            equity=0.5,
            bet_amount=75,
            raise_amount=0,
            num_opponents=1,
            legal_actions=["fold", "call", "bet"],  # No raise
        )
        assert mods.raise_ == 0.0
        assert mods.check == 0.0
