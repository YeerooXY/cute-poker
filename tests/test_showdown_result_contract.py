
from __future__ import annotations

from poker.game import PokerServer
from poker.models import Player, Room, Winner


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = 1000,
    cards: list[str] | None = None,
    folded: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        cards=cards or ["AS", "AH"],
        folded=folded,
    )
    player.hand_start_stack = 1000
    player.last_hand_name = "Pair"
    player.last_hand_detail = "Pair of Aces"
    player.last_best_cards = ["AS", "AH", "KC", "QD", "2S"]
    return player


def make_completed_room() -> Room:
    winner = make_player("p1", "Bot", seat=1, stack=1050)
    loser = make_player("p2", "Bot", seat=2, stack=850)
    folder = make_player("p3", "Folded", seat=3, stack=900, folded=True)

    room = Room(room_id="RESULT_TEST")
    room.phase = "showdown"
    room.players = {p.player_id: p for p in [winner, loser, folder]}
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 300
    room.winners = [
        Winner(
            player_id="p1",
            name="Bot",
            amount=150,
            reason="Best hand at showdown",
            hand_name="Pair",
            best_cards=["AS", "AH", "KC", "QD", "2S"],
            hand_detail="Pair of Aces",
        )
    ]
    room.hand_deltas = {
        "p1": 50,
        "p2": -100,
        "p3": -50,
    }
    room.pot_breakdown = [
        {
            "type": "main",
            "pot": 200,
            "eligible": ["p1", "p2", "p3"],
            "winners": [
                {
                    "player_id": "p1",
                    "name": "Bot",
                    "amount": 100,
                    "hand_name": "Pair",
                }
            ],
        },
        {
            "type": "side",
            "pot": 100,
            "eligible": ["p1", "p2"],
            "winners": [
                {
                    "player_id": "p1",
                    "name": "Bot",
                    "amount": 50,
                    "hand_name": "Pair",
                }
            ],
        },
    ]
    return room


def result_by_player_id(results: list[dict], player_id: str) -> dict:
    return next(result for result in results if result["player_id"] == player_id)


def test_showdown_pot_breakdown_includes_main_and_side_pots() -> None:
    server = PokerServer()
    room = make_completed_room()

    result = server.public_hand_result(room)
    pots = result["pot_breakdown"]

    assert pots[0]["pot_id"] == 0
    assert pots[0]["label"] == "Main Pot"
    assert pots[0]["amount"] == 200
    assert pots[0]["eligible_player_ids"] == ["p1", "p2", "p3"]
    assert pots[0]["winners"][0]["player_id"] == "p1"
    assert pots[0]["winners"][0]["best_cards"]

    assert pots[1]["pot_id"] == 1
    assert pots[1]["label"] == "Side Pot 1"
    assert pots[1]["amount"] == 100
    assert pots[1]["eligible_player_ids"] == ["p1", "p2"]


def test_visible_state_serializes_hand_deltas_by_player_id() -> None:
    server = PokerServer()
    room = make_completed_room()

    state = server.visible_state(room, "token_p1")

    assert state["hand_deltas_by_player_id"] == {
        "p1": 50,
        "p2": -100,
        "p3": -50,
    }


def test_public_hand_result_includes_player_results() -> None:
    server = PokerServer()
    room = make_completed_room()

    result = server.public_hand_result(room)

    assert "player_results" in result
    assert {entry["player_id"] for entry in result["player_results"]} == {"p1", "p2", "p3"}


def test_player_results_separate_won_amount_from_net_delta() -> None:
    server = PokerServer()
    room = make_completed_room()

    result = server.public_hand_result(room)
    winner = result_by_player_id(result["player_results"], "p1")

    assert winner["won_amount"] == 150
    assert winner["net_delta"] == 50
    assert winner["is_winner"] is True
    assert winner["pot_ids_won"] == [0, 1]


def test_duplicate_named_players_have_distinct_results() -> None:
    server = PokerServer()
    room = make_completed_room()

    result = server.public_hand_result(room)
    first_bot = result_by_player_id(result["player_results"], "p1")
    second_bot = result_by_player_id(result["player_results"], "p2")

    assert first_bot["name"] == "Bot"
    assert second_bot["name"] == "Bot"
    assert first_bot["player_id"] != second_bot["player_id"]
    assert first_bot["won_amount"] == 150
    assert second_bot["won_amount"] == 0
    assert first_bot["net_delta"] == 50
    assert second_bot["net_delta"] == -100
