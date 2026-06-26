import asyncio

from poker.game import PokerServer
from poker.models import Player, Room


def make_room():
    server = PokerServer()
    room = Room(room_id="TEST")
    room.phase = "showdown"
    room.community = ["KS", "JS", "TS", "9D", "2C"]
    room.allow_folded_reveals = True

    folder = Player(
        player_id="folder",
        token="folder-token",
        name="Folder",
        seat=1,
        cards=["AS", "QS"],
        folded=True,
        stack=990,
        total_invested=10,
    )
    other = Player(
        player_id="other",
        token="other-token",
        name="Other",
        seat=2,
        cards=["AH", "AD"],
        folded=False,
        stack=1010,
        total_invested=10,
    )
    spectator = Player(
        player_id="spectator",
        token="spectator-token",
        name="Spectator",
        seat=3,
        cards=[],
        is_spectator=True,
        stack=0,
    )

    room.players = {
        folder.player_id: folder,
        other.player_id: other,
        spectator.player_id: spectator,
    }
    room.hand_deltas = {
        folder.player_id: -10,
        other.player_id: 10,
    }
    return server, room, folder, other, spectator


def player_state(state, name):
    return next(p for p in state["players"] if p["name"] == name)


def test_folded_cards_hidden_from_other_players_and_spectators():
    server, room, folder, other, spectator = make_room()

    other_view = server.visible_state(room, other.token)
    assert player_state(other_view, "Folder")["cards"] == ["🂠", "🂠"]

    spectator_view = server.visible_state(room, spectator.token)
    assert player_state(spectator_view, "Folder")["cards"] == ["🂠", "🂠"]


def test_left_and_right_reveal_are_partial_for_other_players():
    server, room, folder, other, _spectator = make_room()

    folder.folded_reveal_mode = "left"
    left_view = server.visible_state(room, other.token)
    assert player_state(left_view, "Folder")["cards"] == ["A♠", "🂠"]

    folder.folded_reveal_mode = "right"
    right_view = server.visible_state(room, other.token)
    assert player_state(right_view, "Folder")["cards"] == ["🂠", "Q♠"]


def test_both_reveal_exposes_cards_and_would_have_hand():
    server, room, folder, other, _spectator = make_room()
    folder.folded_reveal_mode = "both"

    state = server.visible_state(room, other.token)
    folder_state = player_state(state, "Folder")

    assert folder_state["cards"] == ["A♠", "Q♠"]
    assert folder_state["would_have_hand_name"]
    assert folder_state["would_have_hand_detail"]
    assert len(folder_state["would_have_best_cards"]) == 5


def test_owner_can_reveal_then_public_state_updates():
    server, room, folder, other, _spectator = make_room()

    asyncio.run(server.reveal_folded_hand(room, folder, {"mode": "left"}))
    assert folder.folded_reveal_mode == "left"

    public_state = server.visible_state(room, other.token)
    assert player_state(public_state, "Folder")["cards"] == ["A♠", "🂠"]

    asyncio.run(server.reveal_folded_hand(room, folder, {"mode": "right"}))
    assert folder.folded_reveal_mode == "both"


def test_muck_is_final_and_room_setting_can_disable_reveals():
    server, room, folder, _other, _spectator = make_room()

    asyncio.run(server.reveal_folded_hand(room, folder, {"mode": "muck"}))
    assert folder.folded_reveal_mode == "muck"

    asyncio.run(server.reveal_folded_hand(room, folder, {"mode": "left"}))
    assert folder.folded_reveal_mode == "muck"

    server, room, folder, _other, _spectator = make_room()
    room.allow_folded_reveals = False

    asyncio.run(server.reveal_folded_hand(room, folder, {"mode": "left"}))
    assert folder.folded_reveal_mode == "hidden"
