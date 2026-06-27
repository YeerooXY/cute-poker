import asyncio
import json

from poker.game import MAX_CHAT_MESSAGES, MAX_CHAT_TEXT_LEN, PokerServer
from poker.models import ChatMessage, Room


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))


def make_room():
    server = PokerServer()
    room = Room(room_id="CHAT1")
    server.rooms[room.room_id] = room

    ws = FakeWebSocket()
    player = server.add_new_player(room, ws, " Alice ")
    room.creator_token = player.token

    return server, room, player, ws


def run(coro):
    return asyncio.run(coro)


def test_chat_drops_blank_and_non_string_payloads():
    server, room, player, ws = make_room()

    for bad_payload in ["", "   \n\t   ", None, {"text": "hello"}, ["hello"]]:
        run(server.chat(room, player, bad_payload))

    assert room.messages == []
    assert ws.sent == []


def test_handle_chat_does_not_stringify_none_payload():
    server, room, player, _ws = make_room()

    result = run(server.handle(
        player.ws,
        "chat",
        {
            "room_id": room.room_id.lower(),
            "token": player.token,
            "text": None,
        },
    ))

    assert result.room_id == room.room_id
    assert result.player_token == player.token
    assert room.messages == []


def test_chat_normalizes_whitespace_and_truncates_text():
    server, room, player, _ws = make_room()

    noisy = "  hello\r\n\tworld  " + ("x" * (MAX_CHAT_TEXT_LEN + 50))
    run(server.chat(room, player, noisy))

    assert len(room.messages) == 1
    stored = room.messages[0].text
    assert stored.startswith("hello world")
    assert "\n" not in stored
    assert "\r" not in stored
    assert "\t" not in stored
    assert len(stored) <= MAX_CHAT_TEXT_LEN


def test_chat_enforces_room_message_cap():
    server, room, player, _ws = make_room()

    for i in range(MAX_CHAT_MESSAGES + 7):
        run(server.chat(room, player, f"msg {i}"))

    assert len(room.messages) == MAX_CHAT_MESSAGES
    assert room.messages[0].text == "msg 7"
    assert room.messages[-1].text == f"msg {MAX_CHAT_MESSAGES + 6}"

    visible = server.visible_state(room, player.token)
    assert len(visible["messages"]) == MAX_CHAT_MESSAGES


def test_chat_trim_also_caps_preexisting_system_messages():
    server, room, player, _ws = make_room()
    room.messages = [
        ChatMessage(name="system", text=f"old {i}")
        for i in range(MAX_CHAT_MESSAGES + 3)
    ]

    run(server.chat(room, player, "new"))

    assert len(room.messages) == MAX_CHAT_MESSAGES
    assert room.messages[0].text == "old 4"
    assert room.messages[-1].text == "new"
