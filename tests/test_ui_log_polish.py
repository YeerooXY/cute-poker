"""Regression tests for UI/log polish: all-in call wording and showdown display.

Tests:
1. All-in call wording: "calls X and is all-in" when amount > 0, "is all-in" when amount = 0
2. formatWinnerEntry uses hand_detail for richer descriptions
3. describe_hand produces correct kicker explanations
4. Flush-over-flush showdown explanation shows deciding kicker
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.evaluator import evaluate_7, evaluate_5, describe_hand


# ═══════════════════════════════════════════════════════════════
# describe_hand - Kicker explanation tests
# ═══════════════════════════════════════════════════════════════


class TestDescribeHand:
    """Test that describe_hand produces correct human-readable descriptions."""

    def test_flush_ace_high(self):
        score = (5, [14, 12, 10, 7, 3])
        result = describe_hand(score, "Flush")
        assert result == "Flush, Ace-high"

    def test_flush_king_high(self):
        score = (5, [13, 11, 9, 6, 2])
        result = describe_hand(score, "Flush")
        assert result == "Flush, King-high"

    def test_two_pair_kings_and_tens_ace_kicker(self):
        score = (2, [13, 10, 14])
        result = describe_hand(score, "Two pair")
        assert result == "Two pair, Kings and Tens, Ace kicker"

    def test_one_pair_aces_king_kicker(self):
        score = (1, [14, 13, 12, 10])
        result = describe_hand(score, "One pair")
        assert result == "One pair, Aces, King kicker"

    def test_full_house_queens_full_of_sevens(self):
        score = (6, [12, 7])
        result = describe_hand(score, "Full house")
        assert result == "Full house, Queens full of Sevens"

    def test_straight_king_high(self):
        score = (4, [13])
        result = describe_hand(score, "Straight")
        assert result == "Straight, King-high"

    def test_three_of_a_kind_jacks(self):
        score = (3, [11, 9, 5])
        result = describe_hand(score, "Three of a kind")
        assert result == "Three of a kind, Jacks"

    def test_four_of_a_kind_aces(self):
        score = (7, [14, 13])
        result = describe_hand(score, "Four of a kind")
        assert result == "Four of a kind, Aces, King kicker"

    def test_high_card_ace(self):
        score = (0, [14, 12, 10, 8, 5])
        result = describe_hand(score, "High card")
        assert result == "High card, Ace"

    def test_royal_flush(self):
        score = (8, [14])
        result = describe_hand(score, "Royal flush")
        assert result == "Royal flush"

    def test_straight_flush(self):
        score = (8, [10])
        result = describe_hand(score, "Straight flush")
        assert result == "Straight flush"


# ═══════════════════════════════════════════════════════════════
# Flush-over-flush showdown explanation
# ═══════════════════════════════════════════════════════════════


class TestFlushOverFlush:
    """Test that when both players have a flush, the deciding kicker is visible."""

    def test_flush_vs_flush_different_high_cards(self):
        """Ace-high flush beats King-high flush, descriptions show the difference."""
        # Ace-high flush
        cards1 = ["A♠", "J♠", "8♠", "5♠", "3♠", "K♥", "2♦"]
        score1, name1, best1 = evaluate_7(cards1)
        detail1 = describe_hand(score1, name1)

        # King-high flush
        cards2 = ["K♠", "Q♠", "9♠", "6♠", "4♠", "A♥", "2♦"]
        score2, name2, best2 = evaluate_7(cards2)
        detail2 = describe_hand(score2, name2)

        assert name1 == "Flush"
        assert name2 == "Flush"
        assert "Ace-high" in detail1
        assert "King-high" in detail2
        # Score comparison confirms winner
        assert score1 > score2

    def test_flush_vs_flush_same_high_different_second(self):
        """Both Ace-high flushes — descriptions show the same top but kickers differ."""
        # Ace-high flush with King second
        cards1 = ["A♠", "K♠", "8♠", "5♠", "3♠", "2♥", "4♦"]
        score1, name1, best1 = evaluate_7(cards1)
        detail1 = describe_hand(score1, name1)

        # Ace-high flush with Queen second
        cards2 = ["A♠", "Q♠", "9♠", "6♠", "4♠", "2♥", "3♦"]
        score2, name2, best2 = evaluate_7(cards2)
        detail2 = describe_hand(score2, name2)

        assert name1 == "Flush"
        assert name2 == "Flush"
        # Both show "Ace-high" but the score comparison is what decides
        assert "Ace-high" in detail1
        assert "Ace-high" in detail2
        assert score1 > score2  # K > Q as second kicker


# ═══════════════════════════════════════════════════════════════
# All-in call wording (frontend logic, tested via simulation)
# ═══════════════════════════════════════════════════════════════


class TestAllInCallWording:
    """Test the expected frontend wording for all-in call actions.

    The formatActionEntry logic:
    - is_all_in=true, action=check_call, amount > 0 → "calls X and is all-in"
    - is_all_in=true, action=check_call, amount = 0 → "is all-in"
    - is_all_in=false, action=check_call, amount > 0 → "calls X"
    """

    def _format(self, entry):
        """Python simulation of the fixed formatActionEntry logic."""
        player = entry.get("player", "")
        amount = entry.get("amount", 0)

        if entry.get("action") == "small_blind":
            return f"{player} posts SB {amount}"
        if entry.get("action") == "big_blind":
            return f"{player} posts BB {amount}"

        if entry.get("is_all_in"):
            if entry.get("action") == "fold":
                return f"{player} folds"
            if entry.get("action") == "check_call":
                if amount > 0:
                    return f"{player} calls {amount} and is all-in"
                return f"{player} is all-in"
            if entry.get("action") == "bet_raise":
                if entry.get("_isFirstBetOnStreet"):
                    return f"{player} goes all-in for {amount}"
                return f"{player} raises all-in to {amount}"
            return f"{player} is all-in"

        action = entry.get("action")
        if action == "fold":
            return f"{player} folds"
        if action == "check_call":
            return f"{player} calls {amount}" if amount > 0 else f"{player} checks"
        if action == "bet_raise":
            if entry.get("_isFirstBetOnStreet"):
                return f"{player} bets {amount}"
            return f"{player} raises to {amount}"
        return f"{player} acts"

    def test_call_all_in_with_amount(self):
        """Player calls and goes all-in (stack depleted)."""
        entry = {"player": "Alice", "action": "check_call", "amount": 50, "is_all_in": True}
        assert self._format(entry) == "Alice calls 50 and is all-in"

    def test_call_all_in_zero_amount(self):
        """Player is all-in with no additional chips needed (already committed enough)."""
        entry = {"player": "Alice", "action": "check_call", "amount": 0, "is_all_in": True}
        assert self._format(entry) == "Alice is all-in"

    def test_call_not_all_in(self):
        """Player calls but keeps chips behind (not all-in)."""
        entry = {"player": "Alice", "action": "check_call", "amount": 50, "is_all_in": False}
        assert self._format(entry) == "Alice calls 50"

    def test_call_opponent_all_in_but_caller_has_chips(self):
        """Player calls an opponent's all-in but still has chips remaining.
        is_all_in should be False since caller's stack > 0 after call."""
        entry = {"player": "Bob", "action": "check_call", "amount": 200, "is_all_in": False}
        result = self._format(entry)
        assert result == "Bob calls 200"
        assert "all-in" not in result

    def test_raise_all_in(self):
        """Player raises and goes all-in."""
        entry = {"player": "Alice", "action": "bet_raise", "amount": 500, "is_all_in": True}
        assert self._format(entry) == "Alice raises all-in to 500"


