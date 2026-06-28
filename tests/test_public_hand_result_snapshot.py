from __future__ import annotations

import json

from poker.game import PokerServer
from poker.models import Player, Room, Winner


BACK = "\U0001f0a0"


def make_player(
    player_id: str,
    name: str,
    seat: int,
    cards: list[str],
    folded: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"secret_token_{player_id}",
        name=name,
        seat=seat,
        stack=1000,
        cards=cards,
        folded=folded,
        acted=True,
    )
    player.hand_start_stack = 1000
    return player


def make_showdown_room(*players: Player) -> Room:
    room = Room(room_id="RESULT1")
    room.phase = "showdown"
    room.hands_played = 3
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 120
    room.players = {p.player_id: p for p in players}
    return room


def by_name(snapshot: dict, name: str) -> dict:
    return next(player for player in snapshot["players"] if player["name"] == name)


def test_public_result_snapshot_hides_unrevealed_folded_cards_and_private_fields():
    server = PokerServer()

    winner = make_player("p1", "Winner", 1, ["AS", "AH"])
    winner.last_hand_name = "One Pair"
    winner.last_hand_detail = "Pair of Aces"
    winner.last_best_cards = ["AS", "AH", "JH", "9S", "5D"]

    folder = make_player("p2", "Folder", 2, ["QS", "QH"], folded=True)

    room = make_showdown_room(winner, folder)
    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=120,
            reason="Best hand at showdown",
            hand_name="One Pair",
            best_cards=["AS", "AH", "JH", "9S", "5D"],
            hand_detail="Pair of Aces",
        )
    ]
    room.action_log = [
        {
            "player": "Folder",
            "action": "fold",
            "amount": 0,
            "phase": "river",
            "is_all_in": False,
            "hole_cards": ["QS", "QH"],
            "ai_debug": {"should_not": "leak"},
        }
    ]

    snapshot = server.public_hand_result(room)
    encoded = json.dumps(snapshot)

    assert snapshot["completed"] is True
    assert snapshot["community"] == ["2\u2663", "5\u2666", "9\u2660", "J\u2665", "3\u2663"]

    assert by_name(snapshot, "Winner")["cards"] == ["A\u2660", "A\u2665"]
    assert by_name(snapshot, "Folder")["cards"] == [BACK, BACK]

    assert "secret_token" not in encoded
    assert "hole_cards" not in encoded
    assert "ai_debug" not in encoded
    assert "QS" not in encoded
    assert "QH" not in encoded


def test_public_result_snapshot_respects_folded_partial_reveal():
    server = PokerServer()

    winner = make_player("p1", "Winner", 1, ["AS", "AH"])
    folder = make_player("p2", "Folder", 2, ["QS", "QH"], folded=True)
    folder.folded_reveal_mode = "left"

    room = make_showdown_room(winner, folder)
    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=120,
            reason="Best hand at showdown",
        )
    ]

    snapshot = server.public_hand_result(room)

    assert by_name(snapshot, "Folder")["cards"] == ["Q\u2660", BACK]
    assert "Q\u2665" not in json.dumps(snapshot)


def test_public_result_snapshot_keeps_uncontested_winner_cards_hidden_until_revealed():
    server = PokerServer()

    winner = make_player("p1", "Winner", 1, ["AS", "AH"])
    folder = make_player("p2", "Folder", 2, ["QS", "QH"], folded=True)

    room = make_showdown_room(winner, folder)
    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=120,
            reason="Everyone else folded",
        )
    ]

    hidden = server.public_hand_result(room)
    assert by_name(hidden, "Winner")["cards"] == [BACK, BACK]

    winner.uncontested_reveal_mode = "right"
    partially_revealed = server.public_hand_result(room)

    assert by_name(partially_revealed, "Winner")["cards"] == [BACK, "A\u2665"]


def test_public_result_snapshot_sanitizes_pot_breakdown_and_action_log():
    server = PokerServer()

    winner = make_player("p1", "Winner", 1, ["AS", "AH"])
    loser = make_player("p2", "Loser", 2, ["KS", "KH"])

    room = make_showdown_room(winner, loser)
    room.hand_deltas = {
        winner.player_id: 50,
        loser.player_id: -50,
    }
    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=120,
            reason="Best hand at showdown",
            hand_name="One Pair",
        )
    ]
    room.pot_breakdown = [
        {
            "type": "main",
            "pot": 120,
            "eligible": [winner.player_id, loser.player_id],
            "winners": [
                {
                    "player_id": winner.player_id,
                    "name": winner.name,
                    "amount": 120,
                    "hand_name": "One Pair",
                    "private": "drop me",
                }
            ],
            "debug": "drop me too",
        }
    ]
    room.action_log = [
        {
            "player": "Winner",
            "action": "check_call",
            "amount": 20,
            "phase": "river",
            "is_all_in": False,
            "hole_cards": ["AS", "AH"],
            "pot": 120,
            "stack": 980,
        }
    ]

    snapshot = server.public_hand_result(room)
    encoded = json.dumps(snapshot)

    assert snapshot["hand_deltas"] == {"Winner": 50, "Loser": -50}
    assert snapshot["hand_deltas_by_player_id"] == {"p1": 50, "p2": -50}

    pots = snapshot["pot_breakdown"]
    assert len(pots) == 1

    main_pot = pots[0]
    assert main_pot["id"] == 0
    assert main_pot["pot_id"] == 0
    assert main_pot["label"] == "Main Pot"
    assert main_pot["type"] == "main"
    assert main_pot["amount"] == 120
    assert main_pot["pot"] == 120
    assert main_pot["eligible_player_ids"] == [winner.player_id, loser.player_id]
    assert main_pot["eligible"] == [winner.player_id, loser.player_id]
    assert main_pot["winners"][0]["player_id"] == winner.player_id
    assert main_pot["winners"][0]["name"] == winner.name
    assert main_pot["winners"][0]["amount"] == 120
    assert main_pot["winners"][0]["hand_name"] == "One Pair"

    assert snapshot["player_results"]

    assert snapshot["action_log"] == [
        {
            "player": "Winner",
            "action": "check_call",
            "amount": 20,
            "phase": "river",
            "is_all_in": False,
        }
    ]
    assert "private" not in encoded
    assert "debug" not in encoded
    assert "hole_cards" not in encoded
    assert "stack" not in snapshot["action_log"][0]
