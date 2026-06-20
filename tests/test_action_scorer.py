"""Unit tests for poker.bot_ai.action_scorer module.

Tests cover the four core functions:
- compute_base_scores
- apply_personality
- apply_noise
- select_action
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

import pytest

from poker.bot_ai.action_scorer import (
    _ILLEGAL_SCORE,
    apply_noise,
    apply_personality,
    compute_base_scores,
    select_action,
)
from poker.bot_ai.models import (
    ActionScores,
    BluffScore,
    BoardTexture,
    DynamicAdjustments,
    ExploitAdjustments,
    RangeAdvantage,
    RangeEstimate,
    ScoringContext,
)
from poker.bot_ai.personality_engine import get_personality


# ─── Fixtures ──────────────────────────────────────────────────────────────────


def _make_ctx(
    equity: float = 0.5,
    pot_odds: float = 0.3,
    position: str = "BTN",
    street: str = "flop",
    is_preflop_aggressor: bool = True,
    board_dry: bool = True,
    board_wet: bool = False,
    exploit_active: bool = False,
    personality_style: str = "TAG",
) -> ScoringContext:
    """Create a ScoringContext with sensible defaults."""
    return ScoringContext(
        equity=equity,
        pot_odds=pot_odds,
        opponent_range=RangeEstimate(),
        board_texture=BoardTexture(is_dry=board_dry, is_wet=board_wet),
        range_advantage=RangeAdvantage(aggressor_advantage=0.5),
        position=position,
        street=street,
        bluff_score=BluffScore(
            blocker_score=0.3,
            fold_equity=0.4,
            range_advantage=0.5,
            backup_equity=0.2,
            total_score=0.35,
        ),
        exploit_adjustments=ExploitAdjustments(active=exploit_active),
        dynamic_adjustments=DynamicAdjustments(),
        personality=get_personality(personality_style),
        stack_to_pot=5.0,
        is_preflop_aggressor=is_preflop_aggressor,
    )


# ─── compute_base_scores ──────────────────────────────────────────────────────


class TestComputeBaseScores:
    """Tests for compute_base_scores function."""

    def test_all_legal_actions_get_finite_scores(self):
        """Req 9.1: All legal actions get finite scores."""
        ctx = _make_ctx()
        legal = ["fold", "check", "call", "bet", "raise"]
        scores = compute_base_scores(ctx, legal)

        assert math.isfinite(scores.fold)
        assert math.isfinite(scores.check)
        assert math.isfinite(scores.call)
        assert math.isfinite(scores.bet)
        assert math.isfinite(scores.raise_)

    def test_illegal_actions_get_very_negative_score(self):
        """Actions not in legal_actions should get very negative scores."""
        ctx = _make_ctx()
        legal = ["fold", "bet"]
        scores = compute_base_scores(ctx, legal)

        assert scores.check <= _ILLEGAL_SCORE
        assert scores.call <= _ILLEGAL_SCORE
        assert scores.raise_ <= _ILLEGAL_SCORE
        # Legal ones are normal
        assert scores.fold > _ILLEGAL_SCORE
        assert scores.bet > _ILLEGAL_SCORE

    def test_high_equity_boosts_bet_and_raise(self):
        """High equity should produce higher bet/raise scores."""
        ctx_low = _make_ctx(equity=0.3)
        ctx_high = _make_ctx(equity=0.8)
        legal = ["fold", "check", "bet", "raise"]

        scores_low = compute_base_scores(ctx_low, legal)
        scores_high = compute_base_scores(ctx_high, legal)

        assert scores_high.bet > scores_low.bet
        assert scores_high.raise_ > scores_low.raise_

    def test_low_equity_boosts_fold(self):
        """Very low equity should boost fold score."""
        ctx_low = _make_ctx(equity=0.1, pot_odds=0.4)
        ctx_high = _make_ctx(equity=0.6, pot_odds=0.4)
        legal = ["fold", "call"]

        scores_low = compute_base_scores(ctx_low, legal)
        scores_high = compute_base_scores(ctx_high, legal)

        assert scores_low.fold > scores_high.fold

    def test_profitable_call_boosts_call_score(self):
        """When equity > pot_odds, call should be boosted."""
        ctx = _make_ctx(equity=0.6, pot_odds=0.3)
        legal = ["fold", "call"]
        scores = compute_base_scores(ctx, legal)

        assert scores.call > scores.fold

    def test_dry_board_boosts_bet(self):
        """Dry board should boost bet score (cbet incentive)."""
        ctx_dry = _make_ctx(board_dry=True, board_wet=False)
        ctx_wet = _make_ctx(board_dry=False, board_wet=True)
        legal = ["check", "bet"]

        scores_dry = compute_base_scores(ctx_dry, legal)
        scores_wet = compute_base_scores(ctx_wet, legal)

        assert scores_dry.bet > scores_wet.bet

    def test_wet_board_boosts_check_for_aggressor(self):
        """Wet board should boost check (pot control) for aggressor."""
        ctx_dry = _make_ctx(board_dry=True, board_wet=False, is_preflop_aggressor=True)
        ctx_wet = _make_ctx(board_dry=False, board_wet=True, is_preflop_aggressor=True)
        legal = ["check", "bet"]

        scores_dry = compute_base_scores(ctx_dry, legal)
        scores_wet = compute_base_scores(ctx_wet, legal)

        assert scores_wet.check > scores_dry.check


# ─── apply_personality ─────────────────────────────────────────────────────────


class TestApplyPersonality:
    """Tests for apply_personality function."""

    def test_personality_modifies_scores(self):
        """Req 9.2: Personality multipliers should change scores."""
        scores = ActionScores(fold=0.5, check=0.5, call=0.5, bet=0.5, raise_=0.5)
        personality = get_personality("Maniac")
        modified = apply_personality(scores, personality)

        # Maniac has high aggression → raise/bet should be boosted above 0.5
        assert modified.bet > 0.5
        assert modified.raise_ > 0.5

    def test_illegal_scores_unchanged(self):
        """Illegal actions (very negative) should remain untouched."""
        scores = ActionScores(fold=0.5, check=_ILLEGAL_SCORE, call=0.5, bet=0.5, raise_=_ILLEGAL_SCORE)
        personality = get_personality("TAG")
        modified = apply_personality(scores, personality)

        assert modified.check == _ILLEGAL_SCORE
        assert modified.raise_ == _ILLEGAL_SCORE

    def test_aggressive_personality_boosts_raise_bet(self):
        """Aggressive personality increases raise/bet proportionally."""
        scores = ActionScores(fold=0.5, check=0.5, call=0.5, bet=0.5, raise_=0.5)
        passive = get_personality("Calling_Station")  # low aggression
        aggressive = get_personality("Maniac")  # high aggression

        mod_passive = apply_personality(scores, passive)
        mod_aggressive = apply_personality(scores, aggressive)

        assert mod_aggressive.bet > mod_passive.bet
        assert mod_aggressive.raise_ > mod_passive.raise_


# ─── apply_noise ───────────────────────────────────────────────────────────────


class TestApplyNoise:
    """Tests for apply_noise function."""

    def test_noise_produces_finite_values(self):
        """Noise should never produce NaN or infinite values."""
        scores = ActionScores(fold=0.3, check=0.4, call=0.5, bet=0.6, raise_=0.7)
        for _ in range(100):
            noisy = apply_noise(scores, 0.45)
            assert math.isfinite(noisy.fold)
            assert math.isfinite(noisy.check)
            assert math.isfinite(noisy.call)
            assert math.isfinite(noisy.bet)
            assert math.isfinite(noisy.raise_)

    def test_higher_exploitability_produces_more_variance(self):
        """Req 9.3: Higher exploitability → greater variance."""
        base = ActionScores(fold=0.5, check=0.5, call=0.5, bet=0.5, raise_=0.5)

        samples_low = [apply_noise(base, 0.08).bet for _ in range(500)]
        samples_high = [apply_noise(base, 0.45).bet for _ in range(500)]

        var_low = statistics.variance(samples_low)
        var_high = statistics.variance(samples_high)

        assert var_high > var_low

    def test_illegal_scores_not_noised(self):
        """Illegal scores should remain at _ILLEGAL_SCORE."""
        scores = ActionScores(fold=_ILLEGAL_SCORE, check=0.5, call=_ILLEGAL_SCORE, bet=0.5, raise_=0.5)
        noisy = apply_noise(scores, 0.3)

        assert noisy.fold == _ILLEGAL_SCORE
        assert noisy.call == _ILLEGAL_SCORE


# ─── select_action ─────────────────────────────────────────────────────────────


class TestSelectAction:
    """Tests for select_action function."""

    def test_selects_highest_score(self):
        """Should select the action with the clearly highest score."""
        scores = ActionScores(fold=0.1, check=0.3, call=0.5, bet=1.5, raise_=0.2)
        # bet is clearly highest — should always be selected
        for _ in range(100):
            assert select_action(scores) == "bet"

    def test_tied_actions_both_selected(self):
        """Req 9.5: When actions within 5%, both should be selectable."""
        scores = ActionScores(fold=_ILLEGAL_SCORE, check=1.0, call=_ILLEGAL_SCORE, bet=1.0, raise_=_ILLEGAL_SCORE)
        results = Counter(select_action(scores) for _ in range(500))

        assert "check" in results
        assert "bet" in results

    def test_within_five_percent_included(self):
        """Actions within 5% of max should be candidates."""
        # 0.96 is within 5% of 1.0 (threshold = 0.95)
        scores = ActionScores(fold=_ILLEGAL_SCORE, check=0.96, call=_ILLEGAL_SCORE, bet=1.0, raise_=0.5)
        results = Counter(select_action(scores) for _ in range(500))

        assert "check" in results
        assert "bet" in results
        assert "raise" not in results

    def test_fallback_when_all_illegal(self):
        """Should return fold if somehow all scores are illegal."""
        scores = ActionScores(
            fold=_ILLEGAL_SCORE,
            check=_ILLEGAL_SCORE,
            call=_ILLEGAL_SCORE,
            bet=_ILLEGAL_SCORE,
            raise_=_ILLEGAL_SCORE,
        )
        assert select_action(scores) == "fold"

    def test_only_legal_actions_selected(self):
        """Should never select an action with illegal score."""
        scores = ActionScores(fold=0.2, check=_ILLEGAL_SCORE, call=0.8, bet=_ILLEGAL_SCORE, raise_=_ILLEGAL_SCORE)
        for _ in range(100):
            action = select_action(scores)
            assert action in ("fold", "call")
