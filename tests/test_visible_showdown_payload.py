from __future__ import annotations

import pytest

from poker.cards import display_cards
from poker.game import PokerServer
from poker.models import Player, Room, Winner


@pytest.fixture(autouse=True)
def cheap_visible_state_odds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "poker.game.calculate_player_odds",
        lambda *_args, **_kwargs: {
            "equity": 50,
            "current_ahead": None,
            "phase_note": "",
        },
    )


def make_player(
    player_id: str,
    name: str,
    seat: int,
    cards: list[str] | None = None,
    stack: int = 1000,
    folded: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        cards=cards or [],
        folded=folded,
        connected=True,
    )
    player.hand_start_stack = 1000
    return player


def make_room(*players: Player, phase: str = "showdown") -> Room:
    room = Room(room_id="VISIBLE_SHOWDOWN_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 400
    room.current_bet = 0
    room.action_seat = None
    return room


def player_state(state: dict, player_id: str) -> dict:
    for player in state["players"]:
        if player["id"] == player_id:
            return player
    raise AssertionError(f"player {player_id} not found in visible state")


def test_visible_state_exposes_showdown_winners_pot_breakdown_and_deltas() -> None:
    server = PokerServer()

    winner = make_player("p1", "Winner", seat=1, cards=["AS", "AH"], stack=1200)
    loser = make_player("p2", "Loser", seat=2, cards=["KS", "KH"], stack=800)

    winner.last_hand_name = "One Pair"
    winner.last_hand_detail = "Pair of aces"
    winner.last_best_cards = ["AS", "AH", "JH", "9S", "5D"]

    loser.last_hand_name = "One Pair"
    loser.last_hand_detail = "Pair of kings"
    loser.last_best_cards = ["KS", "KH", "JH", "9S", "5D"]

    room = make_room(winner, loser)

    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=400,
            reason="Best hand at showdown",
            hand_name=winner.last_hand_name,
            hand_detail=winner.last_hand_detail,
            best_cards=winner.last_best_cards,
        )
    ]
    room.pot_breakdown = [
        {
            "type": "main",
            "pot": 400,
            "eligible": ["p1", "p2"],
            "winners": [
                {
                    "player_id": "p1",
                    "name": "Winner",
                    "amount": 400,
                    "hand_name": "One Pair",
                }
            ],
        }
    ]
    room.hand_deltas = {
        winner.player_id: 200,
        loser.player_id: -200,
    }

    state = server.visible_state(room, winner.token)

    assert state["phase"] == "showdown"
    assert state["showdown_mode"] is True
    assert state["pot"] == 400

    assert state["winners"] == [
        {
            "player_id": "p1",
            "name": "Winner",
            "amount": 400,
            "reason": "Best hand at showdown",
            "hand_name": "One Pair",
            "hand_detail": "Pair of aces",
            "best_cards": display_cards(winner.last_best_cards),
        }
    ]

    assert state["pot_breakdown"] == room.pot_breakdown

    # Public room-level hand deltas are keyed by display name for frontend use.
    assert state["hand_deltas"] == {
        "Winner": 200,
        "Loser": -200,
    }

    winner_state = player_state(state, winner.player_id)
    loser_state = player_state(state, loser.player_id)

    # Per-player deltas remain attached to the correct player id.
    assert winner_state["hand_delta"] == 200
    assert loser_state["hand_delta"] == -200

    assert winner_state["hand_name"] == "One Pair"
    assert winner_state["hand_detail"] == "Pair of aces"
    assert winner_state["best_cards"] == display_cards(winner.last_best_cards)

    assert loser_state["hand_name"] == "One Pair"
    assert loser_state["hand_detail"] == "Pair of kings"
    assert loser_state["best_cards"] == display_cards(loser.last_best_cards)

    assert winner_state["cards"] == display_cards(winner.cards)
    assert loser_state["cards"] == display_cards(loser.cards)


def test_visible_state_does_not_expose_hand_deltas_before_showdown() -> None:
    server = PokerServer()

    p1 = make_player("p1", "PlayerOne", seat=1, cards=["AS", "AH"], stack=900)
    p2 = make_player("p2", "PlayerTwo", seat=2, cards=["KS", "KH"], stack=1100)

    room = make_room(p1, p2, phase="river")
    room.action_seat = p1.seat
    room.hand_deltas = {
        p1.player_id: -100,
        p2.player_id: 100,
    }

    state = server.visible_state(room, p1.token)

    assert state["phase"] == "river"
    assert state["showdown_mode"] is False
    assert state["hand_deltas"] == {}

    assert player_state(state, p1.player_id)["hand_delta"] is None
    assert player_state(state, p2.player_id)["hand_delta"] is None


