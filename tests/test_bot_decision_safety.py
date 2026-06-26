from __future__ import annotations

import asyncio
import json

import pytest

from poker.bot import BotConfig
from poker.game import PokerServer
from poker.models import Player, Room


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
        ws=DummyWs(),
    )
    player.total_invested = committed
    player.hand_start_stack = stack + committed
    return player


def make_room(
    *players: Player,
    phase: str = "flop",
    action_seat: int | None = 1,
    current_bet: int = 0,
    pot: int = 0,
) -> Room:
    room = Room(room_id="BOT_SAFETY_TEST")
    room.phase = phase
    room.players = {p.player_id: p for p in players}
    room.creator_token = players[0].token if players else ""
    room.action_seat = action_seat
    room.current_bet = current_bet
    room.min_raise = room.big_blind
    room.pot = pot

    if phase in {"flop", "turn", "river", "showdown"}:
        room.community = ["2C", "5D", "9S"]
    if phase in {"turn", "river", "showdown"}:
        room.community.append("JH")
    if phase in {"river", "showdown"}:
        room.community.append("3C")

    return room


def make_bot_config(name: str = "TestBot") -> BotConfig:
    return BotConfig(
        style="tight_aggressive",
        name=name,
        avatar="🤖",
        think_time_min=0.0,
        think_time_max=0.0,
        use_advanced_ai=False,
        difficulty="hard",
    )


async def run_bot_loop_until(
    server: PokerServer,
    room: Room,
    predicate,
    monkeypatch: pytest.MonkeyPatch,
    max_ticks: int = 200,
) -> None:
    """Run the infinite bot loop briefly, then remove the room so it exits."""
    original_sleep = asyncio.sleep

    async def fast_sleep(_delay: float) -> None:
        await original_sleep(0)

    monkeypatch.setattr("poker.game.asyncio.sleep", fast_sleep)

    server.rooms[room.room_id] = room
    task = asyncio.create_task(server._bot_loop(room.room_id))

    try:
        for _ in range(max_ticks):
            if predicate():
                return
            await original_sleep(0)
        raise AssertionError("bot loop predicate was not reached")
    finally:
        server.rooms.pop(room.room_id, None)
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_bot_loop_does_not_act_when_it_is_a_human_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    human = make_player("p1", "Human", seat=1, stack=1000)
    bot = make_player("b1", "Bot", seat=2, stack=1000)
    room = make_room(human, bot, action_seat=1, current_bet=0, pot=0)

    server.bots[bot.player_id] = make_bot_config("Bot")

    called = False

    async def should_not_decide(*_args, **_kwargs):
        nonlocal called
        called = True
        return "check_call", {}

    monkeypatch.setattr("poker.game.bot_decide", should_not_decide)

    await run_bot_loop_until(
        server,
        room,
        lambda: room.room_id in server._bot_loop_active and server._bot_loop_active[room.room_id].is_set(),
        monkeypatch,
    )

    assert called is False
    assert room.action_seat == human.seat
    assert room.action_log == []


