"""
Bug Condition Exploration Tests - Poker Gameplay Bugs
=====================================================

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

Property 1: Bug Condition - These tests encode the EXPECTED (correct) behavior.
On UNFIXED code, these tests MUST FAIL (confirming the bugs exist).
After fixes are applied, all tests should PASS.

CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bugs exist.
DO NOT attempt to fix the tests or the code when they fail.

Three bugs tested:
1. Turn equity performance: exact enumeration is ~50-200x slower than Monte Carlo
2. Side pot incorrect award: short-stack winner receives entire pot instead of contestable portion
3. Unnecessary action prompt: betting_complete() returns False when sole actor faces all-in opponents
"""

import time
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.odds import calculate_equity_hybrid
from poker.game import PokerServer
from poker.models import Player, Room, Winner


# ─── Bug 1: Turn Equity Performance ─────────────────────────────────────────────


class TestTurnEquityPerformance:
    """
    Bug 1: Turn equity uses exact enumeration (~39,700 evaluations) instead of
    Monte Carlo (~300 simulations). This makes turn equity ~50-200x slower than flop.

    **Validates: Requirements 1.1, 1.2**

    EXPECTED TO FAIL on unfixed code: exact enumeration takes much longer than
    the Monte Carlo approach used for flop.
    """

    def test_turn_equity_within_reasonable_time_budget(self):
        """
        Turn equity (4-card board) should complete within 2x the time of flop equity
        (3-card board). On unfixed code, turn uses exact enumeration which is ~50-200x
        slower than the Monte Carlo sampling used for flop.

        Counterexample on unfixed code:
        calculate_equity_hybrid(['AH','KH'], ['2C','5D','9S','JH'], 2)
        takes ~100-500ms vs ~3-10ms for flop equivalent.
        """
        hero_cards = ['AH', 'KH']
        flop_board = ['2C', '5D', '9S']
        turn_board = ['2C', '5D', '9S', 'JH']
        num_opponents = 2

        # Time the flop equity (Monte Carlo, ~300 sims)
        start = time.perf_counter()
        flop_result = calculate_equity_hybrid(hero_cards, flop_board, num_opponents)
        flop_time = time.perf_counter() - start

        # Time the turn equity (on unfixed code: exact enumeration)
        start = time.perf_counter()
        turn_result = calculate_equity_hybrid(hero_cards, turn_board, num_opponents)
        turn_time = time.perf_counter() - start

        # Both should return valid equity values
        assert 0.0 <= flop_result['equity'] <= 1.0, "Flop equity out of range"
        assert 0.0 <= turn_result['equity'] <= 1.0, "Turn equity out of range"

        # Turn should be within 2x flop time if using Monte Carlo
        # On unfixed code: turn takes ~50-200x longer (exact enumeration)
        assert turn_time < flop_time * 3, (
            f"BUG CONFIRMED: Turn equity took {turn_time:.4f}s vs flop {flop_time:.4f}s "
            f"(ratio: {turn_time/flop_time:.1f}x). "
            f"Expected <3x if using Monte Carlo, got {turn_time/flop_time:.1f}x. "
            f"Root cause: calculate_equity_hybrid dispatches to turn_equity_exact "
            f"which enumerates ~39,700 hand evaluations instead of using Monte Carlo."
        )

    def test_turn_equity_absolute_time_limit(self):
        """
        Turn equity should complete within 200ms (generous limit).
        Monte Carlo with 300 sims typically takes 30-100ms depending on opponents.
        Exact enumeration typically takes 1000-4000ms with multiple opponents.

        Counterexample on unfixed code:
        calculate_equity_hybrid(['TH','9H'], ['3C','7D','QS','4H'], 3)
        takes >1000ms due to exact enumeration.
        """
        hero_cards = ['TH', '9H']
        turn_board = ['3C', '7D', 'QS', '4H']
        num_opponents = 3

        start = time.perf_counter()
        result = calculate_equity_hybrid(hero_cards, turn_board, num_opponents)
        elapsed = time.perf_counter() - start

        assert 0.0 <= result['equity'] <= 1.0, "Turn equity out of range"

        # 200ms is generous for Monte Carlo (300 sims typically takes 30-100ms depending on opponents)
        # Exact enumeration typically takes 1000-4000ms with 3 opponents
        assert elapsed < 0.200, (
            f"BUG CONFIRMED: Turn equity took {elapsed*1000:.1f}ms (limit: 200ms). "
            f"Expected <200ms with Monte Carlo, actual: {elapsed*1000:.1f}ms. "
            f"Root cause: turn_equity_exact enumerates all river cards × opponent combos."
        )


# ─── Bug 2: Side Pot Incorrect Award ────────────────────────────────────────────


