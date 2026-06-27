from __future__ import annotations

import json

import pytest

from poker.game import PokerServer, STARTING_STACK
from poker.models import Player, Room


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def messages(ws: DummyWs, event: str) -> list[dict]:
    return [
        message["payload"]
        for message in ws.sent
        if message.get("event") == event
    ]


def error_messages(ws: DummyWs) -> list[str]:
    return [
        message["payload"]["message"]
        for message in ws.sent
        if message.get("event") == "error"
    ]


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = STARTING_STACK,
    cards: list[str] | None = None,
    connected: bool = True,
    folded: bool = False,
    acted: bool = False,
    committed: int = 0,
) -> Player:
    ws = DummyWs() if connected else None
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        cards=cards or [],
        connected=connected,
        ws=ws,
        folded=folded,
        acted=acted,
        committed=committed,
    )
    player.total_invested = committed
    player.hand_start_stack = stack + committed
    return player


def make_room(
    *players: Player,
    room_id: str = "CONNECTION_TEST",
    phase: str = "lobby",
    action_seat: int | None = None,
    pot: int = 0,
    current_bet: int = 0,
) -> Room:
    room = Room(room_id=room_id)
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    room.action_seat = action_seat
    room.pot = pot
    room.current_bet = current_bet
    room.min_raise = room.big_blind
    return room


def player_ws(player: Player) -> DummyWs:
    assert isinstance(player.ws, DummyWs)
    return player.ws


@pytest.mark.asyncio
async def test_reconnect_restores_same_player_token_seat_and_state() -> None:
    server = PokerServer()

    player = make_player("p1", "ReconnectMe", seat=4, connected=False)
    player.disconnected_at = 123.0
    room = make_room(player)
    server.rooms[room.room_id] = room

    new_ws = DummyWs()

    result = await server.reconnect(
        new_ws,
        {"room_id": room.room_id.lower(), "token": player.token},
    )

    assert result.room_id == room.room_id
    assert result.player_token == player.token

    assert player.connected is True
    assert player.ws is new_ws
    assert player.disconnected_at == 0.0
    assert player.seat == 4
    assert player.token == "token_p1"

    joined = messages(new_ws, "joined")
    assert joined == [
        {
            "room_id": room.room_id,
            "player_id": player.player_id,
            "token": player.token,
        }
    ]

    assert messages(new_ws, "state")


@pytest.mark.asyncio
async def test_invalid_reconnect_sends_failure_without_state_leak() -> None:
    server = PokerServer()

    player = make_player("p1", "RealPlayer", seat=1)
    room = make_room(player)
    server.rooms[room.room_id] = room

    ws = DummyWs()

    result = await server.reconnect(
        ws,
        {"room_id": room.room_id, "token": "not-a-real-token"},
    )

    assert result.room_id is None
    assert result.player_token is None

    assert messages(ws, "reconnect_failed") == [
        {"message": "Reconnect token not recognized."}
    ]
    assert messages(ws, "joined") == []
    assert messages(ws, "state") == []


@pytest.mark.asyncio
async def test_reconnect_to_missing_room_sends_failure_without_state_leak() -> None:
    server = PokerServer()

    ws = DummyWs()

    result = await server.reconnect(
        ws,
        {"room_id": "MISSING", "token": "token_p1"},
    )

    assert result.room_id is None
    assert result.player_token is None

    assert messages(ws, "reconnect_failed") == [
        {"message": "Room no longer exists."}
    ]
    assert messages(ws, "joined") == []
    assert messages(ws, "state") == []


@pytest.mark.asyncio
async def test_full_room_join_is_rejected_without_adding_player() -> None:
    server = PokerServer()

    players = [
        make_player(f"p{seat}", f"Player{seat}", seat=seat)
        for seat in range(1, 9)
    ]
    room = make_room(*players, room_id="FULL8")
    server.rooms[room.room_id] = room

    ws = DummyWs()

    result = await server.join_room(
        ws,
        {"room_id": room.room_id, "name": "NinthPlayer", "avatar": "🎭"},
    )

    assert result.room_id is None
    assert result.player_token is None

    assert len(room.players) == 8
    assert server.find_free_seat(room) is None
    assert error_messages(ws) == ["Room is full."]
    assert messages(ws, "joined") == []


@pytest.mark.asyncio
async def test_leave_during_active_hand_folds_player_before_removal() -> None:
    server = PokerServer()

    leaver = make_player(
        "p1",
        "Leaver",
        seat=1,
        cards=["AS", "AH"],
        connected=True,
        folded=False,
    )
    next_player = make_player(
        "p2",
        "NextPlayer",
        seat=2,
        cards=["KS", "KH"],
        connected=True,
        folded=False,
        acted=False,
    )
    third_player = make_player(
        "p3",
        "ThirdPlayer",
        seat=3,
        cards=["QS", "QH"],
        connected=True,
        folded=False,
        acted=False,
    )

    room = make_room(
        leaver,
        next_player,
        third_player,
        phase="flop",
        action_seat=2,
        pot=0,
        current_bet=0,
    )

    await server.leave_room(room, leaver)

    assert leaver.player_id not in room.players
    assert leaver.folded is True
    assert leaver.acted is True

    assert room.phase == "flop"
    assert room.action_seat == 2
    assert next_player.player_id in room.players
    assert third_player.player_id in room.players


