from __future__ import annotations

from poker.game import PokerServer
from poker.models import Player, Room


def make_player(
    player_id: str,
    name: str,
    seat: int,
    cards: list[str],
    folded: bool = False,
    is_spectator: bool = False,
) -> Player:
    return Player(
        player_id=player_id,
        token=f"token_{player_id}",
        name=name,
        seat=seat,
        stack=1000,
        cards=cards,
        folded=folded,
        acted=True,
        connected=True,
        is_spectator=is_spectator,
    )


def make_odds_room() -> tuple[PokerServer, Room, Player, Player, Player]:
    server = PokerServer()

    alice = make_player("alice", "Alice", 1, ["AS", "AH"])
    bob = make_player("bob", "Bob", 2, ["KH", "KD"])
    cara = make_player("cara", "Cara", 3, ["QH", "QD"])

    room = Room(room_id="ODDS_STATE")
    room.phase = "flop"
    room.community = ["2C", "7D", "JS"]
    room.players = {
        alice.player_id: alice,
        bob.player_id: bob,
        cara.player_id: cara,
    }
    server.rooms[room.room_id] = room

    return server, room, alice, bob, cara


def player_entry(state: dict, name: str) -> dict:
    return next(player for player in state["players"] if player["name"] == name)


def patch_odds(monkeypatch):
    calls: list[tuple[tuple[str, ...], tuple[str, ...], int, int]] = []

    def fake_calculate_player_odds(cards, community, num_opp, iterations):
        calls.append((tuple(cards), tuple(community), num_opp, iterations))
        return {
            "equity": len(calls) * 10,
            "current_ahead": None,
            "phase_note": "",
        }

    monkeypatch.setattr("poker.game.calculate_player_odds", fake_calculate_player_odds)
    return calls


def test_viewer_odds_cache_reuses_exact_same_state(monkeypatch):
    calls = patch_odds(monkeypatch)
    server, room, alice, bob, cara = make_odds_room()
    cara.folded = True

    first = server.visible_state(room, alice.token)
    second = server.visible_state(room, alice.token)

    assert len(calls) == 1
    assert first["viewer"]["odds"]["equity"] == 10
    assert second["viewer"]["odds"]["equity"] == 10


def test_viewer_odds_cache_recomputes_when_live_opponent_identity_changes(monkeypatch):
    calls = patch_odds(monkeypatch)
    server, room, alice, bob, cara = make_odds_room()

    cara.folded = True
    first = server.visible_state(room, alice.token)

    bob.folded = True
    cara.folded = False
    second = server.visible_state(room, alice.token)

    assert len(calls) == 2
    assert first["viewer"]["odds"]["equity"] == 10
    assert second["viewer"]["odds"]["equity"] == 20


def test_viewer_odds_cache_recomputes_when_viewer_hole_cards_change(monkeypatch):
    calls = patch_odds(monkeypatch)
    server, room, alice, bob, cara = make_odds_room()
    cara.folded = True

    first = server.visible_state(room, alice.token)

    alice.cards = ["TC", "TD"]
    second = server.visible_state(room, alice.token)

    assert len(calls) == 2
    assert first["viewer"]["odds"]["equity"] == 10
    assert second["viewer"]["odds"]["equity"] == 20


def test_spectator_equity_cache_recomputes_when_live_opponent_identity_changes(monkeypatch):
    calls = patch_odds(monkeypatch)
    server, room, alice, bob, cara = make_odds_room()

    spectator = make_player("spectator", "Spectator", 4, [], is_spectator=True)
    room.players[spectator.player_id] = spectator

    cara.folded = True
    first = server.visible_state(room, spectator.token)

    bob.folded = True
    cara.folded = False
    second = server.visible_state(room, spectator.token)

    assert len(calls) == 4

    assert player_entry(first, "Alice")["equity_pct"] == 10
    assert player_entry(first, "Bob")["equity_pct"] == 20

    assert player_entry(second, "Alice")["equity_pct"] == 30
    assert player_entry(second, "Cara")["equity_pct"] == 40
