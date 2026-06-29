"""
AI bot players with distinct personalities.

Each bot has a "style" that determines how it plays:
- tight_aggressive: Plays few hands but bets/raises aggressively when in
- loose_aggressive: Plays many hands, bluffs often, applies pressure
- calling_station: Calls too much, rarely raises, hard to bluff
- maniac: Raises constantly, plays almost every hand, unpredictable

Bots use the equity calculator to make informed decisions, then apply
their personality filter on top.
"""

from __future__ import annotations

import asyncio
import random
import secrets
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.game import PokerServer
    from poker.models import Room, Player

from poker.odds import estimate_equity
from poker.ranges import get_preflop_action
from poker.terminology import classify_hand
from poker.bot_ai import advanced_bot_decide, _last_decision_debug
from poker.bot_ai.models import AIGameContext
from poker.bot_ai.difficulty_controller import (
    DifficultyLevel,
)
from poker.bot_ai.personality_engine import BALANCED_PROFILE


BOT_NAMES = {
    "tight_aggressive": [
        "Giddybot", "Jerobot",
    ],
    "loose_aggressive": [
        "Dindybot", "Gidrokbot",
    ],
    "calling_station": [
        "Lamobot", "Papperbbot",
    ],
    "maniac": [
        "Gidrokbot", "Dindybot",
    ],
}

# Master list of unique bot names — only one of each per game
ALL_BOT_NAMES = ["Giddybot", "Dindybot", "Lamobot", "Jerobot", "Gidrokbot", "Papperbot"]

BOT_AVATARS = {
    "tight_aggressive": "🤖",
    "loose_aggressive": "😈",
    "calling_station": "🐌",
    "maniac": "🔥",
}

# How likely each style is to play a hand preflop (VPIP approximation)
VPIP = {
    "tight_aggressive": 0.35,
    "loose_aggressive": 0.65,
    "calling_station": 0.75,
    "maniac": 0.88,
}

# How likely to raise vs call when entering a pot
RAISE_FREQUENCY = {
    "tight_aggressive": 0.80,
    "loose_aggressive": 0.78,
    "calling_station": 0.25,
    "maniac": 0.90,
}

# Bluff frequency (raises with weak hands)
BLUFF_FREQ = {
    "tight_aggressive": 0.18,
    "loose_aggressive": 0.40,
    "calling_station": 0.05,
    "maniac": 0.55,
}


@dataclass
class BotConfig:
    style: str
    name: str
    avatar: str
    think_time_min: float = 0.15
    think_time_max: float = 0.35
    last_trash_talk_hand: int = -1
    was_preflop_aggressor: bool = False
    use_advanced_ai: bool = False
    difficulty: str = "hard"  # "easy", "medium", "hard", "expert"


def calculate_think_time(config: BotConfig, equity: float, is_nuts: bool, to_call: int) -> float:
    """
    Calculate context-aware think time for a bot decision.

    - Nuts or obvious fold (equity < 0.15 facing a bet): 0.05-0.25s
    - Normal decisions: config.think_time_min to config.think_time_max
    - Plus random jitter up to 0.1s
    """
    # Clamp equity to valid range
    equity = max(0.0, min(1.0, equity))

    # Determine if this is a fast decision
    obvious_fold = equity < 0.15 and to_call > 0

    if is_nuts or obvious_fold:
        base_time = random.uniform(0.05, 0.15)
    else:
        base_time = random.uniform(config.think_time_min, config.think_time_max)

    # Add random jitter
    jitter = random.uniform(0, 0.1)

    return base_time + jitter


# Track used bot names within a session to ensure uniqueness
_used_bot_names: set[str] = set()


