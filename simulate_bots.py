"""Headless bot-vs-bot poker simulation with random baselines.

Runs full poker hands using the real PokerServer game engine.
Includes random baseline bots (Random50, RandomSafe, RandomHumanish)
and proper zero-sum chip accounting with BB/100 as the primary metric.

Features:
  - Mixed-table scenarios (4-6 players, always 1 expert)
  - Parallel table execution via ProcessPoolExecutor
  - Per-player survival and performance stats
  - Zero-sum accounting assertions

Usage:
    python simulate_bots.py
    
    # Faster (skip delays):
    $env:POKER_SIMULATION="1"; python simulate_bots.py
"""

import asyncio
import random
import secrets
import sys
import os
import builtins
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from time import time

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from poker.bot import BotConfig, create_bot_config, bot_decide
from poker.game import PokerServer
from poker.models import Player, Room


# ─── Configuration ─────────────────────────────────────────────────────────────

STARTING_STACK = 1000
BIG_BLIND = 10
SMALL_BLIND = 5
MAX_HANDS = 500
NUM_TABLES = 20          # tables per scenario
MAX_WORKERS = max(1, os.cpu_count() - 1) if os.cpu_count() else 4

SIMULATION_MODE = os.getenv("POKER_SIMULATION") == "1"


# ─── Random Baseline Bots ─────────────────────────────────────────────────────

def random50_decide(player: Player, room: Room) -> tuple[str, dict]:
    """Random50 (Chaos Maniac): 50% check/fold, 50% random bet/raise."""
    to_call = max(0, room.current_bet - player.committed)
    can_check = to_call == 0

    if random.random() < 0.5:
        if can_check:
            return "check_call", {}
        return "fold", {}
    else:
        min_raise = room.min_raise
        max_amount = player.committed + player.stack
        if player.stack <= to_call + min_raise:
            return "bet_raise", {"amount": max_amount}
        min_bet = min(max_amount, room.current_bet + min_raise)
        amount = random.randint(min_bet, max_amount)
        return "bet_raise", {"amount": amount}


def random_safe_decide(player: Player, room: Room) -> tuple[str, dict]:
    """RandomSafe: 50% check/call, 50% min-raise."""
    if random.random() < 0.5:
        return "check_call", {}
    else:
        min_raise = room.min_raise
        max_amount = player.committed + player.stack
        amount = min(room.current_bet + min_raise, max_amount)
        return "bet_raise", {"amount": amount}


def random_humanish_decide(player: Player, room: Room) -> tuple[str, dict]:
    """RandomHumanish: simulates a weak recreational player.
    
    Distribution:
      35% check/call
      30% fold when facing bet (check if free)
      20% small bet / minraise
      10% medium raise (2-3x pot)
      5% big raise / all-in
    """
    to_call = max(0, room.current_bet - player.committed)
    can_check = to_call == 0
    min_raise = room.min_raise
    max_amount = player.committed + player.stack

    roll = random.random()

    if roll < 0.35:
        # Check/call
        return "check_call", {}
    elif roll < 0.65:
        # Fold (or check if free)
        if can_check:
            return "check_call", {}
        return "fold", {}
    elif roll < 0.85:
        # Small bet / minraise
        amount = min(room.current_bet + min_raise, max_amount)
        return "bet_raise", {"amount": amount}
    elif roll < 0.95:
        # Medium raise (2-3x pot)
        pot_mult = random.uniform(2.0, 3.0)
        amount = int(room.current_bet + room.pot * pot_mult * random.uniform(0.3, 0.6))
        amount = max(room.current_bet + min_raise, min(amount, max_amount))
        return "bet_raise", {"amount": amount}
    else:
        # Big raise / all-in
        amount = max_amount
        return "bet_raise", {"amount": amount}


RANDOM_BOTS = {
    "random50": random50_decide,
    "random_safe": random_safe_decide,
    "random_humanish": random_humanish_decide,
}


# ─── Stats ─────────────────────────────────────────────────────────────────────

@dataclass
class PlayerStats:
    name: str
    difficulty: str
    style: str
    hands_played: int = 0
    hands_won: int = 0
    final_stack: int = 0
    busted_at_hand: int = 0
    all_ins: int = 0
    net_chips: int = 0


