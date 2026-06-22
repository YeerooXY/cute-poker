"""
Unit Tests for add_bot() Advanced AI Defaults
===============================================

Tests that bots created via add_bot() have:
- use_advanced_ai=True
- difficulty in {medium, hard, expert}
- Independent random difficulties across multiple bots in the same room

Requirements: 1.1, 1.2, 1.3
"""

import pytest
from unittest.mock import AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker.game import PokerServer, STARTING_STACK
from poker.models import Player, Room


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


async def create_room_with_admin(server):
    """Create a room with one admin player."""
    ws = make_mock_ws()
    result = await server.create_room(ws, {"name": "Admin", "avatar": "🎭"})
    room = server.rooms[result.room_id]
    return room


# ─── Test: Bot has use_advanced_ai=True (Requirement 1.1) ───

@pytest.mark.asyncio
async def test_add_bot_has_advanced_ai_enabled():
    """A bot created via add_bot() should have use_advanced_ai=True."""
    server = PokerServer()
    room = await create_room_with_admin(server)

    await server.add_bot(room)

    # Find the bot config
    bot_configs = list(server.bots.values())
    assert len(bot_configs) == 1, "Expected exactly one bot config"

    config = bot_configs[0]
    assert config.use_advanced_ai is True, (
        f"Bot should have use_advanced_ai=True, got {config.use_advanced_ai}"
    )


# ─── Test: Bot difficulty is in valid set (Requirement 1.2) ───

@pytest.mark.asyncio
async def test_add_bot_difficulty_in_valid_set():
    """A bot created via add_bot() should have difficulty in {medium, hard, expert}."""
    server = PokerServer()
    room = await create_room_with_admin(server)

    await server.add_bot(room)

    bot_configs = list(server.bots.values())
    assert len(bot_configs) == 1

    config = bot_configs[0]
    valid_difficulties = {"medium", "hard", "expert"}
    assert config.difficulty in valid_difficulties, (
        f"Bot difficulty should be one of {valid_difficulties}, got '{config.difficulty}'"
    )


# ─── Test: Multiple bots get independent random difficulties (Requirement 1.3) ───

@pytest.mark.asyncio
async def test_multiple_bots_get_independent_difficulties():
    """
    Multiple bots in the same room should get independent random difficulties.
    
    We add several bots and verify that over enough trials, not all bots
    end up with the same difficulty (proving independence).
    """
    saw_different = False

    # Run multiple trials to account for randomness
    for _ in range(20):
        server = PokerServer()
        room = await create_room_with_admin(server)

        # Add multiple bots (room has 8 seats, 1 taken by admin)
        for _ in range(3):
            await server.add_bot(room)

        bot_configs = list(server.bots.values())
        assert len(bot_configs) == 3, f"Expected 3 bot configs, got {len(bot_configs)}"

        # All difficulties must be valid
        valid_difficulties = {"medium", "hard", "expert"}
        for config in bot_configs:
            assert config.difficulty in valid_difficulties, (
                f"Bot difficulty should be one of {valid_difficulties}, got '{config.difficulty}'"
            )

        # Check if at least two bots have different difficulties
        difficulties = [c.difficulty for c in bot_configs]
        if len(set(difficulties)) > 1:
            saw_different = True
            break

    assert saw_different, (
        "After 20 trials of adding 3 bots each, all bots always had the same difficulty. "
        "This suggests difficulties are not independently random."
    )
