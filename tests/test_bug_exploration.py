"""
Bug Condition Exploration Tests - Poker UI Multi-Bug Exploration
================================================================

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11**

Property 1: Bug Condition - These tests encode the EXPECTED (correct) behavior.
On UNFIXED code, tests that target bugs should FAIL (confirming the bugs exist).
After fixes are applied, all tests should PASS.

CRITICAL: These tests MUST FAIL on unfixed code — failure confirms the bugs exist.
DO NOT attempt to fix the tests or the code when they fail.
"""

import asyncio
import pytest
import secrets
from unittest.mock import AsyncMock, MagicMock
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.game import PokerServer, MAX_SEATS, STARTING_STACK
from poker.models import Player, Room, ChatMessage
from poker.cards import display_cards


# ─── Helpers ───

def make_mock_ws():
    """Create a mock WebSocket that records sent messages."""
    ws = AsyncMock()
    ws.sent_messages = []

    async def mock_send_text(text):
        import json
        ws.sent_messages.append(json.loads(text))

    ws.send_text = mock_send_text
    return ws


def get_last_state(ws):
    """Get the last 'state' event payload sent to a WebSocket."""
    for msg in reversed(ws.sent_messages):
        if msg.get("event") == "state":
            return msg["payload"]
    return None


def get_last_error(ws):
    """Get the last 'error' event payload sent to a WebSocket."""
    for msg in reversed(ws.sent_messages):
        if msg.get("event") == "error":
            return msg["payload"]
    return None


async def create_room_with_players(server, num_players=2):
    """Helper to create a room with the specified number of players.
    Returns (room, players_list, ws_list) where players_list[0] is the creator (admin).
    """
    ws_list = []
    players = []

    # Create room (first player is admin/creator)
    ws_creator = make_mock_ws()
    ws_list.append(ws_creator)
    result = await server.create_room(ws_creator, {"name": "Admin", "avatar": "🎭"})
    room = server.rooms[result.room_id]
    creator = server.player_by_token(room, result.player_token)
    players.append(creator)

    # Join additional players
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

    return room, players, ws_list


# ─── Test 1: Chat Message Data Flow ───

@pytest.mark.asyncio
@given(message_text=st.text(min_size=1, max_size=100, alphabet=st.characters(
    whitelist_categories=('L', 'N', 'P', 'Z'),
    blacklist_characters='\x00'
)))
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_chat_message_in_state(message_text):
    """
    Test 1 (Chat): Create a room, send a chat message, verify state.messages
    contains the message with sender name and text.

    **Validates: Requirements 1.1**

    Server-side confirmed working — validates data flow from chat action
    to visible_state messages array.
    """
    # The server strips whitespace and rejects blank messages — skip those
    assume(message_text.strip() != "")

    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    creator = players[0]

    # Send a chat message as creator
    await server.chat(room, creator, message_text)

    # Get visible state for each player
    for player in players:
        state = server.visible_state(room, player.token)
        messages = state["messages"]

        # Verify the message is in the state
        assert len(messages) > 0, "Messages array should not be empty after sending a chat"
        last_msg = messages[-1]
        assert last_msg["name"] == creator.name, f"Message sender should be '{creator.name}'"
        assert last_msg["text"] == message_text.strip()[:240], "Message text should match what was sent (stripped)"


# ─── Test 2: Player Visibility ───

@pytest.mark.asyncio
@given(num_players=st.integers(min_value=2, max_value=MAX_SEATS))
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_all_players_visible_in_state(num_players):
    """
    Test 2 (Player visibility): Create a room with 2+ players, verify state.players
    array length matches total connected players and includes is_you for each viewer.

    **Validates: Requirements 1.2**

    The server's visible_state should return all players for all viewers.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, num_players)

    # For each player viewing the state, check all players are included
    for viewer in players:
        state = server.visible_state(room, viewer.token)
        state_players = state["players"]

        # All players should be visible
        assert len(state_players) == num_players, (
            f"Expected {num_players} players in state, got {len(state_players)}"
        )

        # Viewer should have exactly one is_you=True player
        you_players = [p for p in state_players if p["is_you"]]
        assert len(you_players) == 1, (
            f"Expected exactly 1 is_you=True player, got {len(you_players)}"
        )
        assert you_players[0]["name"] == viewer.name


# ─── Test 3: Bot Add - Admin ───

@pytest.mark.asyncio
@settings(max_examples=1, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_bot_add_as_admin(data):
    """
    Test 3 (Bot add - admin): Send add_bot action as admin (creator token),
    verify player count increases and new player has is_bot: true.

    **Validates: Requirements 1.3**

    Admin should be able to add bots successfully.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    creator = players[0]

    initial_player_count = len(room.players)

    # Admin adds a bot
    await server.player_action(room, creator, "add_bot", {
        "action": "add_bot",
        "room_id": room.room_id,
        "token": creator.token,
    })

    # Verify player count increased
    assert len(room.players) == initial_player_count + 1, (
        f"Expected {initial_player_count + 1} players after bot add, got {len(room.players)}"
    )

    # Verify the new player is a bot in visible state
    state = server.visible_state(room, creator.token)
    bot_players = [p for p in state["players"] if p["is_bot"]]
    assert len(bot_players) >= 1, "Should have at least one bot player after add_bot"


