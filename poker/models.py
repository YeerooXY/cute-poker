from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Optional, Any


@dataclass
class ChatMessage:
    name: str
    text: str
    timestamp: float = field(default_factory=time)


@dataclass
class Player:
    player_id: str
    token: str
    name: str
    seat: int
    ws: Any = None
    connected: bool = True

    stack: int = 1000
    hand_start_stack: int = 1000
    cards: list[str] = field(default_factory=list)
    folded: bool = False
    folded_reveal_mode: str = "hidden"  # hidden, left, right, both, muck
    uncontested_reveal_mode: str = "hidden"  # hidden, left, right, both; for winners after everyone else folds
    all_in: bool = False
    committed: int = 0
    total_invested: int = 0
    acted: bool = False

    last_hand_name: str = ""
    last_best_cards: list[str] = field(default_factory=list)
    last_hand_detail: str = ""  # detailed description with kicker info

    disconnected_at: float = 0.0  # timestamp when disconnected
    sitting_out: bool = False
    is_spectator: bool = False
    avatar: str = "🎭"  # emoji avatar


@dataclass
class Winner:
    player_id: str
    name: str
    amount: int
    reason: str
    hand_name: str = ""
    best_cards: list[str] = field(default_factory=list)
    hand_detail: str = ""  # detailed description with kicker info


@dataclass
class Room:
    room_id: str
    creator_token: str = ""
    players: dict[str, Player] = field(default_factory=dict)

    deck: list[str] = field(default_factory=list)
    community: list[str] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    winners: list[Winner] = field(default_factory=list)
    pot_breakdown: list = field(default_factory=list)  # Per-pot tier results for UI
    action_log: list = field(default_factory=list)  # Actions taken this hand (for analysis)
    hand_deltas: dict[str, int] = field(default_factory=dict)  # Net result this hand by player_id
    allow_folded_reveals: bool = True  # If True, folded players may reveal after showdown

    phase: str = "lobby"  # lobby, preflop, flop, turn, river, showdown
    pot: int = 0
    current_bet: int = 0
    min_raise: int = 20
    small_blind: int = 5
    big_blind: int = 10
    ante: int = 0  # Per-player ante (typically 10% of BB, 0 = disabled)
    ante_mode: str = "classic"  # "classic" = all players post, "bba" = dealer posts 1 BB
    auto_ante: bool = False  # If True, ante auto-scales to ~10% of BB on blind increase

    dealer_seat: Optional[int] = None
    action_seat: Optional[int] = None
    sb_seat: Optional[int] = None
    bb_seat: Optional[int] = None
    paused: bool = False

    # Blind level progression
    hands_played: int = 0
    blind_increase_hands: int = 0  # 0 = no auto-increase
    blind_levels: list = field(default_factory=lambda: [
        # ~1.5x progression: realistic tournament structure
        (5, 10),       # Level 0: 5/10
        (8, 15),       # Level 1: 8/15
        (10, 25),      # Level 2: 10/25
        (15, 30),      # Level 3: 15/30
        (25, 50),      # Level 4: 25/50
        (30, 75),      # Level 5: 30/75
        (50, 100),     # Level 6: 50/100
        (75, 150),     # Level 7: 75/150
        (100, 200),    # Level 8: 100/200
        (150, 300),    # Level 9: 150/300
        (200, 400),    # Level 10: 200/400
        (300, 600),    # Level 11: 300/600
        (500, 1000),   # Level 12: 500/1000
    ])
    current_blind_level: int = 0

    def seated_players(self) -> list[Player]:
        return sorted(self.players.values(), key=lambda p: p.seat)

    def active_hand_players(self) -> list[Player]:
        return [p for p in self.seated_players() if p.cards and not p.folded]

    def connected_players(self) -> list[Player]:
        return [p for p in self.seated_players() if p.connected and p.ws is not None]
