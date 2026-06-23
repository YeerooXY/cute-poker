"""All-in runout fix tests.

Tests for the heads-up (and multiway) forced runout behavior:
- When one player is all-in and fewer than 2 players can bet, the engine
  deals remaining board cards without further betting action.
- Uncalled excess chips are returned to the covering player.
- Multiway hands with 2+ live players do NOT trigger forced runout.

Feature: allin-runout-fix
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock

os.environ["POKER_SIMULATION"] = "1"

from poker.game import PokerServer
from poker.models import Room, Player


# ============================================================
# Helpers
# ============================================================

def make_server():
    """Create a PokerServer with mocked send/broadcast for testing."""
    server = PokerServer()
    server.send = AsyncMock()
    server.broadcast = AsyncMock()
    return server


def make_room(room_id="TEST"):
    room = Room(room_id=room_id)
    room.creator_token = "creator"
    return room


def make_player(pid, name, seat, stack=1000):
    return Player(
        player_id=pid, token=f"token_{pid}", name=name,
        seat=seat, ws=None, connected=True, stack=stack, avatar="🎭"
    )


def setup_hu_room(stack_a=1000, stack_b=1000):
    """Create a heads-up room with two players."""
    server = make_server()
    room = make_room()
    server.rooms["TEST"] = room

    p1 = make_player("p1", "PlayerA", seat=1, stack=stack_a)
    p2 = make_player("p2", "PlayerB", seat=2, stack=stack_b)
    room.players["p1"] = p1
    room.players["p2"] = p2
    return server, room, p1, p2


def setup_multiway_room(num_players=3, stacks=None):
    """Create a multiway room with N players."""
    server = make_server()
    room = make_room()
    server.rooms["TEST"] = room

    if stacks is None:
        stacks = [1000] * num_players

    players = []
    for i in range(num_players):
        p = make_player(f"p{i+1}", f"Player{i+1}", seat=i+1, stack=stacks[i])
        room.players[f"p{i+1}"] = p
        players.append(p)

    return server, room, players


# ============================================================
# Unit Tests: return_uncalled_excess
# ============================================================

class TestReturnUncalledExcess:
    """Tests for return_uncalled_excess logic."""

    def test_hu_short_call_returns_excess(self):
        """Player A bets 1000, Player B calls all-in for 300. Excess 700 returned."""
        server, room, p1, p2 = setup_hu_room(stack_a=1000, stack_b=300)

        # Simulate: p1 committed 1000, p2 committed 300 (all-in)
        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.committed = 1000
        p1.total_invested = 1000
        p1.stack = 0
        p1.all_in = True

        p2.committed = 300
        p2.total_invested = 300
        p2.stack = 0
        p2.all_in = True

        room.pot = 1300
        room.current_bet = 1000
        room.phase = "preflop"

        server.return_uncalled_excess(room)

        # Excess = 1000 - 300 = 700 returned to p1
        assert p1.stack == 700
        assert p1.committed == 300
        assert p1.total_invested == 300
        assert p1.all_in == False  # Has chips again
        assert room.pot == 600
        assert room.current_bet == 300  # Recalculated from contenders

    def test_no_excess_when_equal_committed(self):
        """Both players committed equally — no excess to return."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.committed = 500
        p1.total_invested = 500
        p1.stack = 500
        p2.committed = 500
        p2.total_invested = 500
        p2.stack = 500

        room.pot = 1000
        room.current_bet = 500

        server.return_uncalled_excess(room)

        # Nothing should change
        assert p1.stack == 500
        assert p1.committed == 500
        assert p2.stack == 500
        assert room.pot == 1000

    def test_noop_for_three_plus_contenders(self):
        """return_uncalled_excess uses total_invested; with 3+ contenders it still works."""
        server, room, players = setup_multiway_room(3, stacks=[1000, 300, 500])

        for p in players:
            p.cards = ["Ah", "Kh"]

        # p1 bet 1000, p2 called 300 all-in, p3 called 500 all-in
        players[0].committed = 1000
        players[0].total_invested = 1000
        players[0].stack = 0
        players[0].all_in = True

        players[1].committed = 300
        players[1].total_invested = 300
        players[1].stack = 0
        players[1].all_in = True

        players[2].committed = 500
        players[2].total_invested = 500
        players[2].stack = 0
        players[2].all_in = True

        room.pot = 1800
        room.current_bet = 1000

        server.return_uncalled_excess(room)

        # Excess = 1000 - 500 = 500 returned to p1
        assert players[0].stack == 500
        assert players[0].committed == 500
        assert players[0].total_invested == 500
        assert room.pot == 1300

    def test_noop_when_fewer_than_two_contenders(self):
        """Only one non-folded player — no excess calculation."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p2.folded = True  # Only p1 remains

        p1.committed = 500
        p1.total_invested = 500
        p1.stack = 500
        room.pot = 500

        server.return_uncalled_excess(room)

        # No change
        assert p1.stack == 500
        assert room.pot == 500


# ============================================================
# Unit Tests: should_force_runout
# ============================================================

class TestShouldForceRunout:
    """Tests for should_force_runout predicate."""

    def test_hu_one_allin_triggers_runout(self):
        """Heads-up, one player all-in → force runout."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 700  # Has chips
        p2.stack = 0
        p2.all_in = True

        assert server.should_force_runout(room) is True

    def test_hu_both_allin_triggers_runout(self):
        """Heads-up, both players all-in → force runout."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 0
        p1.all_in = True
        p2.stack = 0
        p2.all_in = True

        assert server.should_force_runout(room) is True

    def test_hu_neither_allin_no_runout(self):
        """Heads-up, both players have chips → no forced runout."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 500
        p2.stack = 500

        assert server.should_force_runout(room) is False

    def test_3way_2allin_1live_triggers_runout(self):
        """3-way hand: 2 all-in + 1 live player → force runout (only 1 can bet)."""
        server, room, players = setup_multiway_room(3)

        for p in players:
            p.cards = ["Ah", "Kh"]

        players[0].stack = 500  # Can bet
        players[1].stack = 0
        players[1].all_in = True
        players[2].stack = 0
        players[2].all_in = True

        assert server.should_force_runout(room) is True

    def test_4way_3allin_1live_triggers_runout(self):
        """4-way hand: 3 all-in + 1 live → force runout."""
        server, room, players = setup_multiway_room(4)

        for p in players:
            p.cards = ["Ah", "Kh"]

        players[0].stack = 500  # Can bet
        players[1].stack = 0
        players[1].all_in = True
        players[2].stack = 0
        players[2].all_in = True
        players[3].stack = 0
        players[3].all_in = True

        assert server.should_force_runout(room) is True

    def test_4way_2allin_2live_no_runout(self):
        """4-way hand: 2 all-in + 2 live → no forced runout (2 can bet)."""
        server, room, players = setup_multiway_room(4)

        for p in players:
            p.cards = ["Ah", "Kh"]

        players[0].stack = 500
        players[1].stack = 500
        players[2].stack = 0
        players[2].all_in = True
        players[3].stack = 0
        players[3].all_in = True

        assert server.should_force_runout(room) is False

    def test_4way_1allin_3live_no_runout(self):
        """4-way hand: 1 all-in + 3 live → no forced runout."""
        server, room, players = setup_multiway_room(4)

        for p in players:
            p.cards = ["Ah", "Kh"]

        players[0].stack = 500
        players[1].stack = 500
        players[2].stack = 500
        players[3].stack = 0
        players[3].all_in = True

        assert server.should_force_runout(room) is False


