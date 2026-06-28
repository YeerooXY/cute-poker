from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from poker.bot import BotConfig
from poker.game import PokerServer, STARTING_STACK
from poker.models import Player, Room, Winner


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def run(coro):
    return asyncio.run(coro)


async def wait_until(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


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
        assert await wait_until(
            lambda: creator.folded
            and any(entry.get("action") == "timeout_fold" for entry in room.action_log),
            timeout=3.0,
        )

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


def test_completed_hand_grants_timebank_gain_to_active_dealt_humans_only():
    server, room, creator, guest, _creator_ws, _guest_ws = setup_active_action_room(action_time=1, timebank=2)
    bot = server.add_new_player(room, None, "Bot")
    server.bots[bot.player_id] = SimpleNamespace(difficulty="hard")
    bot.timebank_seconds = 0
    bot.cards = ["2S", "2H"]

    sitting_out = server.add_new_player(room, DummyWs(), "SittingOut")
    sitting_out.timebank_seconds = 2
    sitting_out.cards = ["3S", "3H"]
    sitting_out.sitting_out = True

    spectator = server.add_new_player(room, DummyWs(), "Spectator")
    spectator.timebank_seconds = 2
    spectator.cards = ["4S", "4H"]
    spectator.is_spectator = True

    busted = server.add_new_player(room, DummyWs(), "Busted")
    busted.timebank_seconds = 2
    busted.cards = ["5S", "5H"]
    busted.stack = 0

    not_dealt = server.add_new_player(room, DummyWs(), "NotDealt")
    not_dealt.timebank_seconds = 2
    not_dealt.cards = []

    room.phase = "showdown"
    room.winners = [Winner(creator.player_id, creator.name, 10, "Everyone else folded")]
    room.hands_played = 3
    room.timebank_gain_per_hand = 4

    server.record_completed_hand(room)
    server.refresh_latest_completed_hand(room)

    assert creator.timebank_seconds == 6
    assert guest.timebank_seconds == 6
    assert bot.timebank_seconds == 0
    assert sitting_out.timebank_seconds == 2
    assert spectator.timebank_seconds == 2
    assert busted.timebank_seconds == 2
    assert not_dealt.timebank_seconds == 2

    server.record_completed_hand(room)

    assert creator.timebank_seconds == 6
    assert guest.timebank_seconds == 6


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


def test_between_hands_sit_out_still_toggles_immediately():
    server, room, creator, _guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "lobby"

    run(server.player_action(room, creator, "sit_out", {}))

    assert creator.sitting_out is True


def test_explicit_sit_out_true_false_requests_work():
    server, room, creator, _guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "lobby"

    run(server.player_action(room, creator, "sit_out", {"sitting_out": True}))
    assert creator.sitting_out is True

    run(server.player_action(room, creator, "sit_out", {"sitting_out": False}))
    assert creator.sitting_out is False


def test_busted_player_cannot_sit_in_until_rebuy():
    server, room, creator, _guest, creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "showdown"
    creator.stack = 0
    creator.sitting_out = True

    run(server.player_action(room, creator, "sit_out", {"sitting_out": False}))

    assert creator.sitting_out is True
    assert "Rebuy before sitting in again." in error_messages(creator_ws)


def test_busted_player_can_rebuy_between_hands_and_buy_in_count_increments():
    server, room, creator, _guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "showdown"
    creator.stack = 0
    creator.hand_start_stack = 0
    creator.buy_in_count = 1
    creator.sitting_out = True
    creator.cards = ["AS", "AH"]
    creator.folded = True
    creator.all_in = True
    creator.committed = 1000
    creator.total_invested = 1000
    creator.acted = True

    before = server.visible_state(room, creator.token)
    assert before["viewer"]["can_rebuy"] is True
    assert next(p for p in before["players"] if p["is_you"])["can_rebuy"] is True

    run(server.player_action(room, creator, "rebuy", {}))

    assert creator.stack == STARTING_STACK
    assert creator.hand_start_stack == STARTING_STACK
    assert creator.buy_in_count == 2
    assert creator.sitting_out is False
    assert creator.cards == []
    assert creator.folded is False
    assert creator.all_in is False
    assert creator.committed == 0
    assert creator.total_invested == 0
    assert creator.acted is False

    after = server.visible_state(room, creator.token)
    viewer = next(p for p in after["players"] if p["is_you"])
    assert viewer["buy_in_count"] == 2
    assert after["viewer"]["can_rebuy"] is False


def test_live_all_in_stack_zero_is_not_rebuyable_or_busted_in_visible_state():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "preflop"
    room.action_seat = guest.seat
    room.current_bet = 100
    creator.stack = 0
    creator.cards = ["AS", "AH"]
    creator.all_in = True
    creator.folded = False
    creator.committed = 1000
    creator.total_invested = 1000

    state = server.visible_state(room, creator.token)
    viewer = next(p for p in state["players"] if p["is_you"])

    assert state["viewer"]["can_rebuy"] is False
    assert viewer["can_rebuy"] is False
    assert viewer["is_live_in_hand"] is True
    assert viewer["all_in"] is True


def test_busted_bot_rebuys_before_next_hand_and_increments_buy_in_count():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    bot = Player(
        player_id="BOT1",
        token="bot-token",
        name="Bot One",
        seat=3,
        ws=None,
        connected=True,
        stack=0,
        buy_in_count=1,
    )
    room.players[bot.player_id] = bot
    server.bots[bot.player_id] = BotConfig(style="balanced", name=bot.name, avatar="B", difficulty="easy")
    room.phase = "showdown"
    room.winners = [Winner(player_id=creator.player_id, name=creator.name, amount=10, reason="wins")]

    run(server.start_hand(room))

    assert bot.buy_in_count == 2
    assert bot.stack > 0
    assert bot.sitting_out is False
    assert bot.cards
    state = server.visible_state(room, creator.token)
    bot_view = next(p for p in state["players"] if p["id"] == bot.player_id)
    assert bot_view["buy_in_count"] == 2


def test_rebuy_is_rejected_during_active_hand():
    server, room, creator, _guest, creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "preflop"
    creator.stack = 0
    creator.buy_in_count = 1

    run(server.player_action(room, creator, "rebuy", {}))

    assert creator.stack == 0
    assert creator.buy_in_count == 1
    assert "Rebuy is available between hands only." in error_messages(creator_ws)


def test_reset_stacks_resets_sitting_out_and_buy_in_count():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    room.phase = "showdown"
    guest.stack = 0
    guest.buy_in_count = 3
    guest.sitting_out = True
    guest.cards = ["KS", "KH"]
    guest.folded = True
    guest.committed = 500
    guest.total_invested = 500

    run(server.player_action(room, creator, "reset_stacks", {}))

    assert guest.stack == STARTING_STACK
    assert guest.hand_start_stack == STARTING_STACK
    assert guest.buy_in_count == 1
    assert guest.sitting_out is False
    assert guest.cards == []
    assert guest.folded is False
    assert guest.committed == 0
    assert guest.total_invested == 0


def test_sit_out_toggle_is_checked_when_next_hand_starts():
    server, room, creator, guest, _creator_ws, _guest_ws = make_room_with_two_humans()
    third_ws = DummyWs()
    third = server.add_new_player(room, third_ws, "Third")
    room.phase = "lobby"

    run(server.player_action(room, creator, "sit_out", {}))

    assert creator.sitting_out is True
    run(server.start_hand(room))

    assert creator.cards == []
    assert guest.cards
    assert third.cards

def make_room_with_three_humans():
    server, room, creator, guest, creator_ws, guest_ws = make_room_with_two_humans()
    third_ws = DummyWs()
    third = server.add_new_player(room, third_ws, "Third")
    return server, room, creator, guest, third, creator_ws, guest_ws, third_ws


def test_live_player_can_fold_after_clicking_sit_out_mid_hand():
    server, room, creator, guest, third, creator_ws, _guest_ws, _third_ws = make_room_with_three_humans()

    room.phase = "preflop"
    room.current_bet = 10
    room.min_raise = room.big_blind
    room.action_seat = creator.seat

    creator.cards = ["AS", "AH"]
    guest.cards = ["KS", "KH"]
    third.cards = ["QS", "QH"]

    creator.stack = 990
    creator.committed = 10
    creator.acted = False
    guest.stack = 1000
    guest.committed = 0
    guest.acted = False
    third.stack = 1000
    third.committed = 0
    third.acted = False

    run(server.player_action(room, creator, "sit_out", {}))
    assert creator.sitting_out is True
    assert creator.cards

    run(server.player_action(room, creator, "fold", {}))

    assert "Sitting-out players cannot act" not in " ".join(error_messages(creator_ws))
    assert creator.folded is True
    assert creator.acted is True
    assert room.action_seat != creator.seat


def test_next_action_does_not_skip_live_sitting_out_player():
    server, room, creator, guest, third, _creator_ws, _guest_ws, _third_ws = make_room_with_three_humans()

    room.phase = "preflop"
    room.current_bet = 10
    room.min_raise = room.big_blind

    creator.cards = ["AS", "AH"]
    guest.cards = ["KS", "KH"]
    third.cards = ["QS", "QH"]

    creator.folded = True
    guest.folded = False
    third.folded = False

    guest.sitting_out = True
    guest.stack = 1000
    guest.committed = 0
    guest.acted = False

    third.stack = 990
    third.committed = 10
    third.acted = True

    # From the previous actor, the live sitting-out-next-hand player must still receive action.
    assert server.next_action_seat_after(room, third.seat) == guest.seat

def test_return_uncalled_excess_refunds_only_current_street_unmatched_chips():
    server, room, short, cover, folder, _short_ws, _cover_ws, _folder_ws = make_room_with_three_humans()

    room.phase = "turn"
    room.current_bet = 20

    short.cards = ["AS", "AH"]
    short.stack = 0
    short.committed = 0
    short.total_invested = 125
    short.all_in = True
    short.folded = False

    cover.cards = ["KS", "KH"]
    cover.stack = 845
    cover.committed = 20
    cover.total_invested = 155
    cover.all_in = False
    cover.folded = False

    folder.cards = ["QS", "QH"]
    folder.stack = 855
    folder.committed = 10
    folder.total_invested = 145
    folder.all_in = False
    folder.folded = True

    room.pot = short.total_invested + cover.total_invested + folder.total_invested
    before_total = room.pot + sum(p.stack for p in [short, cover, folder])

    server.return_uncalled_excess(room)

    assert cover.stack == 855
    assert cover.committed == 10
    assert cover.total_invested == 145
    assert room.pot == 415
    assert room.current_bet == 10

    after_total = room.pot + sum(p.stack for p in [short, cover, folder])
    assert after_total == before_total
