from __future__ import annotations

import asyncio
import json

import pytest

from poker.game import PokerServer


class DummyWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


def run(coro):
    return asyncio.run(coro)


def joined_payload(ws: DummyWs) -> dict:
    joined = [message for message in ws.sent if message.get("event") == "joined"]
    assert joined
    return joined[-1]["payload"]


def created_room(server: PokerServer, ws: DummyWs):
    payload = joined_payload(ws)
    return server.rooms[payload["room_id"]]


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"blind_increase_hands": "abc"},
        {"blind_increase_hands": -5},
        {"blind_increase_hands": "-5"},
        {"blind_increase_hands": None},
        {"blind_increase_hands": True},
        {"blind_increase_hands": []},
        {"blind_increase_hands": {}},
        {"ante": "abc"},
        {"ante": -10},
        {"ante": "-10"},
        {"ante": None},
        {"ante": False},
        {"ante": []},
        {"ante": {}},
        {
            "blind_increase_hands": "abc",
            "ante": "lol",
            "ante_mode": "wat",
            "auto_ante": "definitely",
            "allow_folded_reveals": "maybe",
        },
    ],
)
def test_create_room_ignores_malformed_room_settings_without_crashing(bad_payload):
    server = PokerServer()
    ws = DummyWs()

    run(server.create_room(ws, {"name": "Host", **bad_payload}))

    room = created_room(server, ws)
    assert room.blind_increase_hands == 0
    assert room.ante == 0
    assert room.ante_mode == "classic"
    assert room.auto_ante is False
    assert room.allow_folded_reveals is True


def test_create_room_accepts_valid_integer_room_settings_from_ints_and_strings():
    server = PokerServer()
    ws = DummyWs()

    run(server.create_room(ws, {
        "name": "Host",
        "blind_increase_hands": "3",
        "ante": "25",
        "ante_mode": "BBA",
        "auto_ante": "true",
        "allow_folded_reveals": "false",
    }))

    room = created_room(server, ws)
    assert room.blind_increase_hands == 3
    assert room.ante == 25
    assert room.ante_mode == "bba"
    assert room.auto_ante is True
    assert room.allow_folded_reveals is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("TRUE", True),
        (" yes ", True),
        ("on", True),
        ("1", True),
        (1, True),
        ("false", False),
        ("FALSE", False),
        (" no ", False),
        ("off", False),
        ("0", False),
        (0, False),
    ],
)
def test_create_room_parses_boolean_settings_explicitly(value, expected):
    server = PokerServer()
    ws = DummyWs()

    run(server.create_room(ws, {
        "name": "Host",
        "auto_ante": value,
        "allow_folded_reveals": value,
    }))

    room = created_room(server, ws)
    assert room.auto_ante is expected
    assert room.allow_folded_reveals is expected


@pytest.mark.parametrize("value", ["false", "0", "off", "no", "", False, 0])
def test_falsey_string_settings_do_not_accidentally_enable_auto_ante(value):
    server = PokerServer()
    ws = DummyWs()

    run(server.create_room(ws, {
        "name": "Host",
        "auto_ante": value,
    }))

    room = created_room(server, ws)
    assert room.auto_ante is False


def test_create_room_invalid_allow_folded_reveals_keeps_safe_default_true():
    server = PokerServer()
    ws = DummyWs()

    run(server.create_room(ws, {
        "name": "Host",
        "allow_folded_reveals": "maybe",
    }))

    room = created_room(server, ws)
    assert room.allow_folded_reveals is True
