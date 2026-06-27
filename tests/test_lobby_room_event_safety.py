from __future__ import annotations

import json

import pytest

from poker.game import MAX_SEATS, PokerServer, STARTING_STACK
from poker.models import Player, Room


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class BrokenWs:
    async def send_text(self, _text: str) -> None:
        raise RuntimeError("simulated websocket failure")


def messages(ws: DummyWs, event: str) -> list[dict]:
    return [
        message["payload"]
        for message in ws.sent
        if message.get("event") == event
    ]


def make_player(
    player_id: str,
    name: str,
    seat: int,
    connected: bool = True,
    ws=None,
) -> Player:
    return Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=STARTING_STACK,
        connected=connected,
        ws=ws if ws is not None else (DummyWs() if connected else None),
    )


def make_room(*players: Player, room_id: str = "LOBBY_TEST") -> Room:
    room = Room(room_id=room_id)
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    return room


@pytest.mark.asyncio
async def test_create_room_applies_settings_and_sanitizes_creator_identity() -> None:
    server = PokerServer()
    ws = DummyWs()

    result = await server.create_room(
        ws,
        {
            "name": "   ",
            "avatar": "🎲🎲🎲🎲🎲",
            "blind_increase_hands": 3,
            "ante": 2,
            "ante_mode": "BBA",
            "auto_ante": True,
            "allow_folded_reveals": False,
        },
    )

    assert result.room_id is not None
    assert result.player_token is not None

    room = server.rooms[result.room_id]
    creator = next(iter(room.players.values()))

    assert room.creator_token == creator.token
    assert creator.token == result.player_token
    assert creator.seat == 1
    assert creator.stack == STARTING_STACK

    # Blank names fall back to "Player <seat>"; avatars are trimmed defensively.
    assert creator.name == "Player 1"
    assert creator.avatar == "🎲🎲🎲🎲"

    assert room.blind_increase_hands == 3
    assert room.ante == 2
    assert room.ante_mode == "bba"
    assert room.auto_ante is True
    assert room.allow_folded_reveals is False

    joined = messages(ws, "joined")
    states = messages(ws, "state")

    assert joined == [
        {
            "room_id": room.room_id,
            "player_id": creator.player_id,
            "token": creator.token,
        }
    ]
    assert states
    assert states[-1]["room_id"] == room.room_id
    assert states[-1]["viewer"]["is_admin"] is True


@pytest.mark.asyncio
async def test_create_room_ignores_invalid_optional_settings() -> None:
    server = PokerServer()
    ws = DummyWs()

    result = await server.create_room(
        ws,
        {
            "name": "Creator",
            "blind_increase_hands": -10,
            "ante": -5,
            "ante_mode": "nonsense",
            "auto_ante": False,
        },
    )

    assert result.room_id is not None

    room = server.rooms[result.room_id]

    assert room.blind_increase_hands == 0
    assert room.ante == 0
    assert room.ante_mode == "classic"
    assert room.auto_ante is False


@pytest.mark.asyncio
async def test_join_room_normalizes_room_id_assigns_next_seat_and_broadcasts_to_existing_players() -> None:
    server = PokerServer()

    creator_ws = DummyWs()
    create_result = await server.create_room(
        creator_ws,
        {"name": "Creator", "avatar": "🧑"},
    )
    assert create_result.room_id is not None

    room = server.rooms[create_result.room_id]
    creator_state_count_before = len(messages(creator_ws, "state"))

    join_ws = DummyWs()
    join_result = await server.join_room(
        join_ws,
        {
            "room_id": create_result.room_id.lower(),
            "name": "Second Player With Very Long Name",
            "avatar": "abcd-extra",
        },
    )

    assert join_result.room_id == create_result.room_id
    assert join_result.player_token is not None
    assert len(room.players) == 2

    joined_player = next(p for p in room.players.values() if p.token == join_result.player_token)

    assert joined_player.seat == 2
    assert joined_player.name == "Second Player With Very"
    assert joined_player.avatar == "abcd"

    assert messages(join_ws, "joined") == [
        {
            "room_id": room.room_id,
            "player_id": joined_player.player_id,
            "token": joined_player.token,
        }
    ]

    assert len(messages(creator_ws, "state")) > creator_state_count_before
    assert messages(join_ws, "state")


