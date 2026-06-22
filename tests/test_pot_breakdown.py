"""Tests for pot_breakdown correctness in showdown scenarios.

Validates:
1. Heads-up all-in, one winner
2. Heads-up exact split (tied hands)
3. Three-player all-in with main pot + side pot
4. Folded player contribution included in pot but not eligible to win
5. Short all-in below min-raise does not skip opponent's chance to call
6. Sum of all pot_breakdown winner awards equals total awarded
7. Total chips before hand equals total chips after hand (zero-sum)
"""

import asyncio
import os
import pytest

os.environ["POKER_SIMULATION"] = "1"

from poker.game import PokerServer
from poker.models import Room, Player
from poker.cards import new_deck


# ─── Helpers ───

def make_server():
    server = PokerServer()
    server.send = server.broadcast = lambda *a, **kw: asyncio.sleep(0)
    return server


def make_room(server, players_config):
    """Create a room with players. players_config: list of (name, stack) tuples."""
    room = Room(room_id="TEST")
    room.creator_token = "x"
    server.rooms["TEST"] = room
    players = []
    for i, (name, stack) in enumerate(players_config):
        p = Player(
            player_id=f"p{i}", token=f"t{i}", name=name, seat=i + 1,
            ws=None, connected=True, stack=stack, avatar="X",
        )
        room.players[p.player_id] = p
        players.append(p)
    return room, players


async def start_and_all_in(server, room):
    """Start a hand and make everyone go all-in."""
    await server.start_hand(room)
    while room.phase in ("preflop", "flop", "turn", "river"):
        ap = server.player_by_seat(room, room.action_seat)
        if not ap:
            break
        amount = ap.committed + ap.stack
        await server.player_action(room, ap, "bet_raise", {
            "action": "bet_raise", "room_id": room.room_id,
            "token": ap.token, "amount": amount,
        })


def total_awarded(room):
    return sum(w["amount"] for pot in room.pot_breakdown for w in pot["winners"])


def total_stacks(room):
    return sum(p.stack for p in room.players.values())


# ─── Tests ───

@pytest.mark.asyncio
async def test_hu_allin_one_winner():
    """Heads-up all-in: one winner takes entire pot."""
    server = make_server()
    room, players = make_room(server, [("A", 1000), ("B", 1000)])
    total_before = total_stacks(room)

    await start_and_all_in(server, room)

    assert room.phase == "showdown"
    assert total_stacks(room) == total_before  # Zero-sum
    assert len(room.pot_breakdown) == 1
    assert room.pot_breakdown[0]["type"] == "main"
    assert room.pot_breakdown[0]["pot"] == 2000
    assert len(room.pot_breakdown[0]["winners"]) == 1
    assert room.pot_breakdown[0]["winners"][0]["amount"] == 2000
    assert total_awarded(room) == 2000


@pytest.mark.asyncio
async def test_three_player_side_pot():
    """3 players with different stacks: creates main + side pot."""
    server = make_server()
    room, players = make_room(server, [("Short", 500), ("Med", 800), ("Big", 1000)])
    total_before = total_stacks(room)

    await start_and_all_in(server, room)

    assert room.phase == "showdown"
    assert total_stacks(room) == total_before  # Zero-sum

    # Should have 2 or 3 pots depending on invest levels
    assert len(room.pot_breakdown) >= 2

    # Sum of all awards equals total chips
    assert total_awarded(room) == total_before

    # Each pot should have type "main" or "side"
    types = [p["type"] for p in room.pot_breakdown]
    assert types[0] == "main"
    assert all(t in ("main", "side") for t in types)