class TestSidePotIncorrectAward:
    """
    Bug 2: showdown() awards the entire pot to the best hand winner regardless of
    their contribution. A short-stack player who goes all-in for 100 can win 1100
    when they should only win 300 (100×3 from the main pot).

    **Validates: Requirements 1.3, 1.4**

    EXPECTED TO FAIL on unfixed code: Player A receives entire pot (1100) instead
    of just the main pot (300) they can contest.
    """

    def test_short_stack_winner_receives_only_contestable_portion(self):
        """
        3-player scenario: Player A (100 all-in), Player B (500), Player C (500).
        Total pot = 1100. Player A has the best hand.
        Player A should receive at most 300 (100 × 3 players = main pot).
        The remaining 800 side pot should go to the best hand among B and C.

        On unfixed code: Player A receives the entire 1100 pot.

        Counterexample: Player A (100 invested) awarded 1100 instead of 300.
        """
        server = PokerServer()

        # Create room with 3 players
        room = Room(room_id="test_side_pot")
        room.phase = "river"
        room.community = ['2C', '5D', '9S', 'JH', 'QC']  # Community cards

        # Player A: short-stack, all-in for 100, has best hand (Royal Flush setup)
        player_a = Player(
            player_id="player_a", token="token_a", name="PlayerA",
            seat=0, stack=0, all_in=True, committed=0,
            cards=['AH', 'KH'],  # Will pair with community for strong hand
        )
        player_a.total_invested = 100

        # Player B: big stack, contributed 500
        player_b = Player(
            player_id="player_b", token="token_b", name="PlayerB",
            seat=1, stack=0, all_in=True, committed=0,
            cards=['3S', '4S'],  # Weak hand
        )
        player_b.total_invested = 500

        # Player C: big stack, contributed 500
        player_c = Player(
            player_id="player_c", token="token_c", name="PlayerC",
            seat=2, stack=0, all_in=True, committed=0,
            cards=['6H', '7H'],  # Weak hand
        )
        player_c.total_invested = 500

        room.players = {
            "player_a": player_a,
            "player_b": player_b,
            "player_c": player_c,
        }

        # Set total pot: Player A contributed 100, B contributed 500, C contributed 500
        # Total pot = 1100
        room.pot = 1100

        # Run showdown
        server.showdown(room)

        # Player A has best hand (AH KH + community gives top pair AK high)
        # Find Player A's award
        player_a_award = None
        for w in room.winners:
            if w.player_id == "player_a":
                player_a_award = w.amount
                break

        assert player_a_award is not None, "Player A should be a winner (best hand)"

        # Player A can only contest 100 × 3 = 300 (main pot)
        # On unfixed code, Player A gets the entire 1100
        assert player_a_award <= 300, (
            f"BUG CONFIRMED: Player A (short-stack, invested 100) received {player_a_award} "
            f"but should receive at most 300 (100 × 3 players = main pot). "
            f"The remaining {1100 - 300} should go to the best hand among B and C. "
            f"Root cause: showdown() simply awards entire pot to best hand without "
            f"considering per-player contribution limits."
        )


# ─── Bug 3: Unnecessary Action Prompt ───────────────────────────────────────────


class TestUnnecessaryActionPrompt:
    """
    Bug 3: betting_complete() returns False when exactly one player can act and
    all others are all-in. The sole actor's action is meaningless since no one
    can respond, so the betting round should auto-complete.

    **Validates: Requirements 1.5, 1.6**

    EXPECTED TO FAIL on unfixed code: betting_complete() returns False because
    the sole actor has acted=False, even though their action is meaningless.
    """

    def test_betting_complete_with_sole_actor_facing_all_in(self):
        """
        Setup: 3 contenders. Player B and C are all-in. Player A has stack > 0
        and acted=False. betting_complete() should return True since Player A's
        action cannot be raised by anyone.

        On unfixed code: returns False because p.acted == False for Player A.

        Counterexample: betting_complete() returns False with sole actor
        when all opponents are all-in.
        """
        server = PokerServer()

        room = Room(room_id="test_betting")
        room.phase = "flop"
        room.current_bet = 100
        room.community = ['2C', '5D', '9S']

        # Player A: has stack, has NOT acted yet (sole actor)
        player_a = Player(
            player_id="player_a", token="token_a", name="PlayerA",
            seat=0, stack=500, all_in=False, committed=100,
            cards=['AH', 'KH'], acted=False,
        )

        # Player B: all-in (cannot act)
        player_b = Player(
            player_id="player_b", token="token_b", name="PlayerB",
            seat=1, stack=0, all_in=True, committed=100,
            cards=['3S', '4S'], acted=True,
        )

        # Player C: all-in (cannot act)
        player_c = Player(
            player_id="player_c", token="token_c", name="PlayerC",
            seat=2, stack=0, all_in=True, committed=100,
            cards=['6H', '7H'], acted=True,
        )

        room.players = {
            "player_a": player_a,
            "player_b": player_b,
            "player_c": player_c,
        }

        # Call betting_complete
        result = server.betting_complete(room)

        # With sole actor facing all-in opponents, betting should auto-complete
        # On unfixed code: returns False because player_a.acted == False
        assert result is True, (
            f"BUG CONFIRMED: betting_complete() returned False when Player A is the "
            f"sole actor and all opponents (B, C) are all-in. "
            f"Player A's action is meaningless since no one can re-raise. "
            f"Root cause: betting_complete() checks `p.acted == False` without "
            f"considering whether the player is the sole remaining actor facing all-in opponents."
        )

    def test_betting_complete_sole_actor_two_players(self):
        """
        Simpler 2-player case: Player A has stack, Player B is all-in.
        betting_complete() should return True.

        On unfixed code: returns False because Player A hasn't acted.
        """
        server = PokerServer()

        room = Room(room_id="test_betting_2p")
        room.phase = "turn"
        room.current_bet = 200
        room.community = ['2C', '5D', '9S', 'JH']

        # Player A: has stack, hasn't acted
        player_a = Player(
            player_id="player_a", token="token_a", name="PlayerA",
            seat=0, stack=300, all_in=False, committed=200,
            cards=['AH', 'KH'], acted=False,
        )

        # Player B: all-in
        player_b = Player(
            player_id="player_b", token="token_b", name="PlayerB",
            seat=1, stack=0, all_in=True, committed=200,
            cards=['3S', '4S'], acted=True,
        )

        room.players = {
            "player_a": player_a,
            "player_b": player_b,
        }

        result = server.betting_complete(room)

        assert result is True, (
            f"BUG CONFIRMED: betting_complete() returned False in 2-player scenario "
            f"where Player A is sole actor and Player B is all-in. "
            f"Expected True since Player A's action cannot be re-raised. "
            f"Root cause: no sole-actor detection in betting_complete()."
        )
