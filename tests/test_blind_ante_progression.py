from __future__ import annotations

import json

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


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
        ws=DummyWs(),
    )


def make_room(*players: Player, dealer_seat: int | None = None) -> Room:
    room = Room(room_id="BLIND_ANTE_TEST")
    room.phase = "lobby"
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    room.dealer_seat = dealer_seat
    return room


def action_entries(room: Room, action: str) -> list[dict]:
    return [entry for entry in room.action_log if entry.get("action") == action]


@pytest.mark.asyncio
async def test_classic_ante_posts_from_each_active_player_before_blinds() -> None:
    server = PokerServer()

    dealer = make_player("p1", "Dealer", seat=1)
    small_blind = make_player("p2", "SmallBlind", seat=2)
    big_blind = make_player("p3", "BigBlind", seat=3)
    room = make_room(dealer, small_blind, big_blind)
    room.ante = 5
    room.ante_mode = "classic"

    await server.start_hand(room)

    assert room.phase == "preflop"

    ante_entries = action_entries(room, "ante")
    assert [(entry["player"], entry["amount"]) for entry in ante_entries] == [
        ("Dealer", 5),
        ("SmallBlind", 5),
        ("BigBlind", 5),
    ]

    assert room.action_log[3]["action"] == "small_blind"
    assert room.action_log[4]["action"] == "big_blind"

    assert dealer.committed == 5
    assert small_blind.committed == 5 + room.small_blind
    assert big_blind.committed == 5 + room.big_blind

    assert dealer.stack == 1000 - 5
    assert small_blind.stack == 1000 - 5 - room.small_blind
    assert big_blind.stack == 1000 - 5 - room.big_blind

    assert room.pot == (3 * 5) + room.small_blind + room.big_blind
    assert room.current_bet == 5 + room.big_blind


@pytest.mark.asyncio
async def test_classic_ante_skips_spectators_sitting_out_and_zero_stack_players() -> None:
    server = PokerServer()

    active_one = make_player("p1", "ActiveOne", seat=1)
    spectator = make_player("p2", "Spectator", seat=2, is_spectator=True)
    sitting_out = make_player("p3", "SittingOut", seat=3, sitting_out=True)
    busted = make_player("p4", "Busted", seat=4, stack=0)
    active_two = make_player("p5", "ActiveTwo", seat=5)

    room = make_room(active_one, spectator, sitting_out, busted, active_two)
    room.ante = 7
    room.ante_mode = "classic"

    await server.start_hand(room)

    ante_entries = action_entries(room, "ante")
    assert [(entry["player"], entry["amount"]) for entry in ante_entries] == [
        ("ActiveOne", 7),
        ("ActiveTwo", 7),
    ]

    assert spectator.committed == 0
    assert sitting_out.committed == 0
    assert busted.committed == 0

    assert spectator.cards == []
    assert sitting_out.cards == []
    assert busted.cards == []


@pytest.mark.asyncio
async def test_big_blind_ante_posts_from_big_blind_not_dealer() -> None:
    server = PokerServer()

    dealer = make_player("p1", "Dealer", seat=1)
    small_blind = make_player("p2", "SmallBlind", seat=2)
    big_blind = make_player("p3", "BigBlind", seat=3)

    room = make_room(dealer, small_blind, big_blind)
    room.ante = 1
    room.ante_mode = "bba"

    await server.start_hand(room)

    assert room.dealer_seat == 1
    assert room.sb_seat == 2
    assert room.bb_seat == 3

    bba_entries = action_entries(room, "big_blind_ante")
    assert [(entry["player"], entry["amount"]) for entry in bba_entries] == [
        ("BigBlind", room.big_blind),
    ]

    assert dealer.committed == 0
    assert small_blind.committed == room.small_blind
    assert big_blind.committed == room.big_blind + room.big_blind

    assert dealer.stack == 1000
    assert small_blind.stack == 1000 - room.small_blind
    assert big_blind.stack == 1000 - (2 * room.big_blind)

    assert room.pot == room.small_blind + room.big_blind + room.big_blind

    # The table ante is dead money, not part of the live bet others must call.
    assert room.current_bet == room.big_blind
    assert room.current_bet - dealer.committed == room.big_blind
    assert room.current_bet - small_blind.committed == room.big_blind - room.small_blind
    assert room.current_bet - big_blind.committed <= 0


