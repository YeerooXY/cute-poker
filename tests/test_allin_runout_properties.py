"""Property-based tests for all-in runout behavior.

These tests focus on the core correctness properties around forced runout,
showdown completion, and uncalled-excess refunds.
"""

import asyncio
import os

os.environ["POKER_SIMULATION"] = "1"

from hypothesis import HealthCheck, assume, given, settings, strategies as st

import poker.game as game_module
from poker.cards import RANKS, SUITS
from poker.game import PokerServer
from poker.models import Player, Room

game_module._SIMULATION_MODE = True


ALL_CARDS = [rank + suit for suit in SUITS for rank in RANKS]


def make_server():
    server = PokerServer()
    server.send = server.broadcast = lambda *a, **kw: asyncio.sleep(0)
    return server


@st.composite
def runout_room_strategy(draw):
    """Generate a pre-showdown room where should_force_runout is true."""
    phase = draw(st.sampled_from(["preflop", "flop", "turn"]))
    community_count = {"preflop": 0, "flop": 3, "turn": 4}[phase]
    deck_cards_needed = {"preflop": 8, "flop": 4, "turn": 2}[phase]

    num_contenders = draw(st.integers(min_value=2, max_value=6))
    num_folded = draw(st.integers(min_value=0, max_value=2))
    assume((num_contenders * 2) + community_count + deck_cards_needed <= 52)

    shuffled_cards = draw(st.permutations(ALL_CARDS))
    card_idx = 0

    player_hands = []
    for _ in range(num_contenders):
        player_hands.append([shuffled_cards[card_idx], shuffled_cards[card_idx + 1]])
        card_idx += 2

    community = list(shuffled_cards[card_idx:card_idx + community_count])
    card_idx += community_count
    deck = list(shuffled_cards[card_idx:])

    num_can_bet = draw(st.integers(min_value=0, max_value=1))
    contender_states = [{"all_in": True, "stack": 0} for _ in range(num_contenders)]
    if num_can_bet:
        live_indices = draw(
            st.lists(
                st.integers(min_value=0, max_value=num_contenders - 1),
                min_size=num_can_bet,
                max_size=num_can_bet,
                unique=True,
            )
        )
        for idx in live_indices:
            contender_states[idx] = {
                "all_in": False,
                "stack": draw(st.integers(min_value=1, max_value=5000)),
            }

    room = Room(room_id="PROP_TEST")
    room.phase = phase
    room.community = community
    room.deck = deck
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = 0
    room.action_seat = None

    seat_num = 1
    for i, state in enumerate(contender_states):
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

    for _ in range(num_folded):
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


@st.composite
def force_runout_predicate_room_strategy(draw):
    """Generate arbitrary seated-player states for the runout predicate."""
    num_players = draw(st.integers(min_value=2, max_value=8))

    room = Room(room_id="PROP4_TEST")
    room.phase = "flop"
    room.community = []
    room.deck = []
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = 0
    room.action_seat = None

    for seat_num in range(1, num_players + 1):
        has_cards = draw(st.booleans())
        folded = draw(st.booleans())
        is_all_in = draw(st.booleans())
        stack = 0 if is_all_in else draw(st.integers(min_value=0, max_value=5000))
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


class TestForceRunoutPredicate:
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=force_runout_predicate_room_strategy())
    def test_should_force_runout_predicate(self, room):
        server = make_server()

        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        active_players = [p for p in contenders if not p.all_in and p.stack > 0]
        expected = len(contenders) >= 2 and len(active_players) < 2

        result = server.should_force_runout(room)
        assert result == expected, (
            f"should_force_runout returned {result}, expected {expected}. "
            f"contenders={len(contenders)}, active_players={len(active_players)}, "
            f"total_players={len(list(room.seated_players()))}"
        )


