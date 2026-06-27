from poker.game import PokerServer
import json

from poker.models import Player, Room, Winner


BACK = chr(0x1F0A0)


def test_latest_history_snapshot_refreshes_after_folded_card_reveal():
    server = PokerServer()
    room = Room(room_id="REFRESH")

    winner = Player(player_id="winner-id", token="winner-token", name="Winner", seat=1, cards=["AS", "AH"], stack=1010)
    folded = Player(player_id="folded-id", token="folded-token", name="Folded", seat=2, cards=["KS", "KH"], stack=990)
    folded.folded = True

    for p in (winner, folded):
        p.hand_start_stack = 1000

    room.players = {winner.player_id: winner, folded.player_id: folded}
    room.phase = "showdown"
    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 20
    room.winners = []
    room.hand_deltas = {winner.player_id: 10, folded.player_id: -10}

    server.record_completed_hand(room)
    before = room.hand_history[-1]
    folded_before = next(p for p in before["players"] if p["name"] == "Folded")
    assert folded_before["cards"] == [BACK, BACK]

    expected_by_mode = {
        "left": ["K\u2660", BACK],
        "right": [BACK, "K\u2665"],
        "both": ["K\u2660", "K\u2665"],
    }
    for mode, expected_cards in expected_by_mode.items():
        folded.folded_reveal_mode = mode
        server.refresh_latest_completed_hand(room)

        after = room.hand_history[-1]
        folded_after = next(p for p in after["players"] if p["name"] == "Folded")
        latest_folded = next(p for p in server.visible_state(room, winner.token)["latest_hand_result"]["players"] if p["name"] == "Folded")
        detail_folded = next(p for p in server.visible_state(room, winner.token)["hand_history_details"][-1]["players"] if p["name"] == "Folded")

        assert folded_after["cards"] == expected_cards
        assert latest_folded["cards"] == expected_cards
        assert detail_folded["cards"] == expected_cards
        assert folded_after["folded_reveal_mode"] == mode
        assert folded_after["uncontested_reveal_mode"] == "hidden"

    encoded = json.dumps(room.hand_history[-1])
    assert "winner-token" not in encoded
    assert "folded-token" not in encoded


def test_latest_history_snapshot_refreshes_after_uncontested_winner_reveal():
    server = PokerServer()
    room = Room(room_id="REFRESH2")

    winner = Player(player_id="winner-id", token="winner-token", name="Winner", seat=1, cards=["AS", "AH"], stack=1010)
    folded = Player(player_id="folded-id", token="folded-token", name="Folded", seat=2, cards=["KS", "KH"], stack=990)
    folded.folded = True

    for p in (winner, folded):
        p.hand_start_stack = 1000

    room.players = {winner.player_id: winner, folded.player_id: folded}
    room.phase = "showdown"
    room.community = []
    room.pot = 20
    room.winners = []
    room.hand_deltas = {winner.player_id: 10, folded.player_id: -10}

    room.winners = [Winner(winner.player_id, winner.name, 20, "Everyone else folded")]

    server.record_completed_hand(room)
    before = room.hand_history[-1]
    winner_before = next(p for p in before["players"] if p["name"] == "Winner")
    assert winner_before["cards"] == [BACK, BACK]

    expected_by_mode = {
        "left": ["A\u2660", BACK],
        "right": [BACK, "A\u2665"],
        "both": ["A\u2660", "A\u2665"],
    }
    for mode, expected_cards in expected_by_mode.items():
        winner.uncontested_reveal_mode = mode
        server.refresh_latest_completed_hand(room)

        after = room.hand_history[-1]
        winner_after = next(p for p in after["players"] if p["name"] == "Winner")
        latest_winner = next(p for p in server.visible_state(room, folded.token)["latest_hand_result"]["players"] if p["name"] == "Winner")
        detail_winner = next(p for p in server.visible_state(room, folded.token)["hand_history_details"][-1]["players"] if p["name"] == "Winner")
        folded_after = next(p for p in after["players"] if p["name"] == "Folded")

        assert winner_after["cards"] == expected_cards
        assert latest_winner["cards"] == expected_cards
        assert detail_winner["cards"] == expected_cards
        assert folded_after["cards"] == [BACK, BACK]
        assert winner_after["uncontested_reveal_mode"] == mode
        assert winner_after["folded_reveal_mode"] == ""

    encoded = json.dumps(room.hand_history[-1])
    assert "winner-token" not in encoded
    assert "folded-token" not in encoded


