"""Tests for game log persistence (poker/logs.py)."""

import json
import os
import shutil

import pytest

from poker.logs import LOGS_DIR, save_hand_log
from poker.models import Player, Room, Winner


@pytest.fixture(autouse=True)
def cleanup_logs():
    """Remove any log files created during the test."""
    yield
    if os.path.exists(LOGS_DIR):
        shutil.rmtree(LOGS_DIR)


def _make_room_with_showdown() -> Room:
    """Create a minimal room that looks like a completed showdown."""
    room = Room(room_id="test_room_123")
    room.hands_played = 5
    room.pot = 200
    room.community = ["Ah", "Kd", "9s", "3c", "7h"]

    # Add players
    p1 = Player(player_id="p1", token="t1", name="Alice", seat=0)
    p1.cards = ["As", "Ac"]
    p1.stack = 1100
    p1.total_invested = 100
    p1.folded = False
    p1.all_in = False

    p2 = Player(player_id="p2", token="t2", name="Bob", seat=1)
    p2.cards = ["2h", "3d"]
    p2.stack = 900
    p2.total_invested = 100
    p2.folded = False
    p2.all_in = False

    room.players = {"p1": p1, "p2": p2}

    # Set up winners (as if showdown already determined a winner)
    room.winners = [
        Winner(
            player_id="p1",
            name="Alice",
            amount=200,
            reason="Best hand at showdown",
            hand_name="Three of a Kind",
            best_cards=["As", "Ac", "Ah", "Kd", "9s"],
        )
    ]

    return room


def test_log_file_is_created():
    """Verify that save_hand_log creates the expected log file."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    expected_file = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    assert os.path.exists(expected_file), f"Log file not found: {expected_file}"


def test_log_is_valid_json():
    """Verify the log file contains valid JSON that can be deserialized."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    assert isinstance(data, dict)


def test_log_contains_required_fields():
    """Verify the log JSON contains all required top-level fields."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    required_fields = [
        "hand_number",
        "timestamp",
        "room_id",
        "players",
        "community_cards",
        "pot",
        "winners",
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"


def test_log_hand_number_and_room_id():
    """Verify hand_number and room_id are captured correctly."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    assert data["hand_number"] == 5
    assert data["room_id"] == "test_room_123"
    assert data["pot"] == 200


def test_log_players_data():
    """Verify player entries contain expected fields."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    assert len(data["players"]) == 2

    alice = data["players"][0]
    assert alice["name"] == "Alice"
    assert alice["seat"] == 0
    assert alice["hole_cards"] == ["As", "Ac"]
    assert alice["stack_after"] == 1100
    assert alice["total_invested"] == 100
    assert alice["folded"] is False
    assert alice["all_in"] is False


def test_log_community_cards():
    """Verify community cards are broken down by street."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    cc = data["community_cards"]
    assert cc["flop"] == ["Ah", "Kd", "9s"]
    assert cc["turn"] == ["3c"]
    assert cc["river"] == ["7h"]


def test_log_winners_data():
    """Verify winners are captured correctly."""
    room = _make_room_with_showdown()
    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    assert len(data["winners"]) == 1
    winner = data["winners"][0]
    assert winner["name"] == "Alice"
    assert winner["amount"] == 200
    assert winner["reason"] == "Best hand at showdown"
    assert winner["hand_name"] == "Three of a Kind"


def test_log_partial_community_cards():
    """Verify community cards work with fewer than 5 cards (e.g., fold on flop)."""
    room = _make_room_with_showdown()
    room.community = ["Ah", "Kd", "9s"]  # Only flop dealt

    save_hand_log(room)

    filepath = os.path.join(LOGS_DIR, "test_room_123_hand_5.json")
    with open(filepath, "r") as f:
        data = json.load(f)

    cc = data["community_cards"]
    assert cc["flop"] == ["Ah", "Kd", "9s"]
    assert cc["turn"] == []
    assert cc["river"] == []


def test_log_does_not_crash_on_error(monkeypatch):
    """Verify save_hand_log does not raise even if writing fails."""
    room = _make_room_with_showdown()

    # Make os.makedirs raise an error to simulate a write failure
    def fail_makedirs(*args, **kwargs):
        raise PermissionError("No write access")

    monkeypatch.setattr(os, "makedirs", fail_makedirs)

    # Should not raise
    save_hand_log(room)
