"""All-in invariant tests — critical correctness checks.

These test the core poker engine guarantees around all-in scenarios:
- Equal stacks all-in: loser must end at 0
- Total chips conserved
- Both players have equal total_invested after all-in + call
- No street advances with unmatched bets
"""

import asyncio
import os
import pytest

os.environ["POKER_SIMULATION"] = "1"

import poker.game as game_module
from poker.game import PokerServer
from poker.models import Room, Player

game_module._SIMULATION_MODE = True


def make_server():
    server = PokerServer()
    server.send = server.broadcast = lambda *a, **kw: asyncio.sleep(0)
    return server


@pytest.mark.asyncio
async def test_hu_equal_stack_allin_call():
    """Both players 1000, one shoves, other calls. Loser must end at 0."""
    server = make_server()
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room

    p1 = Player(player_id="p1", token="t1", name="Shover", seat=1,
                ws=None, connected=True, stack=1000, avatar="X")
    p2 = Player(player_id="p2", token="t2", name="Caller", seat=2,
                ws=None, connected=True, stack=1000, avatar="X")
    room.players["p1"] = p1
    room.players["p2"] = p2

    await server.start_hand(room)

    # Shover (SB/dealer in HU) goes all-in
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "Shover"
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": "TEST", "token": ap.token,
        "amount": ap.committed + ap.stack,
    })

    # Caller must get to act
    assert room.phase == "preflop", f"Should still be preflop, got {room.phase}"
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "Caller"

    # Caller calls
    await server.player_action(room, ap, "check_call", {
        "action": "check_call", "room_id": "TEST", "token": ap.token,
    })

    # Assertions
    assert room.phase == "showdown"
    assert p1.total_invested == 1000, f"Shover invested {p1.total_invested}, expected 1000"
    assert p2.total_invested == 1000, f"Caller invested {p2.total_invested}, expected 1000"

    # Total chips conserved
    total = p1.stack + p2.stack
    assert total == 2000, f"Chips not conserved: {total}"

    # Loser must have 0
    loser = p1 if p1.stack == 0 else p2
    winner = p1 if p1.stack > 0 else p2
    assert loser.stack == 0, f"Loser should have 0, got {loser.stack}"
    assert winner.stack == 2000, f"Winner should have 2000, got {winner.stack}"

    # pot_breakdown: single main pot of 2000
    assert len(room.pot_breakdown) == 1
    assert room.pot_breakdown[0]["pot"] == 2000


@pytest.mark.asyncio
async def test_hu_unequal_stack_allin():
    """Short stack 400 vs big stack 1000. Short shoves, big calls.
    Verify investments are correct after preflop action."""
    server = make_server()
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room

    p1 = Player(player_id="p1", token="t1", name="Short", seat=1,
                ws=None, connected=True, stack=400, avatar="X")
    p2 = Player(player_id="p2", token="t2", name="Big", seat=2,
                ws=None, connected=True, stack=1000, avatar="X")
    room.players["p1"] = p1
    room.players["p2"] = p2

    await server.start_hand(room)

    # Short shoves
    ap = server.player_by_seat(room, room.action_seat)
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": "TEST", "token": ap.token,
        "amount": ap.committed + ap.stack,
    })

    # Big must still act
    assert room.phase == "preflop"
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "Big"

    # Big calls — matches Short's amount
    await server.player_action(room, ap, "check_call", {
        "action": "check_call", "room_id": "TEST", "token": ap.token,
    })

    # Both players all-in → forced runout to showdown (no further betting)
    assert room.phase == "showdown"
    assert len(room.community) == 5

    # Short invested all 400, Big matched 400
    assert p1.total_invested == 400
    assert p2.total_invested == 400

    # Total chips conserved (starting total was 400 + 1000 = 1400)
    assert p1.stack + p2.stack == 1400
    # Pot was 800 (400 each)
    assert room.pot_breakdown[0]["pot"] == 800


