from __future__ import annotations

import pytest

from poker.cards import new_deck
from poker.game import PokerServer
from poker.models import Player, Room


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = 1000,
    committed: int = 0,
    total_invested: int = 0,
    cards: list[str] | None = None,
    folded: bool = False,
    all_in: bool = False,
    acted: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        committed=committed,
        cards=cards or ["AS", "AH"],
        folded=folded,
        all_in=all_in,
        acted=acted,
    )
    player.total_invested = total_invested
    player.hand_start_stack = stack + total_invested
    return player


def make_room(*players: Player, phase: str = "preflop", pot: int = 0, current_bet: int = 0) -> Room:
    room = Room(room_id="POT_TEST")
    room.phase = phase
    room.pot = pot
    room.current_bet = current_bet
    room.min_raise = room.big_blind
    room.dealer_seat = players[0].seat if players else None
    room.players = {p.player_id: p for p in players}
    room.deck = new_deck()
    return room


def committed_total(room: Room) -> int:
    return sum(max(0, int(p.committed)) for p in room.seated_players())


def invested_total(room: Room) -> int:
    return sum(max(0, int(p.total_invested)) for p in room.seated_players())


def starting_stack_total(room: Room) -> int:
    return sum(int(p.hand_start_stack) for p in room.seated_players())


def current_stack_total(room: Room) -> int:
    return sum(int(p.stack) for p in room.seated_players())


def settled_pot(room: Room) -> int:
    """Amount already in the middle, excluding current street commitments."""
    return room.pot - committed_total(room)


def assert_active_pot_invariants(room: Room) -> None:
    assert room.pot >= 0
    assert committed_total(room) >= 0
    assert invested_total(room) >= 0

    # During an active hand, the raw pot is the authoritative sum of all chips
    # players have put in so far.
    assert room.pot == invested_total(room)

    # Current street committed chips are a subset of the raw pot.
    assert committed_total(room) <= room.pot
    assert settled_pot(room) >= 0

    # No chips are created or destroyed before awards are paid.
    assert current_stack_total(room) + room.pot == starting_stack_total(room)


def test_current_street_commitments_are_not_settled_pot() -> None:
    server = PokerServer()

    small_blind = make_player("p1", "SmallBlind", seat=1)
    big_blind = make_player("p2", "BigBlind", seat=2)
    button = make_player("p3", "Button", seat=3)

    room = make_room(small_blind, big_blind, button, phase="preflop")

    server.commit_chips(room, small_blind, 5)
    server.commit_chips(room, big_blind, 10)
    room.current_bet = 10

    assert room.pot == 15
    assert committed_total(room) == 15
    assert settled_pot(room) == 0
    assert_active_pot_invariants(room)


@pytest.mark.asyncio
async def test_advancing_street_moves_commitments_into_settled_pot() -> None:
    server = PokerServer()

    small_blind = make_player("p1", "SmallBlind", seat=1)
    big_blind = make_player("p2", "BigBlind", seat=2)
    button = make_player("p3", "Button", seat=3)

    room = make_room(small_blind, big_blind, button, phase="preflop")
    room.community = []
    room.dealer_seat = 1
    room.action_seat = 3

    server.commit_chips(room, small_blind, 5)
    server.commit_chips(room, big_blind, 10)
    room.current_bet = 10

    assert settled_pot(room) == 0

    await server.advance_phase(room)

    assert room.phase == "flop"
    assert committed_total(room) == 0
    assert room.pot == 15
    assert settled_pot(room) == 15
    assert_active_pot_invariants(room)


def test_return_uncalled_excess_preserves_pot_accounting() -> None:
    server = PokerServer()

    covering_player = make_player(
        "p1", "CoveringPlayer", seat=1,
        stack=0, committed=1000, total_invested=1000,
        all_in=True,
    )
    caller_one = make_player(
        "p2", "CallerOne", seat=2,
        stack=600, committed=400, total_invested=400,
    )
    caller_two = make_player(
        "p3", "CallerTwo", seat=3,
        stack=600, committed=400, total_invested=400,
    )

    room = make_room(
        covering_player,
        caller_one,
        caller_two,
        phase="river",
        pot=1800,
        current_bet=1000,
    )

    assert_active_pot_invariants(room)

    server.return_uncalled_excess(room)

    assert covering_player.stack == 600
    assert covering_player.committed == 400
    assert covering_player.total_invested == 400
    assert covering_player.all_in is False

    assert room.pot == 1200
    assert room.current_bet == 400
    assert committed_total(room) == 1200
    assert settled_pot(room) == 0
    assert_active_pot_invariants(room)


def test_folded_player_chips_stay_in_pot_when_excess_is_returned() -> None:
    server = PokerServer()

    covering_player = make_player(
        "p1", "CoveringPlayer", seat=1,
        stack=0, committed=1000, total_invested=1000,
        all_in=True,
    )
    live_shorter_player = make_player(
        "p2", "LiveShorterPlayer", seat=2,
        stack=600, committed=400, total_invested=400,
    )
    folded_investor = make_player(
        "p3", "FoldedInvestor", seat=3,
        stack=300, committed=700, total_invested=700,
        folded=True,
    )

    room = make_room(
        covering_player,
        live_shorter_player,
        folded_investor,
        phase="river",
        pot=2100,
        current_bet=1000,
    )

    assert_active_pot_invariants(room)

    server.return_uncalled_excess(room)

    # Only the unmatched amount above the live opponent's 400 is returned.
    assert covering_player.stack == 600
    assert covering_player.committed == 400
    assert covering_player.total_invested == 400

    # Folded player's contribution is dead money and remains in the pot.
    assert folded_investor.total_invested == 700
    assert folded_investor.committed == 700

    assert room.pot == 1500
    assert room.current_bet == 400
    assert room.pot == 400 + 400 + 700
    assert_active_pot_invariants(room)


def test_showdown_winner_amounts_sum_to_exact_pot() -> None:
    server = PokerServer()

    short_stack_best_hand = make_player(
        "p1", "ShortStackBestHand", seat=1,
        stack=0, committed=0, total_invested=100,
        cards=["AS", "AH"],
        all_in=True,
    )
    side_pot_winner = make_player(
        "p2", "SidePotWinner", seat=2,
        stack=0, committed=0, total_invested=500,
        cards=["KS", "KH"],
        all_in=True,
    )
    side_pot_loser = make_player(
        "p3", "SidePotLoser", seat=3,
        stack=0, committed=0, total_invested=500,
        cards=["QS", "QH"],
        all_in=True,
    )

    room = make_room(
        short_stack_best_hand,
        side_pot_winner,
        side_pot_loser,
        phase="river",
        pot=1100,
        current_bet=0,
    )
    room.community = ["2C", "5D", "9S", "JH", "3C"]

    assert room.pot == invested_total(room)

    server.showdown(room)

    assert room.phase == "showdown"
    assert sum(w.amount for w in room.winners) == 1100

    short_stack_award = next(w.amount for w in room.winners if w.player_id == "p1")
    side_pot_award = next(w.amount for w in room.winners if w.player_id == "p2")

    assert short_stack_award == 300
    assert side_pot_award == 800
    assert short_stack_best_hand.stack == 300
    assert side_pot_winner.stack == 800
    assert side_pot_loser.stack == 0
