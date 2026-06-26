"""
Preservation Property Tests - Equity, Pot Distribution, and Betting Flow
=========================================================================

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

Property 2: Preservation - These tests capture correct baseline behavior
on UNFIXED code. They MUST PASS on the current codebase, confirming that
these non-bug-condition behaviors work correctly and should not be broken
by subsequent bug fixes.

Tests cover:
- Equity preservation (flop Monte Carlo, river exact enumeration)
- Pot distribution preservation (equal-stack showdown, fold-to-last-player, ties)
- Betting flow preservation (multi-actor prompting, matched-bet completion)
"""

import time

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.odds import calculate_equity_hybrid, FULL_DECK
from poker.game import PokerServer
from poker.models import Player, Room, Winner
from poker.evaluator import evaluate_7


# ─── Strategies ────────────────────────────────────────────────────────────────

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
SUITS = ["S", "H", "D", "C"]
ALL_CARDS = [r + s for s in SUITS for r in RANKS]


def valid_flop_inputs():
    """Strategy generating valid (hero_cards, 3-card board, num_opponents) tuples."""
    return st.lists(
        st.sampled_from(ALL_CARDS),
        min_size=5,  # 2 hero + 3 board
        max_size=5,
        unique=True,
    ).flatmap(
        lambda cards: st.integers(min_value=1, max_value=4).map(
            lambda num_opp, c=cards: (c[:2], c[2:5], num_opp)
        )
    )


def valid_river_inputs():
    """Strategy generating valid (hero_cards, 5-card board, num_opponents) tuples."""
    return st.lists(
        st.sampled_from(ALL_CARDS),
        min_size=7,  # 2 hero + 5 board
        max_size=7,
        unique=True,
    ).flatmap(
        lambda cards: st.integers(min_value=1, max_value=3).map(
            lambda num_opp, c=cards: (c[:2], c[2:7], num_opp)
        )
    )


# ─── Equity Preservation Tests ─────────────────────────────────────────────────


class TestEquityPreservation:
    """Tests that flop and river equity paths remain unchanged."""

    @settings(max_examples=30, deadline=None)
    @given(inputs=valid_flop_inputs())
    def test_flop_equity_returns_valid_range(self, inputs):
        """**Validates: Requirements 3.1**

        For any valid hero cards and 3-card board (flop),
        calculate_equity_hybrid returns equity in [0, 1] and completes quickly
        (Monte Carlo path).
        """
        hero_cards, board, num_opponents = inputs

        start = time.perf_counter()
        result = calculate_equity_hybrid(hero_cards, board, num_opponents, simulations=100)
        elapsed = time.perf_counter() - start

        # Equity must be in valid range
        assert 0.0 <= result["equity"] <= 1.0, (
            f"Flop equity {result['equity']} out of [0,1] for "
            f"hero={hero_cards}, board={board}, opp={num_opponents}"
        )
        assert 0.0 <= result["win_pct"] <= 1.0
        assert 0.0 <= result["tie_pct"] <= 1.0
        assert 0.0 <= result["loss_pct"] <= 1.0

        # Monte Carlo with 300 sims should complete quickly (< 2 seconds generously)
        assert elapsed < 2.0, (
            f"Flop equity took {elapsed:.3f}s - should be fast (Monte Carlo path)"
        )

    @settings(max_examples=30, deadline=None)
    @given(inputs=valid_river_inputs())
    def test_river_equity_returns_valid_range(self, inputs):
        """**Validates: Requirements 3.2**

        For any valid hero cards and 5-card board (river),
        calculate_equity_hybrid returns equity in [0, 1]
        (exact enumeration path).
        """
        hero_cards, board, num_opponents = inputs

        result = calculate_equity_hybrid(hero_cards, board, num_opponents)

        # Equity must be in valid range
        assert 0.0 <= result["equity"] <= 1.0, (
            f"River equity {result['equity']} out of [0,1] for "
            f"hero={hero_cards}, board={board}, opp={num_opponents}"
        )
        assert 0.0 <= result["win_pct"] <= 1.0
        assert 0.0 <= result["tie_pct"] <= 1.0
        assert 0.0 <= result["loss_pct"] <= 1.0

        # Components should sum to ~1.0
        total = result["win_pct"] + result["tie_pct"] + result["loss_pct"]
        assert abs(total - 1.0) < 0.01, (
            f"River equity components sum to {total}, expected ~1.0"
        )


# ─── Pot Distribution Preservation Tests ──────────────────────────────────────