@st.composite
def multiway_noop_room_strategy(draw):
    """Generate a multiway room with no unique current-street overcommit.

    return_uncalled_excess is now intentionally based on current-street committed
    chips. Equal total_invested alone is not enough for this no-op property, so
    every live contender also gets the same current-street committed amount.
    """
    num_contenders = draw(st.integers(min_value=3, max_value=6))
    num_folded = draw(st.integers(min_value=0, max_value=2))

    shared_invested = draw(st.integers(min_value=10, max_value=2000))
    shared_committed = draw(st.integers(min_value=0, max_value=shared_invested))

    room = Room(room_id="PROP5_TEST")
    room.phase = draw(st.sampled_from(["preflop", "flop", "turn", "river"]))
    room.community = []
    room.deck = []
    room.pot = draw(st.integers(min_value=20, max_value=10000))
    room.current_bet = shared_committed
    room.action_seat = None

    seat_num = 1
    for _ in range(num_contenders):
        is_all_in = draw(st.booleans())
        stack = 0 if is_all_in else draw(st.integers(min_value=1, max_value=5000))
        p = Player(
            player_id=f"p{seat_num}",
            token=f"t{seat_num}",
            name=f"Player{seat_num}",
            seat=seat_num,
            ws=None,
            connected=True,
            stack=stack,
            cards=["Ah", "Kh"],
            folded=False,
            all_in=is_all_in,
            committed=shared_committed,
            total_invested=shared_invested,
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    for _ in range(num_folded):
        folded_invested = draw(st.integers(min_value=0, max_value=1000))
        folded_committed = draw(st.integers(min_value=0, max_value=folded_invested))
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
            committed=folded_committed,
            total_invested=folded_invested,
            acted=False,
            avatar="X",
        )
        room.players[p.player_id] = p
        seat_num += 1

    return room


class TestMultiwayNoop:
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=multiway_noop_room_strategy())
    def test_multiway_noop(self, room):
        server = make_server()

        pot_before = room.pot
        current_bet_before = room.current_bet
        player_snapshots = {
            pid: {
                "stack": p.stack,
                "committed": p.committed,
                "total_invested": p.total_invested,
                "all_in": p.all_in,
                "folded": p.folded,
            }
            for pid, p in room.players.items()
        }

        server.return_uncalled_excess(room)

        assert room.pot == pot_before, f"room.pot changed from {pot_before} to {room.pot}"
        assert room.current_bet == current_bet_before, (
            f"room.current_bet changed from {current_bet_before} to {room.current_bet}"
        )

        for pid, snap in player_snapshots.items():
            p = room.players[pid]
            assert p.stack == snap["stack"], f"{pid}: stack changed from {snap['stack']} to {p.stack}"
            assert p.committed == snap["committed"], (
                f"{pid}: committed changed from {snap['committed']} to {p.committed}"
            )
            assert p.total_invested == snap["total_invested"], (
                f"{pid}: total_invested changed from {snap['total_invested']} to {p.total_invested}"
            )
            assert p.all_in == snap["all_in"], f"{pid}: all_in changed from {snap['all_in']} to {p.all_in}"
            assert p.folded == snap["folded"], f"{pid}: folded changed from {snap['folded']} to {p.folded}"


class TestRunoutCompleteness:
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(room=runout_room_strategy())
    def test_runout_completeness(self, room):
        server = make_server()

        assert server.should_force_runout(room), (
            f"Precondition failed: should_force_runout is False for phase={room.phase}, "
            f"contenders={len([p for p in room.seated_players() if p.cards and not p.folded])}, "
            f"can_bet={len(server.players_who_can_bet(room))}"
        )

        asyncio.run(server.runout_to_showdown(room))

        assert len(room.community) == 5, (
            f"Expected 5 community cards, got {len(room.community)} "
            f"(phase started as {room.phase})"
        )
        assert room.phase == "showdown", f"Expected phase='showdown', got '{room.phase}'"
        assert room.action_seat is None, f"Expected action_seat=None, got {room.action_seat}"
