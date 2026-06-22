"""Unit tests for _normalize_weights function in odds.py.

Validates Requirement 8.4: Category weights must be normalized to sum to 1.0
before sampling.
"""

import math

from poker.odds import _normalize_weights


class TestNormalizeWeights:
    """Tests for _normalize_weights."""

    def test_already_normalized_weights_unchanged(self):
        """Weights that already sum to 1.0 should remain the same."""
        combo_range = {"AA": 0.5, "KK": 0.3, "QQ": 0.2}
        result = _normalize_weights(combo_range)
        assert math.isclose(result["AA"], 0.5, abs_tol=1e-9)
        assert math.isclose(result["KK"], 0.3, abs_tol=1e-9)
        assert math.isclose(result["QQ"], 0.2, abs_tol=1e-9)

    def test_unnormalized_weights_sum_to_one(self):
        """Unnormalized weights should be scaled to sum to 1.0."""
        combo_range = {"AA": 2.0, "KK": 3.0, "QQ": 5.0}
        result = _normalize_weights(combo_range)
        total = sum(result.values())
        assert math.isclose(total, 1.0, abs_tol=1e-9)
        assert math.isclose(result["AA"], 0.2, abs_tol=1e-9)
        assert math.isclose(result["KK"], 0.3, abs_tol=1e-9)
        assert math.isclose(result["QQ"], 0.5, abs_tol=1e-9)

    def test_all_zeros_returns_uniform(self):
        """All-zero weights should produce a uniform distribution."""
        combo_range = {"AA": 0.0, "KK": 0.0, "QQ": 0.0}
        result = _normalize_weights(combo_range)
        expected = 1.0 / 3.0
        for v in result.values():
            assert math.isclose(v, expected, abs_tol=1e-9)

    def test_empty_dict_returns_empty(self):
        """Empty combo_range should return empty dict."""
        result = _normalize_weights({})
        assert result == {}

    def test_single_entry(self):
        """Single entry should be normalized to 1.0."""
        combo_range = {"AA": 7.5}
        result = _normalize_weights(combo_range)
        assert math.isclose(result["AA"], 1.0, abs_tol=1e-9)

    def test_preserves_relative_proportions(self):
        """Relative proportions between weights should be preserved."""
        combo_range = {"AA": 4.0, "KK": 2.0, "QQ": 1.0}
        result = _normalize_weights(combo_range)
        # AA should be 2x KK and 4x QQ
        assert math.isclose(result["AA"] / result["KK"], 2.0, abs_tol=1e-9)
        assert math.isclose(result["AA"] / result["QQ"], 4.0, abs_tol=1e-9)

    def test_very_small_weights_normalized(self):
        """Very small but non-zero weights should still normalize."""
        combo_range = {"AA": 0.001, "KK": 0.002, "QQ": 0.003}
        result = _normalize_weights(combo_range)
        total = sum(result.values())
        assert math.isclose(total, 1.0, abs_tol=1e-9)

    def test_mixed_zero_and_nonzero(self):
        """Mix of zero and non-zero weights: zeros stay zero, rest normalizes."""
        combo_range = {"AA": 0.0, "KK": 3.0, "QQ": 7.0}
        result = _normalize_weights(combo_range)
        assert math.isclose(result["AA"], 0.0, abs_tol=1e-9)
        assert math.isclose(result["KK"], 0.3, abs_tol=1e-9)
        assert math.isclose(result["QQ"], 0.7, abs_tol=1e-9)