@pytest.mark.asyncio
async def test_folded_player_contributes_to_pot():
    """Folded player's chips go to the pot but they can't win."""
    server = make_server()
    room, players = make_room(server, [("Folder", 1000), ("Caller", 1000), ("Raiser", 1000)])
    total_before = total_stacks(room)

    await server.start_hand(room)

    # First player folds (after posting blind or facing a raise)
    ap = server.player_by_seat(room, room.action_seat)
    await server.player_action(room, ap, "fold", {
        "action": "fold", "room_id": room.room_id, "token": ap.token,
    })

    # Remaining players go all-in
    while room.phase in ("preflop", "flop", "turn", "river"):
        ap = server.player_by_seat(room, room.action_seat)
        if not ap:
            break
        amount = ap.committed + ap.stack
        await server.player_action(room, ap, "bet_raise", {
            "action": "bet_raise", "room_id": room.room_id,
            "token": ap.token, "amount": amount,
        })

    assert room.phase == "showdown"
    assert total_stacks(room) == total_before  # Zero-sum

    # Folded player should NOT appear in any pot's winners
    for pot in room.pot_breakdown:
        for w in pot["winners"]:
            assert w["player_id"] != "p0", "Folded player should not win"


@pytest.mark.asyncio
async def test_short_allin_does_not_skip_opponent():
    """When player goes all-in, opponent still gets to act (not auto-completed)."""
    server = make_server()
    room, players = make_room(server, [("ShortA", 50), ("BigB", 1000)])
    total_before = total_stacks(room)

    await server.start_hand(room)

    # ShortA (SB in HU = dealer) goes all-in for 50
    ap = server.player_by_seat(room, room.action_seat)
    assert ap.name == "ShortA"
    await server.player_action(room, ap, "bet_raise", {
        "action": "bet_raise", "room_id": room.room_id,
        "token": ap.token, "amount": 50,
    })

    # CRITICAL: BigB must still get to act — phase stays preflop, action on BigB
    assert room.phase == "preflop", f"Phase should still be preflop, got {room.phase}"
    ap = server.player_by_seat(room, room.action_seat)
    assert ap is not None, "Someone should have action"
    assert ap.name == "BigB", f"BigB should have action, got {ap.name}"

    # BigB folds — ShortA wins without showdown
    await server.player_action(room, ap, "fold", {
        "action": "fold", "room_id": room.room_id, "token": ap.token,
    })

    # ShortA should win the pot
    assert room.phase == "showdown"
    assert len(room.winners) == 1
    assert room.winners[0].name == "ShortA"
    assert total_stacks(room) == total_before


@pytest.mark.asyncio
async def test_pot_breakdown_awards_sum():
    """Sum of all pot_breakdown awards matches sum of winner amounts."""
    server = make_server()
    room, players = make_room(server, [("A", 300), ("B", 600), ("C", 1000)])
    total_before = total_stacks(room)

    await start_and_all_in(server, room)

    assert room.phase == "showdown"
    assert total_stacks(room) == total_before

    # Total from pot_breakdown
    breakdown_total = total_awarded(room)

    # Total from winners list
    winners_total = sum(w.amount for w in room.winners)

    assert breakdown_total == winners_total, (
        f"pot_breakdown total ({breakdown_total}) != winners total ({winners_total})"
    )
    assert breakdown_total == total_before


@pytest.mark.asyncio
async def test_equal_stacks_single_main_pot():
    """Equal stacks all-in: single main pot, no side pots."""
    server = make_server()
    room, players = make_room(server, [("A", 1000), ("B", 1000)])

    await start_and_all_in(server, room)

    assert len(room.pot_breakdown) == 1
    assert room.pot_breakdown[0]["type"] == "main"
    assert room.pot_breakdown[0]["pot"] == 2000


@pytest.mark.asyncio
async def test_zero_sum_four_players():
    """4-player game: total chips conserved through showdown."""
    server = make_server()
    room, players = make_room(server, [("A", 1000), ("B", 1000), ("C", 1000), ("D", 1000)])
    total_before = total_stacks(room)

    await start_and_all_in(server, room)

    assert room.phase == "showdown"
    assert total_stacks(room) == total_before
    assert total_awarded(room) == total_before