# ─── Headless Simulation Engine ────────────────────────────────────────────────

class HeadlessSim:
    def __init__(self):
        self.server = PokerServer()
        # Patch ALL output/broadcast/state methods to no-ops
        for method_name in [
            "send", "broadcast", "broadcast_state", "send_state",
            "send_room_state", "broadcast_room_state",
        ]:
            if hasattr(self.server, method_name):
                setattr(self.server, method_name, self._noop)
        self._random_bots: dict[str, str] = {}

    async def _noop(self, *a, **kw):
        pass

    def create_room(self) -> Room:
        room_id = secrets.token_urlsafe(5)
        room = Room(room_id=room_id)
        room.big_blind = BIG_BLIND
        room.small_blind = SMALL_BLIND
        room.min_raise = BIG_BLIND
        room.creator_token = "sim"
        self.server.rooms[room_id] = room
        return room

    def add_bot(self, room: Room, difficulty: str, style: str = None, starting_stack: int = None) -> tuple[Player, BotConfig]:
        if starting_stack is None:
            starting_stack = STARTING_STACK
        is_random = difficulty == "random"
        random_style = style or "random50"

        if is_random:
            config = BotConfig(
                style=random_style,
                name=f"Fish_{random_style[:4]}_{random.randint(100,999)}",
                avatar="F", use_advanced_ai=False, difficulty="easy",
            )
        else:
            config = create_bot_config(style, use_advanced_ai=True, difficulty=difficulty)

        seat = self.server.find_free_seat(room)
        if seat is None:
            raise RuntimeError("No seat available")

        player = Player(
            player_id=secrets.token_urlsafe(8),
            token=secrets.token_urlsafe(16),
            name=config.name,
            seat=seat, ws=None, connected=True,
            stack=starting_stack, avatar=config.avatar,
        )
        room.players[player.player_id] = player
        self.server.bots[player.player_id] = config
        if is_random:
            self._random_bots[player.player_id] = random_style
        return player, config

    async def _decide(self, player: Player, room: Room, config: BotConfig) -> tuple[str, dict]:
        if player.player_id in self._random_bots:
            return RANDOM_BOTS[self._random_bots[player.player_id]](player, room)
        return await bot_decide(player, room, config)

    async def run_table(self, room: Room, max_hands: int, stats_map: dict, starting_stack: int = None) -> int:
        """Run hands, return count played. Updates stats_map in place."""
        if starting_stack is None:
            starting_stack = STARTING_STACK
        hands = 0

        for h in range(1, max_hands + 1):
            alive = [p for p in room.players.values() if p.stack > 0]
            if len(alive) < 2:
                break

            # Suppress prints during hand
            _print = builtins.print
            builtins.print = lambda *a, **kw: None
            try:
                await self.server.start_hand(room)

                actions = 0
                prev_action_seat = None
                stall_count = 0
                while room.phase in ("preflop", "flop", "turn", "river") and actions < 300:
                    if room.action_seat is None:
                        break
                    ap = self.server.player_by_seat(room, room.action_seat)
                    if not ap or ap.player_id not in self.server.bots:
                        break

                    # Detect stalled action seat (same player acting repeatedly)
                    if room.action_seat == prev_action_seat:
                        stall_count += 1
                        if stall_count >= 3:
                            try:
                                await self.server.player_action(
                                    room, ap, "check_call",
                                    {"action": "check_call", "room_id": room.room_id,
                                     "token": ap.token})
                            except Exception:
                                break
                            stall_count = 0
                            actions += 1
                            prev_action_seat = room.action_seat
                            continue
                    else:
                        stall_count = 0
                    prev_action_seat = room.action_seat

                    cfg = self.server.bots[ap.player_id]
                    stack_before = ap.stack

                    try:
                        act, extras = await self._decide(ap, room, cfg)
                    except Exception:
                        act, extras = "check_call", {}

                    payload = {"action": act, "room_id": room.room_id,
                               "token": ap.token, **extras}
                    try:
                        await self.server.player_action(room, ap, act, payload)
                    except Exception:
                        try:
                            await self.server.player_action(room, ap, "check_call", {})
                        except Exception:
                            break

                    # Track all-in AFTER action (reliable)
                    if ap.player_id in stats_map and stack_before > 0 and ap.stack == 0:
                        stats_map[ap.player_id].all_ins += 1

                    actions += 1
            finally:
                builtins.print = _print

            # Track wins (deduplicate: one win credit per player per hand)
            winners_this_hand = set()
            for w in room.winners:
                if w.player_id in stats_map and w.player_id not in winners_this_hand:
                    stats_map[w.player_id].hands_won += 1
                    winners_this_hand.add(w.player_id)

            hands = h

        # ─── Finalize stats using room.players directly ────────────────────
        for pid, s in stats_map.items():
            p = room.players.get(pid)
            s.hands_played = hands
            if p is None:
                s.final_stack = 0
                s.net_chips = -starting_stack
                s.busted_at_hand = hands
            else:
                s.final_stack = p.stack
                s.net_chips = p.stack - starting_stack
                if p.stack <= 0:
                    s.busted_at_hand = hands

        # ─── Zero-sum sanity check ────────────────────────────────────────
        total_final = sum(s.final_stack for s in stats_map.values())
        expected_total = len(stats_map) * starting_stack
        if total_final != expected_total:
            _real_print = builtins.__dict__.get("print", print)
            # Restore print if suppressed
            pass  # We'll check after returning

        return hands