def test_history_review_persists_would_have_breakdown_for_fully_revealed_folded_hand():
    from poker.models import Winner

    server = PokerServer()
    room = Room(room_id="WOULDHAVE")

    winner = Player(player_id="winner-id", token="winner-token", name="Winner", seat=1, cards=["AS", "KH"], stack=1030)
    folded = Player(player_id="folded-id", token="folded-token", name="Folded", seat=2, cards=["8H", "9H"], stack=970)
    folded.folded = True

    for p in (winner, folded):
        p.hand_start_stack = 1000
        p.total_invested = 30

    room.players = {winner.player_id: winner, folded.player_id: folded}
    room.phase = "showdown"
    room.community = ["2H", "6H", "TH", "3C", "4D"]
    room.pot = 60
    room.hands_played = 3
    room.winners = [Winner(winner.player_id, winner.name, 60, "Everyone else folded")]
    room.hand_deltas = {winner.player_id: 30, folded.player_id: -30}

    server.record_completed_hand(room)

    folded.folded_reveal_mode = "both"
    server.refresh_latest_completed_hand(room)

    detail = server.visible_state(room, winner.token)["hand_history_details"][-1]
    folded_detail = next(p for p in detail["players"] if p["name"] == "Folded")

    assert folded_detail["cards"] == ["8\u2665", "9\u2665"]
    assert folded_detail["folded_reveal_mode"] == "both"
    assert folded_detail["would_have_hand_name"] == "Flush"
    assert "Flush" in folded_detail["would_have_hand_detail"]
    assert len(folded_detail["would_have_best_cards"]) == 5
    assert "winner-token" not in str(detail)
    assert "folded-token" not in str(detail)


def test_history_review_does_not_calculate_would_have_for_partial_reveal():
    from poker.models import Winner

    server = PokerServer()
    room = Room(room_id="PARTIALNOLEAK")

    winner = Player(player_id="winner-id", token="winner-token", name="Winner", seat=1, cards=["AS", "KH"], stack=1030)
    folded = Player(player_id="folded-id", token="folded-token", name="Folded", seat=2, cards=["8H", "9H"], stack=970)
    folded.folded = True

    for p in (winner, folded):
        p.hand_start_stack = 1000
        p.total_invested = 30

    room.players = {winner.player_id: winner, folded.player_id: folded}
    room.phase = "showdown"
    room.community = ["2H", "6H", "TH", "3C", "4D"]
    room.pot = 60
    room.hands_played = 4
    room.winners = [Winner(winner.player_id, winner.name, 60, "Everyone else folded")]
    room.hand_deltas = {winner.player_id: 30, folded.player_id: -30}

    server.record_completed_hand(room)

    folded.folded_reveal_mode = "left"
    server.refresh_latest_completed_hand(room)

    detail = server.visible_state(room, winner.token)["hand_history_details"][-1]
    folded_detail = next(p for p in detail["players"] if p["name"] == "Folded")

    assert folded_detail["cards"] == ["8\u2665", BACK]
    assert folded_detail["would_have_hand_name"] == ""
    assert folded_detail["would_have_best_cards"] == []


def test_history_review_persists_best_hand_for_fully_revealed_uncontested_winner():
    from poker.models import Winner

    server = PokerServer()
    room = Room(room_id="UNCONTESTEDBEST")

    winner = Player(player_id="winner-id", token="winner-token", name="Winner", seat=1, cards=["QH", "QD"], stack=1030)
    folded = Player(player_id="folded-id", token="folded-token", name="Folded", seat=2, cards=["8H", "9H"], stack=970)
    folded.folded = True

    for p in (winner, folded):
        p.hand_start_stack = 1000
        p.total_invested = 30

    room.players = {winner.player_id: winner, folded.player_id: folded}
    room.phase = "showdown"
    room.community = ["QS", "2C", "5D", "7H", "KC"]
    room.pot = 60
    room.hands_played = 5
    room.winners = [Winner(winner.player_id, winner.name, 60, "Everyone else folded")]
    room.hand_deltas = {winner.player_id: 30, folded.player_id: -30}

    server.record_completed_hand(room)

    winner.uncontested_reveal_mode = "both"
    server.refresh_latest_completed_hand(room)

    detail = server.visible_state(room, winner.token)["hand_history_details"][-1]
    winner_detail = next(p for p in detail["players"] if p["name"] == "Winner")

    assert winner_detail["cards"] == ["Q\u2665", "Q\u2666"]
    assert winner_detail["uncontested_reveal_mode"] == "both"
    assert winner_detail["hand_name"].lower() == "three of a kind"
    assert "Queens" in winner_detail["hand_detail"]
    assert len(winner_detail["best_cards"]) == 5
