from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import string
from dataclasses import dataclass
from typing import Optional, Any

from fastapi import WebSocket

from poker.cards import display_cards, new_deck
from poker.evaluator import evaluate_7
from poker.logs import save_hand_log
from poker.models import ChatMessage, Player, Room, Winner
from poker.odds import calculate_player_odds
from poker.terminology import classify_hand
from poker.bot import BotConfig, create_bot_config, bot_decide, calculate_think_time
from poker.trash_talk import get_trash_talk, TrashTalkEvent, DELAY_RANGE


MAX_SEATS = 8
STARTING_STACK = 1000
_SIMULATION_MODE = os.getenv("POKER_SIMULATION") == "1"


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
            await self.chat(room, player, str(payload.get("text", "")))
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

        # Apply room settings from payload (optional)
        blind_increase = int(payload.get("blind_increase_hands", 0))
        if blind_increase > 0:
            room.blind_increase_hands = blind_increase

        ante = int(payload.get("ante", 0))
        if ante >= 0:
            room.ante = ante

        ante_mode = str(payload.get("ante_mode", "classic")).lower()
        if ante_mode in ("classic", "bba"):
            room.ante_mode = ante_mode

        auto_ante = payload.get("auto_ante", False)
        room.auto_ante = bool(auto_ante)

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

        # If room is empty, delete it
        if not room.players:
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
            name=(str(name).strip()[:24] or f"Player {seat}"),
            seat=seat,
            ws=ws,
            connected=True,
            stack=STARTING_STACK,
            avatar=avatar[:4] if avatar else "🎭",
        )
        room.players[player.player_id] = player
        return player

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
        # If room is now empty, remove it
        if not room.players:
            self.rooms.pop(room.room_id, None)

    async def chat(self, room: Room, player: Player, text: str):
        text = text.strip()
        if not text:
            return

        room.messages.append(ChatMessage(player.name, text[:240]))
        room.messages = room.messages[-50:]
        await self.broadcast(room)

    # ─── Bot Management ───

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
                if action_player.player_id not in self.bots:
                    # It's a human's turn — bot loop is idle
                    self._bot_loop_active[room_id].set()
                    continue

                # Bot is about to act — clear event (mark as active/processing)
                self._bot_loop_active[room_id].clear()

                # It's a bot's turn — calculate context-aware think time
                config = self.bots[action_player.player_id]

                # Calculate equity and is_nuts for think time (fewer sims for speed)
                num_opp = len([p for p in room.players.values()
                               if p.cards and not p.folded and p.token != action_player.token])
                if num_opp < 1:
                    num_opp = 1

                try:
                    eq_result = calculate_equity_hybrid(
                        action_player.cards, room.community, num_opp
                    )
                    equity = eq_result["equity"]
                except Exception:
                    equity = 0.5

                try:
                    hand_info = _classify_hand(action_player.cards, room.community)
                    is_nuts = hand_info.get("is_nuts", False)
                except Exception:
                    is_nuts = False

                to_call = max(0, room.current_bet - action_player.committed)

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
                    payload = {"action": action_name, "room_id": room_id,
                               "token": action_player.token, **extras}
                    await self.player_action(room, action_player, action_name, payload)
                except Exception:
                    # Fallback: just check/call
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

    async def player_action(self, room: Room, player: Player, action: str, payload: dict[str, Any]):
        print(f"[ACTION] {player.name} (seat {player.seat}) -> {action} | phase={room.phase} action_seat={room.action_seat} current_bet={room.current_bet} committed={player.committed} stack={player.stack}")

        if action == "start_hand":
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

        if room.phase not in ["preflop", "flop", "turn", "river"]:
            print(f"  -> REJECTED: no betting in phase {room.phase}")
            await self.send(player.ws, "error", {"message": "No betting action is currently available."})
            return

        if room.action_seat != player.seat:
            print(f"  -> REJECTED: not your turn (action_seat={room.action_seat}, your seat={player.seat})")
            await self.send(player.ws, "error", {"message": "It is not your turn."})
            return

        if player.folded or player.all_in:
            print(f"  -> REJECTED: folded={player.folded} all_in={player.all_in}")
            await self.send(player.ws, "error", {"message": "You cannot act right now."})
            return

        if action == "fold":
            player.folded = True
            player.acted = True
            print(f"  -> FOLD by {player.name}")

        elif action == "check_call":
            to_call = max(0, room.current_bet - player.committed)
            # If player can't cover the full call, they go all-in
            call_amount = min(to_call, player.stack)
            print(f"  -> CHECK/CALL by {player.name}: to_call={to_call} call_amount={call_amount}")
            self.commit_chips(room, player, call_amount)
            player.acted = True

        elif action == "bet_raise":
            # "amount" from the client is the TOTAL the player wants to commit
            # (i.e. "raise to X" semantics)
            raise_to = int(payload.get("amount", 0))

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

        await self.after_action(room)

    def commit_chips(self, room: Room, player: Player, amount: int):
        amount = max(0, min(amount, player.stack))
        player.stack -= amount
        player.committed += amount
        player.total_invested += amount
        room.pot += amount
        if player.stack == 0:
            player.all_in = True

    async def start_hand(self, room: Room):
        eligible = [p for p in room.seated_players()
                    if p.stack > 0 and not p.sitting_out and not p.is_spectator]
        if len(eligible) < 2:
            for p in room.connected_players():
                await self.send(p.ws, "error", {"message": "Need at least two active players with chips."})
            return

        room.deck = new_deck()
        room.community = []
        room.pot = 0
        room.current_bet = 0
        room.min_raise = room.big_blind
        room.phase = "preflop"
        room.winners = []

        for p in room.players.values():
            p.cards = []
            p.folded = False
            p.all_in = False
            p.committed = 0
            p.total_invested = 0
            p.acted = False
            p.last_hand_name = ""
            p.last_best_cards = []

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
                # Big Blind Ante: only the dealer posts 1 BB
                dealer_player = self.player_by_seat(room, room.dealer_seat)
                if dealer_player and dealer_player.stack > 0:
                    bba_amount = min(room.big_blind, dealer_player.stack)
                    self.commit_chips(room, dealer_player, bba_amount)
            else:
                # Classic ante: every player posts
                for p in active:
                    ante_amount = min(room.ante, p.stack)
                    if ante_amount > 0:
                        self.commit_chips(room, p, ante_amount)

        if sb:
            self.commit_chips(room, sb, room.small_blind)
            room.sb_seat = sb.seat
        if bb:
            self.commit_chips(room, bb, room.big_blind)
            room.current_bet = bb.committed
            room.bb_seat = bb.seat

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
                await self.advance_phase(room)
            else:
                await self.broadcast(room)
            return

        if self.betting_complete(room):
            self._assert_betting_valid(room, "after_action advance")
            await self.advance_phase(room)
        else:
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
        # are all-in, auto-complete ONLY if that player has already acted
        # and matched the current bet (they can't raise further anyway).
        # If they haven't acted yet, they still need to call/fold.
        if len(can_act) == 1:
            sole = can_act[0]
            others = [p for p in contenders if p != sole]
            if all(p.all_in for p in others):
                # Only auto-complete if sole actor has acted AND matches the bet
                if sole.acted and sole.committed >= room.current_bet:
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

    def award_to_last_player(self, room: Room):
        winner = [p for p in room.seated_players() if p.cards and not p.folded][0]
        amount = room.pot
        winner.stack += amount
        room.winners = [Winner(winner.player_id, winner.name, amount, "Everyone else folded")]
        room.phase = "showdown"
        room.action_seat = None
        save_hand_log(room)

    def _is_all_in_runout(self, room: Room) -> bool:
        """Check if all active players are all-in (no one can act)."""
        active = [p for p in room.players.values() if p.cards and not p.folded]
        return all(p.all_in or p.stack == 0 for p in active)

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
            ))

        # Clean up temp attributes
        for p in contenders:
            if hasattr(p, '_showdown_score'):
                del p._showdown_score

        # Save hand log
        save_hand_log(room)

        room.phase = "showdown"
        room.action_seat = None

    def next_occupied_seat(self, room: Room, after_seat: Optional[int]) -> Optional[int]:
        occupied = [p.seat for p in room.seated_players() if p.stack > 0]
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
            if p and (not require_stack or p.stack > 0):
                return p

        return None

    def next_action_seat_after(self, room: Room, seat: Optional[int]) -> Optional[int]:
        if seat is None:
            return None

        for offset in range(1, MAX_SEATS + 1):
            next_seat = ((seat - 1 + offset) % MAX_SEATS) + 1
            p = self.player_by_seat(room, next_seat)
            if p and p.cards and not p.folded and not p.all_in and p.stack > 0:
                return p.seat

        return None

    def visible_state(self, room: Room, viewer_token: str) -> dict[str, Any]:
        viewer = self.player_by_token(room, viewer_token)

        players = []
        is_spectator_viewer = viewer and viewer.is_spectator
        is_postflop = room.phase in ["flop", "turn", "river"]

        # Detect all-in runout: all active players are all-in (show cards to everyone)
        all_in_runout = self._is_all_in_runout(room) and room.phase in ("flop", "turn", "river")

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
            # Spectators see all cards; players see own cards + showdown + all-in runout
            show_cards = (p.token == viewer_token
                         or room.phase == "showdown"
                         or (viewer and viewer.is_spectator)
                         or (all_in_runout and p.cards and not p.folded))
            cards = p.cards if show_cards else ["BACK"] * len(p.cards)

            to_call = max(0, room.current_bet - p.committed)

            player_dict = {
                "id": p.player_id,
                "name": p.name,
                "avatar": p.avatar,
                "seat": p.seat,
                "connected": p.connected,
                "is_bot": p.player_id in self.bots,
                "stack": p.stack,
                "committed": p.committed,
                "total_invested": p.total_invested,
                "folded": p.folded,
                "all_in": p.all_in,
                "is_you": p.token == viewer_token,
                "is_dealer": p.seat == room.dealer_seat,
                "is_sb": p.seat == room.sb_seat,
                "is_bb": p.seat == room.bb_seat,
                "is_action": p.seat == room.action_seat,
                "cards": display_cards(cards),
                "hand_name": p.last_hand_name if room.phase == "showdown" else "",
                "best_cards": display_cards(p.last_best_cards) if room.phase == "showdown" else [],
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
                        cache_key = (p.token, tuple(room.community), num_opp)
                        room_cache = self._odds_cache.setdefault(room.room_id, {})
                        eq_result = room_cache.get(cache_key)
                        if eq_result is None:
                            eq_result = calculate_player_odds(
                                p.cards, room.community, num_opp, 500
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
        if viewer:
            viewer_to_call = max(0, room.current_bet - viewer.committed)
            is_viewer_turn = room.action_seat == viewer.seat
            viewer_committed = viewer.committed
            viewer_stack = viewer.stack
            is_admin = viewer.token == room.creator_token

            # Calculate odds for the viewer (only during active hand)
            if viewer.cards and not viewer.folded and room.phase in ["preflop", "flop", "turn", "river"]:
                num_opp = len([p for p in room.players.values()
                              if p.cards and not p.folded and p.token != viewer.token])
                if num_opp > 0:
                    # Check cache first
                    cache_key = (viewer.token, tuple(room.community), num_opp)
                    room_cache = self._odds_cache.setdefault(room.room_id, {})
                    odds = room_cache.get(cache_key)
                    if odds is None:
                        try:
                            odds = calculate_player_odds(
                                viewer.cards, room.community, num_opp, 500
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

        return {
            "room_id": room.room_id,
            "phase": room.phase,
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
            "community": display_cards(room.community),
            "players": players,
            "messages": [
                {
                    "name": m.name,
                    "text": m.text,
                    "timestamp": m.timestamp,
                }
                for m in room.messages[-50:]
            ],
            "winners": [
                {
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": w.amount,
                    "reason": w.reason,
                    "hand_name": w.hand_name,
                    "best_cards": display_cards(w.best_cards),
                }
                for w in room.winners
            ],
            "pot_breakdown": room.pot_breakdown,
            "viewer": {
                "is_turn": is_viewer_turn,
                "to_call": viewer_to_call,
                "committed": viewer_committed,
                "stack": viewer_stack,
                "is_admin": is_admin,
                "odds": odds,
            }
        }
