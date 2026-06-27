from __future__ import annotations

import json

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


FULL_BOARD = ["2C", "5D", "9S", "JH", "3C"]


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


@pytest.fixture(autouse=True)
def fast_runout_and_no_hand_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poker.game._SIMULATION_MODE", True)
    monkeypatch.setattr("poker.game.save_hand_log", lambda _room: None)


def make_player(
    player_id: str,
    name: str,
    seat: int,
    cards: list[str],
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=0,
        committed=100,
        cards=cards,
        folded=False,
        all_in=True,
        acted=True,
        connected=True,
        ws=DummyWs(),
    )
    player.total_invested = 100
    player.hand_start_stack = 100
    return player


def make_all_in_room(
    phase: str,
    community: list[str],
    deck: list[str],
    action_seat: int | None = 1,
) -> tuple[Room, Player, Player]:
    winner = make_player("p1", "PocketAces", seat=1, cards=["AS", "AH"])
    loser = make_player("p2", "PocketKings", seat=2, cards=["KS", "KH"])

    room = Room(room_id="RUNOUT_TEST")
    room.phase = phase
    room.players = {
        winner.player_id: winner,
        loser.player_id: loser,
    }
    room.creator_token = winner.token
    room.dealer_seat = 1
    room.sb_seat = 1
    room.bb_seat = 2
    room.action_seat = action_seat
    room.current_bet = 100
    room.min_raise = room.big_blind
    room.pot = 200
    room.community = community[:]
    room.deck = deck[:]

    return room, winner, loser


def preflop_runout_deck() -> list[str]:
    # pop order:
    # burn, flop1, flop2, flop3, burn, turn, burn, river
    return ["3C", "8D", "JH", "7S", "9S", "5D", "2C", "4H"]


def flop_runout_deck() -> list[str]:
    # pop order:
    # burn, turn, burn, river
    return ["3C", "8D", "JH", "7S"]


def turn_runout_deck() -> list[str]:
    # pop order:
    # burn, river
    return ["3C", "8D"]


def state_messages(player: Player) -> list[dict]:
    assert isinstance(player.ws, DummyWs)
    return [
        message["payload"]
        for message in player.ws.sent
        if message.get("event") == "state"
    ]


def assert_clean_showdown_result(
    room: Room,
    winner: Player,
    loser: Player,
    expected_board: list[str],
) -> None:
    assert room.phase == "showdown"
    assert room.action_seat is None
    assert room.community == expected_board

    # Per-street state should be cleared before showdown.
    assert room.current_bet == 0
    assert winner.committed == 0
    assert loser.committed == 0

    # But total investment must remain for side-pot/showdown accounting.
    assert winner.total_invested == 100
    assert loser.total_invested == 100

    assert len(room.winners) == 1
    assert room.winners[0].player_id == winner.player_id
    assert room.winners[0].amount == 200

    assert winner.stack == 200
    assert loser.stack == 0

    assert winner.last_hand_name
    assert loser.last_hand_name
    assert winner.last_best_cards
    assert loser.last_best_cards

    assert sum(w.amount for w in room.winners) == room.pot


@pytest.mark.asyncio
async def test_after_action_forces_preflop_all_in_runout_with_real_deck() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="preflop",
        community=[],
        deck=preflop_runout_deck(),
        action_seat=1,
    )

    await server.after_action(room)

    assert_clean_showdown_result(room, winner, loser, FULL_BOARD)


@pytest.mark.asyncio
async def test_preflop_runout_broadcasts_locked_no_action_state_before_dealing() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="preflop",
        community=[],
        deck=preflop_runout_deck(),
        action_seat=1,
    )

    await server.runout_to_showdown(room)

    winner_states = state_messages(winner)
    loser_states = state_messages(loser)

    assert winner_states
    assert loser_states

    first_state = winner_states[0]

    # The first broadcast happens before the board runs out, but after decisions
    # are locked. This is the important anti-"ghost action" state.
    assert first_state["phase"] == "preflop"
    assert first_state["showdown_mode"] is True
    assert first_state["community"] == []
    assert first_state["viewer"]["is_turn"] is False
    assert not any(player["is_action"] for player in first_state["players"])

    assert_clean_showdown_result(room, winner, loser, FULL_BOARD)


@pytest.mark.asyncio
async def test_flop_all_in_runout_deals_turn_and_river_then_showdown() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="flop",
        community=FULL_BOARD[:3],
        deck=flop_runout_deck(),
        action_seat=1,
    )

    await server.runout_to_showdown(room)

    assert_clean_showdown_result(room, winner, loser, FULL_BOARD)


@pytest.mark.asyncio
async def test_turn_all_in_runout_deals_river_then_showdown() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="turn",
        community=FULL_BOARD[:4],
        deck=turn_runout_deck(),
        action_seat=1,
    )

    await server.runout_to_showdown(room)

    assert_clean_showdown_result(room, winner, loser, FULL_BOARD)


@pytest.mark.asyncio
async def test_river_all_in_runout_goes_directly_to_showdown_without_deck() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="river",
        community=FULL_BOARD,
        deck=[],
        action_seat=1,
    )

    await server.runout_to_showdown(room)

    assert_clean_showdown_result(room, winner, loser, FULL_BOARD)


@pytest.mark.asyncio
async def test_runout_preserves_pot_accounting_after_committed_chips_are_cleared() -> None:
    server = PokerServer()
    room, winner, loser = make_all_in_room(
        phase="flop",
        community=FULL_BOARD[:3],
        deck=flop_runout_deck(),
        action_seat=1,
    )

    assert winner.committed == 100
    assert loser.committed == 100
    assert winner.total_invested == 100
    assert loser.total_invested == 100
    assert room.pot == 200

    await server.runout_to_showdown(room)

    assert winner.committed == 0
    assert loser.committed == 0
    assert winner.total_invested == 100
    assert loser.total_invested == 100
    assert room.pot == 200
    assert sum(w.amount for w in room.winners) == 200
