from __future__ import annotations

import asyncio
import json
import time

from poker.game import PokerServer
from poker.models import Room


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def run(coro):
    return asyncio.run(coro)


def error_messages(ws: DummyWs) -> list[str]:
    return [
        message["payload"]["message"]
        for message in ws.sent
        if message.get("event") == "error"
    ]


def make_room_with_two_humans():
    server = PokerServer()
    room = Room(room_id="ADMIN1")
    server.rooms[room.room_id] = room

    creator_ws = DummyWs()
    guest_ws = DummyWs()

    creator = server.add_new_player(room, creator_ws, "Creator")
    guest = server.add_new_player(room, guest_ws, "Guest")
    room.creator_token = creator.token

    return server, room, creator, guest, creator_ws, guest_ws


def test_explicit_creator_leave_transfers_admin_to_remaining_human():
    server, room, creator, guest, _creator_ws, guest_ws = make_room_with_two_humans()

    run(server.leave_room(room, creator))

    assert creator.player_id not in room.players
    assert room.creator_token == guest.token

    state = server.visible_state(room, guest.token)
    assert state["viewer"]["is_admin"] is True

    run(server.player_action(room, guest, "toggle_pause", {}))

    assert error_messages(guest_ws) == []
    assert room.paused is True


def test_temporary_creator_disconnect_does_not_transfer_admin():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()

    run(server.disconnect(room.room_id, creator.token))

    assert creator.player_id in room.players
    assert creator.connected is False
    assert creator.ws is None
    assert room.creator_token == creator.token

    guest_state = server.visible_state(room, guest.token)
    assert guest_state["viewer"]["is_admin"] is False


def test_creator_reconnect_keeps_admin_after_temporary_disconnect():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()

    run(server.disconnect(room.room_id, creator.token))

    reconnect_ws = DummyWs()
    result = run(server.reconnect(reconnect_ws, {
        "room_id": room.room_id,
        "token": creator.token,
    }))

    assert result.room_id == room.room_id
    assert result.player_token == creator.token
    assert creator.connected is True
    assert creator.ws is reconnect_ws
    assert room.creator_token == creator.token

    creator_state = server.visible_state(room, creator.token)
    guest_state = server.visible_state(room, guest.token)

    assert creator_state["viewer"]["is_admin"] is True
    assert guest_state["viewer"]["is_admin"] is False


def test_stale_evicted_creator_transfers_admin_to_connected_human():
    server, room, creator, guest, _creator_ws, guest_ws = make_room_with_two_humans()

    creator.connected = False
    creator.ws = None
    creator.disconnected_at = time.time() - 999

    server._evict_stale(room)

    assert creator.player_id not in room.players
    assert room.creator_token == guest.token

    run(server.player_action(room, guest, "toggle_pause", {}))

    assert error_messages(guest_ws) == []
    assert room.paused is True


def test_bots_never_receive_admin_when_creator_leaves():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()

    bot_ws = None
    bot = server.add_new_player(room, bot_ws, "Bot")
    server.bots[bot.player_id] = object()

    run(server.leave_room(room, creator))

    assert room.creator_token == guest.token
    assert room.creator_token != bot.token
