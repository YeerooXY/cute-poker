"""Unit tests for sanity gates (Patch 1).

Tests each gate function with specific example scenarios, validate_selection
fallback behavior, gate logging on activation, and edge cases.

Validates: Requirements 2.6, 2.7, 3.3, 4.1, 4.2, 5.1, 5.2, 6.1-6.4, 7.1-7.5
"""

import logging

import pytest

from poker.bot_ai.models import ActionScores, BoardTexture
from poker.bot_ai.sanity_gates import (
    HAND_CLASS_ORDER,
    PREMIUM_HANDS,
    TOP_5_PERCENT_HANDS,
    GateContext,
    _get_hand_representation,
    apply_allin_gate,
    apply_postflop_gate,
    apply_preflop_gate,
    apply_raise_ladder_gate,
    apply_sanity_gates,
    validate_selection,
)


def _make_ctx(**overrides) -> GateContext:
    """Build a GateContext with sensible defaults, allowing field overrides."""
    defaults = dict(
        hole_cards=["Ah", "Kd"],
        hand_percentile=0.02,
        is_premium=True,
        effective_stack_bb=100.0,
        facing_action="raise",
        phase="flop",
        hand_class="top_pair",
        board_texture=BoardTexture(is_dry=False, is_wet=False),
        equity=0.55,
        pot_odds=0.25,
        pot=100,
        spr=4.0,
        has_strong_draw=False,
        remaining_stack=400,
        would_be_all_in=False,
        raises_faced_this_street=0,
        legal_actions=["fold", "check", "call", "bet", "raise"],
    )
    defaults.update(overrides)
    return GateContext(**defaults)


# =============================================================================
# TestPreflopGate
# =============================================================================


class TestPreflopGate:
    """Tests for apply_preflop_gate."""

    def test_premium_protection_triggers(self):
        """Premium hand facing single raise at 50BB+ gets fold blocked and raise boosted."""
        ctx = _make_ctx(
            phase="preflop",
            is_premium=True,
            hole_cards=["Ah", "Kd"],
            facing_action="raise",
            effective_stack_bb=80.0,
            pot=50,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.5, check=0.0, call=0.4, bet=0.0, raise_=0.6)
        result = apply_preflop_gate(scores, ctx)
        assert result.fold == -1e9
        assert result.raise_ == pytest.approx(0.6 + 0.3 * 50)

    def test_deep_stack_blocks_allin_for_non_top5(self):
        """Non-top-5% hand at 100BB+ with would_be_all_in gets raise blocked."""
        ctx = _make_ctx(
            phase="preflop",
            is_premium=False,
            hole_cards=["9h", "8h"],  # 98s is not top 5%
            hand_percentile=0.40,
            facing_action="raise",
            effective_stack_bb=120.0,
            would_be_all_in=True,
        )
        scores = ActionScores(fold=0.2, check=0.0, call=0.4, bet=0.0, raise_=0.8)
        result = apply_preflop_gate(scores, ctx)
        assert result.raise_ == -1e9

    def test_deep_stack_allows_top5_allin(self):
        """Top 5% hand (AA) at 100BB+ with would_be_all_in is NOT blocked."""
        ctx = _make_ctx(
            phase="preflop",
            is_premium=True,
            hole_cards=["Ah", "As"],  # AA is top 5%
            hand_percentile=0.005,
            facing_action="raise",
            effective_stack_bb=120.0,
            would_be_all_in=True,
            pot=60,
        )
        scores = ActionScores(fold=0.2, check=0.0, call=0.4, bet=0.0, raise_=0.8)
        result = apply_preflop_gate(scores, ctx)
        # Premium protection fires (fold blocked, raise boosted) but all-in NOT blocked
        assert result.fold == -1e9
        assert result.raise_ != -1e9

    def test_gate_skips_when_not_preflop(self):
        """Preflop gate does nothing when phase is flop."""
        ctx = _make_ctx(
            phase="flop",
            is_premium=True,
            facing_action="raise",
            effective_stack_bb=100.0,
        )
        scores = ActionScores(fold=0.5, check=0.1, call=0.3, bet=0.2, raise_=0.7)
        result = apply_preflop_gate(scores, ctx)
        assert result.fold == 0.5
        assert result.raise_ == 0.7

    def test_empty_hole_cards_skips_deep_stack_block(self):
        """Empty hole_cards means _get_hand_representation returns '', which is not in TOP_5_PERCENT_HANDS. But the gate handles gracefully."""
        ctx = _make_ctx(
            phase="preflop",
            is_premium=False,
            hole_cards=[],
            hand_percentile=0.50,
            facing_action="raise",
            effective_stack_bb=120.0,
            would_be_all_in=True,
        )
        scores = ActionScores(fold=0.2, check=0.0, call=0.4, bet=0.0, raise_=0.8)
        # Should not crash; _get_hand_representation returns "" for empty cards
        result = apply_preflop_gate(scores, ctx)
        # "" not in TOP_5_PERCENT_HANDS, so deep-stack gate fires only if
        # effective_stack_bb >= 100 and would_be_all_in. But we must confirm no crash.
        # The gate should still block since "" is not in TOP_5_PERCENT_HANDS.
        assert result.raise_ == -1e9


