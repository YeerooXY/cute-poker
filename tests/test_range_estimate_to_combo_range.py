"""Unit tests for _range_estimate_to_combo_range function.

Verifies that a 6-category RangeEstimate is correctly converted into a 169
hand-class combo_range dict.
"""

from poker.bot_ai.models import RangeEstimate
from poker.odds import (
    _range_estimate_to_combo_range,
    CATEGORY_TO_HAND_CLASSES,
    HAND_CLASSES_169,
)


class TestRangeEstimateToComboRange:
    """Tests for _range_estimate_to_combo_range."""

    def test_returns_169_entries(self):
        """Combo range should have exactly 169 entries."""
        re = RangeEstimate(premium=0.9, strong=0.7, playable=0.5,
                           marginal=0.3, speculative=0.2, trash=0.1)
        combo_range = _range_estimate_to_combo_range(re)
        assert len(combo_range) == 169

    def test_all_hand_classes_present(self):
        """Every hand class from HAND_CLASSES_169 should be in the result."""
        re = RangeEstimate()
        combo_range = _range_estimate_to_combo_range(re)
        for hc in HAND_CLASSES_169:
            assert hc in combo_range, f"Missing hand class: {hc}"

    def test_premium_hands_get_premium_weight(self):
        """Premium hand classes should receive the premium weight."""
        re = RangeEstimate(premium=0.85, strong=0.5, playable=0.3,
                           marginal=0.2, speculative=0.1, trash=0.05)
        combo_range = _range_estimate_to_combo_range(re)
        for hc in CATEGORY_TO_HAND_CLASSES["premium"]:
            assert combo_range[hc] == 0.85, f"{hc} should have weight 0.85"

    def test_trash_hands_get_trash_weight(self):
        """Trash hand classes should receive the trash weight."""
        re = RangeEstimate(premium=1.0, strong=0.8, playable=0.6,
                           marginal=0.4, speculative=0.3, trash=0.05)
        combo_range = _range_estimate_to_combo_range(re)
        for hc in CATEGORY_TO_HAND_CLASSES["trash"]:
            assert combo_range[hc] == 0.05, f"{hc} should have weight 0.05"

    def test_each_category_mapped_correctly(self):
        """Each category's hand classes should receive exactly that category's weight."""
        re = RangeEstimate(premium=0.9, strong=0.7, playable=0.5,
                           marginal=0.3, speculative=0.2, trash=0.1)
        combo_range = _range_estimate_to_combo_range(re)

        expected = {
            "premium": 0.9,
            "strong": 0.7,
            "playable": 0.5,
            "marginal": 0.3,
            "speculative": 0.2,
            "trash": 0.1,
        }
        for category, expected_weight in expected.items():
            for hc in CATEGORY_TO_HAND_CLASSES[category]:
                assert combo_range[hc] == expected_weight, (
                    f"{hc} (category={category}) should be {expected_weight}, got {combo_range[hc]}"
                )

    def test_all_zeros_range_estimate(self):
        """All-zero RangeEstimate should produce all-zero weights."""
        re = RangeEstimate(premium=0.0, strong=0.0, playable=0.0,
                           marginal=0.0, speculative=0.0, trash=0.0)
        combo_range = _range_estimate_to_combo_range(re)
        assert all(v == 0.0 for v in combo_range.values())

    def test_default_range_estimate_all_ones(self):
        """Default RangeEstimate (all 1.0) should produce all-1.0 weights."""
        re = RangeEstimate()  # defaults to all 1.0
        combo_range = _range_estimate_to_combo_range(re)
        assert all(v == 1.0 for v in combo_range.values())

    def test_no_extra_keys(self):
        """Result should not contain keys outside of HAND_CLASSES_169."""
        re = RangeEstimate(premium=0.5, strong=0.5, playable=0.5,
                           marginal=0.5, speculative=0.5, trash=0.5)
        combo_range = _range_estimate_to_combo_range(re)
        hand_class_set = set(HAND_CLASSES_169)
        for key in combo_range:
            assert key in hand_class_set, f"Unexpected key in combo_range: {key}"