def test_locked_runout_visible_state_has_showdown_mode_no_action_and_reveals_live_cards() -> None:
    server = PokerServer()

    p1 = make_player("p1", "AllInOne", seat=1, cards=["AS", "AH"], stack=0)
    p2 = make_player("p2", "AllInTwo", seat=2, cards=["KS", "KH"], stack=0)

    p1.all_in = True
    p2.all_in = True

    room = make_room(p1, p2, phase="turn")
    room.community = ["2C", "5D", "9S", "JH"]
    room.action_seat = None
    room.current_bet = 0
    room.winners = []

    state_for_p1 = server.visible_state(room, p1.token)
    state_for_p2 = server.visible_state(room, p2.token)

    assert state_for_p1["phase"] == "turn"
    assert state_for_p1["showdown_mode"] is True
    assert state_for_p1["viewer"]["is_turn"] is False
    assert state_for_p1["viewer"]["to_call"] == 0

    assert not any(player["is_action"] for player in state_for_p1["players"])

    # During locked all-in runout, there are no more decisions. The UI can show
    # both live contenders while the backend still deals remaining streets.
    assert player_state(state_for_p1, p1.player_id)["cards"] == display_cards(p1.cards)
    assert player_state(state_for_p1, p2.player_id)["cards"] == display_cards(p2.cards)

    assert player_state(state_for_p2, p1.player_id)["cards"] == display_cards(p1.cards)
    assert player_state(state_for_p2, p2.player_id)["cards"] == display_cards(p2.cards)


def test_visible_showdown_payload_uses_empty_result_lists_when_no_winners_yet() -> None:
    server = PokerServer()

    p1 = make_player("p1", "PlayerOne", seat=1, cards=["AS", "AH"])
    p2 = make_player("p2", "PlayerTwo", seat=2, cards=["KS", "KH"])

    room = make_room(p1, p2, phase="showdown")
    room.winners = []
    room.pot_breakdown = []
    room.hand_deltas = {}

    state = server.visible_state(room, p1.token)

    assert state["phase"] == "showdown"
    assert state["showdown_mode"] is True
    assert state["winners"] == []
    assert state["pot_breakdown"] == []
    assert state["hand_deltas"] == {}

    assert player_state(state, p1.player_id)["hand_delta"] is None
    assert player_state(state, p2.player_id)["hand_delta"] is None


def test_visible_state_preserves_pot_breakdown_shape_for_split_side_pots() -> None:
    server = PokerServer()

    p1 = make_player("p1", "ShortWinner", seat=1, cards=["AS", "AH"])
    p2 = make_player("p2", "SideOne", seat=2, cards=["KS", "QD"])
    p3 = make_player("p3", "SideTwo", seat=3, cards=["KH", "QC"])

    room = make_room(p1, p2, p3)

    room.winners = [
        Winner("p1", "ShortWinner", 150, "Best hand at showdown", "One Pair", [], []),
        Winner("p2", "SideOne", 50, "Best hand at showdown", "High Card", [], []),
        Winner("p3", "SideTwo", 50, "Best hand at showdown", "High Card", [], []),
    ]
    room.pot_breakdown = [
        {
            "type": "main",
            "pot": 150,
            "eligible": ["p1", "p2", "p3"],
            "winners": [
                {
                    "player_id": "p1",
                    "name": "ShortWinner",
                    "amount": 150,
                    "hand_name": "One Pair",
                }
            ],
        },
        {
            "type": "side",
            "pot": 100,
            "eligible": ["p2", "p3"],
            "winners": [
                {
                    "player_id": "p2",
                    "name": "SideOne",
                    "amount": 50,
                    "hand_name": "High Card",
                },
                {
                    "player_id": "p3",
                    "name": "SideTwo",
                    "amount": 50,
                    "hand_name": "High Card",
                },
            ],
        },
    ]

    state = server.visible_state(room, p1.token)

    assert state["pot_breakdown"] == room.pot_breakdown
    assert sum(tier["pot"] for tier in state["pot_breakdown"]) == 250
    assert sum(
        winner["amount"]
        for tier in state["pot_breakdown"]
        for winner in tier["winners"]
    ) == 250
