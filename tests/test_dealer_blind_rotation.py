from __future__ import annotations

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = 1000,
    sitting_out: bool = False,
    is_spectator: bool = False,
) -> Player:
    return Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        sitting_out=sitting_out,
        is_spectator=is_spectator,
        connected=True,
    )


def make_room(*players: Player, dealer_seat: int | None = None) -> Room:
    room = Room(room_id="BLIND_TEST")
    room.phase = "lobby"
    room.players = {p.player_id: p for p in players}
    room.dealer_seat = dealer_seat
    return room


def player_by_seat(room: Room, seat: int) -> Player:
    player = next((p for p in room.players.values() if p.seat == seat), None)
    assert player is not None
    return player


@pytest.mark.asyncio
async def test_heads_up_dealer_posts_small_blind() -> None:
    server = PokerServer()

    p1 = make_player("p1", "PlayerOne", seat=1)
    p2 = make_player("p2", "PlayerTwo", seat=2)
    room = make_room(p1, p2)

    await server.start_hand(room)

    assert room.phase == "preflop"
    assert room.dealer_seat == 1
    assert room.sb_seat == 1
    assert room.bb_seat == 2
    assert room.action_seat == 1

    assert p1.committed == room.small_blind
    assert p2.committed == room.big_blind
    assert p1.stack == 1000 - room.small_blind
    assert p2.stack == 1000 - room.big_blind
    assert room.pot == room.small_blind + room.big_blind
    assert room.current_bet == room.big_blind


@pytest.mark.asyncio
async def test_three_player_first_hand_blinds_and_action_order() -> None:
    server = PokerServer()

    dealer = make_player("p1", "Dealer", seat=1)
    small_blind = make_player("p2", "SmallBlind", seat=2)
    big_blind = make_player("p3", "BigBlind", seat=3)
    room = make_room(dealer, small_blind, big_blind)

    await server.start_hand(room)

    assert room.dealer_seat == 1
    assert room.sb_seat == 2
    assert room.bb_seat == 3

    # Preflop action starts left of the big blind, wrapping to the dealer.
    assert room.action_seat == 1

    assert small_blind.committed == room.small_blind
    assert big_blind.committed == room.big_blind
    assert dealer.committed == 0
    assert room.pot == room.small_blind + room.big_blind


@pytest.mark.asyncio
async def test_dealer_rotates_on_next_hand() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)
    room = make_room(p1, p2, p3)

    await server.start_hand(room)

    assert room.dealer_seat == 1
    assert room.sb_seat == 2
    assert room.bb_seat == 3
    assert room.action_seat == 1

    room.phase = "showdown"

    await server.start_hand(room)

    assert room.dealer_seat == 2
    assert room.sb_seat == 3
    assert room.bb_seat == 1
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_dealer_and_blinds_skip_sitting_out_and_spectators() -> None:
    server = PokerServer()

    active_one = make_player("p1", "ActiveOne", seat=1)
    sitting_out = make_player("p2", "SittingOut", seat=2, sitting_out=True)
    spectator = make_player("p3", "Spectator", seat=3, is_spectator=True)
    active_two = make_player("p4", "ActiveTwo", seat=4)
    active_three = make_player("p5", "ActiveThree", seat=5)

    # Previous dealer was seat 1. Next active dealer should be seat 4,
    # skipping seat 2 sitting out and seat 3 spectator.
    room = make_room(
        active_one,
        sitting_out,
        spectator,
        active_two,
        active_three,
        dealer_seat=1,
    )

    await server.start_hand(room)

    assert room.dealer_seat == 4
    assert room.sb_seat == 5
    assert room.bb_seat == 1
    assert room.action_seat == 4

    assert active_two.committed == 0
    assert active_three.committed == room.small_blind
    assert active_one.committed == room.big_blind

    assert sitting_out.cards == []
    assert spectator.cards == []
    assert sitting_out.committed == 0
    assert spectator.committed == 0


@pytest.mark.asyncio
async def test_dealer_and_blinds_skip_zero_stack_players() -> None:
    server = PokerServer()

    previous_dealer = make_player("p1", "PreviousDealer", seat=1)
    busted = make_player("p2", "Busted", seat=2, stack=0)
    next_dealer = make_player("p3", "NextDealer", seat=3)
    next_small_blind = make_player("p4", "NextSmallBlind", seat=4)

    room = make_room(previous_dealer, busted, next_dealer, next_small_blind, dealer_seat=1)

    await server.start_hand(room)

    assert room.dealer_seat == 3
    assert room.sb_seat == 4
    assert room.bb_seat == 1
    assert room.action_seat == 3

    assert busted.cards == []
    assert busted.committed == 0
    assert next_small_blind.committed == room.small_blind
    assert previous_dealer.committed == room.big_blind


@pytest.mark.asyncio
async def test_full_eight_seat_room_keeps_capacity_but_skips_inactive_for_hand() -> None:
    server = PokerServer()

    p1 = make_player("p1", "ActiveOne", seat=1)
    p2 = make_player("p2", "SittingOutTwo", seat=2, sitting_out=True)
    p3 = make_player("p3", "SpectatorThree", seat=3, is_spectator=True)
    p4 = make_player("p4", "ActiveFour", seat=4)
    p5 = make_player("p5", "ZeroStackFive", seat=5, stack=0)
    p6 = make_player("p6", "SpectatorSix", seat=6, is_spectator=True)
    p7 = make_player("p7", "SittingOutSeven", seat=7, sitting_out=True)
    p8 = make_player("p8", "ActiveEight", seat=8)

    room = make_room(p1, p2, p3, p4, p5, p6, p7, p8, dealer_seat=1)

    # Capacity still means 8 occupied seats.
    assert len(room.players) == 8
    assert server.find_free_seat(room) is None

    await server.start_hand(room)

    # Dealer/blinds skip inactive occupied seats, but do not remove them.
    assert room.dealer_seat == 4
    assert room.sb_seat == 8
    assert room.bb_seat == 1
    assert room.action_seat == 4

    active_with_cards = {p.seat for p in room.players.values() if p.cards}
    assert active_with_cards == {1, 4, 8}

    inactive_seats = {2, 3, 5, 6, 7}
    for seat in inactive_seats:
        player = player_by_seat(room, seat)
        assert player.cards == []
        assert player.committed == 0

    assert p8.committed == room.small_blind
    assert p1.committed == room.big_blind
    assert p4.committed == 0
    assert room.pot == room.small_blind + room.big_blind