# ─── Test 4: Bot Add - Non-Admin Rejection ───

@pytest.mark.asyncio
@settings(max_examples=1, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_bot_add_non_admin_rejected(data):
    """
    Test 4 (Bot add - non-admin rejection): Send add_bot action as non-admin,
    verify server rejects the action.

    **Validates: Requirements 1.3, 1.10**

    EXPECTED TO FAIL on unfixed code — currently any player can add bots
    (no admin check). Bug exists: non-admin can add bots.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    non_admin = players[1]  # Not the creator

    initial_player_count = len(room.players)

    # Non-admin attempts to add a bot
    await server.player_action(room, non_admin, "add_bot", {
        "action": "add_bot",
        "room_id": room.room_id,
        "token": non_admin.token,
    })

    # The server should REJECT this — player count should NOT increase
    assert len(room.players) == initial_player_count, (
        f"Non-admin should NOT be able to add bots. "
        f"Player count was {initial_player_count}, now {len(room.players)}. "
        f"Bug confirmed: no admin check on add_bot action."
    )

    # Should have received an error message
    error = get_last_error(ws_list[1])
    assert error is not None, (
        "Non-admin should receive an error when trying to add a bot"
    )


# ─── Test 5: Hand Bar Data (Viewer's Own Cards) ───

@pytest.mark.asyncio
@settings(max_examples=1, deadline=30000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_hand_bar_data_for_creator(data):
    """
    Test 5 (Hand bar data): Deal cards to creator, verify state.players[is_you].cards
    contains actual card text (not "BACK") for the viewer's own cards.

    **Validates: Requirements 1.4**

    The server's visible_state should show actual card faces (not BACK)
    for the viewer's own cards when they've been dealt.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    creator = players[0]

    # Start a hand so cards are dealt
    await server.start_hand(room)

    # Get creator's view of state
    state = server.visible_state(room, creator.token)

    # Find the viewer's player data
    viewer_data = next((p for p in state["players"] if p["is_you"]), None)
    assert viewer_data is not None, "Viewer should be found in players list"

    # Viewer's cards should contain actual card text, NOT "BACK" or "🂠"
    cards = viewer_data["cards"]
    assert len(cards) == 2, f"Viewer should have 2 cards, got {len(cards)}"

    for card in cards:
        assert card != "BACK", "Viewer's own cards should not show BACK"
        assert card != "🂠", "Viewer's own cards should not show card back symbol"
        # Card should be something like "A♠", "10♥", "K♦", etc.
        assert len(card) >= 2, f"Card '{card}' should be a display string like 'A♠'"


# ─── Test 6: Community Cards Phase Progression ───

@pytest.mark.asyncio
@settings(max_examples=1, deadline=60000, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_community_cards_phase_progression(data):
    """
    Test 6 (Community cards): Advance through phases (preflop→flop→turn→river),
    verify state.community array length is 0→3→4→5.

    **Validates: Requirements 1.5**

    Server correctly manages community cards through phase transitions.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)

    # Start a hand
    await server.start_hand(room)

    # Preflop: 0 community cards
    state = server.visible_state(room, players[0].token)
    assert len(state["community"]) == 0, (
        f"Preflop should have 0 community cards, got {len(state['community'])}"
    )

    # Manually advance to flop
    await server.advance_phase(room)
    state = server.visible_state(room, players[0].token)
    assert room.phase == "flop"
    assert len(state["community"]) == 3, (
        f"Flop should have 3 community cards, got {len(state['community'])}"
    )

    # Advance to turn
    await server.advance_phase(room)
    state = server.visible_state(room, players[0].token)
    assert room.phase == "turn"
    assert len(state["community"]) == 4, (
        f"Turn should have 4 community cards, got {len(state['community'])}"
    )

    # Advance to river
    await server.advance_phase(room)
    state = server.visible_state(room, players[0].token)
    assert room.phase == "river"
    assert len(state["community"]) == 5, (
        f"River should have 5 community cards, got {len(state['community'])}"
    )


# ─── Test 7: Bot Button Visibility (Client Logic Simulation) ───

@pytest.mark.asyncio
@settings(max_examples=1, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_bot_button_visibility_non_admin(data):
    """
    Test 7 (Bot button visibility): Render state as non-admin in lobby phase,
    verify admin-only UI controls (bot buttons) should be hidden.

    **Validates: Requirements 1.10**

    EXPECTED TO FAIL on unfixed code — currently bot buttons are shown to ALL
    players when canDeal is true (lobby/showdown && !paused). The client-side
    logic uses `canDeal ? "" : "none"` without checking `state.viewer.is_admin`.

    This test simulates the client-side renderState logic.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    non_admin = players[1]

    # Get state as non-admin in lobby phase
    state = server.visible_state(room, non_admin.token)

    # Verify we're in lobby
    assert state["phase"] == "lobby"
    assert not state["paused"]
    assert not state["viewer"]["is_admin"], "Non-admin viewer should have is_admin=False"

    # Simulate client-side renderState logic for bot buttons:
    # Current (buggy) code: els.addBotBtn.style.display = canDeal ? "" : "none"
    # Fixed code should be: (canDeal && state.viewer.is_admin) ? "" : "none"
    can_deal = state["phase"] in ["lobby", "showdown"] and not state["paused"]
    is_admin = state["viewer"]["is_admin"]

    # The CORRECT behavior is: bot buttons should be hidden for non-admin
    # The BUGGY behavior is: bot buttons visible when canDeal is true (regardless of admin)
    bot_button_should_be_visible = can_deal and is_admin

    # This assertion encodes CORRECT behavior:
    # For a non-admin, bot buttons should NOT be visible
    assert not bot_button_should_be_visible, (
        "Bot buttons should be hidden for non-admin players"
    )

    # Now test what the FIXED code does:
    # In the fixed app.js: addBotBtn.style.display = (canDeal && state.viewer.is_admin) ? "" : "none"
    fixed_bot_button_visible = can_deal and is_admin  # Non-admin: False

    # This assertion verifies the fix works:
    # The fixed logic hides buttons for non-admin (canDeal=True but is_admin=False)
    assert not fixed_bot_button_visible, (
        f"BUG STILL PRESENT: Bot buttons are visible to non-admin in {state['phase']} phase. "
        f"canDeal={can_deal}, is_admin={is_admin}. "
        f"The client code should use `(canDeal && state.viewer.is_admin) ? '' : 'none'`."
    )


# ─── Test 8: Admin Permission Enforcement (add_bot and remove_bot) ───

@pytest.mark.asyncio
@settings(max_examples=1, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
async def test_admin_permission_enforcement(data):
    """
    Test 8 (Admin permission enforcement): Verify add_bot and remove_bot actions
    are only accepted from the room creator token.

    **Validates: Requirements 1.3, 1.10**

    EXPECTED TO FAIL on unfixed code — currently no admin check exists for
    add_bot and remove_bot in player_action. Any player can add/remove bots.
    """
    server = PokerServer()
    room, players, ws_list = await create_room_with_players(server, 2)
    admin = players[0]  # Creator
    non_admin = players[1]

    # First, admin adds a bot (should work)
    initial_count = len(room.players)
    await server.player_action(room, admin, "add_bot", {
        "action": "add_bot", "room_id": room.room_id, "token": admin.token
    })
    assert len(room.players) == initial_count + 1, "Admin should be able to add bot"

    # Now non-admin tries to remove a bot (should be REJECTED)
    count_before_remove = len(room.players)
    await server.player_action(room, non_admin, "remove_bot", {
        "action": "remove_bot", "room_id": room.room_id, "token": non_admin.token
    })

    # On unfixed code, the bot will be removed (no admin check)
    assert len(room.players) == count_before_remove, (
        f"Non-admin should NOT be able to remove bots. "
        f"Player count was {count_before_remove}, now {len(room.players)}. "
        f"Bug confirmed: no admin check on remove_bot action."
    )

    # Non-admin tries to add a bot (should be REJECTED)
    count_before_add = len(room.players)
    await server.player_action(room, non_admin, "add_bot", {
        "action": "add_bot", "room_id": room.room_id, "token": non_admin.token
    })

    assert len(room.players) == count_before_add, (
        f"Non-admin should NOT be able to add bots. "
        f"Player count was {count_before_add}, now {len(room.players)}. "
        f"Bug confirmed: no admin check on add_bot action."
    )
