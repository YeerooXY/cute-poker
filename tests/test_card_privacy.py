from __future__ import annotations

import json

import pytest

from poker.game import PokerServer
from poker.models import Player, Room, Winner


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
    cards: list[str] | None = None,
    folded: bool = False,
    is_spectator: bool = False,
) -> Player:
    ws = DummyWs()
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=1000,
        cards=cards or ["AS", "AH"],
        folded=folded,
        is_spectator=is_spectator,
        connected=True,
        ws=ws,
    )
    player.hand_start_stack = 1000
    return player


def make_room(*players: Player, phase: str = "showdown") -> Room:
    room = Room(room_id="PRIVACY_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.allow_folded_reveals = True
    return room


def state_player(state: dict, player_id: str) -> dict:
    player = next((p for p in state["players"] if p["id"] == player_id), None)
    assert player is not None
    return player


def player_ws(player: Player) -> DummyWs:
    assert isinstance(player.ws, DummyWs)
    return player.ws


def test_folded_cards_hidden_from_other_players_and_spectators() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    spectator = make_player("p3", "Spectator", seat=3, is_spectator=True, cards=[])

    room = make_room(folded, opponent, spectator, phase="showdown")

    opponent_state = server.visible_state(room, opponent.token)
    spectator_state = server.visible_state(room, spectator.token)

    folded_for_opponent = state_player(opponent_state, "p1")
    folded_for_spectator = state_player(spectator_state, "p1")

    assert folded_for_opponent["cards"] == ["🂠", "🂠"]
    assert folded_for_spectator["cards"] == ["🂠", "🂠"]
    assert folded_for_opponent["would_have_hand_name"] == ""
    assert folded_for_spectator["would_have_hand_name"] == ""


def test_folded_player_still_sees_own_folded_cards() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    room = make_room(folded, opponent, phase="showdown")

    folded_state = server.visible_state(room, folded.token)
    folded_self = state_player(folded_state, "p1")

    assert folded_self["cards"] == ["A♠", "K♥"]
    assert folded_self["can_reveal_folded_hand"] is True


@pytest.mark.asyncio
async def test_folded_partial_reveal_exposes_only_selected_card() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    room = make_room(folded, opponent, phase="showdown")

    await server.reveal_folded_hand(room, folded, {"mode": "left"})

    opponent_state = server.visible_state(room, opponent.token)
    folded_for_opponent = state_player(opponent_state, "p1")

    assert folded_for_opponent["cards"] == ["A♠", "🂠"]
    assert folded_for_opponent["folded_reveal_mode"] == "left"
    assert folded_for_opponent["would_have_hand_name"] == ""


@pytest.mark.asyncio
async def test_folded_second_partial_reveal_upgrades_to_both_cards() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    room = make_room(folded, opponent, phase="showdown")

    await server.reveal_folded_hand(room, folded, {"mode": "left"})
    await server.reveal_folded_hand(room, folded, {"mode": "right"})

    opponent_state = server.visible_state(room, opponent.token)
    folded_for_opponent = state_player(opponent_state, "p1")

    assert folded_for_opponent["cards"] == ["A♠", "K♥"]
    assert folded_for_opponent["folded_reveal_mode"] == "both"
    assert folded_for_opponent["would_have_hand_name"] != ""
    assert folded_for_opponent["would_have_best_cards"]


@pytest.mark.asyncio
async def test_mucked_folded_hand_stays_hidden_and_cannot_be_revealed_later() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    room = make_room(folded, opponent, phase="showdown")

    await server.reveal_folded_hand(room, folded, {"mode": "muck"})
    await server.reveal_folded_hand(room, folded, {"mode": "both"})

    opponent_state = server.visible_state(room, opponent.token)
    folded_for_opponent = state_player(opponent_state, "p1")

    assert folded_for_opponent["cards"] == ["🂠", "🂠"]
    assert folded_for_opponent["folded_reveal_mode"] == "muck"
    assert "This folded hand has already been mucked." in error_messages(player_ws(folded))


@pytest.mark.asyncio
async def test_folded_reveal_disabled_blocks_public_reveal() -> None:
    server = PokerServer()

    folded = make_player("p1", "Folded", seat=1, cards=["AS", "KH"], folded=True)
    opponent = make_player("p2", "Opponent", seat=2, cards=["QS", "QH"])
    room = make_room(folded, opponent, phase="showdown")
    room.allow_folded_reveals = False

    await server.reveal_folded_hand(room, folded, {"mode": "both"})

    opponent_state = server.visible_state(room, opponent.token)
    folded_for_opponent = state_player(opponent_state, "p1")

    assert folded_for_opponent["cards"] == ["🂠", "🂠"]
    assert folded_for_opponent["folded_reveal_mode"] == "hidden"
    assert "Folded hand reveals are disabled in this room." in error_messages(player_ws(folded))


def test_uncontested_winner_cards_hidden_from_others_by_default() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "KH"], folded=False)
    folded_opponent = make_player("p2", "FoldedOpponent", seat=2, cards=["QS", "QH"], folded=True)
    room = make_room(winner, folded_opponent, phase="showdown")
    room.winners = [
        Winner(winner.player_id, winner.name, 100, "Everyone else folded")
    ]

    opponent_state = server.visible_state(room, folded_opponent.token)
    winner_for_opponent = state_player(opponent_state, "p1")

    assert winner_for_opponent["cards"] == ["🂠", "🂠"]
    assert winner_for_opponent["uncontested_reveal_mode"] == "hidden"

    # No accidental best-card leak for an uncontested/non-showdown win.
    visible_winner = opponent_state["winners"][0]
    assert visible_winner["best_cards"] == []


