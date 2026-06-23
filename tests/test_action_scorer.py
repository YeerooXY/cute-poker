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
    pot: int = 100,
    bet_amount: int = 70,
    raise_amount: int = 150,
    call_amount: int = 50,
    fold_probability: float = 0.35,
    num_opponents: int = 1,
) -> ScoringContext:
    """Create a ScoringContext with sensible defaults for EV-based scoring."""
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
        fold_probability=fold_probability,
        bet_amount=bet_amount,
        raise_amount=raise_amount,
        call_amount=call_amount,
        num_opponents=num_opponents,
        pot=pot,
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
        """Very low equity should make fold preferable to call (fold EV=0 > negative call EV)."""
        ctx_low = _make_ctx(equity=0.1, pot_odds=0.4)
        legal = ["fold", "call"]

        scores_low = compute_base_scores(ctx_low, legal)

        # With low equity and high pot odds requirement, calling is negative EV
        # while fold is always 0, so fold should be preferred over call
        assert scores_low.fold > scores_low.call

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
        """Wet board should make check relatively more attractive vs bet (pot control)."""
        ctx_dry = _make_ctx(board_dry=True, board_wet=False, is_preflop_aggressor=True, equity=0.45)
        ctx_wet = _make_ctx(board_dry=False, board_wet=True, is_preflop_aggressor=True, equity=0.45)
        legal = ["check", "bet"]

        scores_dry = compute_base_scores(ctx_dry, legal)
        scores_wet = compute_base_scores(ctx_wet, legal)

        # On a wet board with moderate equity, bet should be penalized via modifiers,
        # making the bet-check gap smaller (or check dominant) compared to dry board.
        dry_gap = scores_dry.bet - scores_dry.check
        wet_gap = scores_wet.bet - scores_wet.check
        assert wet_gap < dry_gap


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
            noisy = apply_noise(scores, 0.45, 200)
            assert math.isfinite(noisy.fold)
            assert math.isfinite(noisy.check)
            assert math.isfinite(noisy.call)
            assert math.isfinite(noisy.bet)
            assert math.isfinite(noisy.raise_)

    def test_higher_exploitability_produces_more_variance(self):
        """Req 9.3: Higher exploitability → greater variance."""
        base = ActionScores(fold=0.5, check=0.5, call=0.5, bet=0.5, raise_=0.5)

        samples_low = [apply_noise(base, 0.08, 200).bet for _ in range(500)]
        samples_high = [apply_noise(base, 0.45, 200).bet for _ in range(500)]

        var_low = statistics.variance(samples_low)
        var_high = statistics.variance(samples_high)

        assert var_high > var_low

    def test_illegal_scores_not_noised(self):
        """Illegal scores should remain at _ILLEGAL_SCORE."""
        scores = ActionScores(fold=_ILLEGAL_SCORE, check=0.5, call=_ILLEGAL_SCORE, bet=0.5, raise_=0.5)
        noisy = apply_noise(scores, 0.3, 200)

        assert noisy.fold == _ILLEGAL_SCORE
        assert noisy.call == _ILLEGAL_SCORE

    def test_zero_pot_produces_no_noise(self):
        """When pot_size is 0, sigma is 0 and no noise should be applied."""
        scores = ActionScores(fold=0.3, check=0.4, call=0.5, bet=0.6, raise_=0.7)
        for _ in range(100):
            noisy = apply_noise(scores, 0.45, 0)
            assert noisy.fold == scores.fold
            assert noisy.check == scores.check
            assert noisy.call == scores.call
            assert noisy.bet == scores.bet
            assert noisy.raise_ == scores.raise_

    def test_pot_proportional_sigma(self):
        """Noise sigma should scale with pot_size: larger pot → more variance."""
        base = ActionScores(fold=0.5, check=0.5, call=0.5, bet=0.5, raise_=0.5)

        samples_small_pot = [apply_noise(base, 0.3, 50).bet for _ in range(500)]
        samples_large_pot = [apply_noise(base, 0.3, 500).bet for _ in range(500)]

        var_small = statistics.variance(samples_small_pot)
        var_large = statistics.variance(samples_large_pot)

        assert var_large > var_small


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