@pytest.mark.asyncio
async def test_bot_loop_auto_advances_stuck_folded_bot_action_seat(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    folded_bot = make_player("b1", "FoldedBot", seat=1, stack=1000, folded=True)
    human = make_player("p1", "Human", seat=2, stack=1000)
    room = make_room(folded_bot, human, action_seat=1, current_bet=0, pot=0)

    server.bots[folded_bot.player_id] = make_bot_config("FoldedBot")

    await run_bot_loop_until(
        server,
        room,
        lambda: room.action_seat == human.seat,
        monkeypatch,
    )

    assert room.action_seat == human.seat
    assert folded_bot.folded is True
    assert folded_bot.stack == 1000
    assert room.action_log == []


@pytest.mark.asyncio
async def test_bot_loop_rechecks_turn_after_think_time_before_acting(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    bot = make_player("b1", "ThinkingBot", seat=1, stack=1000)
    human = make_player("p1", "Human", seat=2, stack=1000)
    room = make_room(bot, human, action_seat=1, current_bet=0, pot=0)

    server.bots[bot.player_id] = make_bot_config("ThinkingBot")

    original_sleep = asyncio.sleep
    changed_turn_during_think = False
    bot_decide_called = False

    monkeypatch.setattr("poker.game.calculate_think_time", lambda *_args, **_kwargs: 0.25)

    async def sleep_and_change_turn(delay: float) -> None:
        nonlocal changed_turn_during_think
        if delay == 0.25 and not changed_turn_during_think:
            room.action_seat = human.seat
            changed_turn_during_think = True
        await original_sleep(0)

    async def should_not_decide(*_args, **_kwargs):
        nonlocal bot_decide_called
        bot_decide_called = True
        return "bet_raise", {"amount": 100}

    monkeypatch.setattr("poker.game.asyncio.sleep", sleep_and_change_turn)
    monkeypatch.setattr("poker.game.bot_decide", should_not_decide)

    server.rooms[room.room_id] = room
    task = asyncio.create_task(server._bot_loop(room.room_id))

    try:
        for _ in range(200):
            bot_event = server._bot_loop_active.get(room.room_id)
            if changed_turn_during_think and bot_event and bot_event.is_set():
                break
            await original_sleep(0)
        else:
            raise AssertionError("bot loop did not reach post-think idle state")
    finally:
        server.rooms.pop(room.room_id, None)
        await asyncio.wait_for(task, timeout=1.0)

    assert changed_turn_during_think is True
    assert bot_decide_called is False
    assert room.action_seat == human.seat
    assert room.action_log == []
    assert bot.stack == 1000
    assert bot.committed == 0


@pytest.mark.asyncio
async def test_bot_decision_exception_falls_back_to_safe_check_call(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    bot = make_player("b1", "FallbackBot", seat=1, stack=90, committed=10)
    human = make_player("p1", "Human", seat=2, stack=960, committed=40, acted=False)
    room = make_room(bot, human, action_seat=1, current_bet=40, pot=50)

    server.bots[bot.player_id] = make_bot_config("FallbackBot")

    async def exploding_decision(*_args, **_kwargs):
        raise RuntimeError("simulated bot decision failure")

    monkeypatch.setattr("poker.game.bot_decide", exploding_decision)
    monkeypatch.setattr("poker.game.calculate_think_time", lambda *_args, **_kwargs: 0.0)

    await run_bot_loop_until(
        server,
        room,
        lambda: bot.committed == 40 and room.action_seat == human.seat,
        monkeypatch,
    )

    assert bot.stack == 60
    assert bot.committed == 40
    assert bot.total_invested == 40
    assert bot.acted is True
    assert room.pot == 80
    assert room.action_seat == human.seat

    fallback_entry = room.action_log[-1]
    assert fallback_entry["player"] == "FallbackBot"
    assert fallback_entry["action"] == "check_call"
    assert fallback_entry["amount"] == 30
    assert fallback_entry["committed_before"] == 10
    assert fallback_entry["is_all_in"] is False
    assert fallback_entry["note"] == "exception fallback"


@pytest.mark.asyncio
async def test_bot_decision_exception_fallback_can_go_all_in_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    server = PokerServer()

    bot = make_player("b1", "ShortBot", seat=1, stack=25, committed=10)
    human = make_player("p1", "Human", seat=2, stack=940, committed=60, acted=False)
    pending = make_player("p2", "Pending", seat=3, stack=940, committed=60, acted=False)

    # Keep betting open after the short all-in fallback. This test is about the
    # bot fallback action itself, not all-in runout/dealing.
    room = make_room(bot, human, pending, action_seat=1, current_bet=60, pot=70)

    server.bots[bot.player_id] = make_bot_config("ShortBot")

    async def exploding_decision(*_args, **_kwargs):
        raise RuntimeError("simulated bot decision failure")

    monkeypatch.setattr("poker.game.bot_decide", exploding_decision)
    monkeypatch.setattr("poker.game.calculate_think_time", lambda *_args, **_kwargs: 0.0)

    await run_bot_loop_until(
        server,
        room,
        lambda: bot.all_in is True and bot.stack == 0,
        monkeypatch,
    )

    assert bot.stack == 0
    assert bot.committed == 35
    assert bot.total_invested == 35
    assert bot.all_in is True
    assert bot.acted is True
    assert room.pot == 95

    fallback_entry = room.action_log[-1]
    assert fallback_entry["player"] == "ShortBot"
    assert fallback_entry["action"] == "check_call"
    assert fallback_entry["amount"] == 50
    assert fallback_entry["committed_before"] == 10
    assert fallback_entry["is_all_in"] is True
    assert fallback_entry["note"] == "exception fallback"