def create_bot_config(
    style: Optional[str] = None,
    used_names: Optional[set[str]] = None,
    use_advanced_ai: bool = False,
    difficulty: str = "hard",
) -> BotConfig:
    """Create a random bot config with the given style (or random style).
    
    Ensures each bot gets a unique name from ALL_BOT_NAMES.
    
    Args:
        style: Bot style string (tight_aggressive, loose_aggressive, etc.)
        used_names: Set of already-used names to avoid duplicates.
        use_advanced_ai: If True, delegate decisions to the advanced AI pipeline.
        difficulty: Difficulty level for advanced AI ("easy", "medium", "hard", "expert").
    """
    if style is None:
        style = random.choice(list(BOT_NAMES.keys()))
    if style not in BOT_NAMES:
        style = "tight_aggressive"

    # Pick a unique name from the master list
    if used_names is None:
        used_names = _used_bot_names
    
    available = [n for n in ALL_BOT_NAMES if n not in used_names]
    if not available:
        # All names used, reset and pick any
        available = ALL_BOT_NAMES[:]
    
    name = random.choice(available)
    used_names.add(name)
    _used_bot_names.add(name)

    avatar = BOT_AVATARS[style]

    return BotConfig(
        style=style,
        name=name,
        avatar=avatar,
        use_advanced_ai=use_advanced_ai,
        difficulty=difficulty,
    )


def reset_bot_names() -> None:
    """Reset used bot names tracker (e.g., on new game)."""
    _used_bot_names.clear()


def _get_position(player: "Player", room: "Room") -> str:
    """Determine player's position relative to dealer (early/middle/late/blind)."""
    if room.sb_seat == player.seat or room.bb_seat == player.seat:
        return "blind"

    active = [p for p in room.seated_players()
              if p.cards and not p.folded and p.stack >= 0]
    num_active = len(active)

    if num_active <= 3:
        return "late"

    # Get seats ordered from after dealer
    dealer_seat = room.dealer_seat or 1
    ordered_seats = []
    for offset in range(1, 9):
        seat = ((dealer_seat - 1 + offset) % 8) + 1
        for p in active:
            if p.seat == seat and seat != room.sb_seat and seat != room.bb_seat:
                ordered_seats.append(seat)

    if not ordered_seats:
        return "middle"

    try:
        pos_idx = ordered_seats.index(player.seat)
    except ValueError:
        return "middle"

    third = len(ordered_seats) / 3.0
    if pos_idx < third:
        return "early"
    elif pos_idx < third * 2:
        return "middle"
    else:
        return "late"


def _has_flush_draw(draws: list[str]) -> bool:
    """Check if the draw list contains any flush draw."""
    for d in draws:
        if "flush draw" in d.lower():
            return True
    return False


def _has_oesd(draws: list[str]) -> bool:
    """Check if the draw list contains an open-ended straight draw."""
    for d in draws:
        if "open-ended" in d.lower():
            return True
    return False


# ─── Advanced AI helpers ───────────────────────────────────────────────────────

# Difficulty string to DifficultyLevel mapping
_DIFFICULTY_MAPPING: dict[str, DifficultyLevel] = {
    "easy": DifficultyLevel.EASY,
    "medium": DifficultyLevel.MEDIUM,
    "hard": DifficultyLevel.HARD,
    "expert": DifficultyLevel.EXPERT,
}


def _get_position_advanced(player: "Player", room: "Room") -> str:
    """Map player's seat to the 8-position system used by the advanced AI.
    
    Positions: UTG, UTG1, MP, HJ, CO, BTN, SB, BB
    
    For tables with fewer players, positions are compressed towards late positions
    (BTN, SB, BB are always assigned; early positions are dropped first).
    """
    if room.sb_seat == player.seat:
        return "SB"
    if room.bb_seat == player.seat:
        return "BB"

    # Get active non-blind players ordered from after dealer
    active = [p for p in room.seated_players()
              if p.cards and not p.folded and p.stack >= 0]
    
    dealer_seat = room.dealer_seat or 1
    
    # Collect non-blind seats in positional order (after dealer, skipping SB/BB)
    ordered_seats: list[int] = []
    for offset in range(1, 9):
        seat = ((dealer_seat - 1 + offset) % 8) + 1
        for p in active:
            if p.seat == seat and seat != room.sb_seat and seat != room.bb_seat:
                ordered_seats.append(seat)

    if not ordered_seats:
        return "BTN"

    # The last seat before blinds is always the button (dealer)
    # Map positions based on number of non-blind players
    num_positions = len(ordered_seats)
    
    try:
        pos_idx = ordered_seats.index(player.seat)
    except ValueError:
        return "MP"

    # Full 6-position mapping (UTG, UTG1, MP, HJ, CO, BTN)
    # For fewer players, assign from the end (BTN is always last)
    full_positions = ["UTG", "UTG1", "MP", "HJ", "CO", "BTN"]
    
    if num_positions <= len(full_positions):
        # Take the last N positions from the full list
        available_positions = full_positions[-num_positions:]
    else:
        # More players than positions (shouldn't happen with 8 seats - 2 blinds = 6)
        available_positions = full_positions

    if pos_idx < len(available_positions):
        return available_positions[pos_idx]
    
    return "BTN"


