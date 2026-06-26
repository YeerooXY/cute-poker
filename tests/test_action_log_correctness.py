from __future__ import annotations

import json

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


ALLOWED_PUBLIC_ACTION_LOG_KEYS = {
    "player",
    "action",
    "amount",
    "phase",
    "is_all_in",
}


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = 1000,
    committed: int = 0,
    cards: list[str] | None = None,
    folded: bool = False,
    all_in: bool = False,
    acted: bool = False,
) -> Player:
    ws = DummyWs()
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        committed=committed,
        cards=cards or ["AS", "AH"],
        folded=folded,
        all_in=all_in,
        acted=acted,
        connected=True,
        ws=ws,
    )
    player.total_invested = committed
    player.hand_start_stack = stack + committed
    return player


def make_room(
    *players: Player,
    phase: str = "preflop",
    action_seat: int | None = 1,
    current_bet: int = 0,
    pot: int = 0,
) -> Room:
    room = Room(room_id="ACTION_LOG_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    room.action_seat = action_seat
    room.current_bet = current_bet
    room.min_raise = room.big_blind
    room.pot = pot
    return room


def public_action_log(room: Room, viewer: Player) -> list[dict]:
    server = PokerServer()
    return server.visible_state(room, viewer.token)["action_log"]


@pytest.mark.asyncio
async def test_blinds_are_logged_as_small_and_big_blind() -> None:
    server = PokerServer()

    p1 = make_player("p1", "PlayerOne", seat=1, cards=[])
    p2 = make_player("p2", "PlayerTwo", seat=2, cards=[])
    room = make_room(p1, p2, phase="lobby", action_seat=None)

    await server.start_hand(room)

    actions = [(entry["player"], entry["action"], entry["amount"]) for entry in room.action_log]

    assert actions[:2] == [
        ("PlayerOne", "small_blind", room.small_blind),
        ("PlayerTwo", "big_blind", room.big_blind),
    ]

    assert room.action_log[0]["phase"] == "preflop"
    assert room.action_log[1]["phase"] == "preflop"
    assert room.action_log[0]["is_all_in"] is False
    assert room.action_log[1]["is_all_in"] is False


def test_visible_state_sanitizes_action_log_internal_fields() -> None:
    server = PokerServer()

    viewer = make_player("p1", "Viewer", seat=1)
    other = make_player("p2", "Other", seat=2)
    room = make_room(viewer, other)

    room.action_log = [
        {
            "player": "Viewer",
            "action": "bet_raise",
            "amount": 120,
            "phase": "preflop",
            "is_all_in": False,
            # Internal/debug/accounting fields must not leak to clients.
            "is_bot": False,
            "pot": 170,
            "current_bet": 120,
            "committed": 120,
            "committed_before": 20,
            "stack": 880,
            "note": "internal only",
        }
    ]

    state = server.visible_state(room, viewer.token)
    public_entry = state["action_log"][0]

    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry == {
        "player": "Viewer",
        "action": "bet_raise",
        "amount": 120,
        "phase": "preflop",
        "is_all_in": False,
    }


def test_visible_state_adds_safe_defaults_for_missing_action_log_fields() -> None:
    server = PokerServer()

    viewer = make_player("p1", "Viewer", seat=1)
    other = make_player("p2", "Other", seat=2)
    room = make_room(viewer, other)

    room.action_log = [
        {
            "player": "Other",
            "action": "fold",
        }
    ]

    state = server.visible_state(room, viewer.token)
    public_entry = state["action_log"][0]

    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry["player"] == "Other"
    assert public_entry["action"] == "fold"
    assert public_entry["amount"] == 0
    assert public_entry["phase"] == "preflop"
    assert public_entry["is_all_in"] is False


@pytest.mark.asyncio
async def test_check_call_log_amount_is_only_the_added_call_amount() -> None:
    server = PokerServer()

    caller = make_player("p1", "Caller", seat=1, stack=1000, committed=10)
    bettor = make_player("p2", "Bettor", seat=2, stack=980, committed=20, acted=False)
    pending = make_player("p3", "Pending", seat=3, stack=980, committed=20, acted=False)

    room = make_room(caller, bettor, pending, action_seat=1, current_bet=20, pot=50)

    await server.player_action(room, caller, "check_call", {})

    raw_entry = room.action_log[-1]

    assert raw_entry["player"] == "Caller"
    assert raw_entry["action"] == "check_call"
    assert raw_entry["amount"] == 10
    assert raw_entry["committed_before"] == 10
    assert raw_entry["committed"] == 20
    assert raw_entry["stack"] == 990
    assert raw_entry["phase"] == "preflop"
    assert raw_entry["is_all_in"] is False

    public_entry = public_action_log(room, caller)[-1]
    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry["amount"] == 10


@pytest.mark.asyncio
async def test_bet_raise_log_uses_raise_to_amount_and_public_log_is_sanitized() -> None:
    server = PokerServer()

    raiser = make_player("p1", "Raiser", seat=1, stack=1000, committed=20)
    caller = make_player("p2", "Caller", seat=2, stack=980, committed=20, acted=False)
    pending = make_player("p3", "Pending", seat=3, stack=980, committed=20, acted=False)

    room = make_room(raiser, caller, pending, action_seat=1, current_bet=20, pot=60)
    room.min_raise = 20

    await server.player_action(room, raiser, "bet_raise", {"amount": 60})

    raw_entry = room.action_log[-1]

    assert raw_entry["player"] == "Raiser"
    assert raw_entry["action"] == "bet_raise"
    assert raw_entry["amount"] == 60
    assert raw_entry["committed_before"] == 20
    assert raw_entry["committed"] == 60
    assert raw_entry["stack"] == 960
    assert raw_entry["current_bet"] == 60
    assert raw_entry["phase"] == "preflop"
    assert raw_entry["is_all_in"] is False

    public_entry = public_action_log(room, raiser)[-1]
    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry == {
        "player": "Raiser",
        "action": "bet_raise",
        "amount": 60,
        "phase": "preflop",
        "is_all_in": False,
    }


@pytest.mark.asyncio
async def test_fold_log_has_zero_amount_and_no_chip_side_effects() -> None:
    server = PokerServer()

    folder = make_player("p1", "Folder", seat=1, stack=1000, committed=0)
    live_one = make_player("p2", "LiveOne", seat=2, stack=1000, committed=0, acted=False)
    live_two = make_player("p3", "LiveTwo", seat=3, stack=1000, committed=0, acted=False)

    room = make_room(folder, live_one, live_two, action_seat=1, current_bet=0, pot=0)

    await server.player_action(room, folder, "fold", {})

    raw_entry = room.action_log[-1]

    assert folder.folded is True
    assert folder.stack == 1000
    assert folder.committed == 0

    assert raw_entry["player"] == "Folder"
    assert raw_entry["action"] == "fold"
    assert raw_entry["amount"] == 0
    assert raw_entry["phase"] == "preflop"
    assert raw_entry["is_all_in"] is False

    public_entry = public_action_log(room, live_one)[-1]
    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry["action"] == "fold"
    assert public_entry["amount"] == 0


def test_return_uncalled_excess_rewrites_unmatched_shove_to_effective_call() -> None:
    server = PokerServer()

    short = make_player(
        "p1",
        "Short",
        seat=1,
        stack=0,
        committed=50,
        cards=["AS", "AH"],
        all_in=True,
    )
    middle = make_player(
        "p2",
        "Middle",
        seat=2,
        stack=0,
        committed=100,
        cards=["KS", "KH"],
        all_in=True,
    )
    big = make_player(
        "p3",
        "Big",
        seat=3,
        stack=0,
        committed=200,
        cards=["QS", "QH"],
        all_in=True,
    )

    room = make_room(short, middle, big, phase="river", action_seat=None, current_bet=200, pot=350)

    room.action_log = [
        {
            "player": "Big",
            "action": "bet_raise",
            "amount": 200,
            "phase": "river",
            "is_all_in": True,
            "committed_before": 0,
            "committed": 200,
            "stack": 0,
            "pot": 350,
            "current_bet": 200,
        }
    ]

    server.return_uncalled_excess(room)

    assert big.stack == 100
    assert big.committed == 100
    assert big.total_invested == 100
    assert big.all_in is False
    assert room.pot == 250
    assert room.current_bet == 100

    raw_entry = room.action_log[-1]

    assert raw_entry["player"] == "Big"
    assert raw_entry["action"] == "check_call"
    assert raw_entry["amount"] == 100
    assert raw_entry["committed"] == 100
    assert raw_entry["stack"] == 100
    assert raw_entry["is_all_in"] is False
    assert raw_entry["note"] == "uncalled excess returned"

    public_entry = public_action_log(room, big)[-1]
    assert set(public_entry) == ALLOWED_PUBLIC_ACTION_LOG_KEYS
    assert public_entry == {
        "player": "Big",
        "action": "check_call",
        "amount": 100,
        "phase": "river",
        "is_all_in": False,
    }
