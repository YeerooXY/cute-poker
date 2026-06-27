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


def setup_active_action_room(action_time: int = 1, timebank: int = 0):
    server, room, creator, guest, creator_ws, guest_ws = make_room_with_two_humans()
    room.phase = "preflop"
    room.action_time_seconds = action_time
    room.starting_timebank_seconds = timebank
    room.timebank_gain_per_hand = 1
    room.action_seat = creator.seat
    room.current_bet = 0
    room.min_raise = room.big_blind
    creator.cards = ["AS", "AH"]
    guest.cards = ["KS", "KH"]
    creator.timebank_seconds = timebank
    guest.timebank_seconds = timebank
    creator.acted = False
    guest.acted = False
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


def test_backend_action_timer_state_is_visible_for_human_action():
    async def scenario():
        server, room, creator, guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=5, timebank=7)

        await server.broadcast(room)
        creator_state = server.visible_state(room, creator.token)
        guest_state = server.visible_state(room, guest.token)

        assert creator_state["action_timer_active"] is True
        assert guest_state["action_timer_active"] is True
        assert creator_state["action_timer_player_id"] == creator.player_id
        assert creator_state["action_timer_total_seconds"] == 12
        assert creator_state["action_timer_remaining_seconds"] <= 12
        assert creator_state["viewer"]["timebank_seconds"] == 7
        assert guest_state["viewer"]["timebank_seconds"] == 7

    run(scenario())


def test_backend_action_timer_auto_checks_when_no_call():
    async def scenario():
        server, room, creator, _guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=0)

        await server.broadcast(room)
        await asyncio.sleep(1.4)

        assert any(
            entry.get("player") == creator.name
            and entry.get("action") == "timeout_check"
            for entry in room.action_log
        )
        assert creator.folded is False
        assert any(entry.get("action") == "timeout_check" for entry in room.action_log)
        assert room.action_seat != creator.seat

    run(scenario())


def test_backend_action_timer_auto_folds_when_facing_bet():
    async def scenario():
        server, room, creator, guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=0)
        room.current_bet = 20
        guest.committed = 20
        guest.total_invested = 20
        room.pot = 20

        await server.broadcast(room)
        await asyncio.sleep(1.4)

        assert creator.folded is True
        assert any(entry.get("action") == "timeout_fold" for entry in room.action_log)
        assert room.phase == "showdown"
        assert room.winners and room.winners[0].player_id == guest.player_id

    run(scenario())


def test_backend_action_timer_consumes_timebank_before_timeout_action():
    async def scenario():
        server, room, creator, _guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=1)

        await server.broadcast(room)
        await asyncio.sleep(2.4)

        assert creator.timebank_seconds == 0
        assert any(entry.get("action") == "timeout_check" for entry in room.action_log)

    run(scenario())


def test_stale_action_timer_does_not_act_after_manual_action():
    async def scenario():
        server, room, creator, _guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=0)

        await server.broadcast(room)
        await server.player_action(room, creator, "check_call", {})
        await asyncio.sleep(1.4)

        assert not any(
            entry.get("player") == creator.name
            and str(entry.get("action", "")).startswith("timeout_")
            for entry in room.action_log
        )
        assert any(
            entry.get("player") == creator.name
            and entry.get("action") == "check_call"
            for entry in room.action_log
        )

    run(scenario())


def test_paused_room_does_not_timeout_action_player():
    async def scenario():
        server, room, creator, _guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=0)

        await server.broadcast(room)
        room.paused = True
        await server.broadcast(room)
        await asyncio.sleep(1.4)

        assert creator.acted is False
        assert not any(str(entry.get("action", "")).startswith("timeout_") for entry in room.action_log)
        assert room.action_timer_started_at == 0.0

    run(scenario())


def test_bots_are_not_timed_out_by_human_action_timer():
    async def scenario():
        server, room, creator, guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=0)
        server.bots[creator.player_id] = SimpleNamespace(difficulty="hard")

        await server.broadcast(room)
        await asyncio.sleep(1.4)

        assert room.action_timer_started_at == 0.0
        assert creator.acted is False
        assert not any(str(entry.get("action", "")).startswith("timeout_") for entry in room.action_log)

    run(scenario())


def test_completed_hand_grants_timebank_gain_to_humans_only():
    server, room, creator, guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=2)
    bot = server.add_new_player(room, None, "Bot")
    server.bots[bot.player_id] = SimpleNamespace(difficulty="hard")
    bot.timebank_seconds = 0
    room.phase = "showdown"
    room.winners = [Winner(creator.player_id, creator.name, 10, "Everyone else folded")]
    room.hands_played = 3
    room.timebank_gain_per_hand = 4

    server.record_completed_hand(room)
    server.refresh_latest_completed_hand(room)

    assert creator.timebank_seconds == 6
    assert guest.timebank_seconds == 6
    assert bot.timebank_seconds == 0


def test_auto_deal_default_delay_is_five_seconds():
    server = PokerServer()
    ws = DummyWs()

    result = run(server.create_room(ws, {"name": "Creator"}))
    room = server.rooms[result.room_id]

    assert room.auto_deal_delay_seconds == 5


def test_visible_state_separates_regular_action_time_from_timebank():
    server, room, creator, _guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=10, timebank=100)

    room.action_timer_player_id = creator.player_id
    room.action_timer_started_at = time.time() - 12.2

    state = server.visible_state(room, creator.token)

    assert state["action_timer_using_timebank"] is True
    assert state["action_timer_regular_remaining_seconds"] == 0
    assert 0 < state["action_timer_timebank_remaining_seconds"] < 100
    assert state["viewer"]["timebank_seconds"] == state["action_timer_timebank_remaining_seconds"]
