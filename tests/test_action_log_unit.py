"""Unit tests for backend action_log feature.

Tests:
- start_hand clears action_log
- Blind posts appear as action_log entries with correct fields
- is_all_in is correctly set for all-in actions
- visible_state() includes action_log field

Validates: Requirements 1.1, 1.2, 1.3
"""

import asyncio
import pytest
from unittest.mock import AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.game import PokerServer, _sanitize_action_log
from poker.models import Player, Room


# ─── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_ws():
    """Create a mock WebSocket that records sent messages."""
    ws = AsyncMock()
    ws.sent_messages = []

    async def mock_send_text(text):
        import json
        ws.sent_messages.append(json.loads(text))

    ws.send_text = mock_send_text
    return ws


async def create_room_with_players(server, num_players=2, stacks=None):
    """Helper to create a room with the specified number of players and optional stack sizes."""
    ws_list = []
    players = []

    ws_creator = make_mock_ws()
    ws_list.append(ws_creator)
    result = await server.create_room(ws_creator, {"name": "Alice", "avatar": "🎭"})
    room = server.rooms[result.room_id]
    creator = server.player_by_token(room, result.player_token)
    players.append(creator)

    for i in range(1, num_players):
        ws_p = make_mock_ws()
        ws_list.append(ws_p)
        result = await server.join_room(ws_p, {
            "room_id": room.room_id,
            "name": f"Player{i+1}",
            "avatar": "🃏"
        })
        p = server.player_by_token(room, result.player_token)
        players.append(p)

    # Set custom stack sizes if provided
    if stacks:
        for i, p in enumerate(players):
            if i < len(stacks):
                p.stack = stacks[i]

    return room, players, ws_list


# ─── Test: start_hand clears action_log ────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_hand_clears_action_log():
    """After start_hand, action_log should be reset (only contains blind entries).

    Validates: Requirement 1.3
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    # Manually inject some fake action_log entries to simulate a previous hand
    room.action_log = [
        {"player": "OldPlayer", "action": "fold", "amount": 0, "phase": "flop", "is_all_in": False},
        {"player": "OldPlayer2", "action": "bet_raise", "amount": 50, "phase": "flop", "is_all_in": False},
    ]

    # Start a new hand
    await server.start_hand(room)

    # action_log should have been cleared and only contain blind entries (SB + BB)
    assert len(room.action_log) >= 2
    # Old entries should be gone
    for entry in room.action_log:
        assert entry["player"] != "OldPlayer"
        assert entry["player"] != "OldPlayer2"


@pytest.mark.asyncio
async def test_start_hand_action_log_starts_with_blinds():
    """After start_hand, the first entries in action_log should be SB and BB.

    Validates: Requirements 1.2, 1.3
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    assert len(room.action_log) >= 2

    # First entry should be the small blind
    sb_entry = room.action_log[0]
    assert sb_entry["action"] == "small_blind"
    assert sb_entry["phase"] == "preflop"
    assert sb_entry["amount"] == room.small_blind
    assert "is_all_in" in sb_entry

    # Second entry should be the big blind
    bb_entry = room.action_log[1]
    assert bb_entry["action"] == "big_blind"
    assert bb_entry["phase"] == "preflop"
    assert bb_entry["amount"] == room.big_blind
    assert "is_all_in" in bb_entry


# ─── Test: Blind posts have correct fields ─────────────────────────────────────


@pytest.mark.asyncio
async def test_blind_entries_have_all_required_fields():
    """Blind entries should have player, action, amount, phase, and is_all_in fields.

    Validates: Requirement 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    required_fields = {"player", "action", "amount", "phase", "is_all_in"}

    for entry in room.action_log[:2]:
        assert required_fields.issubset(entry.keys()), (
            f"Missing fields in blind entry: {required_fields - set(entry.keys())}"
        )


@pytest.mark.asyncio
async def test_blind_entry_player_names_match_seated_players():
    """Blind entry player names should match actual players in the room.

    Validates: Requirement 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    player_names = {p.name for p in players}
    sb_name = room.action_log[0]["player"]
    bb_name = room.action_log[1]["player"]

    assert sb_name in player_names
    assert bb_name in player_names
    # SB and BB should be different players (in 2-player game, dealer is SB)
    assert sb_name != bb_name


# ─── Test: is_all_in correctly set ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blind_not_all_in_with_large_stack():
    """When stacks are large enough, blind posts should not be all-in.

    Validates: Requirement 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    # Default stacks are 1000, way more than blinds (5/10)
    await server.start_hand(room)

    sb_entry = room.action_log[0]
    bb_entry = room.action_log[1]

    assert sb_entry["is_all_in"] is False
    assert bb_entry["is_all_in"] is False


@pytest.mark.asyncio
async def test_blind_all_in_when_stack_equals_blind(monkeypatch):
    """When a player's stack equals or is less than the blind, they should be all-in.

    Validates: Requirement 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    # Set one player's stack to exactly the small blind amount
    # In heads-up: dealer is SB. We need to figure out which player will be SB.
    # Set both stacks low to guarantee at least one all-in on blind posting
    for p in players:
        p.stack = room.small_blind  # stack = 5, SB = 5 → all-in

    await server.start_hand(room)

    # The SB player should be all-in since their entire stack is the blind
    sb_entry = room.action_log[0]
    assert sb_entry["is_all_in"] is True


