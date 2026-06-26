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
    cards: list[str] | None = None,
    folded: bool = False,
    all_in: bool = False,
    acted: bool = False,
    is_spectator: bool = False,
    sitting_out: bool = False,
) -> Player:
    ws = DummyWs()
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        committed=committed,
        cards=cards or ["AS", "AH"],
        folded=folded,
        all_in=all_in,
        acted=acted,
        ws=ws,
        connected=True,
        is_spectator=is_spectator,
        sitting_out=sitting_out,
    )
    player.total_invested = committed
    player.hand_start_stack = stack + committed
    return player


def make_room(
    *players: Player,
    phase: str = "preflop",
    action_seat: int | None = 1,
    current_bet: int = 0,
    pot: int = 0,
    creator_token: str | None = None,
) -> Room:
    room = Room(room_id="ACTION_TEST")
    room.phase = phase
    room.action_seat = action_seat
    room.current_bet = current_bet
    room.min_raise = room.big_blind
    room.pot = pot
    room.players = {p.player_id: p for p in players}
    room.creator_token = creator_token or (players[0].token if players else "")
    return room


def player_ws(player: Player) -> DummyWs:
    assert isinstance(player.ws, DummyWs)
    return player.ws


@pytest.mark.asyncio
async def test_out_of_turn_action_is_rejected_without_state_change() -> None:
    server = PokerServer()

    actor = make_player("p1", "Actor", seat=1, stack=1000)
    out_of_turn = make_player("p2", "OutOfTurn", seat=2, stack=1000)
    room = make_room(actor, out_of_turn, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, out_of_turn, "bet_raise", {"amount": 100})

    assert "It is not your turn." in error_messages(player_ws(out_of_turn))
    assert out_of_turn.stack == 1000
    assert out_of_turn.committed == 0
    assert room.pot == 0
    assert room.current_bet == 0
    assert room.action_seat == 1


@pytest.mark.asyncio
async def test_betting_action_is_rejected_outside_betting_phase() -> None:
    server = PokerServer()

    player = make_player("p1", "Player", seat=1, stack=1000)
    room = make_room(player, phase="showdown", action_seat=1)

    await server.player_action(room, player, "check_call", {})

    assert "No betting action is currently available." in error_messages(player_ws(player))
    assert player.stack == 1000
    assert player.committed == 0


@pytest.mark.asyncio
async def test_paused_game_rejects_betting_action() -> None:
    server = PokerServer()

    player = make_player("p1", "Player", seat=1, stack=1000)
    room = make_room(player, phase="preflop", action_seat=1)
    room.paused = True

    await server.player_action(room, player, "bet_raise", {"amount": 100})

    assert "Game is paused." in error_messages(player_ws(player))
    assert player.stack == 1000
    assert player.committed == 0
    assert room.pot == 0


@pytest.mark.asyncio
async def test_under_minimum_raise_is_rejected() -> None:
    server = PokerServer()

    raiser = make_player("p1", "Raiser", seat=1, stack=1000, committed=10)
    caller = make_player("p2", "Caller", seat=2, stack=1000, committed=20)
    room = make_room(raiser, caller, action_seat=1, current_bet=20, pot=30)
    room.min_raise = 20

    await server.player_action(room, raiser, "bet_raise", {"amount": 30})

    assert "Minimum raise is to 40. You tried 30." in error_messages(player_ws(raiser))
    assert raiser.stack == 1000
    assert raiser.committed == 10
    assert room.pot == 30
    assert room.current_bet == 20


@pytest.mark.asyncio
async def test_valid_call_commits_only_amount_needed_to_match_bet() -> None:
    server = PokerServer()

    caller = make_player("p1", "Caller", seat=1, stack=1000, committed=10)
    # Keep the betting round open after Caller acts; this test is about call
    # accounting, not street advancement/dealing.
    bettor = make_player("p2", "Bettor", seat=2, stack=980, committed=20, acted=False)
    room = make_room(caller, bettor, action_seat=1, current_bet=20, pot=30)

    await server.player_action(room, caller, "check_call", {})

    assert error_messages(player_ws(caller)) == []
    assert caller.stack == 990
    assert caller.committed == 20
    assert caller.total_invested == 20
    assert room.pot == 40


@pytest.mark.asyncio
async def test_valid_check_with_no_bet_commits_no_chips() -> None:
    server = PokerServer()

    checker = make_player("p1", "Checker", seat=1, stack=1000, committed=0)
    next_player = make_player("p2", "NextPlayer", seat=2, stack=1000, committed=0)
    room = make_room(checker, next_player, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, checker, "check_call", {})

    assert error_messages(player_ws(checker)) == []
    assert checker.stack == 1000
    assert checker.committed == 0
    assert checker.acted is True
    assert room.pot == 0


@pytest.mark.asyncio
async def test_folded_player_cannot_act_even_if_action_seat_is_stuck() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, stack=1000, folded=True)
    live = make_player("p2", "Live", seat=2, stack=1000)
    room = make_room(folded, live, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, folded, "bet_raise", {"amount": 100})

    assert folded.stack == 1000
    assert folded.committed == 0
    assert room.pot == 0
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_all_in_player_cannot_act_even_if_action_seat_is_stuck() -> None:
    server = PokerServer()

    all_in = make_player("p1", "AllIn", seat=1, stack=0, all_in=True)
    live = make_player("p2", "Live", seat=2, stack=1000)
    room = make_room(all_in, live, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, all_in, "check_call", {})

    assert all_in.stack == 0
    assert all_in.committed == 0
    assert room.pot == 0
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_spectator_cannot_act_even_if_bad_client_sends_action() -> None:
    server = PokerServer()

    spectator = make_player("p1", "Spectator", seat=1, stack=1000, is_spectator=True)
    live = make_player("p2", "Live", seat=2, stack=1000)
    room = make_room(spectator, live, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, spectator, "bet_raise", {"amount": 100})

    assert "Spectators cannot act." in error_messages(player_ws(spectator))
    assert spectator.stack == 1000
    assert spectator.committed == 0
    assert room.pot == 0
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_sitting_out_player_cannot_act_even_if_bad_client_sends_action() -> None:
    server = PokerServer()

    sitting_out = make_player("p1", "SittingOut", seat=1, stack=1000, sitting_out=True)
    live = make_player("p2", "Live", seat=2, stack=1000)
    room = make_room(sitting_out, live, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, sitting_out, "bet_raise", {"amount": 100})

    assert "Sitting-out players cannot act." in error_messages(player_ws(sitting_out))
    assert sitting_out.stack == 1000
    assert sitting_out.committed == 0
    assert room.pot == 0
    assert room.action_seat == 2


@pytest.mark.asyncio
async def test_non_creator_cannot_start_hand_or_manage_room_controls() -> None:
    server = PokerServer()

    creator = make_player("p1", "Creator", seat=1)
    guest = make_player("p2", "Guest", seat=2)
    room = make_room(creator, guest, phase="lobby", action_seat=None, creator_token=creator.token)

    await server.player_action(room, guest, "start_hand", {})
    await server.player_action(room, guest, "add_bot", {})
    await server.player_action(room, guest, "toggle_pause", {})

    errors = error_messages(player_ws(guest))

    assert "Only the room creator can deal the next hand." in errors
    assert "Only the room creator can manage bots." in errors
    assert "Only the room creator can pause." in errors
    assert room.phase == "lobby"
    assert room.paused is False
