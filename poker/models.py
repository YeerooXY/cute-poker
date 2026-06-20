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
    cards: list[str] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    committed: int = 0
    acted: bool = False

    last_hand_name: str = ""
    last_best_cards: list[str] = field(default_factory=list)

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


@dataclass
class Room:
    room_id: str
    creator_token: str = ""
    players: dict[str, Player] = field(default_factory=dict)

    deck: list[str] = field(default_factory=list)
    community: list[str] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    winners: list[Winner] = field(default_factory=list)

    phase: str = "lobby"  # lobby, preflop, flop, turn, river, showdown
    pot: int = 0
    current_bet: int = 0
    min_raise: int = 20
    small_blind: int = 5
    big_blind: int = 10

    dealer_seat: Optional[int] = None
    action_seat: Optional[int] = None
    sb_seat: Optional[int] = None
    bb_seat: Optional[int] = None
    paused: bool = False

    # Blind level progression
    hands_played: int = 0
    blind_increase_hands: int = 0  # 0 = no auto-increase
    blind_levels: list = field(default_factory=lambda: [
        (5, 10), (10, 20), (15, 30), (25, 50), (50, 100), (75, 150), (100, 200)
    ])
    current_blind_level: int = 0

    def seated_players(self) -> list[Player]:
        return sorted(self.players.values(), key=lambda p: p.seat)

    def active_hand_players(self) -> list[Player]:
        return [p for p in self.seated_players() if p.cards and not p.folded]

    def connected_players(self) -> list[Player]:
        return [p for p in self.seated_players() if p.connected and p.ws is not None]
