from poker.game import PokerServer
from poker.models import Player, Room, Winner


def player_state(state, name):
    return next(p for p in state["players"] if p["name"] == name)


def make_two_player_room():
    server = PokerServer()
    room = Room(room_id="LOCKED")
    room.community = ["2C", "7D", "9H"]

    hero = Player(
        player_id="hero",
        token="hero-token",
        name="Hero",
        seat=1,
        cards=["AS", "AH"],
        folded=False,
        all_in=True,
        stack=0,
        total_invested=1000,
    )
    caller = Player(
        player_id="caller",
        token="caller-token",
        name="Caller",
        seat=2,
        cards=["KS", "KH"],
        folded=False,
        all_in=True,
        stack=0,
        total_invested=1000,
    )

    room.players = {
        hero.player_id: hero,
        caller.player_id: caller,
    }
    return server, room, hero, caller


def test_locked_runout_enters_showdown_mode_and_reveals_live_hands():
    server, room, hero, caller = make_two_player_room()

    # Backend is still on a street, but betting is locked: no one can act.
    room.phase = "flop"
    room.action_seat = None

    state = server.visible_state(room, hero.token)

    assert state["phase"] == "flop"
    assert state["showdown_mode"] is True
    assert player_state(state, "Caller")["cards"] == ["K♠", "K♥"]


def test_pending_action_does_not_enter_showdown_mode_or_reveal_other_hands():
    server, room, hero, caller = make_two_player_room()

    # Someone can still act, so this is not showdown display mode.
    room.phase = "flop"
    room.action_seat = hero.seat
    hero.all_in = False
    hero.stack = 500

    state = server.visible_state(room, hero.token)

    assert state.get("showdown_mode") is False
    assert player_state(state, "Caller")["cards"] == ["🂠", "🂠"]


def test_uncontested_win_still_hides_winner_until_winner_reveals():
    server, room, winner, folder = make_two_player_room()

    room.phase = "showdown"
    room.action_seat = None
    room.winners = [
        Winner(
            player_id=winner.player_id,
            name=winner.name,
            amount=15,
            reason="Everyone else folded",
        )
    ]

    folder.folded = True
    folder.all_in = False
    folder.stack = 995
    winner.stack = 1015
    winner.uncontested_reveal_mode = "hidden"

    hidden_state = server.visible_state(room, folder.token)

    assert hidden_state["showdown_mode"] is True
    assert player_state(hidden_state, "Hero")["cards"] == ["🂠", "🂠"]

    winner.uncontested_reveal_mode = "both"
    revealed_state = server.visible_state(room, folder.token)

    assert player_state(revealed_state, "Hero")["cards"] == ["A♠", "A♥"]