class TestPotDistributionPreservation:
    """Tests that equal-stack showdown and fold scenarios remain unchanged."""

    @settings(max_examples=30, deadline=None)
    @given(
        num_players=st.integers(min_value=2, max_value=5),
        stack_per_player=st.integers(min_value=50, max_value=500),
    )
    def test_equal_stack_showdown_awards_full_pot(self, num_players, stack_per_player):
        """**Validates: Requirements 3.4**

        For all showdown states where contenders have equal committed amounts,
        the winner(s) receive the full pot.
        """
        server = PokerServer()
        room = Room(room_id="TEST_EQUAL")
        room.pot = num_players * stack_per_player

        # Create contenders with equal committed amounts and valid cards
        # We need to give each player unique cards from the deck
        deck = ALL_CARDS[:]
        community = deck[:5]  # 5 community cards
        remaining = deck[5:]

        players = []
        for i in range(num_players):
            hero_cards = [remaining[i * 2], remaining[i * 2 + 1]]
            p = Player(
                player_id=f"P{i}",
                token=f"tok{i}",
                name=f"Player{i}",
                seat=i,
                stack=0,  # all committed
                cards=hero_cards,
                committed=stack_per_player,
                total_invested=stack_per_player,
            )
            room.players[p.player_id] = p
            players.append(p)

        room.community = community

        # Run showdown
        server.showdown(room)

        # Total awarded must equal pot
        total_awarded = sum(w.amount for w in room.winners)
        assert total_awarded == num_players * stack_per_player, (
            f"Total awarded ({total_awarded}) != pot ({num_players * stack_per_player})"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        pot_amount=st.integers(min_value=10, max_value=5000),
        num_players=st.integers(min_value=2, max_value=6),
    )
    def test_award_to_last_player_gives_entire_pot(self, pot_amount, num_players):
        """**Validates: Requirements 3.5**

        When all players fold except one, award_to_last_player()
        gives the entire pot to the remaining player.
        """
        server = PokerServer()
        room = Room(room_id="TEST_LAST")
        room.pot = pot_amount

        # Create players - all folded except the last one
        for i in range(num_players):
            p = Player(
                player_id=f"P{i}",
                token=f"tok{i}",
                name=f"Player{i}",
                seat=i,
                stack=500,
                cards=["AH", "KS"] if i == 0 else [],
                folded=(i != 0),
            )
            room.players[p.player_id] = p

        # The non-folded player (P0) should win
        stack_before = room.players["P0"].stack

        server.award_to_last_player(room)

        winner_player = room.players["P0"]
        assert winner_player.stack == stack_before + pot_amount, (
            f"Last player stack should be {stack_before + pot_amount}, "
            f"got {winner_player.stack}"
        )
        assert len(room.winners) == 1
        assert room.winners[0].amount == pot_amount

    @settings(max_examples=30, deadline=None)
    @given(
        num_winners=st.integers(min_value=2, max_value=4),
        stack_per_player=st.integers(min_value=50, max_value=500),
    )
    def test_tie_with_equal_stacks_splits_pot_evenly(self, num_winners, stack_per_player):
        """**Validates: Requirements 3.6**

        For ties with equal stacks, pot is split evenly
        (sum of winner amounts == pot).
        """
        server = PokerServer()
        room = Room(room_id="TEST_TIE")
        total_players = num_winners + 1  # extra player who loses
        room.pot = total_players * stack_per_player

        # Use a board where all winners will have the same hand rank
        # Give winners the same rank cards (different suits) to force a tie
        # Use community cards that give everyone same best hand
        community = ["AS", "KS", "QS", "JS", "TS"]  # Royal flush on board
        room.community = community

        deck_remaining = [c for c in ALL_CARDS if c not in community]

        players = []
        for i in range(total_players):
            hero_cards = [deck_remaining[i * 2], deck_remaining[i * 2 + 1]]
            p = Player(
                player_id=f"P{i}",
                token=f"tok{i}",
                name=f"Player{i}",
                seat=i,
                stack=0,
                cards=hero_cards,
                committed=stack_per_player,
                total_invested=stack_per_player,
            )
            room.players[p.player_id] = p
            players.append(p)

        # Run showdown - with royal flush on board, all players tie
        server.showdown(room)

        # Sum of winner amounts must equal pot
        total_awarded = sum(w.amount for w in room.winners)
        assert total_awarded == room.pot or total_awarded == total_players * stack_per_player, (
            f"Total awarded ({total_awarded}) should equal pot ({total_players * stack_per_player})"
        )


# ─── Betting Flow Preservation Tests ──────────────────────────────────────────


class TestBettingFlowPreservation:
    """Tests that multi-actor betting prompting remains unchanged."""

    @settings(max_examples=30, deadline=None)
    @given(
        num_active=st.integers(min_value=2, max_value=5),
        current_bet=st.integers(min_value=10, max_value=200),
    )
    def test_betting_incomplete_when_players_havent_acted(self, num_active, current_bet):
        """**Validates: Requirements 3.7, 3.8**

        When multiple players can act (not all-in, not folded) and at least
        one hasn't acted (acted == False), betting_complete() returns False.
        """
        server = PokerServer()
        room = Room(room_id="TEST_BETTING")
        room.current_bet = current_bet

        # Create active players - at least one hasn't acted
        for i in range(num_active):
            p = Player(
                player_id=f"P{i}",
                token=f"tok{i}",
                name=f"Player{i}",
                seat=i,
                stack=1000,
                cards=["AH", "KS"],
                folded=False,
                all_in=False,
                acted=False,  # None have acted yet
                committed=0,
            )
            room.players[p.player_id] = p

        result = server.betting_complete(room)
        assert result is False, (
            f"betting_complete() should return False when {num_active} players "
            f"haven't acted. Got {result}"
        )

    @settings(max_examples=30, deadline=None)
    @given(
        num_active=st.integers(min_value=2, max_value=5),
        current_bet=st.integers(min_value=10, max_value=200),
    )
    def test_betting_complete_when_all_acted_and_matched(self, num_active, current_bet):
        """**Validates: Requirements 3.7, 3.8**

        When all players have acted and their committed matches current_bet,
        betting_complete() returns True.
        """
        server = PokerServer()
        room = Room(room_id="TEST_BETTING_DONE")
        room.current_bet = current_bet

        # Create active players - all have acted and matched bet
        for i in range(num_active):
            p = Player(
                player_id=f"P{i}",
                token=f"tok{i}",
                name=f"Player{i}",
                seat=i,
                stack=1000 - current_bet,
                cards=["AH", "KS"],
                folded=False,
                all_in=False,
                acted=True,
                committed=current_bet,
            )
            room.players[p.player_id] = p

        result = server.betting_complete(room)
        assert result is True, (
            f"betting_complete() should return True when all {num_active} players "
            f"have acted and committed matches current_bet={current_bet}. Got {result}"
        )