# =============================================================================
# TestPostflopGate
# =============================================================================


class TestPostflopGate:
    """Tests for apply_postflop_gate."""

    def test_dry_board_bottom_pair_blocks_raise(self):
        """Dry board + bottom pair → raise = -1e9."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="bottom_pair",
            board_texture=BoardTexture(is_dry=True),
            equity=0.30,
            pot_odds=0.25,
            pot=100,
        )
        scores = ActionScores(fold=0.3, check=0.2, call=0.4, bet=0.1, raise_=0.6)
        result = apply_postflop_gate(scores, ctx)
        assert result.raise_ == -1e9

    def test_dry_board_trash_blocks_raise(self):
        """Dry board + trash → raise = -1e9."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="trash",
            board_texture=BoardTexture(is_dry=True),
            equity=0.15,
            pot_odds=0.30,
            pot=80,
        )
        scores = ActionScores(fold=0.4, check=0.2, call=0.1, bet=0.0, raise_=0.5)
        result = apply_postflop_gate(scores, ctx)
        assert result.raise_ == -1e9

    def test_dry_board_middle_pair_low_equity_penalizes_raise(self):
        """Dry board + middle pair + equity < 40% → raise penalty."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="middle_pair",
            board_texture=BoardTexture(is_dry=True),
            equity=0.35,
            pot_odds=0.30,
            pot=200,
        )
        scores = ActionScores(fold=0.3, check=0.2, call=0.4, bet=0.1, raise_=1.0)
        result = apply_postflop_gate(scores, ctx)
        expected_raise = 1.0 - 0.2 * 200
        assert result.raise_ == pytest.approx(expected_raise)

    def test_pot_odds_protection_top_pair(self):
        """Equity > pot_odds + 5% AND top pair+ → fold = -1e9, call += bonus."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="top_pair",
            board_texture=BoardTexture(is_dry=False),
            equity=0.55,
            pot_odds=0.25,
            pot=100,
        )
        scores = ActionScores(fold=0.5, check=0.2, call=0.3, bet=0.1, raise_=0.4)
        result = apply_postflop_gate(scores, ctx)
        assert result.fold == -1e9
        assert result.call == pytest.approx(0.3 + 0.15 * 100)

    def test_pot_odds_strong_protection_any_hand(self):
        """Equity > pot_odds + 10% with any hand → fold = -1e9."""
        ctx = _make_ctx(
            phase="turn",
            hand_class="bottom_pair",
            board_texture=BoardTexture(is_dry=False),
            equity=0.50,
            pot_odds=0.35,
            pot=100,
        )
        scores = ActionScores(fold=0.6, check=0.1, call=0.3, bet=0.0, raise_=0.2)
        result = apply_postflop_gate(scores, ctx)
        assert result.fold == -1e9

    def test_gate_skips_on_preflop(self):
        """Postflop gate does nothing when phase is preflop."""
        ctx = _make_ctx(
            phase="preflop",
            hand_class="trash",
            board_texture=BoardTexture(is_dry=True),
            equity=0.50,
            pot_odds=0.10,
        )
        scores = ActionScores(fold=0.5, check=0.2, call=0.3, bet=0.1, raise_=0.6)
        result = apply_postflop_gate(scores, ctx)
        assert result.fold == 0.5
        assert result.raise_ == 0.6


# =============================================================================
# TestAllinGate
# =============================================================================