@pytest.mark.asyncio
async def test_leave_on_current_turn_advances_action_to_next_live_player() -> None:
    server = PokerServer()

    leaver = make_player(
        "p1",
        "Leaver",
        seat=1,
        cards=["AS", "AH"],
        connected=True,
        folded=False,
        acted=False,
    )
    next_player = make_player(
        "p2",
        "NextPlayer",
        seat=2,
        cards=["KS", "KH"],
        connected=True,
        folded=False,
        acted=False,
    )
    third_player = make_player(
        "p3",
        "ThirdPlayer",
        seat=3,
        cards=["QS", "QH"],
        connected=True,
        folded=False,
        acted=False,
    )

    room = make_room(
        leaver,
        next_player,
        third_player,
        phase="flop",
        action_seat=1,
        pot=0,
        current_bet=0,
    )

    await server.leave_room(room, leaver)

    assert leaver.player_id not in room.players
    assert leaver.folded is True
    assert room.phase == "flop"
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_leaving_as_last_opponent_awards_pot_to_remaining_player() -> None:
    server = PokerServer()

    leaver = make_player(
        "p1",
        "Leaver",
        seat=1,
        cards=["AS", "AH"],
        connected=True,
        folded=False,
    )
    remaining = make_player(
        "p2",
        "Remaining",
        seat=2,
        cards=["KS", "KH"],
        connected=True,
        folded=False,
        stack=900,
    )

    room = make_room(
        leaver,
        remaining,
        phase="turn",
        action_seat=1,
        pot=100,
        current_bet=0,
    )

    await server.leave_room(room, leaver)

    assert leaver.player_id not in room.players
    assert room.phase == "showdown"
    assert room.action_seat is None

    assert remaining.stack == 1000
    assert len(room.winners) == 1
    assert room.winners[0].player_id == remaining.player_id
    assert room.winners[0].amount == 100
    assert room.winners[0].reason == "Everyone else folded"


@pytest.mark.asyncio
async def test_leaving_last_human_destroys_room_and_cleans_bot_refs() -> None:
    server = PokerServer()

    human = make_player("p1", "Human", seat=1)
    bot = make_player("b1", "Bot", seat=2)
    room = make_room(human, bot, room_id="BOTONLY")
    server.rooms[room.room_id] = room
    server.bots[bot.player_id] = object()

    await server.leave_room(room, human)

    assert room.room_id not in server.rooms
    assert bot.player_id not in server.bots
    assert room.room_id not in server._bot_task_running
    assert room.room_id not in server._bot_loop_active
    assert room.room_id not in server._pending_start_hand


def test_disconnected_active_player_is_not_evicted_mid_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    active_disconnected = make_player(
        "p1",
        "Disconnected",
        seat=1,
        cards=["AS", "AH"],
        connected=False,
        folded=False,
    )
    active_disconnected.disconnected_at = 800.0

    other = make_player(
        "p2",
        "Other",
        seat=2,
        cards=["KS", "KH"],
        connected=True,
    )

    room = make_room(
        active_disconnected,
        other,
        room_id="NOEVICTMIDHAND",
        phase="flop",
    )
    server.rooms[room.room_id] = room

    monkeypatch.setattr("time.time", lambda: 1000.0)

    server._evict_stale(room)

    assert active_disconnected.player_id in room.players
    assert room.room_id in server.rooms


def test_stale_disconnected_player_is_evicted_between_hands(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    stale = make_player(
        "p1",
        "Stale",
        seat=1,
        connected=False,
    )
    stale.disconnected_at = 800.0

    active = make_player(
        "p2",
        "Active",
        seat=2,
        connected=True,
    )

    room = make_room(stale, active, room_id="EVICTLOBBY", phase="lobby")
    server.rooms[room.room_id] = room

    monkeypatch.setattr("time.time", lambda: 1000.0)

    server._evict_stale(room)

    assert stale.player_id not in room.players
    assert active.player_id in room.players
    assert room.room_id in server.rooms


def test_evict_disconnected_between_hands_frees_seat_for_join() -> None:
    server = PokerServer()

    players = [
        make_player(f"p{seat}", f"Player{seat}", seat=seat)
        for seat in range(1, 9)
    ]

    disconnected = players[-1]
    disconnected.connected = False
    disconnected.ws = None

    room = make_room(*players, room_id="EVICTFREE", phase="lobby")

    assert server.find_free_seat(room) is None

    server.evict_disconnected(room)

    assert disconnected.player_id not in room.players
    assert server.find_free_seat(room) == 8
