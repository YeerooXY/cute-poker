import asyncio
import json

from poker.game import PokerServer
from poker.models import Player, Room


class DummyWs:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def make_admin_room():
    server = PokerServer()
    room = Room(room_id="ADMIN")
    room.phase = "showdown"
    room.creator_token = "creator-token"

    creator_ws = DummyWs()
    guest_ws = DummyWs()

    creator = Player(
        player_id="creator",
        token="creator-token",
        name="Creator",
        seat=1,
        ws=creator_ws,
        connected=True,
        stack=1000,
    )
    guest = Player(
        player_id="guest",
        token="guest-token",
        name="Guest",
        seat=2,
        ws=guest_ws,
        connected=True,
        stack=1000,
    )

    room.players = {
        creator.player_id: creator,
        guest.player_id: guest,
    }
    server.rooms[room.room_id] = room
    return server, room, creator, guest


def test_non_admin_cannot_start_next_hand():
    server, room, _creator, guest = make_admin_room()
    called = {"start": False}

    async def fake_start_hand(_room):
        called["start"] = True

    server.start_hand = fake_start_hand

    asyncio.run(server.player_action(room, guest, "start_hand", {}))

    assert called["start"] is False
    assert guest.ws.sent
    assert guest.ws.sent[0]["event"] == "error"
    assert "Only the room creator" in guest.ws.sent[0]["payload"]["message"]


def test_admin_can_start_next_hand():
    server, room, creator, _guest = make_admin_room()
    called = {"start": False}

    async def fake_start_hand(_room):
        called["start"] = True

    server.start_hand = fake_start_hand

    asyncio.run(server.player_action(room, creator, "start_hand", {}))

    assert called["start"] is True
