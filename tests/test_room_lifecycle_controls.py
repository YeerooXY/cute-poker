from __future__ import annotations

import json

import pytest

from poker.game import PokerServer, STARTING_STACK
from poker.models import Player, Room, Winner


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def error_messages(ws: DummyWs) -> list[str]:
    return [
        message["payload"]["message"]
        for message in ws.sent
        if message.get("event") == "error"
    ]


def state_messages(ws: DummyWs) -> list[dict]:
    return [
        message["payload"]
        for message in ws.sent
        if message.get("event") == "state"
    ]


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = STARTING_STACK,
    sitting_out: bool = False,
    is_spectator: bool = False,
    connected: bool = True,
) -> Player:
    ws = DummyWs()
    return Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        sitting_out=sitting_out,
        is_spectator=is_spectator,
        connected=connected,
        ws=ws,
    )


def make_room(
    *players: Player,
    phase: str = "lobby",
    creator: Player | None = None,
) -> Room:
    room = Room(room_id="LIFECYCLE_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = creator.token if creator else (players[0].token if players else "")
    return room


def player_ws(player: Player) -> DummyWs:
    assert isinstance(player.ws, DummyWs)
    return player.ws


@pytest.mark.asyncio
async def test_start_hand_requires_at_least_two_active_players_with_chips() -> None:
    server = PokerServer()

    active = make_player("p1", "Active", seat=1, stack=STARTING_STACK)
    spectator = make_player("p2", "Spectator", seat=2, is_spectator=True)
    sitting_out = make_player("p3", "SittingOut", seat=3, sitting_out=True)
    busted = make_player("p4", "Busted", seat=4, stack=0)

    room = make_room(active, spectator, sitting_out, busted)

    await server.start_hand(room)

    assert room.phase == "lobby"
    assert room.pot == 0
    assert room.community == []
    assert active.cards == []
    assert spectator.cards == []
    assert sitting_out.cards == []
    assert busted.cards == []

    assert "Need at least two active players with chips." in error_messages(player_ws(active))
    assert "Need at least two active players with chips." in error_messages(player_ws(spectator))
    assert "Need at least two active players with chips." in error_messages(player_ws(sitting_out))
    assert "Need at least two active players with chips." in error_messages(player_ws(busted))


@pytest.mark.asyncio
async def test_start_hand_skips_spectators_sitting_out_and_zero_stack_players() -> None:
    server = PokerServer()

    active_one = make_player("p1", "ActiveOne", seat=1, stack=STARTING_STACK)
    spectator = make_player("p2", "Spectator", seat=2, is_spectator=True)
    sitting_out = make_player("p3", "SittingOut", seat=3, sitting_out=True)
    busted = make_player("p4", "Busted", seat=4, stack=0)
    active_two = make_player("p5", "ActiveTwo", seat=5, stack=STARTING_STACK)

    room = make_room(active_one, spectator, sitting_out, busted, active_two)

    await server.start_hand(room)

    assert room.phase == "preflop"

    assert len(active_one.cards) == 2
    assert len(active_two.cards) == 2

    assert spectator.cards == []
    assert sitting_out.cards == []
    assert busted.cards == []

    assert spectator.committed == 0
    assert sitting_out.committed == 0
    assert busted.committed == 0

    assert room.sb_seat in {1, 5}
    assert room.bb_seat in {1, 5}
    assert room.sb_seat != room.bb_seat
    assert room.action_seat in {1, 5}


@pytest.mark.asyncio
async def test_creator_cannot_start_hand_while_game_is_paused() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1)
    guest = make_player("p2", "Guest", seat=2)
    room = make_room(creator, guest, creator=creator)
    room.paused = True

    await server.player_action(room, creator, "start_hand", {})

    assert "Game is paused." in error_messages(player_ws(creator))
    assert room.phase == "lobby"
    assert creator.cards == []
    assert guest.cards == []


