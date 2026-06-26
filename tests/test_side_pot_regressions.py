from __future__ import annotations

from poker.game import PokerServer
from poker.models import Player, Room


def make_player(
    player_id: str,
    name: str,
    seat: int,
    invested: int,
    cards: list[str],
    stack: int = 0,
    folded: bool = False,
    all_in: bool = True,
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
        all_in=all_in,
        acted=True,
    )
    player.total_invested = invested
    player.hand_start_stack = stack + invested
    return player


def make_showdown_room(*players: Player, board: list[str], pot: int) -> Room:
    room = Room(room_id="SIDE_POT_TEST")
    room.phase = "river"
    room.community = board
    room.pot = pot
    room.current_bet = 0
    room.players = {p.player_id: p for p in players}
    return room


def winner_amounts(room: Room) -> dict[str, int]:
    return {winner.player_id: winner.amount for winner in room.winners}


def assert_awarded_exact_pot(room: Room, expected_pot: int) -> None:
    assert sum(w.amount for w in room.winners) == expected_pot
    assert sum(tier["pot"] for tier in room.pot_breakdown) == expected_pot


def test_three_way_all_in_short_stack_wins_main_only() -> None:
    server = PokerServer()

    short_stack_best = make_player(
        "p1", "ShortStackBest", seat=1,
        invested=100,
        cards=["AS", "AH"],
    )
    side_pot_winner = make_player(
        "p2", "SidePotWinner", seat=2,
        invested=300,
        cards=["KS", "KH"],
    )
    side_pot_loser = make_player(
        "p3", "SidePotLoser", seat=3,
        invested=300,
        cards=["QS", "QH"],
    )

    room = make_showdown_room(
        short_stack_best,
        side_pot_winner,
        side_pot_loser,
        board=["2C", "5D", "9S", "JH", "3C"],
        pot=700,
    )

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 700)
    assert amounts["p1"] == 300
    assert amounts["p2"] == 400
    assert "p3" not in amounts

    assert [tier["pot"] for tier in room.pot_breakdown] == [300, 400]
    assert [tier["type"] for tier in room.pot_breakdown] == ["main", "side"]

    assert short_stack_best.stack == 300
    assert side_pot_winner.stack == 400
    assert side_pot_loser.stack == 0

    assert room.hand_deltas["p1"] == 200
    assert room.hand_deltas["p2"] == 100
    assert room.hand_deltas["p3"] == -300


def test_four_way_staggered_all_in_creates_multiple_side_pots() -> None:
    server = PokerServer()

    main_pot_winner = make_player(
        "p1", "MainPotWinner", seat=1,
        invested=100,
        cards=["AS", "AH"],
    )
    side_pot_loser_one = make_player(
        "p2", "SidePotLoserOne", seat=2,
        invested=300,
        cards=["QS", "QH"],
    )
    side_pot_winner = make_player(
        "p3", "SidePotWinner", seat=3,
        invested=500,
        cards=["KS", "KH"],
    )
    side_pot_loser_two = make_player(
        "p4", "SidePotLoserTwo", seat=4,
        invested=500,
        cards=["JS", "JH"],
    )

    room = make_showdown_room(
        main_pot_winner,
        side_pot_loser_one,
        side_pot_winner,
        side_pot_loser_two,
        board=["2C", "5D", "9S", "7H", "3C"],
        pot=1400,
    )

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 1400)
    assert amounts["p1"] == 400
    assert amounts["p3"] == 1000
    assert "p2" not in amounts
    assert "p4" not in amounts

    assert [tier["pot"] for tier in room.pot_breakdown] == [400, 600, 400]
    assert [tier["type"] for tier in room.pot_breakdown] == ["main", "side", "side"]

    assert room.pot_breakdown[0]["eligible"] == ["p1", "p2", "p3", "p4"]
    assert room.pot_breakdown[1]["eligible"] == ["p2", "p3", "p4"]
    assert room.pot_breakdown[2]["eligible"] == ["p3", "p4"]

    assert main_pot_winner.stack == 400
    assert side_pot_winner.stack == 1000
    assert side_pot_loser_one.stack == 0
    assert side_pot_loser_two.stack == 0

    assert room.hand_deltas["p1"] == 300
    assert room.hand_deltas["p2"] == -300
    assert room.hand_deltas["p3"] == 500
    assert room.hand_deltas["p4"] == -500