def test_uncontested_winner_sees_own_cards_and_reveal_controls() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "KH"], folded=False)
    folded_opponent = make_player("p2", "FoldedOpponent", seat=2, cards=["QS", "QH"], folded=True)
    room = make_room(winner, folded_opponent, phase="showdown")
    room.winners = [
        Winner(winner.player_id, winner.name, 100, "Everyone else folded")
    ]

    winner_state = server.visible_state(room, winner.token)
    winner_self = state_player(winner_state, "p1")

    assert winner_self["cards"] == ["A♠", "K♥"]
    assert winner_self["can_reveal_uncontested_hand"] is True


@pytest.mark.asyncio
async def test_uncontested_partial_reveal_exposes_only_selected_card() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "KH"], folded=False)
    folded_opponent = make_player("p2", "FoldedOpponent", seat=2, cards=["QS", "QH"], folded=True)
    room = make_room(winner, folded_opponent, phase="showdown")
    room.winners = [
        Winner(winner.player_id, winner.name, 100, "Everyone else folded")
    ]

    await server.reveal_uncontested_hand(room, winner, {"mode": "right"})

    opponent_state = server.visible_state(room, folded_opponent.token)
    winner_for_opponent = state_player(opponent_state, "p1")

    assert winner_for_opponent["cards"] == ["🂠", "K♥"]
    assert winner_for_opponent["uncontested_reveal_mode"] == "right"


@pytest.mark.asyncio
async def test_uncontested_second_partial_reveal_upgrades_to_both_cards() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "KH"], folded=False)
    folded_opponent = make_player("p2", "FoldedOpponent", seat=2, cards=["QS", "QH"], folded=True)
    room = make_room(winner, folded_opponent, phase="showdown")
    room.winners = [
        Winner(winner.player_id, winner.name, 100, "Everyone else folded")
    ]

    await server.reveal_uncontested_hand(room, winner, {"mode": "right"})
    await server.reveal_uncontested_hand(room, winner, {"mode": "left"})

    opponent_state = server.visible_state(room, folded_opponent.token)
    winner_for_opponent = state_player(opponent_state, "p1")

    assert winner_for_opponent["cards"] == ["A♠", "K♥"]
    assert winner_for_opponent["uncontested_reveal_mode"] == "both"


@pytest.mark.asyncio
async def test_non_winner_cannot_reveal_uncontested_winner_hand() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "KH"], folded=False)
    folded_opponent = make_player("p2", "FoldedOpponent", seat=2, cards=["QS", "QH"], folded=True)
    room = make_room(winner, folded_opponent, phase="showdown")
    room.winners = [
        Winner(winner.player_id, winner.name, 100, "Everyone else folded")
    ]

    await server.reveal_uncontested_hand(room, folded_opponent, {"mode": "both"})

    opponent_state = server.visible_state(room, folded_opponent.token)
    winner_for_opponent = state_player(opponent_state, "p1")

    assert winner_for_opponent["cards"] == ["🂠", "🂠"]
    assert "You do not have an uncontested winning hand to reveal." in error_messages(player_ws(folded_opponent))