def _count_raises_faced_this_street(room: "Room", player: "Player") -> int:
    """Count opponent raises/re-raises on the current street from action history.

    Only counts bet_raise actions by OTHER players on the current street (phase).
    The count naturally resets to 0 on each street transition because we only look
    at entries matching room.phase.

    Returns 0 if action_log is unavailable or corrupt (conservative default —
    the raise-ladder gate simply won't fire).
    """
    try:
        action_log = getattr(room, "action_log", None)
        if not action_log or not isinstance(action_log, list):
            return 0

        current_phase = room.phase
        count = 0
        for entry in action_log:
            if not isinstance(entry, dict):
                continue
            # Only count actions on the current street
            if entry.get("phase") != current_phase:
                continue
            # Only count opponent raises (not the bot's own raises)
            if entry.get("action") == "bet_raise" and entry.get("player") != getattr(player, "name", None):
                count += 1
        return count
    except Exception:
        return 0


def _determine_facing_action(room: "Room", player: "Player") -> str:
    """Determine what action the bot is facing based on room state.
    
    Returns: "unopened", "raise", "3bet", or "4bet"
    """
    to_call = max(0, room.current_bet - player.committed)
    
    if room.phase == "preflop":
        # Preflop logic: count the number of raises
        if to_call == 0:
            # No bet to face — either checked around or we're first to act
            return "unopened"
        elif room.current_bet <= room.big_blind:
            # Only the big blind is posted, no one has raised
            return "unopened"
        elif room.current_bet <= room.big_blind * 4:
            # A single raise (typically 2-3x BB)
            return "raise"
        elif room.current_bet <= room.big_blind * 12:
            # A 3-bet (re-raise)
            return "3bet"
        else:
            # A 4-bet or more
            return "4bet"
    else:
        # Postflop: simpler classification
        if to_call == 0:
            return "unopened"
        else:
            return "raise"


def _advanced_ai_decide(
    player: "Player",
    room: "Room",
    config: BotConfig,
) -> tuple[str, dict]:
    """Delegate decision to the advanced AI pipeline.
    
    Builds an AIGameContext from the player/room state, gets the appropriate
    personality profile, and calls advanced_bot_decide.
    """
    # Resolve difficulty level
    difficulty = _DIFFICULTY_MAPPING.get(config.difficulty.lower(), DifficultyLevel.HARD)
    
    # Use the balanced profile for all normal gameplay decisions
    personality = BALANCED_PROFILE
    
    # Count active opponents
    num_active_opponents = len([
        p for p in room.players.values()
        if p.cards and not p.folded and p.token != player.token
    ])
    if num_active_opponents < 1:
        num_active_opponents = 1
    
    # Compute raises faced on the current street for raise-ladder tracking
    raises_faced = _count_raises_faced_this_street(room, player)

    # Build the game context
    game_context = AIGameContext(
        hole_cards=player.cards,
        community=room.community,
        phase=room.phase,
        pot=room.pot,
        current_bet=room.current_bet,
        committed=player.committed,
        stack=player.stack,
        big_blind=room.big_blind,
        min_raise=room.min_raise,
        position=_get_position_advanced(player, room),
        num_opponents=num_active_opponents,
        is_preflop_aggressor=config.was_preflop_aggressor,
        facing_action=_determine_facing_action(room, player),
        raises_faced_this_street=raises_faced,
    )
    
    # Call the advanced AI pipeline (synchronous — runs in thread via to_thread)
    action, payload = advanced_bot_decide(game_context, personality, difficulty)
    
    # Capture debug info for game logging
    config._last_debug = dict(_last_decision_debug)
    
    # Track preflop aggressor status for continuation bet logic
    if room.phase == "preflop":
        config.was_preflop_aggressor = (action == "bet_raise")
    
    return (action, payload)


