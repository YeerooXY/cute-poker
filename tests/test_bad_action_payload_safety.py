from __future__ import annotations

import json

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


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
    stack: int = 1000,
    committed: int = 0,
    acted: bool = False,
) -> Player:
    ws = DummyWs()
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        committed=committed,
        total_invested=committed,
        cards=["AS", "AH"],
        acted=acted,
        ws=ws,
        connected=True,
    )
    player.hand_start_stack = stack + committed
    return player


def make_room(actor: Player, opponent: Player) -> Room:
    room = Room(room_id="BAD_PAYLOAD")
    room.phase = "preflop"
    room.action_seat = actor.seat
    room.current_bet = 20
    room.min_raise = 20
    room.pot = actor.committed + opponent.committed
    room.players = {
        actor.player_id: actor,
        opponent.player_id: opponent,
    }
    return room


def player_ws(player: Player) -> DummyWs:
    assert isinstance(player.ws, DummyWs)
    return player.ws


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_amount",
    [
        None,
        True,
        False,
        -1,
        "-1",
        "abc",
        "12.5",
        12.5,
        [],
        {},
        {"amount": 40},
    ],
)
async def test_bad_raise_amount_payloads_are_rejected_without_state_change(bad_amount) -> None:
    server = PokerServer()

    actor = make_player("p1", "Actor", seat=1, stack=1000, committed=10)
    opponent = make_player("p2", "Opponent", seat=2, stack=980, committed=20)
    room = make_room(actor, opponent)

    await server.player_action(room, actor, "bet_raise", {"amount": bad_amount})

    assert "Invalid raise amount." in error_messages(player_ws(actor))
    assert actor.stack == 1000
    assert actor.committed == 10
    assert actor.total_invested == 10
    assert opponent.stack == 980
    assert opponent.committed == 20
    assert room.pot == 30
    assert room.current_bet == 20
    assert room.min_raise == 20
    assert room.action_seat == 1


@pytest.mark.asyncio
async def test_missing_raise_amount_is_rejected_as_too_small_without_crashing() -> None:
    server = PokerServer()

    actor = make_player("p1", "Actor", seat=1, stack=1000, committed=10)
    opponent = make_player("p2", "Opponent", seat=2, stack=980, committed=20)
    room = make_room(actor, opponent)

    await server.player_action(room, actor, "bet_raise", {})

    assert "Minimum raise is to 40. You tried 0." in error_messages(player_ws(actor))
    assert actor.stack == 1000
    assert actor.committed == 10
    assert actor.total_invested == 10
    assert room.pot == 30
    assert room.current_bet == 20


@pytest.mark.asyncio
async def test_huge_raise_amount_is_clamped_to_player_all_in() -> None:
    server = PokerServer()

    actor = make_player("p1", "Actor", seat=1, stack=90, committed=10)
    opponent = make_player("p2", "Opponent", seat=2, stack=980, committed=20)
    room = make_room(actor, opponent)

    await server.player_action(room, actor, "bet_raise", {"amount": 10**18})

    assert error_messages(player_ws(actor)) == []
    assert actor.stack == 0
    assert actor.committed == 100
    assert actor.total_invested == 100
    assert actor.all_in is True
    assert room.pot == 120
    assert room.current_bet == 100


@pytest.mark.asyncio
async def test_integer_string_raise_amount_is_accepted() -> None:
    server = PokerServer()

    actor = make_player("p1", "Actor", seat=1, stack=1000, committed=10)
    opponent = make_player("p2", "Opponent", seat=2, stack=980, committed=20)
    room = make_room(actor, opponent)

    await server.player_action(room, actor, "bet_raise", {"amount": "40"})

    assert error_messages(player_ws(actor)) == []
    assert actor.stack == 970
    assert actor.committed == 40
    assert actor.total_invested == 40
    assert room.pot == 60
    assert room.current_bet == 40
