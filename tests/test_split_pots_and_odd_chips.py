from __future__ import annotations

import pytest

from poker.game import PokerServer
from poker.models import Player, Room


BOARD_STRAIGHT = ["2C", "3D", "4S", "5H", "6C"]
BOARD_PAIR = ["2C", "5D", "9S", "JH", "3C"]


@pytest.fixture(autouse=True)
def no_hand_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poker.game.save_hand_log", lambda _room: None)


def make_player(
    player_id: str,
    name: str,
    seat: int,
    invested: int,
    cards: list[str],
    stack: int = 0,
    folded: bool = False,
) -> Player:
    player = Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        committed=0,
        cards=cards,
        folded=folded,
        all_in=stack == 0 and not folded,
        acted=True,
        connected=True,
    )
    player.total_invested = invested
    player.hand_start_stack = stack + invested
    return player


def make_showdown_room(*players: Player, board: list[str], pot: int) -> Room:
    room = Room(room_id="SPLIT_POT_TEST")
    room.phase = "river"
    room.players = {p.player_id: p for p in players}
    room.community = board[:]
    room.pot = pot
    room.current_bet = 0
    room.action_seat = None
    return room


def winner_amounts(room: Room) -> dict[str, int]:
    return {winner.player_id: winner.amount for winner in room.winners}


def assert_awarded_exact_pot(room: Room, expected_pot: int) -> None:
    assert room.pot == expected_pot
    assert sum(winner.amount for winner in room.winners) == expected_pot
    assert sum(
        winner["amount"]
        for tier in room.pot_breakdown
        for winner in tier["winners"]
    ) == expected_pot


def test_heads_up_exact_split_pot_awards_half_to_each_player() -> None:
    server = PokerServer()

    p1 = make_player("p1", "TieOne", seat=1, invested=100, cards=["AS", "KD"])
    p2 = make_player("p2", "TieTwo", seat=2, invested=100, cards=["AH", "QD"])

    room = make_showdown_room(p1, p2, board=BOARD_STRAIGHT, pot=200)

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 200)
    assert amounts == {
        "p1": 100,
        "p2": 100,
    }

    assert p1.stack == 100
    assert p2.stack == 100
    assert room.pot_breakdown[0]["pot"] == 200
    assert [winner["amount"] for winner in room.pot_breakdown[0]["winners"]] == [100, 100]


def test_heads_up_odd_chip_goes_to_first_tier_winner() -> None:
    server = PokerServer()

    p1 = make_player("p1", "TieOne", seat=1, invested=101, cards=["AS", "KD"])
    p2 = make_player("p2", "TieTwo", seat=2, invested=100, cards=["AH", "QD"])

    # Valid odd-chip synthetic showdown state: one extra chip exists in pot,
    # but both players tie for the single tier they can contest.
    room = make_showdown_room(p1, p2, board=BOARD_STRAIGHT, pot=201)

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 201)
    assert amounts == {
        "p1": 101,
        "p2": 100,
    }

    assert p1.stack == 101
    assert p2.stack == 100
    assert room.pot_breakdown[0]["pot"] == 200
    assert room.pot_breakdown[0]["winners"][0]["amount"] == 100
    assert room.pot_breakdown[0]["winners"][1]["amount"] == 100

    # The remaining odd chip is awarded through the remaining-pot tier.
    assert room.pot_breakdown[1]["pot"] == 1
    assert room.pot_breakdown[1]["winners"][0]["amount"] == 1


def test_three_way_exact_split_main_pot() -> None:
    server = PokerServer()

    p1 = make_player("p1", "TieOne", seat=1, invested=100, cards=["AS", "KD"])
    p2 = make_player("p2", "TieTwo", seat=2, invested=100, cards=["AH", "QD"])
    p3 = make_player("p3", "TieThree", seat=3, invested=100, cards=["AC", "JD"])

    room = make_showdown_room(p1, p2, p3, board=BOARD_STRAIGHT, pot=300)

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 300)
    assert amounts == {
        "p1": 100,
        "p2": 100,
        "p3": 100,
    }

    assert [winner["amount"] for winner in room.pot_breakdown[0]["winners"]] == [100, 100, 100]


