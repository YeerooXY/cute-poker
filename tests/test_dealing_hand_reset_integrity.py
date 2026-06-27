from __future__ import annotations

import json

import pytest

from poker.game import PokerServer, STARTING_STACK
from poker.models import Player, Room, Winner


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def make_player(
    player_id: str,
    name: str,
    seat: int,
    stack: int = STARTING_STACK,
    sitting_out: bool = False,
    is_spectator: bool = False,
) -> Player:
    return Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=stack,
        sitting_out=sitting_out,
        is_spectator=is_spectator,
        connected=True,
        ws=DummyWs(),
    )


def make_room(*players: Player, phase: str = "lobby") -> Room:
    room = Room(room_id="DEAL_RESET_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    return room


def hole_cards(room: Room) -> list[str]:
    return [
        card
        for player in room.players.values()
        for card in player.cards
    ]


def active_players(room: Room) -> list[Player]:
    return [
        p
        for p in room.seated_players()
        if p.stack > 0 and not p.sitting_out and not p.is_spectator
    ]


@pytest.mark.asyncio
async def test_start_hand_deals_two_unique_hole_cards_to_each_active_player() -> None:
    server = PokerServer()

    players = [
        make_player(f"p{seat}", f"Player{seat}", seat=seat)
        for seat in range(1, 5)
    ]
    room = make_room(*players)

    await server.start_hand(room)

    assert room.phase == "preflop"
    assert room.community == []

    for player in players:
        assert len(player.cards) == 2

    dealt = hole_cards(room)
    assert len(dealt) == 8
    assert len(set(dealt)) == 8

    assert len(room.deck) == 52 - 8
    assert set(dealt).isdisjoint(set(room.deck))

    assert [entry["action"] for entry in room.action_log] == [
        "small_blind",
        "big_blind",
    ]


@pytest.mark.asyncio
async def test_start_hand_deck_plus_hole_cards_still_forms_unique_52_card_set() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)

    await server.start_hand(room)

    all_known_cards = room.deck + hole_cards(room) + room.community

    assert len(all_known_cards) == 52
    assert len(set(all_known_cards)) == 52


@pytest.mark.asyncio
async def test_start_hand_skips_inactive_players_and_does_not_consume_cards_for_them() -> None:
    server = PokerServer()

    active_one = make_player("p1", "ActiveOne", seat=1)
    spectator = make_player("p2", "Spectator", seat=2, is_spectator=True)
    sitting_out = make_player("p3", "SittingOut", seat=3, sitting_out=True)
    busted = make_player("p4", "Busted", seat=4, stack=0)
    active_two = make_player("p5", "ActiveTwo", seat=5)

    # Give inactive players stale cards to make sure start_hand clears them.
    spectator.cards = ["AS", "AH"]
    sitting_out.cards = ["KS", "KH"]
    busted.cards = ["QS", "QH"]

    room = make_room(active_one, spectator, sitting_out, busted, active_two)

    await server.start_hand(room)

    assert len(active_one.cards) == 2
    assert len(active_two.cards) == 2

    assert spectator.cards == []
    assert sitting_out.cards == []
    assert busted.cards == []

    assert spectator.committed == 0
    assert sitting_out.committed == 0
    assert busted.committed == 0

    assert spectator.total_invested == 0
    assert sitting_out.total_invested == 0
    assert busted.total_invested == 0

    dealt = hole_cards(room)
    assert len(dealt) == 4
    assert len(set(dealt)) == 4
    assert len(room.deck) == 52 - 4


@pytest.mark.asyncio
async def test_start_hand_clears_previous_showdown_and_reveal_state() -> None:
    server = PokerServer()

    p1 = make_player("p1", "PlayerOne", seat=1)
    p2 = make_player("p2", "PlayerTwo", seat=2)

    room = make_room(p1, p2, phase="showdown")

    room.community = ["2C", "5D", "9S", "JH", "3C"]
    room.pot = 600
    room.current_bet = 200
    room.winners = [Winner(p1.player_id, p1.name, 600, "Best hand at showdown")]
    room.hand_deltas = {
        p1.player_id: 400,
        p2.player_id: -400,
    }
    room.action_log = [
        {
            "player": "OLD",
            "action": "old_action",
            "amount": 999,
            "phase": "river",
            "is_all_in": False,
        }
    ]

    for player in (p1, p2):
        player.cards = ["AS", "AH"]
        player.folded = True
        player.folded_reveal_mode = "both"
        player.uncontested_reveal_mode = "both"
        player.all_in = True
        player.committed = 200
        player.total_invested = 200
        player.acted = True
        player.last_hand_name = "Old Pair"
        player.last_best_cards = ["AS", "AH", "2C", "5D", "9S"]
        player.last_hand_detail = "old detail"

    await server.start_hand(room)

    assert room.phase == "preflop"
    assert room.community == []
    assert room.winners == []
    assert room.hand_deltas == {}

    assert room.pot == room.small_blind + room.big_blind
    assert room.current_bet == room.big_blind

    assert [entry["action"] for entry in room.action_log] == [
        "small_blind",
        "big_blind",
    ]
    assert all(entry["player"] != "OLD" for entry in room.action_log)

    for player in (p1, p2):
        assert len(player.cards) == 2
        assert player.folded is False
        assert player.folded_reveal_mode == "hidden"
        assert player.uncontested_reveal_mode == "hidden"
        assert player.all_in is False
        assert player.acted is False
        assert player.total_invested == player.committed
        assert player.hand_start_stack == STARTING_STACK
        assert player.last_hand_name == ""
        assert player.last_best_cards == []
        assert player.last_hand_detail == ""


@pytest.mark.asyncio
async def test_start_hand_preserves_seats_and_player_identity_while_resetting_hand_fields() -> None:
    server = PokerServer()

    p1 = make_player("p1", "Alice", seat=3)
    p2 = make_player("p2", "Bob", seat=7)
    room = make_room(p1, p2)

    p1.token = "stable-token-alice"
    p2.token = "stable-token-bob"

    await server.start_hand(room)

    assert p1.player_id == "p1"
    assert p2.player_id == "p2"
    assert p1.token == "stable-token-alice"
    assert p2.token == "stable-token-bob"
    assert p1.seat == 3
    assert p2.seat == 7

    assert room.players["p1"] is p1
    assert room.players["p2"] is p2


@pytest.mark.asyncio
async def test_new_hand_replaces_previous_deck_instead_of_reusing_mutated_deck() -> None:
    server = PokerServer()

    p1 = make_player("p1", "P1", seat=1)
    p2 = make_player("p2", "P2", seat=2)
    p3 = make_player("p3", "P3", seat=3)

    room = make_room(p1, p2, p3)

    room.deck = ["AS"]
    room.community = ["2C", "5D", "9S"]

    await server.start_hand(room)

    # Three active players receive six cards from a fresh 52-card deck.
    assert len(hole_cards(room)) == 6
    assert len(room.deck) == 46

    all_known_cards = room.deck + hole_cards(room)
    assert len(all_known_cards) == 52
    assert len(set(all_known_cards)) == 52
    assert room.community == []