class TestAllinGate:
    """Tests for apply_allin_gate."""

    def test_spr_gt_3_blocks_one_pair_allin(self):
        """SPR > 3 + one pair + no strong draw + would_be_all_in → raise = -1e9."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="top_pair",
            spr=4.5,
            has_strong_draw=False,
            would_be_all_in=True,
            equity=0.50,
        )
        scores = ActionScores(fold=0.2, check=0.1, call=0.4, bet=0.1, raise_=0.9)
        result = apply_allin_gate(scores, ctx)
        assert result.raise_ == -1e9

    def test_spr_gt_6_blocks_below_two_pair(self):
        """SPR > 6 + below two pair + equity <= 70% + would_be_all_in → raise = -1e9."""
        ctx = _make_ctx(
            phase="turn",
            hand_class="overpair",  # rank 4, below two_pair (rank 5)
            spr=7.0,
            has_strong_draw=False,
            would_be_all_in=True,
            equity=0.60,
        )
        scores = ActionScores(fold=0.1, check=0.1, call=0.5, bet=0.2, raise_=1.0)
        result = apply_allin_gate(scores, ctx)
        assert result.raise_ == -1e9

    def test_spr_gt_6_allows_high_equity(self):
        """SPR > 6 + below two pair BUT equity > 70% → NOT blocked."""
        ctx = _make_ctx(
            phase="turn",
            hand_class="overpair",
            spr=7.0,
            has_strong_draw=False,
            would_be_all_in=True,
            equity=0.75,
        )
        scores = ActionScores(fold=0.1, check=0.1, call=0.5, bet=0.2, raise_=1.0)
        result = apply_allin_gate(scores, ctx)
        # SPR > 3 + one pair (rank 4 <= 3 is False for overpair rank 4... wait)
        # overpair is rank 4, and the SPR > 3 check requires hand_rank <= 3
        # so SPR > 3 gate does NOT fire for overpair, and SPR > 6 doesn't fire
        # because equity > 0.70. So raise is preserved.
        assert result.raise_ == 1.0

    def test_spr_lte_1_5_bonus(self):
        """SPR <= 1.5 + top pair + would_be_all_in → raise gets bonus."""
        ctx = _make_ctx(
            phase="river",
            hand_class="top_pair",
            spr=1.2,
            has_strong_draw=False,
            would_be_all_in=True,
            pot=200,
            equity=0.65,
        )
        scores = ActionScores(fold=0.1, check=0.0, call=0.3, bet=0.2, raise_=0.8)
        result = apply_allin_gate(scores, ctx)
        assert result.raise_ == pytest.approx(0.8 + 0.2 * 200)

    def test_spr_lte_1_5_bonus_with_strong_draw(self):
        """SPR <= 1.5 + strong draw + would_be_all_in → raise gets bonus."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="bottom_pair",
            spr=1.0,
            has_strong_draw=True,
            would_be_all_in=True,
            pot=150,
            equity=0.40,
        )
        scores = ActionScores(fold=0.3, check=0.1, call=0.4, bet=0.1, raise_=0.5)
        result = apply_allin_gate(scores, ctx)
        # SPR > 3 check: spr=1.0 is NOT > 3, so no block from first rule.
        # SPR <= 1.5 + strong draw → bonus
        assert result.raise_ == pytest.approx(0.5 + 0.2 * 150)

    def test_gate_skips_when_not_allin(self):
        """Gate does nothing when would_be_all_in is False."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="trash",
            spr=0.5,
            has_strong_draw=False,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.3, check=0.2, call=0.4, bet=0.1, raise_=0.7)
        result = apply_allin_gate(scores, ctx)
        assert result.raise_ == 0.7


# =============================================================================
# TestRaiseLadderGate
# =============================================================================


class TestRaiseLadderGate:
    """Tests for apply_raise_ladder_gate."""

    def test_2_raises_low_equity_blocks_raise(self):
        """2+ raises + equity < 45% → raise blocked (set to -1e9 or below).
        
        Note: The penalty rule (hand < two_pair + no draw) may also fire,
        subtracting further from the already-forbidden score.
        """
        ctx = _make_ctx(
            raises_faced_this_street=2,
            equity=0.40,
            hand_class="top_pair",
            spr=3.0,
            pot=100,
            has_strong_draw=False,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.3, check=0.1, call=0.4, bet=0.1, raise_=0.8)
        result = apply_raise_ladder_gate(scores, ctx)
        assert result.raise_ <= -1e9

    def test_3_raises_blocks_raise_and_penalizes_call(self):
        """3+ raises + equity < 60% → raise = -1e9, call -= 0.15 × pot."""
        ctx = _make_ctx(
            raises_faced_this_street=3,
            equity=0.50,
            hand_class="middle_pair",
            spr=3.0,
            pot=200,
            has_strong_draw=False,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.2, check=0.1, call=0.6, bet=0.0, raise_=0.9)
        result = apply_raise_ladder_gate(scores, ctx)
        assert result.raise_ == -1e9
        assert result.call == pytest.approx(0.6 - 0.15 * 200)

    def test_2_raises_below_two_pair_no_draw_penalizes(self):
        """2+ raises + hand < two pair + no strong draw → raise -= 0.25 × pot."""
        ctx = _make_ctx(
            raises_faced_this_street=2,
            equity=0.50,  # above 45%, so first rule doesn't fire
            hand_class="top_pair",  # rank 3, below two_pair (5)
            spr=1.5,  # SPR <= 2.0 so all-in block doesn't fire
            pot=100,
            has_strong_draw=False,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.2, check=0.1, call=0.5, bet=0.1, raise_=1.0)
        result = apply_raise_ladder_gate(scores, ctx)
        # Penalty applied: raise -= 0.25 * 100 = 25
        assert result.raise_ == pytest.approx(1.0 - 0.25 * 100)

    def test_2_raises_one_pair_high_spr_allin_blocks(self):
        """2+ raises + one pair (rank <= 3) + SPR > 2.0 + would_be_all_in → raise blocked.
        
        Note: The penalty rule (hand < two_pair + no draw) may also fire,
        subtracting further from the already-forbidden score.
        """
        ctx = _make_ctx(
            raises_faced_this_street=2,
            equity=0.50,  # above 45%
            hand_class="middle_pair",  # rank 2, <= 3
            spr=3.0,
            pot=100,
            has_strong_draw=False,
            would_be_all_in=True,
        )
        scores = ActionScores(fold=0.2, check=0.1, call=0.5, bet=0.1, raise_=1.0)
        result = apply_raise_ladder_gate(scores, ctx)
        assert result.raise_ <= -1e9

    def test_gate_skips_with_fewer_than_2_raises(self):
        """Gate does nothing with < 2 raises faced."""
        ctx = _make_ctx(
            raises_faced_this_street=1,
            equity=0.20,
            hand_class="trash",
            pot=100,
        )
        scores = ActionScores(fold=0.4, check=0.1, call=0.2, bet=0.0, raise_=0.8)
        result = apply_raise_ladder_gate(scores, ctx)
        assert result.raise_ == 0.8
        assert result.call == 0.2


# =============================================================================
# TestValidateSelection
# =============================================================================


class TestValidateSelection:
    """Tests for validate_selection."""

    def test_non_forbidden_action_passes_through(self):
        """Selected action with score > -1e9 passes through unchanged."""
        scores = ActionScores(fold=0.3, check=0.1, call=0.5, bet=0.2, raise_=0.7)
        legal = ["fold", "call", "raise"]
        result = validate_selection("raise", scores, legal)
        assert result == "raise"

    def test_forbidden_action_falls_back_to_best_legal(self):
        """Forbidden action (score = -1e9) falls back to highest non-forbidden legal action."""
        scores = ActionScores(fold=0.3, check=0.1, call=0.5, bet=0.2, raise_=-1e9)
        legal = ["fold", "call", "raise"]
        result = validate_selection("raise", scores, legal)
        assert result == "call"

    def test_all_forbidden_gives_check(self):
        """All actions forbidden → returns check if in legal_actions."""
        scores = ActionScores(fold=-1e9, check=-1e9, call=-1e9, bet=-1e9, raise_=-1e9)
        legal = ["fold", "check", "call", "raise"]
        result = validate_selection("raise", scores, legal)
        assert result == "check"

    def test_all_forbidden_gives_call_when_no_check(self):
        """All forbidden + no check → returns call."""
        scores = ActionScores(fold=-1e9, check=-1e9, call=-1e9, bet=-1e9, raise_=-1e9)
        legal = ["fold", "call", "raise"]
        result = validate_selection("raise", scores, legal)
        assert result == "call"

    def test_all_forbidden_gives_fold_when_only_option(self):
        """All forbidden + only fold available → returns fold."""
        scores = ActionScores(fold=-1e9, check=-1e9, call=-1e9, bet=-1e9, raise_=-1e9)
        legal = ["fold"]
        result = validate_selection("fold", scores, legal)
        assert result == "fold"

    def test_forbidden_fold_falls_back(self):
        """Forbidden fold falls back to next best legal action."""
        scores = ActionScores(fold=-1e9, check=0.2, call=0.6, bet=0.1, raise_=0.3)
        legal = ["fold", "check", "call", "raise"]
        result = validate_selection("fold", scores, legal)
        assert result == "call"


# =============================================================================
# TestGateLogging
# =============================================================================


class TestGateLogging:
    """Verify log messages are emitted when gates activate."""

    def test_preflop_premium_gate_logs(self, caplog):
        """Preflop premium protection logs on activation."""
        ctx = _make_ctx(
            phase="preflop",
            is_premium=True,
            hole_cards=["Ah", "Kd"],
            facing_action="raise",
            effective_stack_bb=80.0,
            pot=50,
            would_be_all_in=False,
        )
        scores = ActionScores(fold=0.5, check=0.0, call=0.4, bet=0.0, raise_=0.6)
        with caplog.at_level(logging.INFO, logger="poker.bot_ai.sanity_gates"):
            apply_preflop_gate(scores, ctx)
        assert any("Preflop premium gate" in msg for msg in caplog.messages)

    def test_postflop_dry_board_gate_logs(self, caplog):
        """Postflop dry board gate logs when raise is blocked."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="bottom_pair",
            board_texture=BoardTexture(is_dry=True),
            equity=0.30,
            pot_odds=0.25,
            pot=100,
        )
        scores = ActionScores(fold=0.3, check=0.2, call=0.4, bet=0.1, raise_=0.6)
        with caplog.at_level(logging.INFO, logger="poker.bot_ai.sanity_gates"):
            apply_postflop_gate(scores, ctx)
        assert any("Postflop dry board gate" in msg for msg in caplog.messages)

    def test_allin_gate_logs_on_block(self, caplog):
        """All-in gate logs when blocking all-in."""
        ctx = _make_ctx(
            phase="flop",
            hand_class="top_pair",
            spr=4.5,
            has_strong_draw=False,
            would_be_all_in=True,
            equity=0.50,
        )
        scores = ActionScores(fold=0.2, check=0.1, call=0.4, bet=0.1, raise_=0.9)
        with caplog.at_level(logging.INFO, logger="poker.bot_ai.sanity_gates"):
            apply_allin_gate(scores, ctx)
        assert any("All-in gate" in msg for msg in caplog.messages)

    def test_raise_ladder_gate_logs(self, caplog):
        """Raise-ladder gate logs when raise is blocked."""
        ctx = _make_ctx(
            raises_faced_this_street=2,
            equity=0.40,
            hand_class="top_pair",
            pot=100,
            has_strong_draw=False,
        )
        scores = ActionScores(fold=0.3, check=0.1, call=0.4, bet=0.1, raise_=0.8)
        with caplog.at_level(logging.INFO, logger="poker.bot_ai.sanity_gates"):
            apply_raise_ladder_gate(scores, ctx)
        assert any("Raise-ladder gate" in msg for msg in caplog.messages)