def test_three_way_odd_chips_are_distributed_to_first_winners_in_order() -> None:
    server = PokerServer()

    p1 = make_player("p1", "TieOne", seat=1, invested=101, cards=["AS", "KD"])
    p2 = make_player("p2", "TieTwo", seat=2, invested=101, cards=["AH", "QD"])
    p3 = make_player("p3", "TieThree", seat=3, invested=100, cards=["AC", "JD"])

    room = make_showdown_room(p1, p2, p3, board=BOARD_STRAIGHT, pot=302)

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 302)

    # Main tier: 300 split three ways.
    assert room.pot_breakdown[0]["pot"] == 300
    assert [winner["amount"] for winner in room.pot_breakdown[0]["winners"]] == [100, 100, 100]

    # Remaining tier: 2 chips split between the two players invested above 100.
    assert room.pot_breakdown[1]["pot"] == 2
    assert [winner["amount"] for winner in room.pot_breakdown[1]["winners"]] == [1, 1]

    assert amounts == {
        "p1": 101,
        "p2": 101,
        "p3": 100,
    }


def test_side_pot_can_split_between_eligible_players_only() -> None:
    server = PokerServer()

    short_best_main_only = make_player(
        "p1",
        "ShortBestMainOnly",
        seat=1,
        invested=50,
        cards=["AS", "AH"],
    )
    middle_ties_side = make_player(
        "p2",
        "MiddleTieSide",
        seat=2,
        invested=100,
        cards=["KS", "QD"],
    )
    big_ties_side = make_player(
        "p3",
        "BigTieSide",
        seat=3,
        invested=100,
        cards=["KH", "QC"],
    )

    # Aces beat both high-card hands for the 150 main pot.
    # P2/P3 then tie each other for the 100 side pot.
    room = make_showdown_room(
        short_best_main_only,
        middle_ties_side,
        big_ties_side,
        board=BOARD_PAIR,
        pot=250,
    )

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 250)
    assert amounts == {
        "p1": 150,
        "p2": 50,
        "p3": 50,
    }

    assert room.pot_breakdown[0]["type"] == "main"
    assert room.pot_breakdown[0]["pot"] == 150
    assert room.pot_breakdown[0]["eligible"] == ["p1", "p2", "p3"]
    assert room.pot_breakdown[0]["winners"][0]["player_id"] == "p1"
    assert room.pot_breakdown[0]["winners"][0]["amount"] == 150

    assert room.pot_breakdown[1]["type"] == "side"
    assert room.pot_breakdown[1]["pot"] == 100
    assert room.pot_breakdown[1]["eligible"] == ["p2", "p3"]
    assert [winner["player_id"] for winner in room.pot_breakdown[1]["winners"]] == ["p2", "p3"]
    assert [winner["amount"] for winner in room.pot_breakdown[1]["winners"]] == [50, 50]


def test_folded_investor_adds_dead_money_but_never_wins_split_pot() -> None:
    server = PokerServer()

    tie_one = make_player("p1", "TieOne", seat=1, invested=100, cards=["AS", "KD"])
    tie_two = make_player("p2", "TieTwo", seat=2, invested=100, cards=["AH", "QD"])
    folded_dead_money = make_player(
        "p3",
        "FoldedDeadMoney",
        seat=3,
        invested=100,
        cards=["2H", "2D"],
        folded=True,
    )

    room = make_showdown_room(tie_one, tie_two, folded_dead_money, board=BOARD_STRAIGHT, pot=300)

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 300)
    assert amounts == {
        "p1": 150,
        "p2": 150,
    }

    assert "p3" not in amounts
    assert folded_dead_money.stack == 0

    assert room.pot_breakdown[0]["eligible"] == ["p1", "p2"]
    assert [winner["amount"] for winner in room.pot_breakdown[0]["winners"]] == [150, 150]


def test_split_pot_hand_deltas_match_final_stacks() -> None:
    server = PokerServer()

    p1 = make_player("p1", "TieOne", seat=1, invested=100, cards=["AS", "KD"])
    p2 = make_player("p2", "TieTwo", seat=2, invested=100, cards=["AH", "QD"])
    p3 = make_player("p3", "FoldedDeadMoney", seat=3, invested=100, cards=["2H", "2D"], folded=True)

    room = make_showdown_room(p1, p2, p3, board=BOARD_STRAIGHT, pot=300)

    server.showdown(room)

    assert room.hand_deltas == {
        "p1": 50,
        "p2": 50,
        "p3": -100,
    }