async def bot_decide(
    player: "Player",
    room: "Room",
    config: BotConfig,
) -> tuple[str, dict]:
    """
    Decide what action the bot takes.

    Returns (action_name, payload_extras) to be passed to player_action.
    
    If config.use_advanced_ai is True, delegates to the advanced AI pipeline.
    Otherwise, uses the existing equity-based logic.
    """
    # ─── Advanced AI dispatch ───
    if config.use_advanced_ai:
        return await asyncio.to_thread(_advanced_ai_decide, player, room, config)

    style = config.style
    phase = room.phase
    community = room.community
    hole = player.cards

    # Calculate equity (fewer sims for speed)
    num_opp = len([p for p in room.players.values()
                   if p.cards and not p.folded and p.token != player.token])
    if num_opp < 1:
        num_opp = 1

    try:
        eq_result = estimate_equity(hole, community, num_opp, simulations=2000)
        equity = eq_result["equity"]
    except Exception:
        equity = 0.5

    # Get hand classification
    try:
        hand_info = classify_hand(hole, community)
    except Exception:
        hand_info = {"made_hand": "", "draws": [], "is_nuts": False}

    # Pot odds
    to_call = max(0, room.current_bet - player.committed)
    pot_after_call = room.pot + to_call
    pot_odds = to_call / pot_after_call if pot_after_call > 0 else 0

    # Stack-to-pot ratio
    spr = player.stack / room.pot if room.pot > 0 else 20

    # ─── Decision logic ───

    # Preflop: use professional preflop ranges
    if phase == "preflop":
        facing_raise = to_call > room.big_blind
        position = _get_position(player, room)

        action, extras = get_preflop_action(
            hole_cards=hole,
            style=style,
            facing_raise=facing_raise,
            position=position,
            big_blind=room.big_blind,
        )

        # Track if we raised preflop (for continuation bet logic)
        if action == "bet_raise":
            config.was_preflop_aggressor = True
        else:
            config.was_preflop_aggressor = False

        # Convert ranges action format to game action format
        if action == "bet_raise":
            raise_amount = extras.get("amount", room.big_blind * 3)
            # Convert to "raise to" format: current_bet + raise_amount
            raise_to = room.current_bet + raise_amount
            raise_to = min(raise_to, player.committed + player.stack)
            min_raise_to = room.current_bet + room.min_raise
            if raise_to < min_raise_to:
                raise_to = min_raise_to
            raise_to = min(raise_to, player.committed + player.stack)
            return ("bet_raise", {"amount": raise_to})
        elif action == "fold":
            if to_call == 0:
                return ("check_call", {})  # Never fold for free
            return ("fold", {})
        else:
            return ("check_call", {})

    # Postflop
    return _postflop_decision(style, equity, to_call, pot_odds, player, room, hand_info, spr, config)