# =============================================================================
# TestHandRepresentation
# =============================================================================


class TestHandRepresentation:
    """Tests for _get_hand_representation."""

    def test_suited_hand(self):
        """Suited hand converts correctly (e.g., Ah Kh → AKs)."""
        assert _get_hand_representation(["Ah", "Kh"]) == "AKs"

    def test_offsuit_hand(self):
        """Offsuit hand converts correctly (e.g., Ah Kd → AKo)."""
        assert _get_hand_representation(["Ah", "Kd"]) == "AKo"

    def test_pair(self):
        """Pair converts correctly (e.g., Ah As → AA)."""
        assert _get_hand_representation(["Ah", "As"]) == "AA"

    def test_lower_rank_first_reorders(self):
        """Cards are reordered so higher rank comes first."""
        assert _get_hand_representation(["5h", "As"]) == "A5o"

    def test_empty_list_returns_empty(self):
        """Empty list returns empty string."""
        assert _get_hand_representation([]) == ""

    def test_single_card_returns_empty(self):
        """Single card returns empty string."""
        assert _get_hand_representation(["Ah"]) == ""

    def test_invalid_rank_returns_empty(self):
        """Invalid rank character returns empty string."""
        assert _get_hand_representation(["Xh", "Ks"]) == ""

    def test_short_card_string_returns_empty(self):
        """Card string too short returns empty string."""
        assert _get_hand_representation(["A", "K"]) == ""

    def test_suited_low_cards(self):
        """Low suited cards convert correctly."""
        assert _get_hand_representation(["2h", "3h"]) == "32s"

    def test_ten_representation(self):
        """Ten (T) is handled correctly."""
        assert _get_hand_representation(["Th", "9d"]) == "T9o"