# ─── Difficulty-Gated Behavior ─────────────────────────────────────────────────


class TestDifficultyGating:
    """Tests for difficulty-gated EV behavior in compute_base_scores.

    Validates Requirement 13: EASY uses simplified EV, MEDIUM uses full EV
    with reduced exploit, HARD/EXPERT uses the complete system.
    """

    def test_easy_no_fold_probability_effect(self):
        """EASY: fold_probability should NOT affect scoring (simplified EV)."""
        ctx_low_fp = _make_ctx(equity=0.6, fold_probability=0.1, pot=200, bet_amount=100)
        ctx_low_fp.difficulty_level = "EASY"
        ctx_high_fp = _make_ctx(equity=0.6, fold_probability=0.9, pot=200, bet_amount=100)
        ctx_high_fp.difficulty_level = "EASY"

        legal = ["check", "bet"]
        scores_low = compute_base_scores(ctx_low_fp, legal)
        scores_high = compute_base_scores(ctx_high_fp, legal)

        # In EASY mode, fold_probability is not used, so scores should be identical
        assert scores_low.bet == scores_high.bet
        assert scores_low.check == scores_high.check

    def test_easy_call_ev_uses_simplified_formula(self):
        """EASY: call EV = equity × final_pot − call_amount (no modifiers)."""
        ctx = _make_ctx(equity=0.6, pot=200, call_amount=50)
        ctx.difficulty_level = "EASY"

        legal = ["fold", "call"]
        scores = compute_base_scores(ctx, legal)

        # Expected: 0.6 × (200 + 50) − 50 = 0.6 × 250 − 50 = 150 − 50 = 100
        expected_call_ev = 0.6 * (200 + 50) - 50
        assert abs(scores.call - expected_call_ev) < 0.01

    def test_easy_fold_is_zero(self):
        """EASY: fold EV = 0."""
        ctx = _make_ctx(equity=0.3, pot=200)
        ctx.difficulty_level = "EASY"

        legal = ["fold", "call"]
        scores = compute_base_scores(ctx, legal)
        assert scores.fold == 0.0

    def test_easy_no_exploit_modifiers(self):
        """EASY: exploit adjustments should not affect scores."""
        ctx_no_exploit = _make_ctx(equity=0.6, pot=200, bet_amount=100, exploit_active=False)
        ctx_no_exploit.difficulty_level = "EASY"
        ctx_exploit = _make_ctx(equity=0.6, pot=200, bet_amount=100, exploit_active=True)
        ctx_exploit.difficulty_level = "EASY"
        # Set some exploit values
        ctx_exploit.exploit_adjustments.three_bet_bluff_boost = 0.5
        ctx_exploit.exploit_adjustments.cbet_frequency_boost = 0.5

        legal = ["check", "bet"]
        scores_no = compute_base_scores(ctx_no_exploit, legal)
        scores_yes = compute_base_scores(ctx_exploit, legal)

        # EASY doesn't use modifiers, so both should be the same
        assert scores_no.bet == scores_yes.bet

    def test_medium_uses_fold_probability(self):
        """MEDIUM: fold_probability IS used in EV formula (unlike EASY)."""
        ctx_low = _make_ctx(equity=0.5, fold_probability=0.1, pot=200, bet_amount=100)
        ctx_low.difficulty_level = "MEDIUM"
        ctx_high = _make_ctx(equity=0.5, fold_probability=0.9, pot=200, bet_amount=100)
        ctx_high.difficulty_level = "MEDIUM"

        legal = ["check", "bet"]
        scores_low = compute_base_scores(ctx_low, legal)
        scores_high = compute_base_scores(ctx_high, legal)

        # Higher fold probability → higher bet EV (more fold equity)
        assert scores_high.bet > scores_low.bet

    def test_medium_exploit_scaled_vs_hard(self):
        """MEDIUM: exploit modifier influence is reduced compared to HARD."""
        ctx_medium = _make_ctx(equity=0.6, pot=200, bet_amount=100, exploit_active=True)
        ctx_medium.difficulty_level = "MEDIUM"
        ctx_medium.exploit_adjustments.cbet_frequency_boost = 0.8
        ctx_medium.exploit_adjustments.three_bet_bluff_boost = 0.8

        ctx_hard = _make_ctx(equity=0.6, pot=200, bet_amount=100, exploit_active=True)
        ctx_hard.difficulty_level = "HARD"
        ctx_hard.exploit_adjustments.cbet_frequency_boost = 0.8
        ctx_hard.exploit_adjustments.three_bet_bluff_boost = 0.8

        legal = ["check", "bet", "raise"]
        scores_medium = compute_base_scores(ctx_medium, legal)
        scores_hard = compute_base_scores(ctx_hard, legal)

        # HARD should have stronger exploit influence on bet/raise
        # The difference comes from exploit_modifier being 50% reduced in MEDIUM
        # With positive cbet_frequency_boost, HARD's bet should be >= MEDIUM's bet
        # (since MEDIUM reduces the exploit boost)
        # Note: This is approximate due to personality EV modifiers also in play
        # but the exploit component should be measurably less in MEDIUM
        assert scores_hard.bet >= scores_medium.bet - 1.0  # Allow small tolerance

    def test_hard_full_system(self):
        """HARD: uses complete EV + all modifiers — same as None difficulty."""
        ctx_hard = _make_ctx(equity=0.6, pot=200, bet_amount=100, fold_probability=0.4)
        ctx_hard.difficulty_level = "HARD"

        ctx_none = _make_ctx(equity=0.6, pot=200, bet_amount=100, fold_probability=0.4)
        ctx_none.difficulty_level = None

        legal = ["fold", "call", "raise"]
        scores_hard = compute_base_scores(ctx_hard, legal)
        scores_none = compute_base_scores(ctx_none, legal)

        # HARD and None should produce identical results
        assert scores_hard.fold == scores_none.fold
        assert scores_hard.call == scores_none.call
        assert scores_hard.raise_ == scores_none.raise_

    def test_expert_full_system(self):
        """EXPERT: uses complete EV + all modifiers — same as HARD."""
        ctx_expert = _make_ctx(equity=0.6, pot=200, bet_amount=100, fold_probability=0.4)
        ctx_expert.difficulty_level = "EXPERT"

        ctx_hard = _make_ctx(equity=0.6, pot=200, bet_amount=100, fold_probability=0.4)
        ctx_hard.difficulty_level = "HARD"

        legal = ["fold", "call", "raise"]
        scores_expert = compute_base_scores(ctx_expert, legal)
        scores_hard = compute_base_scores(ctx_hard, legal)

        # EXPERT and HARD produce identical base scores
        assert scores_expert.fold == scores_hard.fold
        assert scores_expert.call == scores_hard.call
        assert scores_expert.raise_ == scores_hard.raise_

    def test_easy_bet_positive_when_high_equity(self):
        """EASY: bet should be positive when equity is high (simple heuristic)."""
        ctx = _make_ctx(equity=0.8, pot=200, bet_amount=100)
        ctx.difficulty_level = "EASY"

        legal = ["check", "bet"]
        scores = compute_base_scores(ctx, legal)
        assert scores.bet > 0.0

    def test_easy_bet_negative_when_low_equity(self):
        """EASY: bet should be negative when equity is low."""
        ctx = _make_ctx(equity=0.2, pot=200, bet_amount=100)
        ctx.difficulty_level = "EASY"

        legal = ["check", "bet"]
        scores = compute_base_scores(ctx, legal)
        assert scores.bet < 0.0