@pytest.mark.asyncio
async def test_reset_stacks_is_rejected_during_active_hand() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1, stack=750)
    guest = make_player("p2", "Guest", seat=2, stack=525)
    room = make_room(creator, guest, phase="flop", creator=creator)
    room.pot = 300
    room.community = ["2C", "5D", "9S"]

    await server.player_action(room, creator, "reset_stacks", {})

    assert "Reset stacks between hands only." in error_messages(player_ws(creator))
    assert creator.stack == 750
    assert guest.stack == 525
    assert room.phase == "flop"
    assert room.pot == 300
    assert room.community == ["2C", "5D", "9S"]


@pytest.mark.asyncio
async def test_reset_stacks_between_hands_resets_non_spectators_and_room_state() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1, stack=125)
    guest = make_player("p2", "Guest", seat=2, stack=220)
    spectator = make_player("p3", "Spectator", seat=3, stack=0, is_spectator=True)

    room = make_room(creator, guest, spectator, phase="showdown", creator=creator)
    room.pot = 600
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.winners = [Winner(creator.player_id, creator.name, 600, "Best hand at showdown")]

    await server.player_action(room, creator, "reset_stacks", {})

    assert error_messages(player_ws(creator)) == []

    assert room.phase == "lobby"
    assert room.pot == 0
    assert room.community == []
    assert room.winners == []

    assert creator.stack == STARTING_STACK
    assert guest.stack == STARTING_STACK

    # Spectators remain spectators and do not get a playing stack.
    assert spectator.is_spectator is True
    assert spectator.stack == 0


@pytest.mark.asyncio
async def test_spectate_toggle_is_rejected_during_active_hand() -> None:
    server = PokerServer()

    player = make_player("p1", "Player", seat=1)
    other = make_player("p2", "Other", seat=2)
    room = make_room(player, other, phase="turn")

    await server.player_action(room, player, "spectate", {})

    assert "Can only toggle spectate between hands." in error_messages(player_ws(player))
    assert player.is_spectator is False
    assert player.stack == STARTING_STACK


@pytest.mark.asyncio
async def test_spectate_toggle_between_hands_sets_zero_stack_and_clears_cards() -> None:
    server = PokerServer()

    player = make_player("p1", "Player", seat=1)
    other = make_player("p2", "Other", seat=2)
    room = make_room(player, other, phase="lobby")

    player.cards = ["AS", "AH"]

    await server.player_action(room, player, "spectate", {})

    assert error_messages(player_ws(player)) == []
    assert player.is_spectator is True
    assert player.stack == 0
    assert player.cards == []


@pytest.mark.asyncio
async def test_spectator_toggle_back_restores_starting_stack_between_hands() -> None:
    server = PokerServer()

    spectator = make_player("p1", "Spectator", seat=1, stack=0, is_spectator=True)
    other = make_player("p2", "Other", seat=2)
    room = make_room(spectator, other, phase="showdown")

    await server.player_action(room, spectator, "spectate", {})

    assert error_messages(player_ws(spectator)) == []
    assert spectator.is_spectator is False
    assert spectator.stack == STARTING_STACK


@pytest.mark.asyncio
async def test_toggle_pause_is_creator_only_and_does_not_need_active_hand() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1)
    guest = make_player("p2", "Guest", seat=2)
    room = make_room(creator, guest, phase="lobby", creator=creator)

    await server.player_action(room, guest, "toggle_pause", {})
    assert "Only the room creator can pause." in error_messages(player_ws(guest))
    assert room.paused is False

    await server.player_action(room, creator, "toggle_pause", {})
    assert error_messages(player_ws(creator)) == []
    assert room.paused is True

    await server.player_action(room, creator, "toggle_pause", {})
    assert room.paused is False


@pytest.mark.asyncio
async def test_successful_start_hand_broadcasts_state_to_connected_players() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1)
    guest = make_player("p2", "Guest", seat=2)
    room = make_room(creator, guest, phase="lobby", creator=creator)

    await server.player_action(room, creator, "start_hand", {})

    assert room.phase == "preflop"
    assert state_messages(player_ws(creator))
    assert state_messages(player_ws(guest))
