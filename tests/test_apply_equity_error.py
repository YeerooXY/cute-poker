"""Unit tests for apply_equity_error in difficulty_controller.py.

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
"""

import math
from unittest.mock import patch

from poker.bot_ai.difficulty_controller import apply_equity_error


class TestApplyEquityError:
    """Tests for the apply_equity_error function."""

    def test_zero_error_returns_true_equity(self):
        """With equity_error_max=0.0, the function returns exactly true_equity."""
        assert apply_equity_error(0.5, 0.0) == 0.5
        assert apply_equity_error(0.0, 0.0) == 0.0
        assert apply_equity_error(1.0, 0.0) == 1.0

    def test_negative_error_max_treated_as_zero(self):
        """Negative equity_error_max is treated as 0.0 (no error applied)."""
        assert apply_equity_error(0.5, -0.1) == 0.5
        assert apply_equity_error(0.75, -1.0) == 0.75

    def test_nan_error_max_treated_as_zero(self):
        """NaN equity_error_max is treated as 0.0 (no error applied)."""
        assert apply_equity_error(0.5, float("nan")) == 0.5
        assert apply_equity_error(0.3, float("nan")) == 0.3

    def test_result_clamped_to_zero(self):
        """Result is clamped to 0.0 when error would push below zero."""
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=-0.15):
            result = apply_equity_error(0.05, 0.15)
            assert result == 0.0

    def test_result_clamped_to_one(self):
        """Result is clamped to 1.0 when error would push above one."""
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.15):
            result = apply_equity_error(0.95, 0.15)
            assert result == 1.0

    def test_positive_error_applied(self):
        """Positive error increases the equity value."""
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.10):
            result = apply_equity_error(0.5, 0.15)
            assert result == 0.6

    def test_negative_error_applied(self):
        """Negative error decreases the equity value."""
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=-0.10):
            result = apply_equity_error(0.5, 0.15)
            assert result == 0.4

    def test_output_always_in_valid_range(self):
        """Output is always in [0.0, 1.0] for many random calls."""
        for _ in range(500):
            result = apply_equity_error(0.01, 0.15)
            assert 0.0 <= result <= 1.0

            result = apply_equity_error(0.99, 0.15)
            assert 0.0 <= result <= 1.0

            result = apply_equity_error(0.5, 0.5)
            assert 0.0 <= result <= 1.0

    def test_uniform_called_with_correct_bounds(self):
        """random.uniform is called with (-equity_error_max, +equity_error_max)."""
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.0) as mock_uniform:
            apply_equity_error(0.5, 0.08)
            mock_uniform.assert_called_once_with(-0.08, 0.08)

    def test_difficulty_level_error_values(self):
        """Each difficulty level's error max produces bounded results."""
        # Easy: 0.15
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.15):
            assert apply_equity_error(0.5, 0.15) == 0.65

        # Medium: 0.08
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.08):
            assert apply_equity_error(0.5, 0.08) == 0.58

        # Hard: 0.04
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.04):
            assert apply_equity_error(0.5, 0.04) == 0.54

        # Expert: 0.02
        with patch("poker.bot_ai.difficulty_controller.random.uniform", return_value=0.02):
            assert apply_equity_error(0.5, 0.02) == 0.52