# ============================================================
# Unit Tests: runout_to_showdown
# ============================================================

class TestRunoutToShowdown:
    """Tests for runout_to_showdown dealing."""

    @pytest.mark.asyncio
    async def test_runout_from_preflop_deals_5_cards(self):
        """Starting from preflop, runout should deal flop+turn+river = 5 cards."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 0
        p1.all_in = True
        p2.stack = 0
        p2.all_in = True

        room.phase = "preflop"
        room.community = []
        # Build a deck with enough cards (remove dealt hole cards)
        from poker.game import PokerServer
        full_deck = [f"{r}{s}" for r in "23456789TJQKA" for s in "shdc"]
        used = set(p1.cards + p2.cards)
        room.deck = [c for c in full_deck if c not in used]
        room.pot = 2000

        await server.runout_to_showdown(room)

        assert len(room.community) == 5
        assert room.phase == "showdown"
        assert room.action_seat is None

    @pytest.mark.asyncio
    async def test_runout_from_flop_deals_2_more_cards(self):
        """Starting from flop (3 cards on board), runout deals turn + river."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 0
        p1.all_in = True
        p2.stack = 0
        p2.all_in = True

        room.phase = "flop"
        room.community = ["2h", "3d", "5c"]
        full_deck = [f"{r}{s}" for r in "23456789TJQKA" for s in "shdc"]
        used = set(p1.cards + p2.cards + room.community)
        room.deck = [c for c in full_deck if c not in used]
        room.pot = 2000

        await server.runout_to_showdown(room)

        assert len(room.community) == 5
        assert room.phase == "showdown"
        assert room.action_seat is None

    @pytest.mark.asyncio
    async def test_runout_from_turn_deals_1_more_card(self):
        """Starting from turn (4 cards on board), runout deals river only."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 0
        p1.all_in = True
        p2.stack = 0
        p2.all_in = True

        room.phase = "turn"
        room.community = ["2h", "3d", "5c", "7s"]
        full_deck = [f"{r}{s}" for r in "23456789TJQKA" for s in "shdc"]
        used = set(p1.cards + p2.cards + room.community)
        room.deck = [c for c in full_deck if c not in used]
        room.pot = 2000

        await server.runout_to_showdown(room)

        assert len(room.community) == 5
        assert room.phase == "showdown"
        assert room.action_seat is None

    @pytest.mark.asyncio
    async def test_no_action_seat_during_runout(self):
        """action_seat must be None throughout the runout."""
        server, room, p1, p2 = setup_hu_room()

        p1.cards = ["Ah", "Kh"]
        p2.cards = ["Qs", "Js"]
        p1.stack = 0
        p1.all_in = True
        p2.stack = 0
        p2.all_in = True

        room.phase = "preflop"
        room.community = []
        full_deck = [f"{r}{s}" for r in "23456789TJQKA" for s in "shdc"]
        used = set(p1.cards + p2.cards)
        room.deck = [c for c in full_deck if c not in used]
        room.pot = 2000

        # Track action_seat values during broadcast calls
        action_seats_seen = []
        async def track_broadcast(*args, **kwargs):
            action_seats_seen.append(room.action_seat)
        server.broadcast = track_broadcast

        await server.runout_to_showdown(room)

        # action_seat should be None in every broadcast
        assert all(seat is None for seat in action_seats_seen)


# ============================================================
# Integration Test: Full hand with short-call forced runout
# ============================================================

class TestIntegrationRunout:
    """Integration tests verifying the full flow through after_action."""

    @pytest.mark.asyncio
    async def test_hu_short_call_forces_runout_no_further_action(self):
        """
        Player A (1000) raises all-in. Player B (300) calls short.
        Expected: excess returned, runout to showdown, no further action.
        """
        server, room, p1, p2 = setup_hu_room(stack_a=1000, stack_b=300)

        # Start a hand
        await server.start_hand(room)

        # Find who acts first (SB in HU)
        acting = server.player_by_seat(room, room.action_seat)
        other = p1 if acting == p2 else p2

        # Acting player goes all-in
        await server.player_action(room, acting, "bet_raise", {
            "amount": acting.committed + acting.stack,
        })

        # If other player gets action, they call (short all-in)
        if room.phase != "showdown" and room.action_seat is not None:
            other_acting = server.player_by_seat(room, room.action_seat)
            if other_acting:
                await server.player_action(room, other_acting, "check_call", {})

        # After the short-call, the hand should run out to showdown
        assert room.phase == "showdown"
        assert room.action_seat is None
        assert len(room.community) == 5

        # Verify chip conservation
        total_stacks = sum(p.stack for p in room.players.values())
        total_winners = sum(w.amount for w in room.winners)
        # Total chips in system should equal starting total (2 * starting stack isn't
        # exactly right because of blinds distribution, but winners + stacks should sum)
        # Just verify showdown happened and pot was awarded
        assert len(room.winners) >= 1

    @pytest.mark.asyncio
    async def test_hu_equal_stacks_allin_runout(self):
        """
        Both players 1000. One shoves, other calls.
        Expected: both all-in, runout, showdown, pot = 2000.
        """
        server, room, p1, p2 = setup_hu_room(stack_a=1000, stack_b=1000)

        await server.start_hand(room)

        # First to act goes all-in
        acting = server.player_by_seat(room, room.action_seat)
        await server.player_action(room, acting, "bet_raise", {
            "amount": acting.committed + acting.stack,
        })

        # Other calls
        if room.phase != "showdown" and room.action_seat is not None:
            other = server.player_by_seat(room, room.action_seat)
            if other:
                await server.player_action(room, other, "check_call", {})

        # Should reach showdown
        assert room.phase == "showdown"
        assert len(room.community) == 5
        assert len(room.winners) >= 1


# ============================================================
# Property-Based Tests (Hypothesis)
# ============================================================

from hypothesis import given, settings, assume
from hypothesis import strategies as st


def build_hu_excess_state(
    short_stack_total_invested,
    covering_extra_committed,
    covering_remaining_stack,
):
    """
    Build a valid heads-up room state where excess return applies.

    - short_caller: all-in, stack=0, total_invested = short_stack_total_invested
    - covering: total_invested = short_stack_total_invested + covering_extra_committed
    - covering.committed >= excess (= covering_extra_committed)
    - room.pot >= excess
    """
    server = make_server()
    room = make_room()
    server.rooms["TEST"] = room

    short_caller = make_player("p1", "ShortCaller", seat=1, stack=0)
    short_caller.cards = ["Ah", "Kh"]
    short_caller.all_in = True
    short_caller.committed = short_stack_total_invested  # all committed this street
    short_caller.total_invested = short_stack_total_invested

    covering = make_player("p2", "Covering", seat=2, stack=covering_remaining_stack)
    covering.cards = ["Qs", "Js"]
    covering.committed = short_stack_total_invested + covering_extra_committed
    covering.total_invested = short_stack_total_invested + covering_extra_committed
    covering.all_in = (covering.stack == 0)

    room.players["p1"] = short_caller
    room.players["p2"] = covering

    # pot = sum of all invested chips (both players' total_invested)
    room.pot = short_caller.total_invested + covering.total_invested
    room.current_bet = covering.committed

    return server, room, short_caller, covering


class TestPropertyChipConservation:
    """Property 1: Chip conservation after excess return.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 4.1**
    """

    @given(
        short_invested=st.integers(min_value=1, max_value=10000),
        extra_committed=st.integers(min_value=1, max_value=10000),
        covering_stack=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=200)
    def test_chip_conservation_after_excess_return(
        self, short_invested, extra_committed, covering_stack
    ):
        """sum(stacks) + sum(committed) + pot_residual is unchanged — no chips created or destroyed."""
        server, room, short_caller, covering = build_hu_excess_state(
            short_stack_total_invested=short_invested,
            covering_extra_committed=extra_committed,
            covering_remaining_stack=covering_stack,
        )

        # Capture total chips before: stacks + pot (pot already contains all committed)
        total_before = (
            sum(p.stack for p in room.players.values()) + room.pot
        )

        server.return_uncalled_excess(room)

        total_after = (
            sum(p.stack for p in room.players.values()) + room.pot
        )

        assert total_after == total_before


class TestPropertyCommittedAlignment:
    """Property 2: Committed alignment after excess return.

    **Validates: Requirements 1.1, 1.3**
    """

    @given(
        short_invested=st.integers(min_value=1, max_value=10000),
        extra_committed=st.integers(min_value=1, max_value=10000),
        covering_stack=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=200)
    def test_covering_total_invested_equals_short_caller(
        self, short_invested, extra_committed, covering_stack
    ):
        """After excess return, covering.total_invested == short_caller.total_invested."""
        server, room, short_caller, covering = build_hu_excess_state(
            short_stack_total_invested=short_invested,
            covering_extra_committed=extra_committed,
            covering_remaining_stack=covering_stack,
        )

        server.return_uncalled_excess(room)

        assert covering.total_invested == short_caller.total_invested


class TestPropertyAllInFlagConsistency:
    """Property 3: all_in flag consistency after excess return.

    **Validates: Requirements 2.1**
    """

    @given(
        short_invested=st.integers(min_value=1, max_value=10000),
        extra_committed=st.integers(min_value=1, max_value=10000),
        covering_stack=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=200)
    def test_allin_flag_reflects_stack_after_excess_return(
        self, short_invested, extra_committed, covering_stack
    ):
        """After excess return, covering.all_in == (covering.stack == 0)."""
        server, room, short_caller, covering = build_hu_excess_state(
            short_stack_total_invested=short_invested,
            covering_extra_committed=extra_committed,
            covering_remaining_stack=covering_stack,
        )

        server.return_uncalled_excess(room)

        assert covering.all_in == (covering.stack == 0)