def test_folded_player_dead_money_stays_in_pot_but_cannot_win() -> None:
    server = PokerServer()

    folded_investor = make_player(
        "p1", "FoldedInvestor", seat=1,
        invested=200,
        cards=["AS", "AH"],
        folded=True,
        all_in=False,
    )
    live_winner = make_player(
        "p2", "LiveWinner", seat=2,
        invested=200,
        cards=["KS", "KH"],
    )
    live_loser = make_player(
        "p3", "LiveLoser", seat=3,
        invested=200,
        cards=["QS", "QH"],
    )

    room = make_showdown_room(
        folded_investor,
        live_winner,
        live_loser,
        board=["2C", "5D", "9S", "7H", "3C"],
        pot=600,
    )

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 600)
    assert amounts == {"p2": 600}

    assert len(room.pot_breakdown) == 1
    assert room.pot_breakdown[0]["pot"] == 600
    assert room.pot_breakdown[0]["eligible"] == ["p2", "p3"]

    assert folded_investor.stack == 0
    assert live_winner.stack == 600
    assert live_loser.stack == 0

    assert room.hand_deltas["p1"] == -200
    assert room.hand_deltas["p2"] == 400
    assert room.hand_deltas["p3"] == -200


def test_side_pot_breakdown_winner_amounts_match_winner_list() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1, invested=125, cards=["AS", "AH"])
    p2 = make_player("p2", "P2", seat=2, invested=250, cards=["KS", "KH"])
    p3 = make_player("p3", "P3", seat=3, invested=625, cards=["QS", "QH"])
    p4 = make_player("p4", "P4", seat=4, invested=625, cards=["JS", "JH"])

    room = make_showdown_room(
        p1, p2, p3, p4,
        board=["2C", "5D", "9S", "7H", "3C"],
        pot=1625,
    )

    server.showdown(room)

    from_winners = winner_amounts(room)

    from_breakdown: dict[str, int] = {}
    for tier in room.pot_breakdown:
        for winner in tier["winners"]:
            from_breakdown[winner["player_id"]] = (
                from_breakdown.get(winner["player_id"], 0) + winner["amount"]
            )

    assert_awarded_exact_pot(room, 1625)
    assert from_breakdown == from_winners
    assert [tier["pot"] for tier in room.pot_breakdown] == [500, 375, 750]

def test_textbook_three_way_side_pot_50_100_200_after_uncalled_return() -> None:
    """Three-way all-in side-pot example: stacks 50 / 100 / 200.

    Poker accounting:
    - Player A can contest 50 from each player: main pot = 150.
    - Player B can contest the next 50 from B and C: side pot = 100.
    - Player C's extra 100 is uncalled and should already be returned before
      showdown, so the showdown pot is 250, not 350.

    This locks down the clean textbook case that is easiest to reason about.
    """
    server = PokerServer()

    short_stack_best = make_player(
        "p1", "ShortStackBest", seat=1,
        invested=50,
        cards=["AS", "AH"],
    )
    middle_stack_second_best = make_player(
        "p2", "MiddleStackSecondBest", seat=2,
        invested=100,
        cards=["KS", "KH"],
    )
    big_stack_worst_hand = make_player(
        "p3", "BigStackWorstHand", seat=3,
        invested=100,
        cards=["QS", "QH"],
        stack=100,
        all_in=False,
    )

    room = make_showdown_room(
        short_stack_best,
        middle_stack_second_best,
        big_stack_worst_hand,
        board=["2C", "5D", "9S", "7H", "3C"],
        pot=250,
    )

    server.showdown(room)

    amounts = winner_amounts(room)

    assert_awarded_exact_pot(room, 250)

    # A has the best hand but can only win the 150 main pot.
    assert amounts["p1"] == 150

    # B beats C and wins the 100 side pot.
    assert amounts["p2"] == 100

    # C's unmatched extra 100 was returned before showdown and is not awarded.
    assert "p3" not in amounts
    assert big_stack_worst_hand.stack == 100

    assert [tier["pot"] for tier in room.pot_breakdown] == [150, 100]
    assert [tier["type"] for tier in room.pot_breakdown] == ["main", "side"]
    assert room.pot_breakdown[0]["eligible"] == ["p1", "p2", "p3"]
    assert room.pot_breakdown[1]["eligible"] == ["p2", "p3"]

    assert short_stack_best.stack == 150
    assert middle_stack_second_best.stack == 100

    assert room.hand_deltas["p1"] == 100
    assert room.hand_deltas["p2"] == 0
    assert room.hand_deltas["p3"] == -100