@pytest.mark.asyncio
async def test_is_all_in_set_on_player_action():
    """When a player bets their entire stack, is_all_in should be True in the log.

    Validates: Requirement 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    # Find the player whose turn it is
    action_player = None
    for p in players:
        if p.seat == room.action_seat:
            action_player = p
            break

    assert action_player is not None

    # Go all-in: raise to committed + stack (total they can bet)
    all_in_amount = action_player.committed + action_player.stack
    await server.player_action(room, action_player, "bet_raise", {"amount": all_in_amount})

    # Find the logged action for this player (skip blind entries)
    player_actions = [
        e for e in room.action_log
        if e["player"] == action_player.name and e["action"] == "bet_raise"
    ]
    assert len(player_actions) >= 1
    assert player_actions[-1]["is_all_in"] is True


def test_returned_excess_rewrites_covering_shove_as_call():
    """A covering player's unmatched shove should read as the effective call."""
    server = PokerServer()
    room = Room(room_id="TEST_EXCESS_LOG")

    short = Player(
        player_id="p1",
        token="t1",
        name="Player",
        seat=1,
        stack=0,
        cards=["AH", "KH"],
        all_in=True,
        committed=760,
        total_invested=760,
    )
    cover = Player(
        player_id="p2",
        token="t2",
        name="Dindybot",
        seat=2,
        stack=0,
        cards=["QH", "JH"],
        all_in=True,
        committed=978,
        total_invested=978,
    )
    room.players = {short.player_id: short, cover.player_id: cover}
    room.pot = 1738
    room.current_bet = 978
    room.action_log = [
        {"player": "Dindybot", "action": "bet_raise", "amount": 142, "phase": "river", "is_all_in": False},
        {"player": "Player", "action": "bet_raise", "amount": 760, "phase": "river", "is_all_in": True},
        {
            "player": "Dindybot",
            "action": "bet_raise",
            "amount": 978,
            "phase": "river",
            "is_all_in": True,
            "committed_before": 142,
            "committed": 978,
            "stack": 0,
        },
    ]

    server.return_uncalled_excess(room)

    assert cover.stack == 218
    assert cover.committed == 760
    assert cover.all_in is False
    assert room.pot == 1520

    entry = room.action_log[-1]
    assert entry["player"] == "Dindybot"
    assert entry["action"] == "check_call"
    assert entry["amount"] == 618
    assert entry["is_all_in"] is False


# ─── Test: visible_state includes action_log ───────────────────────────────────


@pytest.mark.asyncio
async def test_visible_state_includes_action_log():
    """visible_state() should include an action_log field.

    Validates: Requirement 1.1
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    state = server.visible_state(room, players[0].token)

    assert "action_log" in state
    assert isinstance(state["action_log"], list)
    assert len(state["action_log"]) >= 2  # At least SB + BB


@pytest.mark.asyncio
async def test_visible_state_action_log_is_sanitized():
    """visible_state() action_log should only contain allowed fields, no debug data.

    Validates: Requirements 1.1, 1.2
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    state = server.visible_state(room, players[0].token)
    allowed_fields = {"player", "action", "amount", "phase", "is_all_in"}

    for entry in state["action_log"]:
        assert set(entry.keys()) == allowed_fields, (
            f"Unexpected fields in sanitized action_log: {set(entry.keys()) - allowed_fields}"
        )


@pytest.mark.asyncio
async def test_visible_state_action_log_no_internal_fields():
    """visible_state() action_log must NOT contain internal debug fields.

    Validates: Requirement 1.4 (no hole_cards, ai_debug, community, etc.)
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    await server.start_hand(room)

    # Perform an action to create a human action_log entry (which has debug fields internally)
    action_player = None
    for p in players:
        if p.seat == room.action_seat:
            action_player = p
            break

    if action_player:
        await server.player_action(room, action_player, "check_call", {})

    state = server.visible_state(room, players[0].token)
    internal_fields = {"hole_cards", "ai_debug", "community", "is_bot", "current_bet",
                       "committed", "stack", "to_call", "note", "pot"}

    for entry in state["action_log"]:
        for field in internal_fields:
            assert field not in entry, f"Internal field '{field}' leaked into broadcast action_log"


@pytest.mark.asyncio
async def test_visible_state_action_log_empty_before_hand():
    """Before a hand starts, action_log in visible_state should be empty.

    Validates: Requirement 1.3
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    # Don't start a hand — still in lobby
    state = server.visible_state(room, players[0].token)

    assert "action_log" in state
    assert state["action_log"] == []