@pytest.mark.asyncio
async def test_bb_shoves_sb_calls():
    """BB shoves, SB calls — verify BB investment is correct."""
    server = make_server()
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room

    p1 = Player(player_id="p1", token="t1", name="SB", seat=1,
                ws=None, connected=True, stack=1000, avatar="X")
    p2 = Player(player_id="p2", token="t2", name="BB", seat=2,
                ws=None, connected=True, stack=1000, avatar="X")
    room.players["p1"] = p1
    room.players["p2"] = p2

    await server.start_hand(room)

    # In HU: seat 1 is dealer/SB, seat 2 is BB
    # SB acts first preflop in HU
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "SB"

    # SB raises to 30
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": "TEST", "token": ap.token, "amount": 30,
    })

    # BB shoves
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "BB"
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": "TEST", "token": ap.token,
        "amount": ap.committed + ap.stack,
    })

    # SB must get to call/fold
    assert room.phase == "preflop"
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "SB"

    # SB calls
    await server.player_action(room, ap, "check_call", {
        "action": "check_call", "room_id": "TEST", "token": ap.token,
    })

    assert room.phase == "showdown"
    assert p1.total_invested == 1000
    assert p2.total_invested == 1000
    assert p1.stack + p2.stack == 2000


@pytest.mark.asyncio
async def test_three_player_various_stacks():
    """3 players with 300/600/1000, all shove. Verify pot tiers and zero-sum."""
    server = make_server()
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room

    p1 = Player(player_id="p1", token="t1", name="Tiny", seat=1,
                ws=None, connected=True, stack=300, avatar="X")
    p2 = Player(player_id="p2", token="t2", name="Mid", seat=2,
                ws=None, connected=True, stack=600, avatar="X")
    p3 = Player(player_id="p3", token="t3", name="Deep", seat=3,
                ws=None, connected=True, stack=1000, avatar="X")
    room.players["p1"] = p1
    room.players["p2"] = p2
    room.players["p3"] = p3

    await server.start_hand(room)

    # Everyone shoves
    while room.phase in ("preflop", "flop", "turn", "river"):
        ap = server.player_by_seat(room, room.action_seat)
        if not ap:
            break
        await server.player_action(room, ap, "bet_raise", {
            "action": "bet_raise", "room_id": "TEST", "token": ap.token,
            "amount": ap.committed + ap.stack,
        })

    assert room.phase == "showdown"

    # Zero-sum: all chips are conserved in the system
    total = p1.stack + p2.stack + p3.stack
    assert total == 1900, f"Chips not conserved: {total}"

    # Should have 2+ pot tiers (main + at least 1 side)
    assert len(room.pot_breakdown) >= 2


@pytest.mark.asyncio
async def test_fold_after_opponent_allin():
    """Player A shoves, player B folds. A wins pot, no showdown cards needed."""
    server = make_server()
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room

    p1 = Player(player_id="p1", token="t1", name="Shover", seat=1,
                ws=None, connected=True, stack=1000, avatar="X")
    p2 = Player(player_id="p2", token="t2", name="Folder", seat=2,
                ws=None, connected=True, stack=1000, avatar="X")
    room.players["p1"] = p1
    room.players["p2"] = p2

    await server.start_hand(room)

    # Shover all-in
    ap = server.player_by_seat(room, room.action_seat)
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": "TEST", "token": ap.token,
        "amount": ap.committed + ap.stack,
    })

    # Folder folds
    assert room.phase == "preflop"
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "Folder"
    await server.player_action(room, ap, "fold", {
        "action": "fold", "room_id": "TEST", "token": ap.token,
    })

    assert room.phase == "showdown"
    assert len(room.winners) == 1
    assert room.winners[0].name == "Shover"
    assert room.winners[0].reason == "Everyone else folded"

    # Shover gets the pot (BB blind from folder = 10 chips)
    assert p1.stack + p2.stack == 2000