# ─── Single Table Runner (for multiprocessing) ────────────────────────────────

def _run_one_table_sync(args: tuple) -> list[PlayerStats]:
    """Run a single table synchronously (for ProcessPoolExecutor)."""
    bots, max_hands, seed, starting_stack = args
    random.seed(seed)
    return asyncio.run(_run_one_table_async(bots, max_hands, starting_stack))


async def _run_one_table_async(bots: list, max_hands: int, starting_stack: int = None) -> list[PlayerStats]:
    """Run a single table and return the stats list."""
    if starting_stack is None:
        starting_stack = STARTING_STACK
    sim = HeadlessSim()
    room = sim.create_room()

    stats_map = {}
    for diff, style in bots:
        player, config = sim.add_bot(room, diff, style, starting_stack=starting_stack)
        stats_map[player.player_id] = PlayerStats(
            name=player.name, difficulty=diff, style=config.style)

    await sim.run_table(room, max_hands, stats_map, starting_stack=starting_stack)
    return list(stats_map.values())


# ─── Scenario Runner ───────────────────────────────────────────────────────────

def run_scenario_parallel(name: str, bots: list, num_tables: int = NUM_TABLES,
                          max_hands: int = MAX_HANDS) -> dict[str, list[PlayerStats]]:
    """Run a scenario across multiple tables using multiprocessing."""
    from concurrent.futures import as_completed

    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"  Bots: {', '.join(f'{d}({s})' for d, s in bots)} | "
          f"{num_tables} tables x {max_hands} hands")
    print(f"{'='*70}")

    args_list = [
        (bots, max_hands, 42 + t * 997, STARTING_STACK)
        for t in range(num_tables)
    ]

    by_diff: dict[str, list[PlayerStats]] = defaultdict(list)
    chip_warnings = 0

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_run_one_table_sync, args) for args in args_list]
        results = []
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % max(1, num_tables // 4) == 0 or i == num_tables:
                print(f"  ... table {i}/{num_tables} done")

    for table_stats in results:
        # Zero-sum check per table
        total_final = sum(s.final_stack for s in table_stats)
        expected = len(table_stats) * STARTING_STACK
        if total_final != expected:
            chip_warnings += 1

        for s in table_stats:
            by_diff[s.difficulty].append(s)

    if chip_warnings:
        print(f"  [WARN] {chip_warnings}/{num_tables} tables had chip mismatch!")

    _print_results(by_diff)
    return by_diff


async def run_scenario_sequential(name: str, bots: list, num_tables: int = NUM_TABLES,
                                  max_hands: int = MAX_HANDS) -> dict[str, list[PlayerStats]]:
    """Run a scenario sequentially (for debugging or when parallel fails)."""
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"  Bots: {', '.join(f'{d}({s})' for d, s in bots)} | "
          f"{num_tables} tables x {max_hands} hands (sequential)")
    print(f"{'='*70}")

    by_diff: dict[str, list[PlayerStats]] = defaultdict(list)
    chip_warnings = 0

    for t in range(num_tables):
        random.seed(42 + t * 997)
        sim = HeadlessSim()
        room = sim.create_room()

        stats_map = {}
        for diff, style in bots:
            player, config = sim.add_bot(room, diff, style)
            stats_map[player.player_id] = PlayerStats(
                name=player.name, difficulty=diff, style=config.style)

        await sim.run_table(room, max_hands, stats_map)

        # Zero-sum check
        total_final = sum(s.final_stack for s in stats_map.values())
        expected = len(stats_map) * STARTING_STACK
        if total_final != expected:
            chip_warnings += 1

        for s in stats_map.values():
            by_diff[s.difficulty].append(s)

        if (t + 1) % max(1, num_tables // 4) == 0:
            print(f"  ... table {t+1}/{num_tables} done")

    if chip_warnings:
        print(f"  [WARN] {chip_warnings}/{num_tables} tables had chip mismatch!")

    _print_results(by_diff)
    return by_diff


def _print_results(by_diff: dict[str, list[PlayerStats]]):
    """Print formatted results table."""
    print(f"\n  {'Diff':<10} {'Style':<15} {'Win%':<7} {'BB/100':<9} {'AvgStk':<8} "
          f"{'Hands':<7} {'Bust%':<7} {'AI/100':<7} {'Survival':<9}")
    print(f"  {'-'*80}")

    for diff in ["random", "easy", "medium", "hard", "expert"]:
        if diff not in by_diff:
            continue
        sl = by_diff[diff]
        n = len(sl)
        total_hands = sum(s.hands_played for s in sl)
        total_wins = sum(s.hands_won for s in sl)
        # Win% = per-player win rate (wins / hands played per player)
        # Since each entry in sl is one player-table, total_hands already
        # accounts for multiple players: win_pct = total_wins / total_hands
        win_pct = total_wins / total_hands * 100 if total_hands > 0 else 0

        # BB/100: aggregate-based
        total_net = sum(s.net_chips for s in sl)
        bb100 = (total_net / BIG_BLIND) / max(1, total_hands) * 100

        avg_stk = sum(s.final_stack for s in sl) / n
        bust_pct = sum(1 for s in sl if s.busted_at_hand > 0) / n * 100
        total_allins = sum(s.all_ins for s in sl)
        ai100 = total_allins / total_hands * 100 if total_hands > 0 else 0

        # Survival: avg hands before bust (or MAX if never busted)
        busted = [s for s in sl if s.busted_at_hand > 0]
        if busted:
            avg_survival = sum(s.busted_at_hand for s in busted) / len(busted)
            survival_str = f"{avg_survival:.0f}h"
        else:
            survival_str = "alive"

        # Get dominant style
        styles = defaultdict(int)
        for s in sl:
            styles[s.style] += 1
        dominant_style = max(styles, key=styles.get)
        style_short = dominant_style[:13]

        print(f"  {diff:<10} {style_short:<15} {win_pct:<7.1f} {bb100:<+9.1f} "
              f"{avg_stk:<8.0f} {total_hands/n:<7.0f} {bust_pct:<7.0f} "
              f"{ai100:<7.1f} {survival_str:<9}")
    print()


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    start = time()
    print(f"\n{'#'*70}")
    print(f"  BOT SIMULATION BENCHMARK")
    print(f"  Stack:{STARTING_STACK} Blinds:{SMALL_BLIND}/{BIG_BLIND} "
          f"Max:{MAX_HANDS}h/table | Workers:{MAX_WORKERS}")
    print(f"  Simulation mode: {'ON (no delays)' if SIMULATION_MODE else 'OFF'}")
    print(f"{'#'*70}")

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 1: Heads-Up Matchups (baseline validation)
    # Fast: HU tables bust quickly, only 2 players per table.
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─'*70}")
    print(f"  SECTION 1: HEADS-UP MATCHUPS")
    print(f"{'─'*70}")

    run_scenario_parallel("Expert TAG vs Random50 (HU)",
        [("expert", "tight_aggressive"), ("random", "random50")],
        num_tables=20, max_hands=500)

    run_scenario_parallel("Expert TAG vs RandomHumanish (HU)",
        [("expert", "tight_aggressive"), ("random", "random_humanish")],
        num_tables=20, max_hands=500)

    run_scenario_parallel("Expert TAG vs Easy CallingStation (HU)",
        [("expert", "tight_aggressive"), ("easy", "calling_station")],
        num_tables=20, max_hands=500)

    run_scenario_parallel("Expert TAG vs Medium TAG (HU)",
        [("expert", "tight_aggressive"), ("medium", "tight_aggressive")],
        num_tables=20, max_hands=500)

    run_scenario_parallel("Expert TAG vs Hard TAG (HU)",
        [("expert", "tight_aggressive"), ("hard", "tight_aggressive")],
        num_tables=20, max_hands=500)

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 2: Difficulty Ladder (same style, isolate difficulty)
    # 4P tables with full AI are expensive — use shorter hand counts.
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─'*70}")
    print(f"  SECTION 2: DIFFICULTY LADDER (same style)")
    print(f"{'─'*70}")

    run_scenario_parallel("Easy vs Medium vs Hard vs Expert TAG (4P)",
        [("easy", "tight_aggressive"), ("medium", "tight_aggressive"),
         ("hard", "tight_aggressive"), ("expert", "tight_aggressive")],
        num_tables=10, max_hands=200)

    run_scenario_parallel("Easy vs Medium vs Hard vs Expert LAG (4P)",
        [("easy", "loose_aggressive"), ("medium", "loose_aggressive"),
         ("hard", "loose_aggressive"), ("expert", "loose_aggressive")],
        num_tables=10, max_hands=200)

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 3: Mixed Tables (1 expert + varied opponents)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─'*70}")
    print(f"  SECTION 3: MIXED TABLES (always 1 expert)")
    print(f"{'─'*70}")

    run_scenario_parallel("1 Expert TAG + 3 Random50 (4P)",
        [("expert", "tight_aggressive"),
         ("random", "random50"), ("random", "random50"), ("random", "random50")],
        num_tables=15, max_hands=500)

    run_scenario_parallel("1 Expert TAG + 2 Easy + 1 Medium (4P)",
        [("expert", "tight_aggressive"),
         ("easy", "calling_station"), ("easy", "loose_aggressive"),
         ("medium", "tight_aggressive")],
        num_tables=10, max_hands=200)

    run_scenario_parallel("1 Expert TAG + 1 Random + 1 Easy + 1 Med + 1 Hard (5P)",
        [("expert", "tight_aggressive"),
         ("random", "random_humanish"), ("easy", "calling_station"),
         ("medium", "tight_aggressive"), ("hard", "loose_aggressive")],
        num_tables=10, max_hands=200)

    run_scenario_parallel("1 Expert LAG + 2 RandomHumanish + 2 Easy (5P)",
        [("expert", "loose_aggressive"),
         ("random", "random_humanish"), ("random", "random_humanish"),
         ("easy", "calling_station"), ("easy", "tight_aggressive")],
        num_tables=10, max_hands=200)

    run_scenario_parallel(
        "1 Expert TAG + Full Mix (6P)",
        [("expert", "tight_aggressive"),
         ("random", "random50"), ("random", "random_humanish"),
         ("easy", "calling_station"), ("medium", "tight_aggressive"),
         ("hard", "tight_aggressive")],
        num_tables=6, max_hands=150)

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 4: Style Matchups at Expert Level
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─'*70}")
    print(f"  SECTION 4: STYLE MATCHUPS (all expert)")
    print(f"{'─'*70}")

    run_scenario_parallel("Expert TAG vs Expert LAG (HU)",
        [("expert", "tight_aggressive"), ("expert", "loose_aggressive")],
        num_tables=10, max_hands=300)

    run_scenario_parallel("All Expert Styles (4P)",
        [("expert", "tight_aggressive"), ("expert", "loose_aggressive"),
         ("expert", "calling_station"), ("expert", "maniac")],
        num_tables=6, max_hands=150)

    # ═══════════════════════════════════════════════════════════════════════
    # DONE
    # ═══════════════════════════════════════════════════════════════════════
    elapsed = time() - start
    print(f"\n{'#'*70}")
    print(f"  COMPLETE | Total time: {elapsed:.1f}s")
    print(f"{'#'*70}\n")


if __name__ == "__main__":
    main()
