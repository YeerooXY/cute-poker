"""Unit tests for poker.bot_ai.board_analyzer module.

Tests the analyze_board and compute_range_advantage functions
for correctness across various board textures.
"""

import pytest

from poker.bot_ai.board_analyzer import analyze_board, compute_range_advantage


class TestAnalyzeBoard:
    """Tests for analyze_board function."""

    def test_monotone_three_suited(self):
        """Board with 3+ cards of same suit is monotone."""
        texture = analyze_board(["AH", "KH", "2H"])
        assert texture.is_monotone is True
        assert texture.flush_possible is True

    def test_monotone_four_suited(self):
        """Board with 4 cards of same suit is monotone."""
        texture = analyze_board(["AH", "KH", "QH", "2H"])
        assert texture.is_monotone is True

    def test_not_monotone_two_suited(self):
        """Board with only 2 of same suit is not monotone."""
        texture = analyze_board(["AH", "KH", "2D"])
        assert texture.is_monotone is False

    def test_paired_board(self):
        """Board with a pair is classified as paired."""
        texture = analyze_board(["AH", "AS", "2D"])
        assert texture.is_paired is True

    def test_trips_on_board(self):
        """Board with three of a kind is also paired."""
        texture = analyze_board(["AH", "AS", "AD"])
        assert texture.is_paired is True

    def test_not_paired(self):
        """Board with all unique ranks is not paired."""
        texture = analyze_board(["AH", "KS", "2D"])
        assert texture.is_paired is False

    def test_connected_three_consecutive(self):
        """Board with 3 consecutive ranks is connected."""
        texture = analyze_board(["7H", "8S", "9D"])
        assert texture.is_connected is True
        assert texture.straight_possible is True

    def test_connected_with_ace_high(self):
        """QKA is connected (3 consecutive ranks)."""
        texture = analyze_board(["QH", "KS", "AD"])
        assert texture.is_connected is True

    def test_connected_with_ace_low(self):
        """A23 is connected via ace-low."""
        texture = analyze_board(["AH", "2S", "3D"])
        assert texture.is_connected is True

    def test_not_connected_gaps(self):
        """Board with gaps between ranks is not connected."""
        texture = analyze_board(["AH", "7S", "2D"])
        assert texture.is_connected is False

    def test_dry_board(self):
        """Dry = not wet, not connected, not monotone."""
        texture = analyze_board(["AH", "7S", "2D"])
        assert texture.is_dry is True
        assert texture.is_wet is False
        assert texture.is_connected is False
        assert texture.is_monotone is False

    def test_wet_board_flush_draw(self):
        """Board with 2+ same suit is wet (flush draw possible)."""
        texture = analyze_board(["AH", "KH", "3D"])
        assert texture.is_wet is True
        assert texture.is_dry is False

    def test_wet_board_straight_draws(self):
        """Board with multiple straight draw combos is wet."""
        # 8, 9, T - many straight windows hit these
        texture = analyze_board(["8H", "9S", "TD"])
        assert texture.is_wet is True

    def test_high_card_rank(self):
        """high_card_rank returns the highest rank value on board."""
        texture = analyze_board(["AH", "KS", "2D"])
        assert texture.high_card_rank == 14  # Ace

        texture = analyze_board(["7H", "8S", "9D"])
        assert texture.high_card_rank == 9

    def test_empty_community(self):
        """Empty community returns default BoardTexture."""
        texture = analyze_board([])
        assert texture.is_dry is False
        assert texture.is_wet is False
        assert texture.is_paired is False
        assert texture.is_monotone is False
        assert texture.is_connected is False
        assert texture.high_card_rank == 0

    def test_five_card_board(self):
        """Full 5-card board still classifies correctly."""
        texture = analyze_board(["AH", "KH", "QH", "JH", "TH"])
        assert texture.is_monotone is True
        assert texture.is_connected is True
        assert texture.flush_possible is True


class TestComputeRangeAdvantage:
    """Tests for compute_range_advantage function."""

    def test_advantage_bounded_high_board(self):
        """Range advantage is in [0.0, 1.0] for high-card boards."""
        ra = compute_range_advantage(["AH", "KS", "QD"], True)
        assert 0.0 <= ra.aggressor_advantage <= 1.0

    def test_advantage_bounded_low_board(self):
        """Range advantage is in [0.0, 1.0] for low-card boards."""
        ra = compute_range_advantage(["3H", "4S", "5D"], True)
        assert 0.0 <= ra.aggressor_advantage <= 1.0

    def test_high_board_favors_aggressor(self):
        """High-card board gives higher aggressor advantage."""
        high_board = compute_range_advantage(["AH", "KS", "QD"], True)
        low_board = compute_range_advantage(["3H", "5S", "7D"], True)
        assert high_board.aggressor_advantage > low_board.aggressor_advantage

    def test_low_connected_board_favors_caller(self):
        """Low connected board should give lower aggressor advantage."""
        ra = compute_range_advantage(["5H", "6S", "7D"], True)
        assert ra.aggressor_advantage < 0.5

    def test_nut_advantage_high_not_connected(self):
        """Nut advantage is True when board is high-card heavy and not connected."""
        ra = compute_range_advantage(["AH", "QS", "TD"], True)
        assert ra.nut_advantage is True

    def test_no_nut_advantage_connected(self):
        """Nut advantage is False when board is connected even if high."""
        ra = compute_range_advantage(["QH", "KS", "AD"], True)
        # QKA is connected, so nut advantage should be False
        assert ra.nut_advantage is False

    def test_no_nut_advantage_low_board(self):
        """Nut advantage is False on low boards."""
        ra = compute_range_advantage(["3H", "5S", "7D"], True)
        assert ra.nut_advantage is False

    def test_empty_community_neutral(self):
        """Empty community returns neutral advantage."""
        ra = compute_range_advantage([], True)
        assert ra.aggressor_advantage == 0.5
        assert ra.nut_advantage is False

    def test_monotone_board_favors_caller(self):
        """Monotone board reduces aggressor advantage."""
        monotone = compute_range_advantage(["2H", "5H", "8H"], True)
        rainbow = compute_range_advantage(["2H", "5S", "8D"], True)
        assert monotone.aggressor_advantage < rainbow.aggressor_advantage

    def test_paired_board_favors_aggressor(self):
        """Paired board slightly increases aggressor advantage."""
        paired = compute_range_advantage(["AH", "AS", "7D"], True)
        unpaired = compute_range_advantage(["AH", "KS", "7D"], True)
        assert paired.aggressor_advantage > unpaired.aggressor_advantage