# ═══════════════════════════════════════════════════════════════
# Winner entry formatting
# ═══════════════════════════════════════════════════════════════


class TestWinnerEntryFormat:
    """Test that winner entries use hand_detail for richer descriptions."""

    def _format_winner(self, winner):
        """Python simulation of the fixed formatWinnerEntry logic."""
        if winner.get("hand_name") and winner.get("reason") != "Everyone else folded":
            detail = winner.get("hand_detail") or winner.get("hand_name")
            return f"{winner['name']} wins {winner['amount']} with {detail}"
        return f"{winner['name']} wins {winner['amount']}"

    def test_winner_with_hand_detail(self):
        winner = {
            "name": "Alice",
            "amount": 1782,
            "hand_name": "Flush",
            "hand_detail": "Flush, Ace-high",
            "reason": "Best hand at showdown"
        }
        result = self._format_winner(winner)
        assert result == "Alice wins 1782 with Flush, Ace-high"

    def test_winner_without_hand_detail_falls_back_to_hand_name(self):
        winner = {
            "name": "Bob",
            "amount": 500,
            "hand_name": "Two pair",
            "hand_detail": "",
            "reason": "Best hand at showdown"
        }
        result = self._format_winner(winner)
        assert result == "Bob wins 500 with Two pair"

    def test_fold_winner_no_hand_shown(self):
        winner = {
            "name": "Alice",
            "amount": 300,
            "hand_name": "",
            "hand_detail": "",
            "reason": "Everyone else folded"
        }
        result = self._format_winner(winner)
        assert result == "Alice wins 300"

    def test_pot_area_headline_format(self):
        """The pot area should show 'Player wins X with a Hand' not the old format."""
        winner = {
            "name": "Alice",
            "amount": 1782,
            "hand_name": "Flush",
            "hand_detail": "Flush, Ace-high",
            "reason": "Best hand at showdown"
        }
        # Simulate the new pot area logic
        if winner["hand_name"] and winner["reason"] != "Everyone else folded":
            headline = f"{winner['name']} wins {winner['amount']} with a {winner['hand_name']}"
        else:
            headline = f"{winner['name']} wins {winner['amount']}"
        assert headline == "Alice wins 1782 with a Flush"
        assert "—" not in headline  # no longer has the pot-dash-winner format