def _postflop_decision(
    style: str,
    equity: float,
    to_call: int,
    pot_odds: float,
    player: "Player",
    room: "Room",
    hand_info: dict,
    spr: float,
    config: BotConfig,
) -> tuple[str, dict]:
    """Postflop decision based on equity, pot odds, style, and aggression rules."""
    raise_freq = RAISE_FREQUENCY[style]
    bluff_freq = BLUFF_FREQ[style]

    draws = hand_info.get("draws", [])
    has_draws = len(draws) > 0
    is_nuts = hand_info.get("is_nuts", False)
    made_hand = hand_info.get("made_hand", "")
    phase = room.phase

    has_flush = _has_flush_draw(draws)
    has_open_ended = _has_oesd(draws)
    has_strong_draw = has_flush or has_open_ended

    aggressive_styles = {"tight_aggressive", "loose_aggressive", "maniac"}

    # ─── Rule: The nuts — always raise/bet ───
    if is_nuts:
        return _make_raise_street(player, room, equity=1.0)

    # ─── Rule: High equity aggression (Req 4.3) ───
    # equity > 0.65 → bet/raise at least 75% of the time
    if equity > 0.65:
        if random.random() < 0.75:
            return _make_raise_street(player, room, equity=equity)
        # 25% of the time: slow play / call
        if to_call > 0:
            return ("check_call", {})
        return ("check_call", {})

    # ─── Rule: Continuation bet (Req 4.1) ───
    # Preflop aggressor, flop, checked to (to_call == 0), aggressive styles
    if (config.was_preflop_aggressor and phase == "flop" and
            to_call == 0 and style in aggressive_styles):
        if random.random() < 0.70:  # >= 65% c-bet frequency
            return _make_raise_street(player, room, equity=equity)

    # ─── Rule: Semi-bluff with draws (Req 4.2) ───
    # Flush draw or open-ended straight draw → bet/raise at least 40%
    if has_strong_draw:
        if random.random() < 0.45:  # >= 40% semi-bluff frequency
            return _make_raise_street(player, room, equity=equity)

    # ─── Rule: No-fold when equity > 0.30 facing a bet (Req 2.3) ───
    if equity > 0.30 and to_call > 0:
        # Never fold. Either call or raise.
        if random.random() < raise_freq * 0.4:
            return _make_raise_street(player, room, equity=equity)
        return ("check_call", {})

    # ─── Rule: Bluff logic for aggressive styles (Req 2.4) ───
    # equity < 0.30 facing a bet: loose_aggressive and maniac fold only 50%
    if equity < 0.30 and to_call > 0:
        if style in ("loose_aggressive", "maniac"):
            if random.random() < 0.50:
                # Don't fold — call or raise
                if random.random() < bluff_freq:
                    return _make_raise_street(player, room, equity=equity)
                return ("check_call", {})
            else:
                return ("fold", {})
        # Other styles facing bet with weak hand
        if style == "calling_station" and random.random() < 0.4:
            return ("check_call", {})
        return ("fold", {})

    # ─── Medium equity (0.30 to 0.65), not covered above ───
    if to_call == 0:
        # We can bet/check freely
        if has_draws and random.random() < raise_freq * 0.3:
            return _make_raise_street(player, room, equity=equity)
        if random.random() < bluff_freq:
            return _make_raise_street(player, room, equity=equity)
        return ("check_call", {})
    else:
        # Facing a bet with medium equity — pot odds check
        if equity > pot_odds or style in ("calling_station", "loose_aggressive"):
            return ("check_call", {})
        if style == "maniac" and random.random() < 0.3:
            return _make_raise_street(player, room, equity=equity)
        return ("fold", {})


def _make_raise_street(
    player: "Player",
    room: "Room",
    equity: float = 0.5,
) -> tuple[str, dict]:
    """
    Generate a raise action with street-based sizing (Req 4.4).

    Value bets (equity > 0.65):
      - Flop: 0.4x-0.7x pot
      - Turn: 0.5x-0.9x pot
      - River: 0.7x-1.2x pot

    Other bets use smaller sizing.
    """
    pot = room.pot
    phase = room.phase
    min_raise_to = room.current_bet + room.min_raise
    max_raise = player.committed + player.stack

    # Determine pot fraction based on street and equity
    if equity > 0.65:
        # Value bet sizing (Req 4.4)
        if phase == "flop":
            pot_fraction = random.uniform(0.4, 0.7)
        elif phase == "turn":
            pot_fraction = random.uniform(0.5, 0.9)
        else:  # river
            pot_fraction = random.uniform(0.7, 1.2)
    else:
        # Non-value bets (bluffs, semi-bluffs, c-bets): smaller sizing
        if phase == "flop":
            pot_fraction = random.uniform(0.33, 0.55)
        elif phase == "turn":
            pot_fraction = random.uniform(0.4, 0.7)
        else:  # river
            pot_fraction = random.uniform(0.5, 0.8)

    amount = room.current_bet + int(pot * pot_fraction)
    amount = max(min_raise_to, min(amount, max_raise))

    # Occasionally shove with very strong hands
    if equity > 0.85 and random.random() < 0.2:
        amount = max_raise

    return ("bet_raise", {"amount": amount})
