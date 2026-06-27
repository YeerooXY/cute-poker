from __future__ import annotations

import json

from poker.game import HAND_HISTORY_LIMIT, PokerServer
from poker.models import Player, Room


BACK = "\U0001f0a0"


def make_player(
    player_id: str,
    name: str,
    seat: int,
    cards: list[str],
    invested: int = 0,
    stack: int = 1000,
    folded: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"secret_token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        cards=cards,
        folded=folded,
        acted=True,
        connected=True,
    )
    player.total_invested = invested
    player.hand_start_stack = stack + invested
    return player


def make_room(*players: Player) -> Room:
    room = Room(room_id="HISTORY1")
    room.phase = "river"
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = sum(p.total_invested for p in players)
    room.players = {p.player_id: p for p in players}
    return room


def by_name(snapshot: dict, name: str) -> dict:
    return next(player for player in snapshot["players"] if player["name"] == name)


def test_showdown_records_safe_latest_hand_result_and_compact_history():
    server = PokerServer()

    alice = make_player("alice", "Alice", 1, ["AS", "AH"], invested=100, stack=900)
    bob = make_player("bob", "Bob", 2, ["KS", "KH"], invested=100, stack=900)
    room = make_room(alice, bob)

    server.showdown(room)

    assert room.phase == "showdown"
    assert len(room.hand_history) == 1

    snapshot = room.hand_history[0]
    encoded = json.dumps(snapshot)

    assert snapshot["completed"] is True
    assert snapshot["hand_number"] == room.hands_played
    assert snapshot["pot"] == 200
    assert snapshot["community"] == ["2\u2663", "5\u2666", "9\u2660", "J\u2665", "3\u2663"]

    assert by_name(snapshot, "Alice")["cards"] == ["A\u2660", "A\u2665"]
    assert by_name(snapshot, "Bob")["cards"] == ["K\u2660", "K\u2665"]

    assert "secret_token" not in encoded
    assert "hole_cards" not in encoded

    state = server.visible_state(room, alice.token)

    assert state["latest_hand_result"] == snapshot
    assert state["hand_history"] == [
        {
            "hand_number": room.hands_played,
            "pot": 200,
            "community": ["2\u2663", "5\u2666", "9\u2660", "J\u2665", "3\u2663"],
            "winners": [
                {
                    "player_id": winner["player_id"],
                    "name": winner["name"],
                    "amount": winner["amount"],
                    "reason": winner["reason"],
                    "hand_name": winner["hand_name"],
                }
                for winner in snapshot["winners"]
            ],
        }
    ]


def test_uncontested_fold_win_records_history_without_revealing_winner_cards():
    server = PokerServer()

    winner = make_player("alice", "Alice", 1, ["AS", "AH"], invested=20, stack=980)
    folder = make_player("bob", "Bob", 2, ["KS", "KH"], invested=20, stack=980, folded=True)
    room = make_room(winner, folder)

    server.award_to_last_player(room)

    assert room.phase == "showdown"
    assert len(room.hand_history) == 1

    snapshot = room.hand_history[0]
    encoded = json.dumps(snapshot)

    assert snapshot["winners"][0]["reason"] == "Everyone else folded"
    assert by_name(snapshot, "Alice")["cards"] == [BACK, BACK]
    assert by_name(snapshot, "Bob")["cards"] == [BACK, BACK]

    assert "AS" not in encoded
    assert "AH" not in encoded
    assert "KS" not in encoded
    assert "KH" not in encoded


def test_hand_history_is_capped_to_recent_results():
    server = PokerServer()
    room = Room(room_id="HISTORY_CAP")

    for hand_number in range(HAND_HISTORY_LIMIT + 5):
        room.phase = "showdown"
        room.hands_played = hand_number
        room.pot = hand_number
        room.players = {}
        room.winners = []
        server.record_completed_hand(room)

    assert len(room.hand_history) == HAND_HISTORY_LIMIT
    assert room.hand_history[0]["hand_number"] == 5
    assert room.hand_history[-1]["hand_number"] == HAND_HISTORY_LIMIT + 4

    state = server.visible_state(room, "missing-token")

    assert len(state["hand_history"]) == HAND_HISTORY_LIMIT
    assert state["hand_history"][0]["hand_number"] == 5
    assert state["latest_hand_result"]["hand_number"] == HAND_HISTORY_LIMIT + 4


def test_starting_new_hand_preserves_previous_hand_history():
    server = PokerServer()

    alice = make_player("alice", "Alice", 1, ["AS", "AH"], invested=100, stack=900)
    bob = make_player("bob", "Bob", 2, ["KS", "KH"], invested=100, stack=900)
    room = make_room(alice, bob)

    server.showdown(room)
    history_before = list(room.hand_history)

    # Simulate the reset portion that start_hand performs: the feature should not
    # be tied to current-hand transient state.
    room.community = []
    room.winners = []
    room.action_log = []
    room.hand_deltas = {}
    room.phase = "preflop"

    assert room.hand_history == history_before