@pytest.mark.asyncio
async def test_join_room_reclaims_disconnected_lobby_seat_before_rejecting_full_room() -> None:
    server = PokerServer()

    players = [
        make_player(f"p{seat}", f"Player{seat}", seat=seat)
        for seat in range(1, MAX_SEATS + 1)
    ]
    disconnected = players[-1]
    disconnected.connected = False
    disconnected.ws = None

    room = make_room(*players, room_id="FULLISH")
    server.rooms[room.room_id] = room

    assert server.find_free_seat(room) is None

    ws = DummyWs()

    result = await server.join_room(
        ws,
        {
            "room_id": "fullish",
            "name": "Replacement",
        },
    )

    assert result.room_id == "FULLISH"
    assert result.player_token is not None

    assert disconnected.player_id not in room.players
    assert len(room.players) == MAX_SEATS

    replacement = next(p for p in room.players.values() if p.token == result.player_token)
    assert replacement.seat == MAX_SEATS
    assert replacement.name == "Replacement"
    assert messages(ws, "joined")


@pytest.mark.asyncio
async def test_join_missing_room_sends_error_without_creating_room() -> None:
    server = PokerServer()
    ws = DummyWs()

    result = await server.join_room(ws, {"room_id": "missing", "name": "Nope"})

    assert result.room_id is None
    assert result.player_token is None
    assert server.rooms == {}
    assert messages(ws, "error") == [{"message": "Room not found."}]
    assert messages(ws, "joined") == []


@pytest.mark.asyncio
async def test_list_rooms_includes_only_rooms_with_connected_human_players() -> None:
    server = PokerServer()

    human_ws = DummyWs()
    human_room = make_room(
        make_player("p1", "Human", seat=1, connected=True, ws=human_ws),
        make_player("b1", "Bot", seat=2, connected=True, ws=None),
        room_id="HUMAN",
    )
    server.bots["b1"] = object()

    bot_only_room = make_room(
        make_player("b2", "OnlyBot", seat=1, connected=True, ws=None),
        room_id="BOTONLY",
    )
    server.bots["b2"] = object()

    disconnected_human_room = make_room(
        make_player("p2", "DisconnectedHuman", seat=1, connected=False, ws=None),
        room_id="GONE",
    )

    server.rooms = {
        human_room.room_id: human_room,
        bot_only_room.room_id: bot_only_room,
        disconnected_human_room.room_id: disconnected_human_room,
    }

    ws = DummyWs()

    await server.list_rooms(ws)

    payloads = messages(ws, "rooms_list")
    assert len(payloads) == 1

    rooms = payloads[0]["rooms"]
    assert rooms == [
        {
            "room_id": "HUMAN",
            "players": 2,
            "connected": 1,
            "max": MAX_SEATS,
            "phase": "lobby",
        }
    ]


@pytest.mark.asyncio
async def test_handle_rejects_room_scoped_event_without_valid_room_and_player() -> None:
    server = PokerServer()
    ws = DummyWs()

    result = await server.handle(
        ws,
        "chat",
        {
            "room_id": "MISSING",
            "token": "bad-token",
            "text": "hello",
        },
    )

    assert result.room_id is None
    assert result.player_token is None
    assert messages(ws, "error") == [
        {"message": "Join or reconnect to a room first."}
    ]


@pytest.mark.asyncio
async def test_handle_unknown_room_scoped_event_reports_unknown_event() -> None:
    server = PokerServer()

    room = make_room(make_player("p1", "PlayerOne", seat=1), room_id="KNOWN")
    server.rooms[room.room_id] = room
    player = next(iter(room.players.values()))
    assert isinstance(player.ws, DummyWs)

    result = await server.handle(
        player.ws,
        "mystery_event",
        {
            "room_id": room.room_id,
            "token": player.token,
        },
    )

    assert result.room_id == room.room_id
    assert result.player_token == player.token
    assert messages(player.ws, "error") == [
        {"message": "Unknown event: mystery_event"}
    ]


@pytest.mark.asyncio
async def test_broadcast_marks_player_disconnected_when_websocket_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    good_ws = DummyWs()
    good = make_player("p1", "Good", seat=1, connected=True, ws=good_ws)
    broken = make_player("p2", "Broken", seat=2, connected=True, ws=BrokenWs())

    room = make_room(good, broken, room_id="BROADCAST")
    server.rooms[room.room_id] = room

    monkeypatch.setattr("time.time", lambda: 1234.5)

    await server.broadcast(room)

    assert messages(good_ws, "state")

    assert broken.connected is False
    assert broken.ws is None
    assert broken.disconnected_at == 1234.5
