"""Unit tests for _sample_hand_from_range in poker/odds.py.

Tests the weighted sampling, blocker filtering, and fallback behavior.
"""

import random

import pytest

from poker.odds import (
    _sample_hand_from_range,
    _hand_class_to_combos,
    FULL_DECK,
)


class TestSampleHandFromRange:
    """Tests for _sample_hand_from_range function."""

    def test_basic_sampling_returns_two_cards(self):
        """A basic combo_range with a single hand class returns a valid 2-card hand."""
        combo_range = {"AA": 1.0}
        known_cards = set()
        result = _sample_hand_from_range(combo_range, known_cards)
        assert len(result) == 2
        # Both cards should be aces
        assert result[0][0] == "A"
        assert result[1][0] == "A"

    def test_sampled_hand_never_contains_known_cards(self):
        """Blocker filtering: returned hand must not contain any known card."""
        combo_range = {"AKs": 1.0, "AQs": 0.5, "KQs": 0.3}
        known_cards = {"AH", "KS", "QD", "TC", "9H"}  # Hero + board
        random.seed(42)

        for _ in range(100):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            assert result[0] not in known_cards
            assert result[1] not in known_cards

    def test_empty_combo_range_falls_back_to_random(self):
        """Empty combo_range triggers fallback to random unseen hand."""
        combo_range = {}
        known_cards = {"AH", "KS"}
        result = _sample_hand_from_range(combo_range, known_cards)
        assert len(result) == 2
        assert result[0] not in known_cards
        assert result[1] not in known_cards

    def test_all_weights_zero_falls_back_to_random(self):
        """All weights == 0 triggers fallback to random unseen hand."""
        combo_range = {"AA": 0.0, "KK": 0.0, "QQ": 0.0}
        known_cards = {"AH", "KS"}
        result = _sample_hand_from_range(combo_range, known_cards)
        assert len(result) == 2
        assert result[0] not in known_cards
        assert result[1] not in known_cards

    def test_all_combos_blocked_falls_back_to_random(self):
        """When all combos in all hand classes are blocked, falls back to random."""
        # AA has only 6 combos. Block all aces so no AA combo is valid.
        combo_range = {"AA": 1.0}
        known_cards = {"AS", "AH", "AD", "AC"}
        result = _sample_hand_from_range(combo_range, known_cards, max_retries=5)
        assert len(result) == 2
        # Should fallback to a random hand from remaining deck
        assert result[0] not in known_cards
        assert result[1] not in known_cards

    def test_weighted_sampling_respects_weights(self):
        """Higher-weight classes are sampled more frequently."""
        # Give AA weight 10x more than 22
        combo_range = {"AA": 10.0, "22": 1.0}
        known_cards = set()
        random.seed(123)

        aa_count = 0
        twos_count = 0
        trials = 1000

        for _ in range(trials):
            result = _sample_hand_from_range(combo_range, known_cards)
            if result[0][0] == "A" and result[1][0] == "A":
                aa_count += 1
            elif result[0][0] == "2" and result[1][0] == "2":
                twos_count += 1

        # AA should be sampled ~10x more often than 22
        # With 10:1 weights, expect ~909 AA and ~91 22
        assert aa_count > twos_count * 3, (
            f"Expected AA sampled much more than 22: AA={aa_count}, 22={twos_count}"
        )

    def test_blocker_filtering_removes_specific_combos(self):
        """Blocker filtering should only remove combos containing known cards,
        not the entire hand class."""
        # AKs has 4 combos (one per suit). Block AS so only 3 suited combos remain.
        combo_range = {"AKs": 1.0}
        known_cards = {"AS"}
        random.seed(42)

        for _ in range(50):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            assert "AS" not in result
            # Should still get valid AKs combos (AH+KH, AD+KD, AC+KC)
            assert result[0][0] == "A" or result[0][0] == "K"

    def test_retry_on_blocked_class_picks_different_class(self):
        """When one class is fully blocked, retry should sample from another class."""
        # AA fully blocked, KK available
        combo_range = {"AA": 1.0, "KK": 1.0}
        known_cards = {"AS", "AH", "AD", "AC"}  # All aces blocked

        for _ in range(20):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            # Must be KK since AA is fully blocked
            assert result[0][0] == "K" and result[1][0] == "K"

    def test_result_cards_are_from_full_deck(self):
        """Returned cards should be valid cards from the standard deck."""
        combo_range = {"AKs": 0.5, "QJs": 0.3, "TT": 0.8}
        known_cards = {"AH", "KS"}

        for _ in range(50):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            assert result[0] in FULL_DECK
            assert result[1] in FULL_DECK

    def test_result_cards_are_distinct(self):
        """The two returned cards should always be different."""
        combo_range = {"AKo": 1.0, "QJs": 0.5, "TT": 0.3}
        known_cards = set()
        random.seed(7)

        for _ in range(100):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            assert result[0] != result[1]

    def test_fallback_with_very_few_remaining_cards(self):
        """When nearly all cards are known, fallback still works."""
        combo_range = {"AA": 1.0}
        # Block 50 cards, leaving only 2
        known_cards = set(FULL_DECK[:50])
        remaining = [c for c in FULL_DECK if c not in known_cards]

        result = _sample_hand_from_range(combo_range, known_cards, max_retries=3)
        assert len(result) == 2
        assert result[0] not in known_cards
        assert result[1] not in known_cards

    def test_single_hand_class_with_partial_blocking(self):
        """A single hand class with some combos blocked should still work."""
        # 72o has 12 combos. Block some 7s.
        combo_range = {"72o": 1.0}
        known_cards = {"7S", "7H"}

        for _ in range(30):
            result = _sample_hand_from_range(combo_range, known_cards)
            assert len(result) == 2
            assert result[0] not in known_cards
            assert result[1] not in known_cards
