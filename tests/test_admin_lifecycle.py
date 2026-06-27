from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from poker.game import PokerServer
from poker.models import Room, Winner


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


def events(ws: DummyWs, event_name: str) -> list[dict]:
    return [
        message
        for message in ws.sent
        if message.get("event") == event_name
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


def test_admin_kicks_specific_human_between_hands_and_notifies_target():
    server, room, creator, guest, creator_ws, guest_ws = make_room_with_two_humans()
    room.phase = "lobby"

    run(server.player_action(room, creator, "kick_player", {
        "target_player_id": guest.player_id,
    }))

    assert guest.player_id not in room.players
    assert events(guest_ws, "left")
    assert events(creator_ws, "state")


def test_admin_kicks_specific_bot_without_removing_other_bots():
    server, room, creator, _guest, creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "showdown"

    bot_one = server.add_new_player(room, None, "Bot One")
    bot_two = server.add_new_player(room, None, "Bot Two")
    server.bots[bot_one.player_id] = SimpleNamespace(difficulty="hard")
    server.bots[bot_two.player_id] = SimpleNamespace(difficulty="easy")

    run(server.player_action(room, creator, "kick_player", {
        "target_player_id": bot_one.player_id,
    }))

    assert bot_one.player_id not in room.players
    assert bot_one.player_id not in server.bots
    assert bot_two.player_id in room.players
    assert bot_two.player_id in server.bots
    assert events(creator_ws, "state")


def test_admin_kick_rejects_self_current_admin_and_active_hand():
    server, room, creator, guest, creator_ws, _guest_ws = make_room_with_two_humans()

    room.phase = "lobby"
    run(server.player_action(room, creator, "kick_player", {
        "target_player_id": creator.player_id,
    }))
    assert "You cannot kick yourself." in error_messages(creator_ws)
    assert creator.player_id in room.players

    duplicate_admin = server.add_new_player(room, None, "Duplicate Admin")
    duplicate_admin.token = room.creator_token
    run(server.player_action(room, creator, "kick_player", {
        "target_player_id": duplicate_admin.player_id,
    }))
    assert "The current table admin cannot be kicked." in error_messages(creator_ws)
    assert duplicate_admin.player_id in room.players

    room.phase = "preflop"
    run(server.player_action(room, creator, "kick_player", {
        "target_player_id": guest.player_id,
    }))
    assert "Kick players between hands only." in error_messages(creator_ws)
    assert guest.player_id in room.players


def test_backend_auto_deal_state_is_visible_to_all_players():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "showdown"
    room.winners = [Winner(creator.player_id, creator.name, 10, "Everyone else folded")]
    room.auto_deal_enabled = True
    room.auto_deal_delay_seconds = 10
    room.auto_deal_started_at = time.time()
    room.auto_deal_hand_number = room.hands_played

    creator_state = server.visible_state(room, creator.token)
    guest_state = server.visible_state(room, guest.token)

    assert creator_state["auto_deal_enabled"] is True
    assert guest_state["auto_deal_enabled"] is True
    assert creator_state["auto_deal_active"] is True
    assert guest_state["auto_deal_active"] is True
    assert creator_state["auto_deal_remaining_seconds"] <= 10
    assert guest_state["auto_deal_remaining_seconds"] <= 10


def test_admin_can_toggle_backend_auto_deal_but_guest_cannot():
    server, room, creator, guest, creator_ws, guest_ws = make_room_with_two_humans()

    run(server.player_action(room, guest, "toggle_auto_deal", {"enabled": False}))
    assert "Only the room creator can change auto-deal." in error_messages(guest_ws)
    assert room.auto_deal_enabled is True

    run(server.player_action(room, creator, "toggle_auto_deal", {"enabled": False}))
    assert room.auto_deal_enabled is False
    assert events(creator_ws, "state")


def test_backend_auto_deal_starts_next_hand_after_countdown():
    async def scenario():
        server, room, creator, guest, creator_ws, guest_ws = make_room_with_two_humans()
        room.phase = "showdown"
        room.winners = [Winner(creator.player_id, creator.name, 10, "Everyone else folded")]
        room.pot = 10
        room.auto_deal_enabled = True
        room.auto_deal_delay_seconds = 1

        await server.broadcast(room)
        assert room.auto_deal_started_at > 0

        for _ in range(20):
            if room.phase == "preflop":
                break
            await asyncio.sleep(0.1)

        assert room.phase == "preflop"
        assert room.winners == []
        assert room.auto_deal_started_at == 0.0
        assert events(creator_ws, "state")
        assert events(guest_ws, "state")

    run(scenario())
