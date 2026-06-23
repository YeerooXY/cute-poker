"""Shared data models for the Advanced Bot AI system.

All state (ranges, opponent stats, board texture, scoring contexts) is stored
in typed dataclasses for clarity and testability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DifficultyLevel(Enum):
    """Four difficulty levels for bot AI."""

    EASY = 1
    MEDIUM = 2
    HARD = 3
    EXPERT = 4


@dataclass
class AIGameContext:
    """All information the AI needs to make a decision."""

    hole_cards: list[str]
    community: list[str]
    phase: str  # "preflop", "flop", "turn", "river"
    pot: int
    current_bet: int
    committed: int
    stack: int
    big_blind: int
    min_raise: int
    position: str  # "UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB"
    num_opponents: int
    is_preflop_aggressor: bool
    facing_action: str  # "unopened", "bet", "raise", "3bet", "4bet"
    raises_faced_this_street: int = 0  # Count of opponent raises on current street


@dataclass
class ActionContext:
    """Context about an observed action for stat tracking."""

    street: str
    action: str  # "fold", "call", "raise", "check", "bet"
    position: str
    is_3bet_situation: bool
    is_cbet_situation: bool
    facing_bet: bool
    pot_relative_size: float  # Size of action relative to pot


@dataclass
class HandSummary:
    """Summary of a completed hand for table tendency tracking."""

    players_who_folded: list[str]
    players_who_called: list[str]
    players_who_raised: list[str]
    went_to_showdown: bool
    winner_token: str
    pot_size: int


@dataclass
class ExploitAdjustments:
    """Adjustments to make against a specific opponent based on their stats."""

    three_bet_bluff_boost: float = 0.0
    cbet_frequency_boost: float = 0.0
    bluff_frequency_reduction: float = 0.0
    value_bet_boost: float = 0.0
    active: bool = False


@dataclass
class RangeEstimate:
    """Probability distribution over hand categories for one opponent."""

    premium: float = 1.0
    strong: float = 1.0
    playable: float = 1.0
    marginal: float = 1.0
    speculative: float = 1.0
    trash: float = 1.0


@dataclass
class ComboRange:
    """A range distribution mapping each of 169 hand classes to a weight [0.0, 1.0].

    Used by the ComboRangeTracker for precise range narrowing at the hand-class level.
    All weights start at 1.0 (full range) and are narrowed based on observed actions.
    """

    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class BoardTexture:
    """Classification of community card texture."""

    is_dry: bool = False
    is_wet: bool = False
    is_paired: bool = False
    is_monotone: bool = False
    is_connected: bool = False
    flush_possible: bool = False
    straight_possible: bool = False
    high_card_rank: int = 0


@dataclass
class RangeAdvantage:
    """Measure of which player's range is favored on the board."""

    aggressor_advantage: float = 0.5  # 0.0 = caller favored, 1.0 = aggressor favored
    nut_advantage: bool = False  # Does aggressor have more nut combos?


@dataclass
class BluffScore:
    """Bluff viability assessment using multiple factors."""

    blocker_score: float  # 0.0-1.0, how much our cards block strong opponent hands
    fold_equity: float  # 0.0-1.0, estimated probability opponent folds
    range_advantage: float  # 0.0-1.0, how much the board favors our range
    backup_equity: float  # 0.0-1.0, equity if called (draw outs, etc.)
    total_score: float  # Weighted combination


@dataclass
class ActionScores:
    """Numeric scores for each possible action."""

    fold: float = 0.0
    check: float = 0.0
    call: float = 0.0
    bet: float = 0.0
    raise_: float = 0.0


@dataclass
class ActionModifiers:
    """Additive modifiers for each action, computed from personality/exploit/board texture."""

    fold: float = 0.0
    check: float = 0.0
    call: float = 0.0
    bet: float = 0.0
    raise_: float = 0.0


@dataclass
class DynamicAdjustments:
    """Table-level strategic adjustments based on recent play."""

    steal_frequency_boost: float = 0.0
    open_range_expansion: float = 0.0
    bluff_frequency_adjustment: float = 0.0
    value_bet_sizing_boost: float = 0.0
    four_bet_frequency_boost: float = 0.0
    trap_frequency_boost: float = 0.0
    push_fold_mode: bool = False


@dataclass
class ActiveSubsystems:
    """Configuration of which AI subsystems are active at a given difficulty level."""

    hand_strength: bool = True
    pot_odds: bool = True
    preflop_charts: bool = False
    bet_sizing: bool = False
    range_tracking: bool = False
    board_texture: bool = False
    opponent_modeling: bool = False
    bluff_calculator: bool = False
    dynamic_adjustment: bool = False
    full_action_scoring: bool = False


@dataclass
class DifficultyConfig:
    """Patch 1: simplified to only essential fields."""

    level: DifficultyLevel
    equity_error_max: float
    active_subsystems: ActiveSubsystems


@dataclass
class ScoringContext:
    """All context needed by the action scorer to compute scores."""

    equity: float
    pot_odds: float
    opponent_range: RangeEstimate
    board_texture: BoardTexture
    range_advantage: RangeAdvantage
    position: str
    street: str
    bluff_score: BluffScore
    exploit_adjustments: ExploitAdjustments
    dynamic_adjustments: DynamicAdjustments
    personality: Any  # PokerPersonality (defined in personality_engine)
    stack_to_pot: float
    is_preflop_aggressor: bool

    # EV calculation inputs (populated by fold equity calculator and bet sizer)
    fold_probability: float = 0.35  # Estimated probability opponents fold to a bet/raise
    bet_amount: int = 0  # Computed bet size for EV calculations
    raise_amount: int = 0  # Computed raise size for raise EV formula
    num_opponents: int = 1  # Number of active opponents for multiway EV
    call_amount: int = 0  # Amount the bot needs to call
    pot: int = 0  # Current pot size (for modifier bounding)

    # Difficulty level for gating EV behavior (None means full system / HARD+EXPERT)
    difficulty_level: str | None = None  # "EASY", "MEDIUM", "HARD", "EXPERT", or None


@dataclass
class PreflopGateContext:
    """Context for preflop sanity gate evaluation."""

    hole_cards: list[str]
    hand_percentile: float  # 0.0 = best, 1.0 = worst
    effective_stack_bb: float  # Effective stack in big blinds
    facing_action: str  # "unopened", "raise", "3bet", "4bet"
    proposed_action: str  # What the pipeline wants to do


@dataclass
class PostflopGateContext:
    """Context for postflop sanity gate evaluation."""

    hand_strength: str  # "bottom_pair", "top_pair", "overpair", "two_pair", etc.
    board_texture: BoardTexture
    equity: float
    pot_odds: float
    proposed_action: str


@dataclass
class AllinGateContext:
    """Context for SPR-based all-in gate evaluation."""

    spr: float  # Stack-to-Pot Ratio
    hand_strength: str
    equity: float
    has_strong_draw: bool  # flush draw + pair, OESFD
    has_combo_draw: bool  # flush draw + OESD
    proposed_action: str


@dataclass
class MistakeType:
    """Classification of a mistake for logging and testing."""

    category: str  # "second_best", "sizing_error", "missed_value", "loose_call", "tight_fold"
    original_action: str
    substituted_action: str
    sizing_delta_pct: float | None  # For sizing errors only