@pytest.mark.asyncio
async def test_short_big_blind_ante_and_blind_are_capped_by_stack() -> None:
    server = PokerServer()

    dealer = make_player("p1", "Dealer", seat=1, stack=1000)
    small_blind = make_player("p2", "SmallBlind", seat=2, stack=1000)
    big_blind = make_player("p3", "ShortBigBlind", seat=3, stack=35)

    room = make_room(dealer, small_blind, big_blind)
    room.small_blind = 15
    room.big_blind = 30
    room.min_raise = 30
    room.ante = 1
    room.ante_mode = "bba"

    await server.start_hand(room)

    assert room.bb_seat == 3

    bba_entries = action_entries(room, "big_blind_ante")
    bb_entries = action_entries(room, "big_blind")

    assert bba_entries[0]["player"] == "ShortBigBlind"
    assert bba_entries[0]["amount"] == 30
    assert bba_entries[0]["is_all_in"] is False

    assert bb_entries[0]["player"] == "ShortBigBlind"
    assert bb_entries[0]["amount"] == 5
    assert bb_entries[0]["is_all_in"] is True

    assert big_blind.stack == 0
    assert big_blind.committed == 35
    assert big_blind.total_invested == 35
    assert big_blind.all_in is True

    assert room.pot == room.small_blind + 35
    # Only the actually posted blind portion is live; BBA remains dead money.
    assert room.current_bet == 5
    assert room.current_bet - dealer.committed == 5
    assert room.current_bet - small_blind.committed <= 0
    assert room.current_bet - big_blind.committed <= 0


@pytest.mark.asyncio
async def test_blind_level_increases_after_configured_number_of_hands_for_next_hand() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)
    room.blind_increase_hands = 1

    starting_small_blind = room.small_blind
    starting_big_blind = room.big_blind

    await server.start_hand(room)

    # Blinds posted for this hand use the level that was active at hand start.
    assert action_entries(room, "small_blind")[0]["amount"] == starting_small_blind
    assert action_entries(room, "big_blind")[0]["amount"] == starting_big_blind

    # After the hand count increments, the next level is ready for the next hand.
    assert room.hands_played == 1
    assert room.current_blind_level == 1
    assert room.small_blind == room.blind_levels[1][0]
    assert room.big_blind == room.blind_levels[1][1]
    assert room.min_raise == room.blind_levels[1][1]

    assert room.messages[-1].name == "⚡ Blinds Up"
    assert f"Level {room.current_blind_level}" in room.messages[-1].text
    assert f"blinds now {room.small_blind}/{room.big_blind}" in room.messages[-1].text


@pytest.mark.asyncio
async def test_auto_ante_scales_when_blinds_increase() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)
    room.blind_increase_hands = 1
    room.auto_ante = True
    room.ante = 1
    room.ante_mode = "classic"

    await server.start_hand(room)

    next_big_blind = room.blind_levels[1][1]

    assert room.current_blind_level == 1
    assert room.big_blind == next_big_blind
    assert room.ante == max(1, next_big_blind // 10)

    assert room.messages[-1].name == "⚡ Blinds Up"
    assert f"ante {room.ante}" in room.messages[-1].text


@pytest.mark.asyncio
async def test_auto_ante_can_scale_from_zero_when_blinds_increase() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)
    room.blind_increase_hands = 1
    room.auto_ante = True
    room.ante = 0
    room.ante_mode = "classic"

    await server.start_hand(room)

    next_big_blind = room.blind_levels[1][1]

    assert room.current_blind_level == 1
    assert room.big_blind == next_big_blind
    assert room.ante == max(1, next_big_blind // 10)


@pytest.mark.asyncio
async def test_auto_ante_disabled_keeps_zero_ante_when_blinds_increase() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)
    room.blind_increase_hands = 1
    room.auto_ante = False
    room.ante = 0
    room.ante_mode = "classic"

    await server.start_hand(room)

    assert room.current_blind_level == 1
    assert room.ante == 0
