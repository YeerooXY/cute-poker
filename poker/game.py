from __future__ import annotations

import asyncio
import builtins
import json
import os
import random
import secrets
import string
import time as time_module
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from fastapi import WebSocket

from poker.cards import display_cards, new_deck
from poker.evaluator import evaluate_7, describe_hand
from poker.logs import save_hand_log
from poker.models import ChatMessage, Player, Room, Winner
from poker.odds import calculate_player_odds
from poker.terminology import classify_hand
from poker.bot import BotConfig, create_bot_config, bot_decide, calculate_think_time


# ─── Timestamped print for server_log.txt ─────────────────────────────────────
_original_print = builtins.print


def print(*args, **kwargs):
    """Print with HH:MM:SS.mmm timestamp prefix."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    _original_print(f"[{ts}]", *args, **kwargs)

from poker.trash_talk import get_trash_talk, TrashTalkEvent, DELAY_RANGE


MAX_SEATS = 8
STARTING_STACK = 1000
MAX_CHAT_MESSAGES = 50
MAX_CHAT_TEXT_LEN = 240
HAND_HISTORY_LIMIT = 20
AUTO_DEAL_DEFAULT_DELAY_SECONDS = 5
ACTION_TIMER_DEFAULT_SECONDS = 10
STARTING_TIMEBANK_DEFAULT_SECONDS = 100
TIMEBANK_GAIN_DEFAULT_SECONDS = 1
_SIMULATION_MODE = os.getenv("POKER_SIMULATION") == "1"

# ─── Action log sanitization ──────────────────────────────────────────────────

_ALLOWED_ACTION_LOG_FIELDS = {"player", "action", "amount", "phase", "is_all_in"}

_ACTION_LOG_DEFAULTS: dict[str, Any] = {
    "player": "",
    "action": "",
    "amount": 0,
    "phase": "preflop",
    "is_all_in": False,
}


def _sanitize_action_log(raw_log: list[dict]) -> list[dict]:
    """Strip debug/internal fields from action_log for client broadcast."""
    return [
        {k: entry.get(k, _ACTION_LOG_DEFAULTS[k]) for k in _ALLOWED_ACTION_LOG_FIELDS}
        for entry in raw_log
    ]


def _sanitize_chat_text(text: Any) -> str:
    """Return a safe, bounded chat message, or empty string to drop it."""
    if not isinstance(text, str):
        return ""
    clean = " ".join(text.split())
    return clean[:MAX_CHAT_TEXT_LEN].strip()


def _append_room_message(room: Room, name: str, text: Any) -> bool:
    """Append a sanitized room message and enforce the room message cap."""
    clean = _sanitize_chat_text(text)
    if not clean:
        return False

    clean_name = (str(name).strip()[:24].strip() or "Player")
    room.messages.append(ChatMessage(clean_name, clean))

    if len(room.messages) > MAX_CHAT_MESSAGES:
        del room.messages[:-MAX_CHAT_MESSAGES]

    return True

def _parse_non_negative_int_amount(value: Any) -> Optional[int]:
    """Parse a client-provided chip amount without accepting weird values."""
    if isinstance(value, bool):
        return None

    if isinstance(value, float) and not value.is_integer():
        return None

    if isinstance(value, str) and not value.strip().isdigit():
        return None

    try:
        amount = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if amount < 0:
        return None

    return amount

def _parse_bool_setting(value: Any, default: bool = False) -> bool:
    """Parse client-provided boolean settings without Python truthiness surprises."""
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False

    if value in (0, 1):
        return bool(value)

    return default

def _live_opponent_tokens(room: Room, player: Player) -> tuple[str, ...]:
    """Return the exact live opponent identities used by odds calculations."""
    return tuple(sorted(
        other.token
        for other in room.players.values()
        if other.cards and not other.folded and other.token != player.token
    ))


def _odds_cache_key(room: Room, player: Player, num_opp: int) -> tuple[Any, ...]:
    """Cache odds by actual visible poker state, not just board/opponent count."""
    return (
        player.token,
        tuple(player.cards),
        tuple(room.community),
        num_opp,
        _live_opponent_tokens(room, player),
    )

@dataclass
class HandleResult:
    room_id: Optional[str] = None
    player_token: Optional[str] = None


def make_id(length: int = 5) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PokerServer:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.bots: dict[str, BotConfig] = {}  # player_id -> BotConfig
        self._bot_task_running: set[str] = set()  # room_ids with active bot loops
        self._odds_cache: dict[str, dict] = {}  # room_id -> {(token, board_tuple): odds_result}
        self._bot_loop_active: dict[str, asyncio.Event] = {}  # room_id → Event (set when idle)
        self._pending_start_hand: dict[str, bool] = {}  # room_id → queued start_hand flag
        self._auto_deal_tasks: dict[str, asyncio.Task] = {}
        self._action_timer_tasks: dict[str, asyncio.Task] = {}

    async def handle(self, ws: WebSocket, event: str, payload: dict[str, Any]) -> HandleResult:
        if event == "create":
            return await self.create_room(ws, payload)

        if event == "join":
            return await self.join_room(ws, payload)

        if event == "reconnect":
            return await self.reconnect(ws, payload)

        if event == "list_rooms":
            await self.list_rooms(ws)
            return HandleResult()

        room, player = self.get_room_and_player(payload)
        if not room or not player:
            print(f"[HANDLE] Failed to find room/player for event='{event}' room_id='{payload.get('room_id','')}' token='{str(payload.get('token',''))[:8]}...'")
            await self.send(ws, "error", {"message": "Join or reconnect to a room first."})
            return HandleResult()

        if event == "leave":
            await self.leave_room(room, player)
            await self.send(ws, "left", {})
            return HandleResult()

        if event == "action":
            await self.player_action(room, player, payload.get("action"), payload)
            return HandleResult(room.room_id, player.token)

        if event == "chat":
            await self.chat(room, player, payload.get("text", ""))
            return HandleResult(room.room_id, player.token)

        await self.send(ws, "error", {"message": f"Unknown event: {event}"})
        return HandleResult(room.room_id, player.token)

    async def send(self, ws: WebSocket, event: str, payload: dict):
        if ws is None:
            return  # Bot or disconnected player, skip
        await ws.send_text(json.dumps({"event": event, "payload": payload}))

    async def broadcast(self, room: Room):
        # Clean up stale disconnected players
        self._evict_stale(room)

        # Backend-owned auto-deal countdown
        self._ensure_auto_deal(room)
        self._ensure_action_timer(room)

        # Clear odds cache on new hand (preflop start with empty board)
        if room.phase == "preflop" and not room.community:
            self._odds_cache.pop(room.room_id, None)

        for p in room.connected_players():
            try:
                state = await asyncio.to_thread(
                    self.visible_state, room, p.token
                )
                await self.send(p.ws, "state", state)
            except Exception:
                p.connected = False
                p.ws = None
                p.disconnected_at = __import__('time').time()

    async def create_room(self, ws: WebSocket, payload: dict[str, Any]) -> HandleResult:
        room_id = make_id()
        while room_id in self.rooms:
            room_id = make_id()

        room = Room(room_id=room_id)
        self.rooms[room_id] = room

        # Apply room settings from payload (optional, safely parsed)
        blind_increase = _parse_non_negative_int_amount(
            payload.get("blind_increase_hands", 0)
        )
        if blind_increase and blind_increase > 0:
            room.blind_increase_hands = blind_increase

        ante = _parse_non_negative_int_amount(payload.get("ante", 0))
        if ante is not None:
            room.ante = ante

        ante_mode = str(payload.get("ante_mode", "classic")).strip().lower()
        if ante_mode in ("classic", "bba"):
            room.ante_mode = ante_mode

        room.auto_ante = _parse_bool_setting(payload.get("auto_ante", False))
        room.allow_folded_reveals = _parse_bool_setting(
            payload.get("allow_folded_reveals", True),
            default=True,
        )

        room.auto_deal_enabled = _parse_bool_setting(
            payload.get("auto_deal_enabled", True),
            default=True,
        )
        auto_deal_delay = _parse_non_negative_int_amount(
            payload.get("auto_deal_delay_seconds", AUTO_DEAL_DEFAULT_DELAY_SECONDS)
        )
        if auto_deal_delay is None or auto_deal_delay < 1:
            auto_deal_delay = AUTO_DEAL_DEFAULT_DELAY_SECONDS
        room.auto_deal_delay_seconds = auto_deal_delay
        action_time = _parse_non_negative_int_amount(
            payload.get("action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)
        )
        room.action_time_seconds = max(1, action_time if action_time is not None else ACTION_TIMER_DEFAULT_SECONDS)

        starting_timebank = _parse_non_negative_int_amount(
            payload.get("starting_timebank_seconds", STARTING_TIMEBANK_DEFAULT_SECONDS)
        )
        room.starting_timebank_seconds = max(
            0,
            starting_timebank if starting_timebank is not None else STARTING_TIMEBANK_DEFAULT_SECONDS,
        )

        timebank_gain = _parse_non_negative_int_amount(
            payload.get("timebank_gain_per_hand", TIMEBANK_GAIN_DEFAULT_SECONDS)
        )
        room.timebank_gain_per_hand = max(
            0,
            timebank_gain if timebank_gain is not None else TIMEBANK_GAIN_DEFAULT_SECONDS,
        )

        player = self.add_new_player(room, ws, payload.get("name", "Player"), payload.get("avatar", "🎭"))
        room.creator_token = player.token

        print(f"[CREATE] Room {room_id} created by {player.name} "
              f"(blind_increase={room.blind_increase_hands}, ante={room.ante})")

        await self.send(ws, "joined", {
            "room_id": room.room_id,
            "player_id": player.player_id,
            "token": player.token,
        })
        await self.broadcast(room)

        return HandleResult(room.room_id, player.token)

    async def join_room(self, ws: WebSocket, payload: dict[str, Any]) -> HandleResult:
        room_id = str(payload.get("room_id", "")).strip().upper()
        room = self.rooms.get(room_id)

        print(f"[JOIN] room_id='{room_id}' exists={room is not None} available_rooms={list(self.rooms.keys())}")

        if not room:
            await self.send(ws, "error", {"message": "Room not found."})
            return HandleResult()

        if self.find_free_seat(room) is None:
            # Try to evict disconnected players who aren't in an active hand
            self.evict_disconnected(room)
            if self.find_free_seat(room) is None:
                print(f"[JOIN] Room {room_id} is full. Players: {[(p.name, p.seat, p.connected) for p in room.players.values()]}")
                await self.send(ws, "error", {"message": "Room is full."})
                return HandleResult()

        player = self.add_new_player(room, ws, payload.get("name", "Player"), payload.get("avatar", "🎭"))
        print(f"[JOIN] Success: {player.name} -> seat {player.seat} in room {room_id}")

        await self.send(ws, "joined", {
            "room_id": room.room_id,
            "player_id": player.player_id,
            "token": player.token,
        })
        await self.broadcast(room)

        return HandleResult(room.room_id, player.token)

    async def reconnect(self, ws: WebSocket, payload: dict[str, Any]) -> HandleResult:
        room_id = str(payload.get("room_id", "")).strip().upper()
        token = str(payload.get("token", "")).strip()

        room = self.rooms.get(room_id)
        print(f"[RECONNECT] room_id='{room_id}' token='{token[:8]}...' room_exists={room is not None}")

        if not room:
            await self.send(ws, "reconnect_failed", {"message": "Room no longer exists."})
            return HandleResult()

        player = self.player_by_token(room, token)
        if not player:
            print(f"[RECONNECT] Token not found. Tokens in room: {[p.token[:8] for p in room.players.values()]}")
            await self.send(ws, "reconnect_failed", {"message": "Reconnect token not recognized."})
            return HandleResult()

        player.ws = ws
        player.connected = True
        player.disconnected_at = 0.0
        print(f"[RECONNECT] Success: {player.name} reconnected to room {room_id}")

        await self.send(ws, "joined", {
            "room_id": room.room_id,
            "player_id": player.player_id,
            "token": player.token,
        })
        await self.broadcast(room)

        return HandleResult(room.room_id, player.token)

    async def disconnect(self, room_id: str, token: str):
        room = self.rooms.get(room_id)
        if not room:
            return

        player = self.player_by_token(room, token)
        if player:
            player.connected = False
            player.ws = None
            player.disconnected_at = __import__('time').time()

        # Auto-evict stale disconnected players (gone for 60+ seconds, not in a hand)
        self._evict_stale(room)

        # If no humans are connected anymore, destroy the room
        room = self.rooms.get(room_id)
        if room:
            humans_connected = [p for p in room.players.values()
                               if p.connected and p.player_id not in self.bots]
            if not humans_connected:
                # Grace period: don't destroy immediately (player might reconnect)
                # But if NO humans at all (all left), clean up
                humans_present = [p for p in room.players.values()
                                 if p.player_id not in self.bots]
                if not humans_present:
                    for pid in list(room.players.keys()):
                        self.bots.pop(pid, None)
                    self._bot_task_running.discard(room_id)
                    self._bot_loop_active.pop(room_id, None)
                    self._pending_start_hand.pop(room_id, None)
                    self._cancel_auto_deal_for_room_id(room_id)
                    self._cancel_action_timer_for_room_id(room_id)
                    self.rooms.pop(room_id, None)
                    return

        if room_id in self.rooms:
            await self.broadcast(self.rooms[room_id])

    async def list_rooms(self, ws: WebSocket):
        """Send a list of active rooms with player counts."""
        rooms_list = []
        for room in self.rooms.values():
            # Count human players (connected, non-bot)
            humans = len([p for p in room.players.values()
                         if p.connected and p.player_id not in self.bots])
            total = len(room.players)
            if humans > 0:  # Only show rooms with at least one connected human
                rooms_list.append({
                    "room_id": room.room_id,
                    "players": total,
                    "connected": humans,
                    "max": MAX_SEATS,
                    "phase": room.phase,
                })
        await self.send(ws, "rooms_list", {"rooms": rooms_list})

    async def leave_room(self, room: Room, player: Player):
        """Remove a player from the room entirely."""
        # If in a hand, fold them first
        if player.cards and not player.folded and room.phase in ["preflop", "flop", "turn", "river"]:
            player.folded = True
            player.acted = True
            # If it was their turn, advance
            if room.action_seat == player.seat:
                await self.after_action(room)

        # Remove from room
        pid_to_remove = None
        for pid, p in room.players.items():
            if p.token == player.token:
                pid_to_remove = pid
                break
        if pid_to_remove:
            del room.players[pid_to_remove]
            self.assign_new_creator_if_needed(room)

        # If room is empty, delete it
        if not room.players:
            self._cancel_auto_deal_for_room_id(room.room_id)
            self._cancel_action_timer_for_room_id(room.room_id)
            self.rooms.pop(room.room_id, None)
        else:
            # If only bots remain (no human players), destroy the room
            humans = [p for p in room.players.values() if p.player_id not in self.bots]
            if not humans:
                # Clean up bot references
                for pid in list(room.players.keys()):
                    self.bots.pop(pid, None)
                self._bot_task_running.discard(room.room_id)
                self._bot_loop_active.pop(room.room_id, None)
                self._pending_start_hand.pop(room.room_id, None)
                self._cancel_auto_deal_for_room_id(room.room_id)
                self._cancel_action_timer_for_room_id(room.room_id)
                self.rooms.pop(room.room_id, None)
            else:
                # If only one player left in a hand, award them the pot
                if room.phase in ["preflop", "flop", "turn", "river"] and self.only_one_remaining(room):
                    self.award_to_last_player(room)
                await self.broadcast(room)

    def add_new_player(self, room: Room, ws: WebSocket, name: str, avatar: str = "🎭") -> Player:
        seat = self.find_free_seat(room)
        if seat is None:
            raise RuntimeError("No free seat")

        player = Player(
            player_id=make_id(10),
            token=secrets.token_urlsafe(24),
            name=(str(name).strip()[:24].strip() or f"Player {seat}"),
            seat=seat,
            ws=ws,
            connected=True,
            stack=STARTING_STACK,
            avatar=avatar[:4] if avatar else "🎭",
            timebank_seconds=max(0, int(getattr(room, "starting_timebank_seconds", STARTING_TIMEBANK_DEFAULT_SECONDS))),
        )
        room.players[player.player_id] = player
        return player

    def assign_new_creator_if_needed(self, room: Room) -> None:
        """Transfer room creator/admin if the current creator token no longer belongs to a human player."""
        if room.creator_token and self.player_by_token(room, room.creator_token):
            return

        # Prefer connected human players. Bots should never become room admins.
        for p in room.seated_players():
            if p.player_id not in self.bots and p.connected:
                room.creator_token = p.token
                return

        # Fallback to any remaining human, even if currently disconnected.
        for p in room.seated_players():
            if p.player_id not in self.bots:
                room.creator_token = p.token
                return

        room.creator_token = ""


    def get_room_and_player(self, payload: dict[str, Any]) -> tuple[Optional[Room], Optional[Player]]:
        room_id = str(payload.get("room_id", "")).strip().upper()
        token = str(payload.get("token", "")).strip()
        room = self.rooms.get(room_id)
        if not room:
            return None, None
        return room, self.player_by_token(room, token)

    def player_by_token(self, room: Room, token: str) -> Optional[Player]:
        for p in room.players.values():
            if p.token == token:
                return p
        return None

    def find_free_seat(self, room: Room) -> Optional[int]:
        occupied = {p.seat for p in room.players.values()}
        for seat in range(1, MAX_SEATS + 1):
            if seat not in occupied:
                return seat
        return None

    def evict_disconnected(self, room: Room):
        """Remove disconnected players who aren't in an active hand."""
        in_hand = room.phase in ["preflop", "flop", "turn", "river"]
        to_remove = []
        for pid, p in room.players.items():
            if not p.connected and p.ws is None:
                # Don't evict during a hand if they have cards (they might reconnect)
                if in_hand and p.cards and not p.folded:
                    continue
                to_remove.append(pid)
        for pid in to_remove:
            del room.players[pid]
        if to_remove:
            self.assign_new_creator_if_needed(room)

    def _evict_stale(self, room: Room):
        """Remove players disconnected for more than 120 seconds (if not in active hand)."""
        import time
        now = time.time()
        in_hand = room.phase in ["preflop", "flop", "turn", "river"]
        to_remove = []
        for pid, p in room.players.items():
            # Never evict bots
            if pid in self.bots:
                continue
            if not p.connected and p.ws is None and p.disconnected_at > 0:
                elapsed = now - p.disconnected_at
                if elapsed > 120:  # 2 minutes before eviction
                    # Don't evict if in hand with live cards
                    if in_hand and p.cards and not p.folded:
                        continue
                    to_remove.append(pid)
        for pid in to_remove:
            print(f"[EVICT] Removing stale player {room.players[pid].name} from room {room.room_id}")
            del room.players[pid]
        if to_remove:
            self.assign_new_creator_if_needed(room)
        # If room is now empty, remove it
        if not room.players:
            self._cancel_auto_deal_for_room_id(room.room_id)
            self._cancel_action_timer_for_room_id(room.room_id)
            self.rooms.pop(room.room_id, None)

    async def chat(self, room: Room, player: Player, text: Any):
        if _append_room_message(room, player.name, text):
            await self.broadcast(room)


    async def add_bot(self, room: Room, style: Optional[str] = None, difficulty: Optional[str] = None):
        """Add an AI bot player to the room."""
        import asyncio

        print(f"[BOT] Adding bot to room {room.room_id}, style={style}, difficulty={difficulty}")

        if self.find_free_seat(room) is None:
            self.evict_disconnected(room)
            if self.find_free_seat(room) is None:
                print(f"[BOT] No free seat in room {room.room_id}")
                return  # Room full

        valid_difficulties = ["easy", "medium", "hard", "expert"]
        if difficulty not in valid_difficulties:
            difficulty = random.choice(["medium", "hard", "expert"])
        config = create_bot_config(style, use_advanced_ai=True, difficulty=difficulty)
        seat = self.find_free_seat(room)
        if seat is None:
            print(f"[BOT] No free seat after eviction")
            return

        bot_player = Player(
            player_id=make_id(10),
            token=secrets.token_urlsafe(24),
            name=config.name,
            seat=seat,
            ws=None,  # Bots have no WebSocket
            connected=True,
            stack=STARTING_STACK,
            avatar=config.avatar,
            timebank_seconds=0,
        )
        room.players[bot_player.player_id] = bot_player
        self.bots[bot_player.player_id] = config

        print(f"[BOT] Added {config.name} ({config.style}) at seat {seat}")

        await self.broadcast(room)

        # Start bot loop for this room if not already running
        if room.room_id not in self._bot_task_running:
            self._bot_task_running.add(room.room_id)
            asyncio.create_task(self._bot_loop(room.room_id))
            print(f"[BOT] Started bot loop for room {room.room_id}")

    async def remove_bot(self, room: Room):
        """Remove the last bot from the room."""
        bot_ids = [pid for pid in room.players if pid in self.bots]
        if not bot_ids:
            return

        # Remove the last one added
        pid = bot_ids[-1]
        player = room.players[pid]

        # If bot is in a hand, fold them
        if player.cards and not player.folded and room.phase in ["preflop", "flop", "turn", "river"]:
            player.folded = True
            player.acted = True
            if room.action_seat == player.seat:
                await self.after_action(room)

        del room.players[pid]
        del self.bots[pid]
        await self.broadcast(room)

    async def _bot_loop(self, room_id: str):
        """Background loop that makes bots act when it's their turn."""
        import asyncio
        import random
        from poker.odds import calculate_equity_hybrid
        from poker.terminology import classify_hand as _classify_hand

        # Initialize the bot loop event for this room (set = idle/not processing)
        if room_id not in self._bot_loop_active:
            self._bot_loop_active[room_id] = asyncio.Event()
        self._bot_loop_active[room_id].set()  # Start as idle

        try:
            while True:
                await asyncio.sleep(1)

                room = self.rooms.get(room_id)
                if not room:
                    break

                # Check if any bot has action
                if room.action_seat is None:
                    # No bot acting — ensure event is set (idle)
                    self._bot_loop_active[room_id].set()
                    continue
                if room.phase not in ["preflop", "flop", "turn", "river"]:
                    # Not in a betting phase — ensure event is set (idle)
                    self._bot_loop_active[room_id].set()
                    continue

                action_player = self.player_by_seat(room, room.action_seat)
                if not action_player:
                    self._bot_loop_active[room_id].set()
                    continue

                # Safety: detect stuck state where action_seat points to ineligible player
                if action_player.folded or action_player.all_in or action_player.stack <= 0:
                    print(f"  [BOT_LOOP SAFETY] action_seat={room.action_seat} is ineligible "
                          f"(folded={action_player.folded} all_in={action_player.all_in}), auto-advancing...")
                    room.action_seat = self.next_action_seat_after(room, room.action_seat)
                    if room.action_seat is None:
                        # No one can act — force advance phase
                        await self.after_action(room)
                    else:
                        await self.broadcast(room)
                    continue

                if action_player.player_id not in self.bots:
                    # It's a human's turn — bot loop is idle
                    self._bot_loop_active[room_id].set()
                    continue

                # Bot is about to act — clear event (mark as active/processing)
                self._bot_loop_active[room_id].clear()

                # It's a bot's turn — calculate context-aware think time
                config = self.bots[action_player.player_id]

                # Lightweight think time: avoid expensive equity calc just for timing.
                # Use a simple heuristic based on to_call and phase instead.
                to_call = max(0, room.current_bet - action_player.committed)
                is_nuts = False  # Not worth computing just for think_time

                # Quick equity estimate only for preflop (instant lookup) or skip
                if room.phase == "preflop":
                    try:
                        eq_result = calculate_equity_hybrid(
                            action_player.cards, room.community, 1
                        )
                        equity = eq_result["equity"]
                    except Exception:
                        equity = 0.5
                else:
                    equity = 0.5  # Placeholder — real equity computed in bot_decide

                # Context-aware think time
                think_time = calculate_think_time(config, equity, is_nuts, to_call)
                await asyncio.sleep(think_time)

                # Re-check state (might have changed during think time)
                room = self.rooms.get(room_id)
                if not room or room.action_seat != action_player.seat:
                    # State changed — set event back to idle
                    if room_id in self._bot_loop_active:
                        self._bot_loop_active[room_id].set()
                    continue

                # Snapshot state before action for trash talk detection
                winners_before = list(room.winners)
                pot_before = room.pot

                # Make decision
                try:
                    action_name, extras = await bot_decide(action_player, room, config)
                    
                    # Log bot decision with AI debug info
                    debug = getattr(config, '_last_debug', {})
                    committed_before = action_player.committed
                    to_call_amount = max(0, room.current_bet - action_player.committed)
                    if action_name == "fold":
                        will_be_all_in = False
                    elif action_name == "check_call":
                        will_be_all_in = action_player.stack <= to_call_amount
                    elif action_name == "bet_raise":
                        will_be_all_in = extras.get("amount", 0) >= action_player.committed + action_player.stack
                    else:
                        will_be_all_in = False
                    room.action_log.append({
                        "player": config.name,
                        "is_bot": True,
                        "phase": room.phase,
                        "hole_cards": list(action_player.cards),
                        "community": list(room.community),
                        "pot": room.pot,
                        "current_bet": room.current_bet,
                        "committed": action_player.committed,
                        "committed_before": committed_before,
                        "stack": action_player.stack,
                        "to_call": max(0, room.current_bet - action_player.committed),
                        "action": action_name,
                        "amount": extras.get("amount", 0) if action_name == "bet_raise" else to_call_amount if action_name == "check_call" else 0,
                        "ai_debug": debug,
                        "is_all_in": will_be_all_in,
                    })
                    
                    payload = {"action": action_name, "room_id": room_id,
                               "token": action_player.token, **extras}
                    await self.player_action(room, action_player, action_name, payload)
                except Exception:
                    # Fallback: just check/call
                    fallback_to_call = max(0, room.current_bet - action_player.committed)
                    room.action_log.append({
                        "player": config.name,
                        "is_bot": True,
                        "phase": room.phase,
                        "action": "check_call",
                        "amount": fallback_to_call,
                        "committed_before": action_player.committed,
                        "note": "exception fallback",
                        "is_all_in": action_player.stack <= fallback_to_call,
                    })
                    await self.player_action(room, action_player, "check_call", {})

                # Bot action complete — set event (idle) after acting
                self._bot_loop_active[room_id].set()

                # Check if there's a pending start_hand request to process
                if self._pending_start_hand.get(room_id, False):
                    room = self.rooms.get(room_id)
                    if room and room.phase in ["showdown", "lobby"]:
                        self._pending_start_hand[room_id] = False
                        await self.start_hand(room)

                # ─── Trash talk detection (after action) ───
                # Re-fetch room state after action
                room = self.rooms.get(room_id)
                if not room:
                    break

                # Once-per-hand check using config
                current_hand = room.hands_played
                if config.last_trash_talk_hand == current_hand:
                    continue

                trash_event = None

                # Check for bluff_success: bot won without showdown and had weak equity
                if (room.winners and not winners_before and
                        len(room.winners) == 1 and
                        room.winners[0].player_id == action_player.player_id and
                        room.winners[0].reason == "Everyone else folded" and
                        equity < 0.30):
                    trash_event = TrashTalkEvent(
                        event_type="bluff_success",
                        bot_style=config.style,
                        bot_name=config.name,
                        pot_size=room.winners[0].amount,
                        equity_at_showdown=equity,
                        hand_number=current_hand,
                    )
                # Check for win_pot: bot won a pot (any method)
                elif (room.winners and not winners_before and
                      any(w.player_id == action_player.player_id for w in room.winners)):
                    trash_event = TrashTalkEvent(
                        event_type="win_pot",
                        bot_style=config.style,
                        bot_name=config.name,
                        pot_size=sum(w.amount for w in room.winners
                                     if w.player_id == action_player.player_id),
                        equity_at_showdown=equity,
                        hand_number=current_hand,
                    )
                # Check for lose_big: bot lost a large pot (> 25% of starting stack)
                elif (room.winners and not winners_before and
                      not any(w.player_id == action_player.player_id for w in room.winners)):
                    starting_stack = room.big_blind * 100
                    pot_lost = pot_before
                    if pot_lost > starting_stack * 0.25:
                        trash_event = TrashTalkEvent(
                            event_type="lose_big",
                            bot_style=config.style,
                            bot_name=config.name,
                            pot_size=pot_lost,
                            equity_at_showdown=equity,
                            hand_number=current_hand,
                        )

                # Send trash talk if event detected
                if trash_event:
                    message = get_trash_talk(trash_event)
                    if message:
                        config.last_trash_talk_hand = current_hand
                        # Delay 1-3 seconds before sending
                        await asyncio.sleep(random.uniform(DELAY_RANGE[0], DELAY_RANGE[1]))
                        # Add message to room and broadcast
                        room = self.rooms.get(room_id)
                        if room:
                            room.messages.append(ChatMessage(
                                name=config.name,
                                text=message,
                            ))
                            await self.broadcast(room)

        finally:
            # On exit, check for pending start_hand before cleaning up
            if self._pending_start_hand.get(room_id, False):
                room = self.rooms.get(room_id)
                if room:
                    self._pending_start_hand[room_id] = False
                    try:
                        await self.start_hand(room)
                    except Exception:
                        pass  # Room may have been destroyed
            # Clean up state
            self._bot_task_running.discard(room_id)
            self._bot_loop_active.pop(room_id, None)
            self._pending_start_hand.pop(room_id, None)


    def _cancel_auto_deal_for_room_id(self, room_id: str) -> None:
        task = self._auto_deal_tasks.pop(room_id, None)
        if task and not task.done():
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if task is not current:
                task.cancel()

        room = self.rooms.get(room_id)
        if room:
            room.auto_deal_started_at = 0.0
            room.auto_deal_hand_number = 0

    def _cancel_auto_deal(self, room: Room) -> None:
        self._cancel_auto_deal_for_room_id(room.room_id)

    def _cancel_action_timer_for_room_id(self, room_id: str) -> None:
        task = self._action_timer_tasks.pop(room_id, None)
        if task and not task.done():
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if task is not current:
                task.cancel()

        room = self.rooms.get(room_id)
        if room:
            room.action_timer_started_at = 0.0
            room.action_timer_player_id = ""
            room.action_timer_generation += 1

    def _cancel_action_timer(self, room: Room) -> None:
        self._cancel_action_timer_for_room_id(room.room_id)

    def _action_timer_player(self, room: Room) -> Optional[Player]:
        if room.phase not in ("preflop", "flop", "turn", "river"):
            return None
        if room.paused or room.action_seat is None:
            return None

        player = self.player_by_seat(room, room.action_seat)
        if not player:
            return None
        if player.player_id in self.bots:
            return None
        if player.folded or player.all_in or player.stack <= 0:
            return None
        if not player.cards or player.is_spectator:
            return None
        return player

    def _action_timer_total_seconds_for_player(self, room: Room, player: Player) -> int:
        action_seconds = max(1, int(getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)))
        timebank = max(0, int(getattr(player, "timebank_seconds", 0)))
        return action_seconds + timebank

    def action_timer_remaining_seconds(self, room: Room) -> int:
        if not getattr(room, "action_timer_started_at", 0.0):
            return 0

        player = self._action_timer_player(room)
        if not player or player.player_id != getattr(room, "action_timer_player_id", ""):
            return 0

        total = self._action_timer_total_seconds_for_player(room, player)
        elapsed = time_module.time() - float(room.action_timer_started_at)
        remaining = max(0.0, total - elapsed)
        return int(remaining + 0.999)

    def _action_timer_elapsed_seconds(self, room: Room) -> float:
        if not getattr(room, "action_timer_started_at", 0.0):
            return 0.0
        return max(0.0, time_module.time() - float(room.action_timer_started_at))

    def action_timer_regular_remaining_seconds(self, room: Room) -> int:
        player = self._action_timer_player(room)
        if not player or player.player_id != getattr(room, "action_timer_player_id", ""):
            return 0

        action_seconds = max(1, int(getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)))
        remaining = max(0.0, action_seconds - self._action_timer_elapsed_seconds(room))
        return int(remaining + 0.999)

    def action_timer_using_timebank(self, room: Room) -> bool:
        player = self._action_timer_player(room)
        if not player or player.player_id != getattr(room, "action_timer_player_id", ""):
            return False

        action_seconds = max(1, int(getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)))
        return self._action_timer_elapsed_seconds(room) >= action_seconds

    def displayed_timebank_seconds(self, room: Room, player: Player) -> int:
        stored = max(0, int(getattr(player, "timebank_seconds", 0)))

        if player.player_id != getattr(room, "action_timer_player_id", ""):
            return stored
        if not getattr(room, "action_timer_started_at", 0.0):
            return stored
        if player != self._action_timer_player(room):
            return stored

        action_seconds = max(1, int(getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)))
        overage = max(0, int((self._action_timer_elapsed_seconds(room) - action_seconds) + 0.999))
        return max(0, stored - overage)

    def action_timer_timebank_remaining_seconds(self, room: Room) -> int:
        player = self._action_timer_player(room)
        if not player or player.player_id != getattr(room, "action_timer_player_id", ""):
            return 0
        return self.displayed_timebank_seconds(room, player)

    def _consume_action_timebank_for_player(self, room: Room, player: Player) -> None:
        if player.player_id != getattr(room, "action_timer_player_id", ""):
            return
        if not getattr(room, "action_timer_started_at", 0.0):
            return

        action_seconds = max(1, int(getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS)))
        elapsed = time_module.time() - float(room.action_timer_started_at)
        overage = max(0, int((elapsed - action_seconds) + 0.999))
        if overage:
            player.timebank_seconds = max(0, int(getattr(player, "timebank_seconds", 0)) - overage)

    def _ensure_action_timer(self, room: Room) -> None:
        player = self._action_timer_player(room)
        if not player:
            self._cancel_action_timer(room)
            return

        room_id = room.room_id
        existing = self._action_timer_tasks.get(room_id)
        if (
            existing
            and not existing.done()
            and room.action_timer_player_id == player.player_id
            and getattr(room, "action_timer_started_at", 0.0) > 0
        ):
            return

        self._cancel_action_timer(room)
        room.action_timer_started_at = time_module.time()
        room.action_timer_player_id = player.player_id
        generation = room.action_timer_generation
        self._action_timer_tasks[room_id] = asyncio.create_task(
            self._action_timer_countdown(room_id, generation, player.player_id)
        )

    async def _action_timer_countdown(self, room_id: str, generation: int, player_id: str) -> None:
        try:
            while True:
                room = self.rooms.get(room_id)
                if not room:
                    return
                if room.action_timer_generation != generation:
                    return

                player = self._action_timer_player(room)
                if not player or player.player_id != player_id:
                    return

                remaining = self.action_timer_remaining_seconds(room)
                await self.broadcast(room)
                if remaining <= 0:
                    break

                await asyncio.sleep(min(1.0, float(remaining)))

            room = self.rooms.get(room_id)
            if room and room.action_timer_generation == generation:
                await self._apply_action_timeout(room, player_id, generation)
        finally:
            task = self._action_timer_tasks.get(room_id)
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if task is current:
                self._action_timer_tasks.pop(room_id, None)

    async def _apply_action_timeout(self, room: Room, player_id: str, generation: int) -> None:
        player = room.players.get(player_id)
        if not player or room.action_timer_generation != generation:
            return
        if player != self._action_timer_player(room):
            return

        to_call = max(0, room.current_bet - player.committed)
        action = "timeout_fold" if to_call > 0 else "timeout_check"
        player.timebank_seconds = 0
        committed_before = player.committed

        if to_call > 0:
            player.folded = True
            amount = 0
        else:
            amount = 0

        player.acted = True
        room.action_log.append({
            "player": player.name,
            "is_bot": False,
            "phase": room.phase,
            "pot": room.pot,
            "current_bet": room.current_bet,
            "committed": player.committed,
            "committed_before": committed_before,
            "stack": player.stack,
            "action": action,
            "amount": amount,
            "is_all_in": player.all_in,
        })

        self._cancel_action_timer(room)
        await self.after_action(room)

    def _auto_deal_can_run(self, room: Room) -> bool:
        if not getattr(room, "auto_deal_enabled", True):
            return False
        if room.paused:
            return False
        if room.phase != "showdown" or not room.winners:
            return False

        eligible = [
            p for p in room.seated_players()
            if p.stack > 0 and not p.sitting_out and not p.is_spectator
        ]
        return len(eligible) >= 2

    def auto_deal_remaining_seconds(self, room: Room) -> int:
        if not getattr(room, "auto_deal_started_at", 0.0):
            return 0

        delay = max(1, int(getattr(room, "auto_deal_delay_seconds", AUTO_DEAL_DEFAULT_DELAY_SECONDS)))
        elapsed = time_module.time() - float(room.auto_deal_started_at)
        remaining = max(0.0, delay - elapsed)
        return int(remaining + 0.999)

    def _ensure_auto_deal(self, room: Room) -> None:
        if not self._auto_deal_can_run(room):
            self._cancel_auto_deal(room)
            return

        room_id = room.room_id
        hand_number = room.hands_played
        existing = self._auto_deal_tasks.get(room_id)

        if (
            existing
            and not existing.done()
            and room.auto_deal_hand_number == hand_number
            and getattr(room, "auto_deal_started_at", 0.0) > 0
        ):
            return

        self._cancel_auto_deal(room)
        room.auto_deal_started_at = time_module.time()
        room.auto_deal_hand_number = hand_number
        self._auto_deal_tasks[room_id] = asyncio.create_task(
            self._auto_deal_countdown(room_id, hand_number)
        )

    async def _auto_deal_countdown(self, room_id: str, hand_number: int) -> None:
        try:
            while True:
                room = self.rooms.get(room_id)
                if not room:
                    return
                if room.auto_deal_hand_number != hand_number:
                    return
                if not self._auto_deal_can_run(room):
                    return

                await self.broadcast(room)

                remaining = self.auto_deal_remaining_seconds(room)
                if remaining <= 0:
                    break

                await asyncio.sleep(min(1.0, float(remaining)))

            room = self.rooms.get(room_id)
            if (
                room
                and room.auto_deal_hand_number == hand_number
                and self._auto_deal_can_run(room)
            ):
                await self.start_hand(room)
        finally:
            self._auto_deal_tasks.pop(room_id, None)

    async def player_action(self, room: Room, player: Player, action: str, payload: dict[str, Any]):
        print(f"[ACTION] {player.name} (seat {player.seat}) -> {action} | phase={room.phase} action_seat={room.action_seat} current_bet={room.current_bet} committed={player.committed} stack={player.stack}")

        if action == "start_hand":
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can deal the next hand."})
                return

            if room.paused:
                await self.send(player.ws, "error", {"message": "Game is paused."})
                return

            room_id = room.room_id

            # Check if bot loop is currently active (processing actions)
            bot_event = self._bot_loop_active.get(room_id)
            if bot_event and not bot_event.is_set():
                # Bots still processing — queue the start_hand and return silently
                self._pending_start_hand[room_id] = True
                return

            # Bot loop is idle (or no bots) — proceed with start_hand
            try:
                await self.start_hand(room)
                self._pending_start_hand.pop(room_id, None)
            except Exception:
                # Race condition: stale state — wait for bot loop to finish, then retry once
                bot_event = self._bot_loop_active.get(room_id)
                if bot_event:
                    try:
                        await asyncio.wait_for(bot_event.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                    # Retry once after bot loop signals completion
                    room = self.rooms.get(room_id)
                    if room:
                        try:
                            await self.start_hand(room)
                        except Exception:
                            pass  # Give up after one retry
                self._pending_start_hand.pop(room_id, None)
            return

        if action == "reset_stacks":
            if room.phase != "lobby" and room.phase != "showdown":
                await self.send(player.ws, "error", {"message": "Reset stacks between hands only."})
                return
            for p in room.players.values():
                if not p.is_spectator:
                    p.stack = STARTING_STACK
            room.phase = "lobby"
            room.pot = 0
            room.community = []
            room.winners = []
            self._cancel_auto_deal(room)
            self._cancel_action_timer(room)
            await self.broadcast(room)
            return

        if action == "sit_out":
            player.sitting_out = not player.sitting_out
            await self.broadcast(room)
            return

        if action == "toggle_pause":
            # Only admin can pause
            if player.token == room.creator_token:
                room.paused = not room.paused
                await self.broadcast(room)
            else:
                await self.send(player.ws, "error", {"message": "Only the room creator can pause."})
            return

        if action == "toggle_auto_deal":
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can change auto-deal."})
                return

            room.auto_deal_enabled = _parse_bool_setting(
                payload.get("enabled", not getattr(room, "auto_deal_enabled", True)),
                default=not getattr(room, "auto_deal_enabled", True),
            )

            if not room.auto_deal_enabled:
                self._cancel_auto_deal(room)

            await self.broadcast(room)
            return

        if action == "spectate":
            # Toggle spectator mode (only between hands)
            if room.phase not in ["lobby", "showdown"]:
                await self.send(player.ws, "error", {"message": "Can only toggle spectate between hands."})
                return
            player.is_spectator = not player.is_spectator
            if player.is_spectator:
                player.stack = 0
                player.cards = []
            else:
                player.stack = STARTING_STACK
            await self.broadcast(room)
            return

        if action == "set_avatar":
            avatar = str(payload.get("avatar", "🎭"))[:4]
            player.avatar = avatar
            await self.broadcast(room)
            return

        if action == "add_bot":
            print(f"  [ADD_BOT] player.token={player.token[:8]}... creator_token={room.creator_token[:8]}... match={player.token == room.creator_token}")
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can manage bots."})
                return
            style = payload.get("style", None)
            difficulty = payload.get("difficulty", None)
            await self.add_bot(room, style, difficulty)
            return

        if action == "remove_bot":
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can manage bots."})
                return
            await self.remove_bot(room)
            return

        if action == "transfer_admin":
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can transfer admin."})
                return

            target_player_id = str(payload.get("target_player_id", "")).strip()
            target = room.players.get(target_player_id)
            if not target:
                await self.send(player.ws, "error", {"message": "Target player not found."})
                return

            if target.player_id in self.bots:
                await self.send(player.ws, "error", {"message": "Bots cannot become table admin."})
                return

            room.creator_token = target.token
            _append_room_message(room, "Admin", f"{player.name} made {target.name} table admin.")
            await self.broadcast(room)
            return

        if action == "kick_player":
            if player.token != room.creator_token:
                await self.send(player.ws, "error", {"message": "Only the room creator can remove players."})
                return

            if room.phase not in ["lobby", "showdown"]:
                await self.send(player.ws, "error", {"message": "Kick players between hands only."})
                return

            target_player_id = str(payload.get("target_player_id", "")).strip()
            target = room.players.get(target_player_id)
            if not target:
                await self.send(player.ws, "error", {"message": "Target player not found."})
                return

            if target.player_id == player.player_id:
                await self.send(player.ws, "error", {"message": "You cannot kick yourself."})
                return

            if target.token == room.creator_token:
                await self.send(player.ws, "error", {"message": "The current table admin cannot be kicked."})
                return

            if target.ws is not None:
                await self.send(target.ws, "left", {"reason": "You were removed from the table by the admin."})

            room.players.pop(target.player_id, None)
            self.bots.pop(target.player_id, None)
            self.assign_new_creator_if_needed(room)
            _append_room_message(room, "Admin", f"{player.name} removed {target.name} from the table.")
            await self.broadcast(room)
            return

        if action == "reveal_folded_hand":
            await self.reveal_folded_hand(room, player, payload)
            return

        if action == "reveal_uncontested_hand":
            await self.reveal_uncontested_hand(room, player, payload)
            return

        if room.phase not in ["preflop", "flop", "turn", "river"]:
            print(f"  -> REJECTED: no betting in phase {room.phase}")
            await self.send(player.ws, "error", {"message": "No betting action is currently available."})
            return

        if room.paused:
            print("  -> REJECTED: game is paused")
            await self.send(player.ws, "error", {"message": "Game is paused."})
            return

        if player.is_spectator:
            print(f"  -> REJECTED: spectator cannot act ({player.name})")
            await self.send(player.ws, "error", {"message": "Spectators cannot act."})
            if room.action_seat == player.seat:
                room.action_seat = self.next_action_seat_after(room, room.action_seat)
                await self.broadcast(room)
            return

        if player.sitting_out and not player.cards:
            print(f"  -> REJECTED: sitting-out player cannot act without live cards ({player.name})")
            await self.send(player.ws, "error", {"message": "Sitting-out players cannot act until they sit in."})
            if room.action_seat == player.seat:
                room.action_seat = self.next_action_seat_after(room, room.action_seat)
                await self.broadcast(room)
            return

        if room.action_seat != player.seat:
            print(f"  -> REJECTED: not your turn (action_seat={room.action_seat}, your seat={player.seat})")
            await self.send(player.ws, "error", {"message": "It is not your turn."})
            return

        if player.folded or player.all_in:
            print(f"  -> REJECTED: folded={player.folded} all_in={player.all_in}")
            # Safety: if action_seat is stuck on this player, advance past them
            if room.action_seat == player.seat:
                print(f"  [SAFETY] action_seat stuck on ineligible player {player.name}, advancing...")
                room.action_seat = self.next_action_seat_after(room, room.action_seat)
                await self.broadcast(room)
            else:
                await self.send(player.ws, "error", {"message": "You cannot act right now."})
            return

        committed_before = player.committed

        if action == "fold":
            self._consume_action_timebank_for_player(room, player)
            self._cancel_action_timer(room)
            player.folded = True
            player.acted = True
            print(f"  -> FOLD by {player.name}")

        elif action == "check_call":
            self._consume_action_timebank_for_player(room, player)
            self._cancel_action_timer(room)
            to_call = max(0, room.current_bet - player.committed)
            # If player can't cover the full call, they go all-in
            call_amount = min(to_call, player.stack)
            print(f"  -> CHECK/CALL by {player.name}: to_call={to_call} call_amount={call_amount}")
            self.commit_chips(room, player, call_amount)
            player.acted = True

        elif action == "bet_raise":
            # "amount" from the client is the TOTAL the player wants to commit
            # (i.e. "raise to X" semantics)
            raise_to = _parse_non_negative_int_amount(payload.get("amount", 0))
            if raise_to is None:
                await self.send(player.ws, "error", {"message": "Invalid raise amount."})
                return

            # Player's maximum possible total = what they've already committed + their stack
            max_total = player.committed + player.stack

            # Minimum legal raise total
            min_raise_total = room.current_bet + room.min_raise

            # If the player is going all-in, allow it even if below min raise (short all-in)
            if raise_to >= max_total:
                # All-in: always allowed
                raise_to = max_total
            elif raise_to < min_raise_total:
                # Not a valid raise (not all-in and below minimum)
                await self.send(player.ws, "error", {
                    "message": f"Minimum raise is to {min_raise_total}. You tried {raise_to}."
                })
                return

            # How many more chips this player needs to put in
            needed = raise_to - player.committed
            if needed <= 0:
                await self.send(player.ws, "error", {"message": "Raise amount too small."})
                return

            self._consume_action_timebank_for_player(room, player)
            self._cancel_action_timer(room)

            # Calculate the raise increment (for min_raise tracking)
            raise_increment = raise_to - room.current_bet

            # Commit the chips
            self.commit_chips(room, player, needed)

            # Update room state
            is_full_raise = raise_increment >= room.min_raise

            room.current_bet = max(room.current_bet, player.committed)

            if is_full_raise:
                room.min_raise = raise_increment
                # Full raise reopens action for all other players
                for p in room.players.values():
                    if p != player:
                        p.acted = False

            player.acted = True

        else:
            await self.send(player.ws, "error", {"message": f"Unknown action: {action}"})
            return

        # Log human actions (bot actions are logged in bot_loop)
        if player.player_id not in self.bots:
            room.action_log.append({
                "player": player.name,
                "is_bot": False,
                "phase": room.phase,
                "pot": room.pot,
                "current_bet": room.current_bet,
                "committed": player.committed,
                "committed_before": committed_before,
                "stack": player.stack,
                "action": action,
                "amount": int(payload.get("amount", 0)) if action == "bet_raise" else call_amount if action == "check_call" else 0,
                "is_all_in": player.all_in,
            })

        await self.after_action(room)

    def uncontested_cards_for_viewer(self, room: Room, player: Player, viewer_token: str) -> list[str]:
        """Return visible cards for an uncontested winner's optional reveal."""
        if len(player.cards) != 2:
            return ["BACK"] * len(player.cards)

        mode = getattr(player, "uncontested_reveal_mode", "hidden")
        if player.token == viewer_token or mode == "both":
            return player.cards

        if mode == "left":
            return [player.cards[0], "BACK"]

        if mode == "right":
            return ["BACK", player.cards[1]]

        return ["BACK", "BACK"]

    def folded_cards_for_viewer(self, room: Room, player: Player, viewer_token: str) -> list[str]:
        """Return the folded player's cards as this viewer is allowed to see them.

        Critical privacy rule:
        folded cards are never sent to other players/spectators until the owner
        explicitly reveals left, right, or both after showdown.
        """
        if not player.cards:
            return []

        backs = ["BACK"] * len(player.cards)

        if not player.folded:
            return backs

        # The owner may receive their own cards. The frontend still renders the
        # public showdown row according to folded_reveal_mode.
        if player.token == viewer_token:
            return list(player.cards)

        if room.phase != "showdown":
            return backs

        if not getattr(room, "allow_folded_reveals", True):
            return backs

        if len(player.cards) != 2:
            return backs

        mode = getattr(player, "folded_reveal_mode", "hidden")
        if mode == "left":
            return [player.cards[0], "BACK"]
        if mode == "right":
            return ["BACK", player.cards[1]]
        if mode == "both":
            return list(player.cards)

        return backs

    async def reveal_folded_hand(self, room: Room, player: Player, payload: dict[str, Any]):
        """Reveal part/all of the folded player's own hand after showdown."""
        if not getattr(room, "allow_folded_reveals", True):
            await self.send(player.ws, "error", {"message": "Folded hand reveals are disabled in this room."})
            return

        if room.phase != "showdown":
            await self.send(player.ws, "error", {"message": "Folded hands can only be revealed after the hand."})
            return

        if not player.folded or len(player.cards) != 2:
            await self.send(player.ws, "error", {"message": "You do not have a folded hand to reveal."})
            return

        current = getattr(player, "folded_reveal_mode", "hidden")
        if current == "muck":
            await self.send(player.ws, "error", {"message": "This folded hand has already been mucked."})
            return

        if current == "both":
            await self.send(player.ws, "error", {"message": "This folded hand is already fully revealed."})
            return

        mode = str(payload.get("mode", "")).lower()
        if mode not in {"left", "right", "both", "muck"}:
            await self.send(player.ws, "error", {"message": "Invalid reveal mode."})
            return

        # Muck is a final hidden choice. Do not allow hiding again after a card
        # was publicly revealed.
        if mode == "muck" and current != "hidden":
            await self.send(player.ws, "error", {"message": "This folded hand has already been partially revealed."})
            return

        if mode == "left" and current == "right":
            mode = "both"
        elif mode == "right" and current == "left":
            mode = "both"

        player.folded_reveal_mode = mode
        self.refresh_latest_completed_hand(room)
        await self.broadcast(room)

    async def reveal_uncontested_hand(self, room: Room, player: Player, payload: dict[str, Any]):
        """Let an uncontested winner reveal one or both hole cards after everyone else folded."""
        if not getattr(room, "allow_folded_reveals", True):
            await self.send(player.ws, "error", {"message": "Post-hand reveals are disabled in this room."})
            return

        if room.phase != "showdown":
            await self.send(player.ws, "error", {"message": "Hands can only be revealed after the hand."})
            return

        is_uncontested_winner = any(
            w.player_id == player.player_id and w.reason == "Everyone else folded"
            for w in room.winners
        )
        if not is_uncontested_winner or player.folded or len(player.cards) != 2:
            await self.send(player.ws, "error", {"message": "You do not have an uncontested winning hand to reveal."})
            return

        mode = str(payload.get("mode", "both")).lower()
        if mode not in ("left", "right", "both"):
            await self.send(player.ws, "error", {"message": "Invalid reveal option."})
            return

        current = getattr(player, "uncontested_reveal_mode", "hidden")
        if current == "both":
            await self.send(player.ws, "error", {"message": "This hand is already fully revealed."})
            return

        if mode == "both":
            player.uncontested_reveal_mode = "both"
        elif current == "hidden":
            player.uncontested_reveal_mode = mode
        elif current != mode:
            player.uncontested_reveal_mode = "both"

        self.refresh_latest_completed_hand(room)
        await self.broadcast(room)

    def commit_chips(self, room: Room, player: Player, amount: int):
        amount = max(0, min(amount, player.stack))
        player.stack -= amount
        player.committed += amount
        player.total_invested += amount
        room.pot += amount
        if player.stack == 0:
            player.all_in = True

    def finalize_hand_deltas(self, room: Room) -> None:
        """Store each player's net result for the completed hand.

        Net result is final stack minus stack at hand start.
        This is safer than reconstructing from action logs because it naturally
        includes blinds, antes, calls, raises, returned excess, side pots,
        split pots, and odd chips.
        """
        winner_ids = {w.player_id for w in room.winners}
        deltas: dict[str, int] = {}

        for p in room.seated_players():
            if p.cards or p.total_invested > 0 or p.player_id in winner_ids:
                start_stack = int(getattr(p, "hand_start_stack", p.stack + p.total_invested))
                deltas[p.player_id] = int(p.stack) - start_stack

        room.hand_deltas = deltas

    async def start_hand(self, room: Room):
        eligible = [p for p in room.seated_players()
                    if p.stack > 0 and not p.sitting_out and not p.is_spectator]
        if len(eligible) < 2:
            for p in room.connected_players():
                await self.send(p.ws, "error", {"message": "Need at least two active players with chips."})
            return

        self._cancel_auto_deal(room)
        self._cancel_action_timer(room)
        self._odds_cache.pop(room.room_id, None)
        room.deck = new_deck()
        room.community = []
        room.pot = 0
        room.current_bet = 0
        room.min_raise = room.big_blind
        room.phase = "preflop"
        room.winners = []
        room.action_log = []
        room.hand_deltas = {}

        for p in room.players.values():
            p.hand_start_stack = p.stack
            p.cards = []
            p.folded = False
            p.folded_reveal_mode = "hidden"
            p.uncontested_reveal_mode = "hidden"
            p.all_in = False
            p.committed = 0
            p.total_invested = 0
            p.acted = False
            p.last_hand_name = ""
            p.last_best_cards = []
            p.last_hand_detail = ""

        active = [p for p in room.seated_players()
                  if p.stack > 0 and not p.sitting_out and not p.is_spectator]

        room.dealer_seat = self.next_occupied_seat(room, room.dealer_seat)
        if room.dealer_seat is None:
            room.dealer_seat = active[0].seat

        sb = self.next_player_after(room, room.dealer_seat, require_stack=True)
        bb = self.next_player_after(room, sb.seat, require_stack=True) if sb else None

        # Heads-up rule: dealer is small blind.
        if len(active) == 2:
            dealer_player = self.player_by_seat(room, room.dealer_seat)
            sb = dealer_player
            bb = self.next_player_after(room, sb.seat, require_stack=True)

        for _ in range(2):
            for p in active:
                p.cards.append(room.deck.pop())

        # Collect antes (if enabled)
        if room.ante > 0:
            if room.ante_mode == "bba":
                # Big Blind Ante: the big blind posts one big blind as the table ante.
                ante_player = bb
                if ante_player and ante_player.stack > 0:
                    bba_amount = min(room.big_blind, ante_player.stack)
                    self.commit_chips(room, ante_player, bba_amount)
                    room.action_log.append({
                        "player": ante_player.name,
                        "action": "big_blind_ante",
                        "amount": bba_amount,
                        "phase": "preflop",
                        "is_all_in": ante_player.all_in,
                    })
            else:
                # Classic ante: every player posts
                for p in active:
                    ante_amount = min(room.ante, p.stack)
                    if ante_amount > 0:
                        self.commit_chips(room, p, ante_amount)
                        room.action_log.append({
                            "player": p.name,
                            "action": "ante",
                            "amount": ante_amount,
                            "phase": "preflop",
                            "is_all_in": p.all_in,
                        })

        if sb:
            sb_amount = min(room.small_blind, sb.stack)
            self.commit_chips(room, sb, room.small_blind)
            room.sb_seat = sb.seat
            room.action_log.append({
                "player": sb.name,
                "action": "small_blind",
                "amount": sb_amount,
                "phase": "preflop",
                "is_all_in": sb.all_in,
            })
        if bb:
            bb_amount = min(room.big_blind, bb.stack)
            self.commit_chips(room, bb, room.big_blind)
            room.current_bet = bb.committed
            room.bb_seat = bb.seat
            room.action_log.append({
                "player": bb.name,
                "action": "big_blind",
                "amount": bb_amount,
                "phase": "preflop",
                "is_all_in": bb.all_in,
            })

        # Track hands played for blind progression
        room.hands_played += 1
        if room.blind_increase_hands > 0 and room.hands_played % room.blind_increase_hands == 0:
            if room.current_blind_level < len(room.blind_levels) - 1:
                room.current_blind_level += 1
                sb_val, bb_val = room.blind_levels[room.current_blind_level]
                room.small_blind = sb_val
                room.big_blind = bb_val
                room.min_raise = bb_val

                # Auto-scale ante to ~10% of new BB (if auto_ante enabled)
                if room.auto_ante and room.ante > 0:
                    room.ante = max(1, bb_val // 10)

                # Store notification for clients
                room.messages.append(ChatMessage(
                    name="⚡ Blinds Up",
                    text=f"Level {room.current_blind_level}: blinds now {sb_val}/{bb_val}"
                         + (f" (ante {room.ante})" if room.ante > 0 else ""),
                ))

        # Preflop action starts left of big blind.
        room.action_seat = self.next_action_seat_after(room, bb.seat if bb else room.dealer_seat)

        await self.after_action(room, just_started=True)

    async def after_action(self, room: Room, just_started: bool = False):
        print(f"  [AFTER_ACTION] just_started={just_started} only_one={self.only_one_remaining(room)} betting_complete={self.betting_complete(room)} action_seat={room.action_seat}")
        if self.only_one_remaining(room):
            self.award_to_last_player(room)
            await self.broadcast(room)
            return

        if just_started:
            if room.action_seat is None or self.betting_complete(room):
                self._assert_betting_valid(room, "just_started advance")
                self.return_uncalled_excess(room)
                if self.should_force_runout(room):
                    await self.runout_to_showdown(room)
                else:
                    await self.advance_phase(room)
            else:
                await self.broadcast(room)
            return

        if self.betting_complete(room):
            self._assert_betting_valid(room, "after_action advance")
            self.return_uncalled_excess(room)
            if self.should_force_runout(room):
                await self.runout_to_showdown(room)
            else:
                await self.advance_phase(room)
        else:
            room.action_seat = self.next_action_seat_after(room, room.action_seat)
            # Safety: if action_seat landed on an ineligible player (race condition),
            # keep advancing until we find a valid player or exhaust all seats.
            if room.action_seat is not None:
                p = self.player_by_seat(room, room.action_seat)
                if p and (p.folded or p.all_in or p.stack <= 0):
                    print(f"  [SAFETY] action_seat={room.action_seat} is ineligible "
                          f"(folded={p.folded} all_in={p.all_in} stack={p.stack}), advancing...")
                    room.action_seat = self.next_action_seat_after(room, room.action_seat)
            await self.broadcast(room)

    def _assert_betting_valid(self, room: Room, where: str = ""):
        """Debug invariant: betting must not complete while a live player owes chips."""
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        live = [p for p in contenders if not p.all_in and p.stack > 0]
        bad = [p for p in live if p.committed < room.current_bet]
        if bad:
            print(f"[BETTING BUG] {where}")
            print(f"  phase={room.phase} current_bet={room.current_bet} pot={room.pot}")
            for p in contenders:
                print(f"  {p.name}: stack={p.stack} committed={p.committed} "
                      f"total_invested={p.total_invested} all_in={p.all_in} "
                      f"folded={p.folded} acted={p.acted}")

    def betting_complete(self, room: Room) -> bool:
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        if len(contenders) <= 1:
            return True

        can_act = [p for p in contenders if not p.all_in and p.stack > 0]
        if not can_act:
            return True

        # Sole-actor detection: if only one player can act and all others
        # are all-in, auto-complete if that player already matches the current bet.
        # Nobody can re-raise, so giving them action is pointless.
        if len(can_act) == 1:
            sole = can_act[0]
            others = [p for p in contenders if p != sole]
            if all(p.all_in for p in others):
                # Auto-complete if sole actor matches or exceeds the bet
                if sole.committed >= room.current_bet:
                    return True

        for p in can_act:
            if not p.acted:
                return False
            if p.committed < room.current_bet:
                return False

        return True

    def only_one_remaining(self, room: Room) -> bool:
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        return len(contenders) == 1

    def players_who_can_bet(self, room: Room) -> list[Player]:
        """Return players who can still act (have cards, not folded, not all-in, have chips)."""
        return [
            p for p in room.seated_players()
            if p.cards and not p.folded and not p.all_in and p.stack > 0
        ]

    def should_force_runout(self, room: Room) -> bool:
        """Return True when fewer than 2 players can still bet (force runout)."""
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        if len(contenders) < 2:
            return False
        return len(self.players_who_can_bet(room)) < 2

    def return_uncalled_excess(self, room: Room) -> None:
        """Return unmatched chips to covering player when no one can match their bet.

        Logic:
        - Build contenders from seated players with cards who are not folded.
        - Find the non-folded contender with the highest total_invested.
        - Find the second-highest total_invested among non-folded contenders.
        - If highest.total_invested > second_highest.total_invested, the difference is uncalled excess.
        - Return that excess to the highest investor.
        - Folded players' chips stay in the pot and are never returned.
        """
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        if len(contenders) < 2:
            return

        # Find highest and second-highest total_invested among non-folded contenders
        sorted_by_invested = sorted(contenders, key=lambda p: p.total_invested)
        highest_player = sorted_by_invested[-1]
        second_highest_invested = sorted_by_invested[-2].total_invested

        excess = highest_player.total_invested - second_highest_invested
        if excess <= 0:
            return

        # Safety: uncalled excess should come from the current street
        if excess > highest_player.committed:
            raise RuntimeError(
                f"return_uncalled_excess: excess ({excess}) > highest.committed "
                f"({highest_player.committed}). This should not happen — uncalled "
                f"excess must come from the current street."
            )

        # Return excess to the highest investor
        highest_player.stack += excess
        highest_player.committed -= excess
        highest_player.total_invested -= excess
        room.pot -= excess
        highest_player.all_in = highest_player.stack == 0
        self._normalize_returned_excess_action_log(room, highest_player)

        # Recalculate room.current_bet from remaining non-folded contenders' committed values
        room.current_bet = max(p.committed for p in contenders)

    def _normalize_returned_excess_action_log(self, room: Room, player: Player) -> None:
        """Rewrite the covering player's unmatched shove as the effective call."""
        for entry in reversed(room.action_log):
            if entry.get("player") != player.name:
                continue
            if entry.get("action") != "bet_raise" or not entry.get("is_all_in"):
                return

            committed_before = entry.get("committed_before")
            if committed_before is None:
                committed_before = 0

            call_amount = max(0, player.committed - committed_before)
            entry["action"] = "check_call"
            entry["amount"] = call_amount
            entry["committed"] = player.committed
            entry["stack"] = player.stack
            entry["is_all_in"] = player.all_in
            entry["note"] = "uncalled excess returned"
            return

    def award_to_last_player(self, room: Room):
        winner = [p for p in room.seated_players() if p.cards and not p.folded][0]
        amount = room.pot
        winner.stack += amount
        room.winners = [Winner(winner.player_id, winner.name, amount, "Everyone else folded")]
        room.phase = "showdown"
        room.action_seat = None
        self.finalize_hand_deltas(room)
        self.record_completed_hand(room)
        save_hand_log(room)

    def _is_all_in_runout(self, room: Room) -> bool:
        """Check if all active players are all-in (no one can act)."""
        active = [p for p in room.players.values() if p.cards and not p.folded]
        return all(p.all_in or p.stack == 0 for p in active)

    async def runout_to_showdown(self, room: Room) -> None:
        """Deal remaining streets without action, then showdown."""
        import asyncio

        room.action_seat = None

        # No more player decisions can happen from this point. Broadcast this
        # locked state immediately so the UI can switch to showdown display mode
        # before the board finishes running out.
        await self.broadcast(room)

        # Reset per-street state
        for p in room.players.values():
            p.committed = 0
            p.acted = False
        room.current_bet = 0

        # Deal remaining streets
        phases_to_deal = []
        if room.phase == "preflop":
            phases_to_deal = ["flop", "turn", "river"]
        elif room.phase == "flop":
            phases_to_deal = ["turn", "river"]
        elif room.phase == "turn":
            phases_to_deal = ["river"]
        # If already on river, just go to showdown

        for phase_name in phases_to_deal:
            if not _SIMULATION_MODE:
                if phase_name == "flop":
                    await asyncio.sleep(1.5)
                else:
                    await asyncio.sleep(1.0)

            self.burn(room)
            if phase_name == "flop":
                room.community.extend([room.deck.pop(), room.deck.pop(), room.deck.pop()])
            else:
                room.community.append(room.deck.pop())
            room.phase = phase_name
            await self.broadcast(room)

        # Final showdown
        if not _SIMULATION_MODE:
            await asyncio.sleep(1.5)
        self.showdown(room)
        await self.broadcast(room)

    async def advance_phase(self, room: Room):
        import asyncio

        for p in room.players.values():
            p.committed = 0
            p.acted = False

        room.current_bet = 0
        room.min_raise = room.big_blind

        if room.phase == "preflop":
            self.burn(room)
            room.community.extend([room.deck.pop(), room.deck.pop(), room.deck.pop()])
            room.phase = "flop"
        elif room.phase == "flop":
            self.burn(room)
            room.community.append(room.deck.pop())
            room.phase = "turn"
        elif room.phase == "turn":
            self.burn(room)
            room.community.append(room.deck.pop())
            room.phase = "river"
        elif room.phase == "river":
            is_runout = self._is_all_in_runout(room)
            if is_runout and not _SIMULATION_MODE:
                # All-in runout: wait 2.5s after river card before showdown
                await asyncio.sleep(2.5)
            self.showdown(room)
            await self.broadcast(room)
            if is_runout and not _SIMULATION_MODE:
                # Show hands face-up for at least 2 seconds before Winner_Overlay
                await asyncio.sleep(2.0)
                await self.broadcast(room)
            return

        room.action_seat = self.next_action_seat_after(room, room.dealer_seat)

        if room.action_seat is None or self.betting_complete(room):
            # Everyone may be all-in; broadcast current state then advance with delay
            all_in_runout = self._is_all_in_runout(room)
            await self.broadcast(room)

            if not _SIMULATION_MODE:
                if all_in_runout:
                    # Dramatic pacing: 1.2s per card dealt + 0.5s buffer between streets
                    if room.phase == "flop":
                        # 3 cards × 1.2s + 0.5s buffer = 4.1s
                        await asyncio.sleep(4.1)
                    else:
                        # turn or river: 1 card × 1.2s + 0.5s buffer = 1.7s
                        await asyncio.sleep(1.7)
                else:
                    await asyncio.sleep(1.5)

            await self.advance_phase(room)
        else:
            await self.broadcast(room)

    def burn(self, room: Room):
        if room.deck:
            room.deck.pop()

    def showdown(self, room: Room):
        contenders = [p for p in room.seated_players() if p.cards and not p.folded]
        if not contenders:
            room.phase = "showdown"
            room.action_seat = None
            return

        # Evaluate all hands
        for p in contenders:
            score, name, best_cards = evaluate_7(p.cards + room.community)
            p._showdown_score = score
            p.last_hand_name = name
            p.last_best_cards = best_cards
            p.last_hand_detail = describe_hand(score, name)

        # Calculate side pots based on total_invested
        # Sort contenders by investment level
        sorted_contenders = sorted(contenders, key=lambda p: p.total_invested)

        # ALL players who invested (including folded) — needed for accurate pot calculation
        all_investors = [p for p in room.seated_players() if p.total_invested > 0]

        room.winners = []
        room.pot_breakdown = []
        already_awarded = {}  # player_id -> total amount awarded
        prev_level = 0
        remaining_pot = room.pot
        pot_index = 0

        for i, current_player in enumerate(sorted_contenders):
            current_level = current_player.total_invested
            if current_level <= prev_level:
                continue

            # Eligible players for this pot level: non-folded who invested at least current_level
            eligible = [p for p in contenders if p.total_invested >= current_level]

            # Calculate tier pot: sum each investor's actual contribution to this tier
            tier_pot = sum(
                min(p.total_invested, current_level) - prev_level
                for p in all_investors
                if p.total_invested > prev_level
            )

            if tier_pot <= 0:
                prev_level = current_level
                continue

            # Find best hand among eligible
            best_score = max(p._showdown_score for p in eligible)
            tier_winners = [p for p in eligible if p._showdown_score == best_score]

            # Split tier_pot among winners
            split = tier_pot // len(tier_winners)
            remainder = tier_pot % len(tier_winners)

            pot_tier_winners = []
            for j, w in enumerate(tier_winners):
                amount = split + (1 if j < remainder else 0)
                if w.player_id not in already_awarded:
                    already_awarded[w.player_id] = 0
                already_awarded[w.player_id] += amount
                w.stack += amount
                pot_tier_winners.append({
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": amount,
                    "hand_name": w.last_hand_name,
                })

            # Record pot breakdown for this tier
            room.pot_breakdown.append({
                "type": "main" if pot_index == 0 else "side",
                "pot": tier_pot,
                "eligible": [p.player_id for p in eligible],
                "winners": pot_tier_winners,
            })
            pot_index += 1

            remaining_pot -= tier_pot
            prev_level = current_level

        # Any remaining pot (from folded player contributions beyond max all-in)
        if remaining_pot > 0:
            best_score = max(p._showdown_score for p in contenders)
            pot_winners = [p for p in contenders if p._showdown_score == best_score]
            split = remaining_pot // len(pot_winners)
            remainder = remaining_pot % len(pot_winners)

            pot_tier_winners = []
            for j, w in enumerate(pot_winners):
                amount = split + (1 if j < remainder else 0)
                if w.player_id not in already_awarded:
                    already_awarded[w.player_id] = 0
                already_awarded[w.player_id] += amount
                w.stack += amount
                pot_tier_winners.append({
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": amount,
                    "hand_name": w.last_hand_name,
                })

            room.pot_breakdown.append({
                "type": "side" if pot_index > 0 else "main",
                "pot": remaining_pot,
                "eligible": [p.player_id for p in contenders],
                "winners": pot_tier_winners,
            })

        # Build winner list
        for pid, amount in already_awarded.items():
            p = room.players[pid]
            room.winners.append(Winner(
                player_id=p.player_id,
                name=p.name,
                amount=amount,
                reason="Best hand at showdown",
                hand_name=p.last_hand_name,
                best_cards=p.last_best_cards,
                hand_detail=p.last_hand_detail,
            ))

        self.finalize_hand_deltas(room)

        # Clean up temp attributes
        for p in contenders:
            if hasattr(p, '_showdown_score'):
                del p._showdown_score

        # Save hand log
        save_hand_log(room)

        room.phase = "showdown"
        room.action_seat = None
        self.record_completed_hand(room)

    def next_occupied_seat(self, room: Room, after_seat: Optional[int]) -> Optional[int]:
        occupied = [
            p.seat
            for p in room.seated_players()
            if p.stack > 0 and not p.sitting_out and not p.is_spectator
        ]
        if not occupied:
            return None

        if after_seat is None:
            return occupied[0]

        for offset in range(1, MAX_SEATS + 1):
            seat = ((after_seat - 1 + offset) % MAX_SEATS) + 1
            if seat in occupied:
                return seat

        return occupied[0]

    def player_by_seat(self, room: Room, seat: Optional[int]) -> Optional[Player]:
        if seat is None:
            return None
        for p in room.players.values():
            if p.seat == seat:
                return p
        return None

    def next_player_after(self, room: Room, seat: Optional[int], require_stack: bool = False) -> Optional[Player]:
        if seat is None:
            return None

        for offset in range(1, MAX_SEATS + 1):
            next_seat = ((seat - 1 + offset) % MAX_SEATS) + 1
            p = self.player_by_seat(room, next_seat)
            if not p:
                continue
            if require_stack and (p.stack <= 0 or p.sitting_out or p.is_spectator):
                continue
            return p

        return None

    def next_action_seat_after(self, room: Room, seat: Optional[int]) -> Optional[int]:
        if seat is None:
            return None

        for offset in range(1, MAX_SEATS + 1):
            next_seat = ((seat - 1 + offset) % MAX_SEATS) + 1
            p = self.player_by_seat(room, next_seat)
            if (
                p
                and p.cards
                and not p.folded
                and not p.all_in
                and p.stack > 0
                and not p.is_spectator
            ):
                return p.seat

        return None

    def _public_completed_hand_cards(self, room: Room, player: Player) -> list[str]:
        """Return the cards safe to show in a public completed-hand snapshot."""
        if not player.cards:
            return []

        backs = ["BACK"] * len(player.cards)

        if room.phase != "showdown":
            return backs

        if player.folded:
            if not getattr(room, "allow_folded_reveals", True):
                return backs
            if len(player.cards) != 2:
                return backs

            mode = getattr(player, "folded_reveal_mode", "hidden")
            if mode == "left":
                return [player.cards[0], "BACK"]
            if mode == "right":
                return ["BACK", player.cards[1]]
            if mode == "both":
                return list(player.cards)
            return backs

        real_showdown = any(
            winner.reason != "Everyone else folded"
            for winner in room.winners
        )
        if real_showdown:
            return list(player.cards)

        is_uncontested_winner = any(
            winner.player_id == player.player_id
            and winner.reason == "Everyone else folded"
            for winner in room.winners
        )
        if not is_uncontested_winner or len(player.cards) != 2:
            return backs

        mode = getattr(player, "uncontested_reveal_mode", "hidden")
        if mode == "left":
            return [player.cards[0], "BACK"]
        if mode == "right":
            return ["BACK", player.cards[1]]
        if mode == "both":
            return list(player.cards)
        return backs

    def public_hand_result(self, room: Room) -> dict[str, Any]:
        """Build a sanitized public snapshot for history/replay/share-result UI.

        This intentionally excludes reconnect tokens, WebSocket data, raw private
        hole-card fields, bot debug data, and any unrevealed cards.
        """
        sanitized_pots = []
        for tier in getattr(room, "pot_breakdown", []):
            sanitized_pots.append({
                "type": tier.get("type", ""),
                "pot": int(tier.get("pot", 0)),
                "eligible": list(tier.get("eligible", [])),
                "winners": [
                    {
                        "player_id": winner.get("player_id", ""),
                        "name": winner.get("name", ""),
                        "amount": int(winner.get("amount", 0)),
                        "hand_name": winner.get("hand_name", ""),
                    }
                    for winner in tier.get("winners", [])
                ],
            })

        players = []
        real_showdown = any(w.reason != "Everyone else folded" for w in room.winners)

        for p in room.seated_players():
            public_cards = self._public_completed_hand_cards(room, p)
            public_hole_fully_revealed = (
                len(public_cards) == 2
                and all(card != "BACK" for card in public_cards)
            )

            revealed_public_hand_name = ""
            revealed_public_hand_detail = ""
            revealed_public_best_cards: list[str] = []
            if (
                room.phase == "showdown"
                and public_hole_fully_revealed
                and len(room.community) == 5
                and len(p.cards) == 2
            ):
                try:
                    score, revealed_public_hand_name, revealed_public_best_cards = evaluate_7(p.cards + room.community)
                    revealed_public_hand_detail = describe_hand(score, revealed_public_hand_name)
                except Exception:
                    revealed_public_hand_name = ""
                    revealed_public_hand_detail = ""
                    revealed_public_best_cards = []

            is_uncontested_winner = any(
                winner.player_id == p.player_id
                and winner.reason == "Everyone else folded"
                for winner in room.winners
            )

            show_showdown_hand_detail = (
                room.phase == "showdown"
                and not p.folded
                and real_showdown
            )
            show_uncontested_public_hand_detail = (
                room.phase == "showdown"
                and not p.folded
                and is_uncontested_winner
                and public_hole_fully_revealed
                and bool(revealed_public_hand_name)
            )

            hand_name = ""
            hand_detail = ""
            best_cards: list[str] = []
            if show_showdown_hand_detail:
                hand_name = p.last_hand_name
                hand_detail = p.last_hand_detail
                best_cards = p.last_best_cards
            elif show_uncontested_public_hand_detail:
                hand_name = revealed_public_hand_name
                hand_detail = revealed_public_hand_detail
                best_cards = revealed_public_best_cards

            would_have_hand_name = ""
            would_have_hand_detail = ""
            would_have_best_cards: list[str] = []
            if (
                p.folded
                and getattr(p, "folded_reveal_mode", "hidden") == "both"
                and public_hole_fully_revealed
                and bool(revealed_public_hand_name)
            ):
                would_have_hand_name = revealed_public_hand_name
                would_have_hand_detail = revealed_public_hand_detail
                would_have_best_cards = revealed_public_best_cards

            players.append({
                "player_id": p.player_id,
                "name": p.name,
                "seat": p.seat,
                "stack": p.stack,
                "folded": p.folded,
                "all_in": p.all_in,
                "cards": display_cards(public_cards),
                "folded_reveal_mode": getattr(p, "folded_reveal_mode", "hidden") if p.folded else "",
                "uncontested_reveal_mode": getattr(p, "uncontested_reveal_mode", "hidden"),
                "can_reveal_folded_hand": False,
                "can_reveal_uncontested_hand": False,
                "would_have_hand_name": would_have_hand_name,
                "would_have_hand_detail": would_have_hand_detail,
                "would_have_best_cards": display_cards(would_have_best_cards) if would_have_best_cards else [],
                "hand_name": hand_name,
                "hand_detail": hand_detail,
                "best_cards": display_cards(best_cards) if best_cards else [],
            })

        return {
            "room_id": room.room_id,
            "hand_number": room.hands_played,
            "completed": room.phase == "showdown",
            "phase": room.phase,
            "community": display_cards(room.community),
            "pot": room.pot,
            "players": players,
            "winners": [
                {
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": w.amount,
                    "reason": w.reason,
                    "hand_name": w.hand_name,
                    "hand_detail": w.hand_detail,
                    "best_cards": display_cards(w.best_cards),
                }
                for w in room.winners
            ],
            "pot_breakdown": sanitized_pots,
            "hand_deltas": {
                p.name: getattr(room, "hand_deltas", {}).get(p.player_id, 0)
                for p in room.seated_players()
                if p.player_id in getattr(room, "hand_deltas", {})
            },
            "action_log": _sanitize_action_log(room.action_log),
        }


    def record_completed_hand(self, room: Room) -> dict[str, Any]:
        """Store a safe public completed-hand snapshot for later history/replay UI."""
        self._grant_completed_hand_timebank(room)
        snapshot = self.public_hand_result(room)

        history = getattr(room, "hand_history", None)
        if history is None:
            room.hand_history = []
            history = room.hand_history

        history.append(snapshot)
        if len(history) > HAND_HISTORY_LIMIT:
            del history[:-HAND_HISTORY_LIMIT]

        return snapshot

    def _grant_completed_hand_timebank(self, room: Room) -> None:
        hand_number = int(getattr(room, "hands_played", 0))
        if getattr(room, "timebank_awarded_hand_number", -1) == hand_number:
            return

        gain = max(0, int(getattr(room, "timebank_gain_per_hand", TIMEBANK_GAIN_DEFAULT_SECONDS)))
        if gain <= 0:
            room.timebank_awarded_hand_number = hand_number
            return

        for p in room.seated_players():
            if p.player_id not in self.bots:
                p.timebank_seconds = max(0, int(getattr(p, "timebank_seconds", 0))) + gain

        room.timebank_awarded_hand_number = hand_number

    def full_hand_history(self, room: Room) -> list[dict[str, Any]]:
        """Return full safe public snapshots for recent completed hands."""
        return list(getattr(room, "hand_history", [])[-HAND_HISTORY_LIMIT:])

    def refresh_latest_completed_hand(self, room: Room) -> dict[str, Any] | None:
        """Refresh the latest safe hand-history snapshot after post-hand reveal changes."""
        history = getattr(room, "hand_history", None)
        if not history:
            return None

        snapshot = self.public_hand_result(room)
        history[-1] = snapshot
        return snapshot

    def compact_hand_history(self, room: Room) -> list[dict[str, Any]]:
        """Return compact metadata for the recent hand-history list."""
        compact: list[dict[str, Any]] = []
        for hand in getattr(room, "hand_history", [])[-HAND_HISTORY_LIMIT:]:
            compact.append({
                "hand_number": hand.get("hand_number", 0),
                "pot": hand.get("pot", 0),
                "community": list(hand.get("community", [])),
                "winners": [
                    {
                        "player_id": winner.get("player_id", ""),
                        "name": winner.get("name", ""),
                        "amount": winner.get("amount", 0),
                        "reason": winner.get("reason", ""),
                        "hand_name": winner.get("hand_name", ""),
                    }
                    for winner in hand.get("winners", [])
                ],
            })
        return compact


    def visible_state(self, room: Room, viewer_token: str) -> dict[str, Any]:
        viewer = self.player_by_token(room, viewer_token)

        players = []
        is_spectator_viewer = viewer and viewer.is_spectator
        is_postflop = room.phase in ["flop", "turn", "river"]

        # Detect states where betting is locked and no more player decisions can happen.
        # Backend phase still tracks the runout street, but the frontend may display
        # this as showdown mode immediately.
        contenders_for_showdown_mode = [
            p for p in room.seated_players()
            if p.cards and not p.folded
        ]
        showdown_mode = (
            room.phase == "showdown"
            or (
                room.phase in ("preflop", "flop", "turn", "river")
                and room.action_seat is None
                and len(contenders_for_showdown_mode) >= 2
            )
        )
        all_in_runout = showdown_mode and room.phase != "showdown"
        uncontested_winner_ids = {
            w.player_id for w in room.winners
            if w.reason == "Everyone else folded"
        }
        real_showdown = (
            room.phase == "showdown"
            and any(w.reason != "Everyone else folded" for w in room.winners)
        )

        # Showdown display mode means betting is locked and no more player
        # decisions can happen, even if the backend is still running out board cards.
        live_contenders_for_showdown_mode = [
            p for p in room.seated_players()
            if p.cards and not p.folded
        ]
        showdown_mode = (
            room.phase == "showdown"
            or (
                room.phase in ("preflop", "flop", "turn", "river")
                and room.action_seat is None
                and len(live_contenders_for_showdown_mode) >= 2
            )
        )
        locked_runout_reveal = showdown_mode and room.phase != "showdown"

        # Compute clockwise seat offsets from dealer for active players
        seat_offsets: dict[int, int] = {}  # seat -> offset
        if room.dealer_seat is not None:
            active_seats = [
                p.seat for p in room.seated_players()
                if not p.sitting_out and not p.is_spectator
            ]
            if active_seats:
                # Build clockwise order starting from dealer
                # Seats are 1-indexed, wrap around using MAX_SEATS
                ordered: list[int] = []
                # Start from dealer seat, then proceed clockwise
                for offset in range(MAX_SEATS):
                    seat = ((room.dealer_seat - 1 + offset) % MAX_SEATS) + 1
                    if seat in active_seats:
                        ordered.append(seat)
                # Assign offsets: dealer=0, next clockwise=1, etc.
                for i, seat in enumerate(ordered):
                    seat_offsets[seat] = i

        for p in room.seated_players():
            # Card visibility:
            # - A player may always receive their own hole cards.
            # - Spectators may see live/non-folded cards as before.
            # - At showdown, reveal non-folded contenders.
            # - Folded cards are privacy-gated by folded_reveal_mode.
            #   Spectators do NOT bypass folded-card privacy.
            folded_reveal_mode = getattr(p, "folded_reveal_mode", "hidden") if p.folded else ""
            can_reveal_folded_hand = (
                bool(getattr(room, "allow_folded_reveals", True))
                and room.phase == "showdown"
                and p.folded
                and p.token == viewer_token
                and folded_reveal_mode not in ("both", "muck")
                and len(p.cards) == 2
            )
            uncontested_reveal_mode = getattr(p, "uncontested_reveal_mode", "hidden")
            can_reveal_uncontested_hand = (
                bool(getattr(room, "allow_folded_reveals", True))
                and room.phase == "showdown"
                and not p.folded
                and p.player_id in uncontested_winner_ids
                and p.token == viewer_token
                and uncontested_reveal_mode != "both"
                and len(p.cards) == 2
            )

            would_have_hand_name = ""
            would_have_hand_detail = ""
            would_have_best_cards: list[str] = []

            if p.folded:
                cards = self.folded_cards_for_viewer(room, p, viewer_token)

                if (
                    room.phase == "showdown"
                    and folded_reveal_mode == "both"
                    and len(p.cards) == 2
                    and len(room.community) == 5
                ):
                    try:
                        score, name, best_cards = evaluate_7(p.cards + room.community)
                        would_have_hand_name = name
                        would_have_hand_detail = describe_hand(score, name)
                        would_have_best_cards = best_cards
                    except Exception:
                        would_have_hand_name = ""
                        would_have_hand_detail = ""
                        would_have_best_cards = []
            else:
                has_showdown_hand = bool(p.last_hand_name)

                show_cards = (
                    p.token == viewer_token
                    or (viewer and viewer.is_spectator and room.phase != "showdown")
                    or (viewer and viewer.is_spectator and (has_showdown_hand or real_showdown or locked_runout_reveal))
                    or (room.phase == "showdown" and (has_showdown_hand or real_showdown))
                    or (locked_runout_reveal and p.cards)
                    or (p.player_id in uncontested_winner_ids and uncontested_reveal_mode == "both")
                    or all_in_runout
                )
                if p.player_id in uncontested_winner_ids and room.phase == "showdown":
                    cards = self.uncontested_cards_for_viewer(room, p, viewer_token)
                else:
                    cards = p.cards if show_cards else ["BACK"] * len(p.cards)

            to_call = max(0, room.current_bet - p.committed)

            player_dict = {
                "id": p.player_id,
                "name": p.name,
                "avatar": p.avatar,
                "seat": p.seat,
                "connected": p.connected,
                "is_bot": p.player_id in self.bots,
                "is_admin": p.token == room.creator_token,
                "bot_difficulty": self.bots[p.player_id].difficulty if p.player_id in self.bots else "",
                "stack": p.stack,
                "committed": p.committed,
                "total_invested": p.total_invested,
                "hand_delta": getattr(room, "hand_deltas", {}).get(p.player_id) if room.phase == "showdown" else None,
                "folded": p.folded,
                "folded_reveal_mode": folded_reveal_mode,
                "can_reveal_folded_hand": can_reveal_folded_hand,
                "uncontested_reveal_mode": uncontested_reveal_mode,
                "can_reveal_uncontested_hand": can_reveal_uncontested_hand,
                "would_have_hand_name": would_have_hand_name,
                "would_have_hand_detail": would_have_hand_detail,
                "would_have_best_cards": display_cards(would_have_best_cards) if would_have_best_cards else [],
                "all_in": p.all_in,
                "is_you": p.token == viewer_token,
                "is_dealer": p.seat == room.dealer_seat,
                "is_sb": p.seat == room.sb_seat,
                "is_bb": p.seat == room.bb_seat,
                "is_action": p.seat == room.action_seat,
                "timebank_seconds": self.displayed_timebank_seconds(room, p),
                "cards": display_cards(cards),
                "hand_name": p.last_hand_name if room.phase == "showdown" and not p.folded else "",
                "hand_detail": p.last_hand_detail if room.phase == "showdown" and not p.folded else "",
                "best_cards": display_cards(p.last_best_cards) if room.phase == "showdown" and not p.folded else [],
                "to_call": to_call,
                "sitting_out": p.sitting_out,
                "is_spectator": p.is_spectator,
                "seat_offset_from_dealer": seat_offsets.get(p.seat) if not p.sitting_out and not p.is_spectator else None,
            }

            # Spectator-only hand strength and equity data (postflop only)
            if is_spectator_viewer and is_postflop and not p.folded and p.cards:
                # Hand classification
                try:
                    term = classify_hand(p.cards, room.community)
                    player_dict["hand_classification"] = term.get("made_hand", "")
                except Exception:
                    pass

                # Equity calculation (with caching)
                try:
                    num_opp = len([
                        other for other in room.players.values()
                        if other.cards and not other.folded and other.token != p.token
                    ])
                    if num_opp > 0:
                        # Check cache first
                        cache_key = _odds_cache_key(room, p, num_opp)
                        room_cache = self._odds_cache.setdefault(room.room_id, {})
                        eq_result = room_cache.get(cache_key)
                        if eq_result is None:
                            eq_result = calculate_player_odds(
                                p.cards, room.community, num_opp, 150
                            )
                            room_cache[cache_key] = eq_result

                        if eq_result and eq_result.get("equity") is not None:
                            equity_pct = int(eq_result["equity"])
                            player_dict["equity_pct"] = equity_pct
                            # Equity tier color mapping
                            if equity_pct >= 65:
                                player_dict["equity_tier"] = "gold"
                            elif equity_pct >= 45:
                                player_dict["equity_tier"] = "green"
                            elif equity_pct >= 30:
                                player_dict["equity_tier"] = "blue"
                            else:
                                player_dict["equity_tier"] = "gray"
                except Exception:
                    pass

            players.append(player_dict)

        viewer_to_call = 0
        is_viewer_turn = False
        viewer_committed = 0
        viewer_stack = 0
        is_admin = False
        odds = None
        viewer_timebank = 0
        if viewer:
            viewer_to_call = max(0, room.current_bet - viewer.committed)
            is_viewer_turn = room.action_seat == viewer.seat
            viewer_committed = viewer.committed
            viewer_stack = viewer.stack
            viewer_timebank = self.displayed_timebank_seconds(room, viewer)
            is_admin = viewer.token == room.creator_token

            # Calculate odds for the viewer (only during active hand)
            if viewer.cards and not viewer.folded and room.phase in ["preflop", "flop", "turn", "river"]:
                num_opp = len([p for p in room.players.values()
                              if p.cards and not p.folded and p.token != viewer.token])
                if num_opp > 0:
                    # Check cache first
                    cache_key = _odds_cache_key(room, viewer, num_opp)
                    room_cache = self._odds_cache.setdefault(room.room_id, {})
                    odds = room_cache.get(cache_key)
                    if odds is None:
                        try:
                            odds = calculate_player_odds(
                                viewer.cards, room.community, num_opp, 200
                            )
                            room_cache[cache_key] = odds
                        except Exception:
                            odds = None

                # Hand terminology
                try:
                    term = classify_hand(viewer.cards, room.community)
                    if odds:
                        odds["made_hand"] = term.get("made_hand", "")
                        odds["draws"] = term.get("draws", [])
                        odds["nuts_rank"] = term.get("nuts_rank")
                        odds["is_nuts"] = term.get("is_nuts", False)
                    else:
                        odds = {
                            "equity": None,
                            "current_ahead": None,
                            "phase_note": "",
                            "made_hand": term.get("made_hand", ""),
                            "draws": term.get("draws", []),
                            "nuts_rank": term.get("nuts_rank"),
                            "is_nuts": term.get("is_nuts", False),
                        }
                except Exception:
                    pass

        action_timer_player_id = getattr(room, "action_timer_player_id", "")
        action_timer_player = room.players.get(action_timer_player_id) if action_timer_player_id else None
        action_timer_active = (
            bool(action_timer_player)
            and action_timer_player == self._action_timer_player(room)
            and getattr(room, "action_timer_started_at", 0.0) > 0
        )
        action_timer_total_seconds = (
            self._action_timer_total_seconds_for_player(room, action_timer_player)
            if action_timer_active and action_timer_player
            else 0
        )

        return {
            "room_id": room.room_id,
            "phase": room.phase,
            "showdown_mode": showdown_mode,
            "paused": room.paused,
            "pot": room.pot,
            "current_bet": room.current_bet,
            "min_raise": room.min_raise,
            "small_blind": room.small_blind,
            "big_blind": room.big_blind,
            "ante": room.ante,
            "ante_mode": room.ante_mode,
            "hands_played": room.hands_played,
            "blind_level": room.current_blind_level,
            "blind_increase_hands": room.blind_increase_hands,
            "allow_folded_reveals": getattr(room, "allow_folded_reveals", True),
            "auto_deal_enabled": getattr(room, "auto_deal_enabled", True),
            "auto_deal_delay_seconds": getattr(room, "auto_deal_delay_seconds", AUTO_DEAL_DEFAULT_DELAY_SECONDS),
            "auto_deal_active": (
                room.phase == "showdown"
                and bool(room.winners)
                and getattr(room, "auto_deal_enabled", True)
                and getattr(room, "auto_deal_started_at", 0.0) > 0
            ),
            "auto_deal_remaining_seconds": self.auto_deal_remaining_seconds(room),
            "action_timer_active": action_timer_active,
            "action_timer_player_id": action_timer_player_id if action_timer_active else "",
            "action_timer_remaining_seconds": self.action_timer_remaining_seconds(room) if action_timer_active else 0,
            "action_timer_regular_remaining_seconds": self.action_timer_regular_remaining_seconds(room) if action_timer_active else 0,
            "action_timer_timebank_remaining_seconds": self.action_timer_timebank_remaining_seconds(room) if action_timer_active else 0,
            "action_timer_using_timebank": self.action_timer_using_timebank(room) if action_timer_active else False,
            "action_timer_total_seconds": action_timer_total_seconds,
            "action_time_seconds": getattr(room, "action_time_seconds", ACTION_TIMER_DEFAULT_SECONDS),
            "community": display_cards(room.community),
            "players": players,
            "messages": [
                {
                    "name": m.name,
                    "text": m.text,
                    "timestamp": m.timestamp,
                }
                for m in room.messages[-MAX_CHAT_MESSAGES:]
            ],
            "winners": [
                {
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": w.amount,
                    "reason": w.reason,
                    "hand_name": w.hand_name,
                    "hand_detail": w.hand_detail,
                    "best_cards": display_cards(w.best_cards),
                }
                for w in room.winners
            ],
            "pot_breakdown": room.pot_breakdown,
            "hand_history": self.compact_hand_history(room),
            "hand_history_details": self.full_hand_history(room),
            "latest_hand_result": (
                getattr(room, "hand_history", [])[-1]
                if getattr(room, "hand_history", [])
                else None
            ),
            "hand_deltas": {
                p.name: getattr(room, "hand_deltas", {}).get(p.player_id, 0)
                for p in room.seated_players()
                if room.phase == "showdown" and p.player_id in getattr(room, "hand_deltas", {})
            },
            "action_log": _sanitize_action_log(room.action_log),
            "viewer": {
                "is_turn": is_viewer_turn,
                "to_call": viewer_to_call,
                "committed": viewer_committed,
                "stack": viewer_stack,
                "timebank_seconds": viewer_timebank,
                "is_admin": is_admin,
                "odds": odds,
            }
        }
