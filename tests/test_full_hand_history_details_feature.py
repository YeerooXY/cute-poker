import json

from poker.game import PokerServer
from poker.models import Player, Room


def make_showdown_room() -> tuple[PokerServer, Room, Player, Player]:
    server = PokerServer()
    room = Room(room_id="HISTFULL")

    alice = Player(
        player_id="alice-id",
        token="alice-secret-token",
        name="Alice",
        seat=1,
        cards=["AS", "AH"],
        stack=900,
    )
    bob = Player(
        player_id="bob-id",
        token="bob-secret-token",
        name="Bob",
        seat=2,
        cards=["KS", "KH"],
        stack=900,
    )

    for player in (alice, bob):
        player.hand_start_stack = 1000
        player.total_invested = 100

    room.players = {
        alice.player_id: alice,
        bob.player_id: bob,
    }
    room.phase = "river"
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 200
    room.hands_played = 7

    return server, room, alice, bob


def test_visible_state_exposes_full_safe_hand_history_details():
    server, room, alice, _bob = make_showdown_room()

    server.showdown(room)

    state = server.visible_state(room, alice.token)

    assert len(state["hand_history"]) == 1
    assert len(state["hand_history_details"]) == 1

    detail = state["hand_history_details"][0]
    compact = state["hand_history"][0]

    assert state["latest_hand_result"] == detail
    assert compact["hand_number"] == detail["hand_number"]
    assert compact["pot"] == detail["pot"]

    assert detail["completed"] is True
    assert detail["phase"] == "showdown"
    assert detail["players"]
    assert detail["winners"]
    assert "action_log" in detail
    assert "hand_deltas" in detail

    encoded = json.dumps(detail)
    assert "alice-secret-token" not in encoded
    assert "bob-secret-token" not in encoded


def test_full_history_details_preserve_partial_board_when_hand_ends_by_fold():
    server = PokerServer()
    room = Room(room_id="PARTIALBOARD")

    winner = Player(
        player_id="winner-id",
        token="winner-secret-token",
        name="Winner",
        seat=1,
        cards=["AS", "AH"],
        stack=1015,
    )
    folded = Player(
        player_id="folded-id",
        token="folded-secret-token",
        name="Folded",
        seat=2,
        cards=["KS", "KH"],
        stack=985,
    )
    folded.folded = True

    for player in (winner, folded):
        player.hand_start_stack = 1000
        player.total_invested = 15

    room.players = {
        winner.player_id: winner,
        folded.player_id: folded,
    }
    room.phase = "showdown"
    room.community = ["TH", "4H", "JS"]
    room.pot = 30
    room.hands_played = 12
    from poker.models import Winner
    room.winners = [Winner(winner.player_id, winner.name, 30, "Everyone else folded")]
    room.hand_deltas = {winner.player_id: 15, folded.player_id: -15}

    server.record_completed_hand(room)
    state = server.visible_state(room, winner.token)

    assert state["hand_history_details"][0]["community"] == ["10\u2665", "4\u2665", "J\u2660"]
    assert state["latest_hand_result"]["community"] == ["10\u2665", "4\u2665", "J\u2660"]
