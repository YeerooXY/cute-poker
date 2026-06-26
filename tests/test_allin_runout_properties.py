"""Property-based tests for all-in runout fix.

Tests the core correctness properties of:
- return_uncalled_excess (chip conservation, committed alignment, all_in flag)
- should_force_runout predicate
- runout_to_showdown (completeness)
"""

import asyncio
import os

os.environ["POKER_SIMULATION"] = "1"

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck

import poker.game as game_module
from poker.game import PokerServer
from poker.models import Room, Player
from poker.cards import RANKS, SUITS

game_module._SIMULATION_MODE = True


# ─── Helpers ───────────────────────────────────────────────────────────────────

ALL_CARDS = [r + s for s in SUITS for r in RANKS]


def make_server():
    server = PokerServer()
    server.send = server.broadcast = lambda *a, **kw: asyncio.sleep(0)
    return server


# ─── Strategies ────────────────────────────────────────────────────────────────


@st.composite
def runout_room_strategy(draw):
    """Generate a room at preflop/flop/turn where should_force_runout is True.

    For should_force_runout to be True:
    - 2+ contenders (players with cards, not folded)
    - Fewer than 2 players_who_can_bet (not folded, not all-in, has cards, stack > 0)

    This means: at most 1 player can still bet. So among contenders, at most 1
    has (not all_in AND stack > 0).
    """
    # Choose phase
    phase = draw(st.sampled_from(["preflop", "flop", "turn"]))

    # Determine community card count for this phase
    if phase == "preflop":
        community_count = 0
    elif phase == "flop":
        community_count = 3
    else:  # turn
        community_count = 4

    # Number of contenders (players with cards who haven't folded): 2-6
    num_contenders = draw(st.integers(min_value=2, max_value=6))

    # Number of folded players: 0-2
    num_folded = draw(st.integers(min_value=0, max_value=2))

    total_players = num_contenders + num_folded

    # Calculate cards needed:
    # - 2 per player (hole cards) for players with cards (contenders)
    # - community_count cards already dealt
    # - Remaining cards for burn+deal:
    #   From preflop: burn+3 (flop) + burn+1 (turn) + burn+1 (river) = 8
    #   From flop: burn+1 (turn) + burn+1 (river) = 4
    #   From turn: burn+1 (river) = 2
    if phase == "preflop":
        deck_cards_needed = 8
    elif phase == "flop":
        deck_cards_needed = 4
    else:  # turn
        deck_cards_needed = 2

    total_cards_needed = (num_contenders * 2) + community_count + deck_cards_needed

    # We have 52 cards total, so this should always be feasible
    assume(total_cards_needed <= 52)

    # Shuffle all cards and distribute
    shuffled_cards = draw(st.permutations(ALL_CARDS))
    card_idx = 0

    # Deal hole cards to contenders
    player_hands = []
    for i in range(num_contenders):
        hand = [shuffled_cards[card_idx], shuffled_cards[card_idx + 1]]
        player_hands.append(hand)
        card_idx += 2

    # Deal community cards
    community = list(shuffled_cards[card_idx:card_idx + community_count])
    card_idx += community_count

    # Remaining cards form the deck
    deck = list(shuffled_cards[card_idx:])

    # For should_force_runout to be True: at most 1 contender can bet
    # A player can bet if: has cards, not folded, not all_in, stack > 0
    # So among contenders: at most 1 should have (not all_in AND stack > 0)

    # Decide how many contenders can still bet: 0 or 1
    num_can_bet = draw(st.integers(min_value=0, max_value=1))

    # Assign all-in/stack states to contenders
    # Players who cannot bet are all-in (stack == 0)
    # At most num_can_bet players have stack > 0 and not all-in
    contender_states = []
    can_bet_assigned = 0
    for i in range(num_contenders):
        if can_bet_assigned < num_can_bet and i == num_contenders - 1 - (num_can_bet - can_bet_assigned - 1):
            # This player can still bet
            stack = draw(st.integers(min_value=1, max_value=5000))
            contender_states.append({"all_in": False, "stack": stack})
            can_bet_assigned += 1
        else:
            # This player is all-in (cannot bet)
            contender_states.append({"all_in": True, "stack": 0})

    # If we haven't assigned enough can-bet players, fix it
    # (shuffle approach: pick positions for can-bet players)
    if can_bet_assigned < num_can_bet:
        # Reassign: pick specific indices for can-bet players
        pass  # handled above with the index logic

    # Actually, let's use a cleaner approach: shuffle positions
    # First, create all as all-in, then pick num_can_bet to make live
    contender_states = []
    for i in range(num_contenders):
        contender_states.append({"all_in": True, "stack": 0})

    if num_can_bet > 0:
        # Pick which contender(s) can bet
        live_indices = draw(
            st.lists(
                st.integers(min_value=0, max_value=num_contenders - 1),
                min_size=num_can_bet,
                max_size=num_can_bet,
                unique=True,
            )
        )
        for idx in live_indices:
            stack = draw(st.integers(min_value=1, max_value=5000))
            contender_states[idx] = {"all_in": False, "stack": stack}

    # Build the room
    room = Room(room_id="PROP_TEST")
    room.phase = phase
    room.community = community
    room.deck = deck
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = 0
    room.action_seat = None

    seat_num = 1
    # Add contenders
    for i in range(num_contenders):
        state = contender_states[i]
        total_invested = draw(st.integers(min_value=10, max_value=2000))
        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Player{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=state["stack"],
            cards=player_hands[i],
            folded=False,
            all_in=state["all_in"],
            committed=0,
            total_invested=total_invested,
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    # Add folded players (no cards needed for showdown evaluation)
    for i in range(num_folded):
        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Folded{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=draw(st.integers(min_value=0, max_value=5000)),
            cards=[],
            folded=True,
            all_in=False,
            committed=0,
            total_invested=0,
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    return room


# ─── Strategies for Property 4 ─────────────────────────────────────────────────


@st.composite
def force_runout_predicate_room_strategy(draw):
    """Generate a room with 2–8 players having arbitrary folded/all-in/stack states.

    Unlike runout_room_strategy, this does NOT constrain to rooms where
    should_force_runout is True. It generates diverse scenarios covering both
    True and False cases to verify the predicate's correctness.
    """
    num_players = draw(st.integers(min_value=2, max_value=8))

    room = Room(room_id="PROP4_TEST")
    room.phase = "flop"
    room.community = []
    room.deck = []
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = 0
    room.action_seat = None

    for seat_num in range(1, num_players + 1):
        # Randomly decide player state
        has_cards = draw(st.booleans())
        folded = draw(st.booleans())
        is_all_in = draw(st.booleans())
        stack = draw(st.integers(min_value=0, max_value=5000))

        # If all_in, stack should be 0 (realistic constraint)
        if is_all_in:
            stack = 0

        cards = ["Ah", "Kh"] if has_cards else []

        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Player{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=stack,
            cards=cards,
            folded=folded,
            all_in=is_all_in,
            committed=0,
            total_invested=draw(st.integers(min_value=0, max_value=2000)),
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p

    return room


# ─── Property 4: should_force_runout predicate correctness ─────────────────────


class TestForceRunoutPredicate:
    """Property 4: should_force_runout predicate correctness

    For any room with 2 to 8 seated players having arbitrary folded/all-in/stack
    states, should_force_runout SHALL return True if and only if the number of
    contenders (cards and not folded) is at least 2 AND the number of
    Active_Players (not folded, not all-in, stack > 0, have cards) is fewer than 2.

    **Validates: Requirements 3.1, 3.6, 3.7, 3.8**
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=force_runout_predicate_room_strategy())
    def test_should_force_runout_predicate(self, room):
        """**Validates: Requirements 3.1, 3.6, 3.7, 3.8**

        should_force_runout returns True iff contenders >= 2 AND active_players < 2.
        """
        server = make_server()

        # Independently compute expected result
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        active_players = [p for p in contenders if not p.all_in and p.stack > 0]
        expected = len(contenders) >= 2 and len(active_players) < 2

        # Assert predicate matches independent computation
        result = server.should_force_runout(room)
        assert result == expected, (
            f"should_force_runout returned {result}, expected {expected}. "
            f"contenders={len(contenders)}, active_players={len(active_players)}, "
            f"total_players={len(list(room.seated_players()))}"
        )


# ─── Strategies for Property 5 ─────────────────────────────────────────────────


@st.composite
def multiway_noop_room_strategy(draw):
    """Generate a room with 3+ contenders where highest total_invested equals
    the second-highest total_invested, ensuring return_uncalled_excess is a no-op.

    This models the common multiway scenario where no single player has an
    uncalled excess — the function should leave all state unchanged.
    """
    num_contenders = draw(st.integers(min_value=3, max_value=6))
    num_folded = draw(st.integers(min_value=0, max_value=2))

    # All contenders share the same total_invested so excess == 0
    shared_invested = draw(st.integers(min_value=10, max_value=2000))

    # Build the room
    room = Room(room_id="PROP5_TEST")
    room.phase = draw(st.sampled_from(["preflop", "flop", "turn", "river"]))
    room.community = []
    room.deck = []
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = draw(st.integers(min_value=0, max_value=500))
    room.action_seat = None

    seat_num = 1
    for i in range(num_contenders):
        # Mix of all-in and live players
        is_all_in = draw(st.booleans())
        stack = 0 if is_all_in else draw(st.integers(min_value=1, max_value=5000))
        committed = draw(st.integers(min_value=0, max_value=shared_invested))
        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Player{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=stack,
            cards=["Ah", "Kh"],  # Placeholder cards — not evaluated
            folded=False,
            all_in=is_all_in,
            committed=committed,
            total_invested=shared_invested,
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    # Add folded players
    for i in range(num_folded):
        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Folded{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=draw(st.integers(min_value=0, max_value=5000)),
            cards=[],
            folded=True,
            all_in=False,
            committed=0,
            total_invested=draw(st.integers(min_value=0, max_value=1000)),
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    return room


# ─── Property 5: Excess return is no-op for multiway hands ────────────────────


class TestMultiwayNoop:
    """Property 5: Excess return is no-op for multiway hands

    When 3+ contenders all share the same highest total_invested (so excess <= 0),
    return_uncalled_excess SHALL leave all player fields and room.pot unchanged.

    **Validates: Requirements 1.5**
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=multiway_noop_room_strategy())
    def test_multiway_noop(self, room):
        """**Validates: Requirements 1.5**

        When all contenders have equal total_invested, return_uncalled_excess
        must not mutate any player fields or room.pot.
        """
        server = make_server()

        # Snapshot state before
        pot_before = room.pot
        current_bet_before = room.current_bet
        player_snapshots = {}
        for pid, p in room.players.items():
            player_snapshots[pid] = {
                "stack": p.stack,
                "committed": p.committed,
                "total_invested": p.total_invested,
                "all_in": p.all_in,
                "folded": p.folded,
            }

        # Act
        server.return_uncalled_excess(room)

        # Assert: room.pot unchanged
        assert room.pot == pot_before, (
            f"room.pot changed from {pot_before} to {room.pot}"
        )

        # Assert: room.current_bet unchanged
        assert room.current_bet == current_bet_before, (
            f"room.current_bet changed from {current_bet_before} to {room.current_bet}"
        )

        # Assert: all player fields unchanged
        for pid, snap in player_snapshots.items():
            p = room.players[pid]
            assert p.stack == snap["stack"], (
                f"{pid}: stack changed from {snap['stack']} to {p.stack}"
            )
            assert p.committed == snap["committed"], (
                f"{pid}: committed changed from {snap['committed']} to {p.committed}"
            )
            assert p.total_invested == snap["total_invested"], (
                f"{pid}: total_invested changed from {snap['total_invested']} to {p.total_invested}"
            )
            assert p.all_in == snap["all_in"], (
                f"{pid}: all_in changed from {snap['all_in']} to {p.all_in}"
            )
            assert p.folded == snap["folded"], (
                f"{pid}: folded changed from {snap['folded']} to {p.folded}"
            )


# ─── Property 6: Runout completeness ──────────────────────────────────────────


class TestRunoutCompleteness:
    """Property 6: Runout completeness

    For any room at any pre-showdown phase (preflop, flop, or turn) where
    should_force_runout returns True, after runout_to_showdown completes,
    len(room.community) SHALL equal 5, room.phase SHALL be "showdown",
    and room.action_seat SHALL be None.

    **Validates: Requirements 3.1, 3.3, 3.4, 3.5**
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=runout_room_strategy())
    def test_runout_completeness(self, room):
        """**Validates: Requirements 3.1, 3.3, 3.4, 3.5**

        After runout_to_showdown completes on a room where should_force_runout
        is True: community == 5 cards, phase == "showdown", action_seat == None.
        """
        server = make_server()

        # Precondition: should_force_runout must be True
        assert server.should_force_runout(room), (
            f"Precondition failed: should_force_runout is False for phase={room.phase}, "
            f"contenders={len([p for p in room.seated_players() if p.cards and not p.folded])}, "
            f"can_bet={len(server.players_who_can_bet(room))}"
        )

        # Run the async method
        asyncio.run(server.runout_to_showdown(room))

        # Assert: community has exactly 5 cards
        assert len(room.community) == 5, (
            f"Expected 5 community cards, got {len(room.community)} "
            f"(phase started as {room.phase})"
        )

        # Assert: phase is showdown
        assert room.phase == "showdown", (
            f"Expected phase='showdown', got '{room.phase}'"
        )

        # Assert: action_seat is None
        assert room.action_seat is None, (
            f"Expected action_seat=None, got {room.action_seat}"
        )
