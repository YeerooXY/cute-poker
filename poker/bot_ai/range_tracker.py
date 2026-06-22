"""Range-based opponent hand tracking.

Maintains probability distributions over opponent hand categories based on
observed actions. Each player has a separate RangeEstimate that starts at
full (all 1.0) and narrows as actions are observed.

Position ordering (early to late): UTG, UTG1, MP, HJ, CO, BTN, SB, BB
"""

from __future__ import annotations

from poker.bot_ai.models import ComboRange, RangeEstimate
from poker.odds import HAND_CLASSES_169, CATEGORY_TO_HAND_CLASSES

# Position classification helpers
EARLY_POSITIONS = {"UTG", "UTG1"}
MIDDLE_POSITIONS = {"MP", "HJ"}
LATE_POSITIONS = {"CO", "BTN"}
BLIND_POSITIONS = {"SB", "BB"}

# Weights assigned by preflop action + position.
# Each tuple: (premium, strong, playable, marginal, speculative, trash)
# These represent the probability that a player holds each category
# given the observed action and position.

_PREFLOP_WEIGHTS: dict[tuple[str, str], tuple[float, ...]] = {}


def _position_group(position: str) -> str:
    """Classify a position into early/middle/late/blind."""
    if position in EARLY_POSITIONS:
        return "early"
    elif position in MIDDLE_POSITIONS:
        return "middle"
    elif position in LATE_POSITIONS:
        return "late"
    else:
        return "blind"


# --- Preflop weight tables ---
# Format: weights per category (premium, strong, playable, marginal, speculative, trash)
# Higher = more likely they hold that category given the action.

_RAISE_WEIGHTS = {
    "early": (0.95, 0.85, 0.40, 0.10, 0.05, 0.02),
    "middle": (0.90, 0.80, 0.60, 0.30, 0.15, 0.05),
    "late": (0.85, 0.75, 0.70, 0.55, 0.40, 0.15),
    "blind": (0.90, 0.80, 0.55, 0.30, 0.20, 0.08),
}

_CALL_WEIGHTS = {
    "early": (0.30, 0.50, 0.70, 0.60, 0.40, 0.10),
    "middle": (0.25, 0.45, 0.75, 0.65, 0.50, 0.15),
    "late": (0.20, 0.40, 0.80, 0.75, 0.65, 0.30),
    "blind": (0.20, 0.40, 0.75, 0.70, 0.60, 0.25),
}

_THREE_BET_WEIGHTS = {
    "early": (0.95, 0.60, 0.15, 0.05, 0.10, 0.02),
    "middle": (0.95, 0.55, 0.20, 0.08, 0.12, 0.03),
    "late": (0.90, 0.50, 0.25, 0.10, 0.15, 0.05),
    "blind": (0.95, 0.55, 0.20, 0.05, 0.15, 0.03),
}

_FOUR_BET_WEIGHTS = {
    "early": (0.98, 0.30, 0.05, 0.02, 0.03, 0.01),
    "middle": (0.98, 0.30, 0.05, 0.02, 0.03, 0.01),
    "late": (0.95, 0.35, 0.10, 0.03, 0.05, 0.02),
    "blind": (0.98, 0.30, 0.05, 0.02, 0.03, 0.01),
}

# --- Postflop narrowing multipliers ---
# These are applied as multipliers to the existing range (monotonic narrowing).
# All values <= 1.0 to ensure probabilities never increase.

_POSTFLOP_MULTIPLIERS: dict[str, tuple[float, ...]] = {
    # (premium, strong, playable, marginal, speculative, trash)
    "bet": (0.95, 0.90, 0.80, 0.60, 0.40, 0.20),
    "raise": (0.90, 0.85, 0.70, 0.45, 0.25, 0.10),
    "check": (0.85, 0.95, 0.95, 0.95, 0.95, 0.95),
    "call": (0.90, 0.90, 0.85, 0.80, 0.70, 0.50),
    "fold": (0.10, 0.20, 0.30, 0.50, 0.70, 0.90),
}

# Large bet adjustments: when pot_relative_size > 0.75, skew toward premium/strong
_LARGE_BET_MULTIPLIERS: tuple[float, ...] = (1.0, 0.95, 0.75, 0.50, 0.35, 0.15)


# Category strength weights for estimated_hand_strength calculation.
# Higher weight = stronger category.
_CATEGORY_STRENGTHS = {
    "premium": 0.95,
    "strong": 0.80,
    "playable": 0.60,
    "marginal": 0.40,
    "speculative": 0.25,
    "trash": 0.10,
}


class RangeTracker:
    """Tracks opponent hand range probabilities based on observed actions.

    Each player has a RangeEstimate that starts at all 1.0 and narrows
    as preflop and postflop actions are observed. Ranges are maintained
    per player token and are fully isolated from each other.
    """

    def __init__(self) -> None:
        self._ranges: dict[str, RangeEstimate] = {}

    def reset(self, player_token: str) -> None:
        """Reset a single player's range to the full starting distribution."""
        self._ranges[player_token] = RangeEstimate()

    def reset_all(self) -> None:
        """Reset all tracked players to the full starting range (all 1.0)."""
        for token in self._ranges:
            self._ranges[token] = RangeEstimate()

    def update_preflop(self, player_token: str, action: str, position: str) -> None:
        """Update a player's range based on their preflop action and position.

        Args:
            player_token: Unique identifier for the player.
            action: The preflop action taken ("raise", "call", "3bet", "4bet").
            position: The player's position ("UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB").
        """
        # Ensure the player has a range entry
        if player_token not in self._ranges:
            self._ranges[player_token] = RangeEstimate()

        pos_group = _position_group(position)

        # Select the weight table based on action
        action_lower = action.lower()
        if action_lower in ("3bet", "3-bet"):
            weights = _THREE_BET_WEIGHTS[pos_group]
        elif action_lower in ("4bet", "4-bet"):
            weights = _FOUR_BET_WEIGHTS[pos_group]
        elif action_lower == "call":
            weights = _CALL_WEIGHTS[pos_group]
        elif action_lower == "raise":
            weights = _RAISE_WEIGHTS[pos_group]
        else:
            # Unknown action — don't modify range
            return

        current = self._ranges[player_token]

        # Apply weights as multipliers (narrowing). Use min to ensure monotonic.
        self._ranges[player_token] = RangeEstimate(
            premium=min(current.premium, max(0.0, current.premium * weights[0])),
            strong=min(current.strong, max(0.0, current.strong * weights[1])),
            playable=min(current.playable, max(0.0, current.playable * weights[2])),
            marginal=min(current.marginal, max(0.0, current.marginal * weights[3])),
            speculative=min(current.speculative, max(0.0, current.speculative * weights[4])),
            trash=min(current.trash, max(0.0, current.trash * weights[5])),
        )

    def update_postflop(
        self, player_token: str, action: str, street: str, pot_relative_size: float
    ) -> None:
        """Narrow a player's range based on their postflop action.

        Postflop updates are monotonic — category probabilities can only
        decrease, never increase.

        Args:
            player_token: Unique identifier for the player.
            action: The postflop action taken ("bet", "raise", "check", "call", "fold").
            street: The current street ("flop", "turn", "river").
            pot_relative_size: The size of the action relative to pot (0.0+).
        """
        if player_token not in self._ranges:
            self._ranges[player_token] = RangeEstimate()

        current = self._ranges[player_token]
        action_lower = action.lower()

        # Get base multipliers for this action
        multipliers = _POSTFLOP_MULTIPLIERS.get(action_lower)
        if multipliers is None:
            # Unknown action — don't modify
            return

        # Apply street-based tightening: later streets narrow more aggressively
        street_factor = 1.0
        if street == "turn":
            street_factor = 0.95
        elif street == "river":
            street_factor = 0.90

        # Compute adjusted multipliers
        adjusted = tuple(m * street_factor for m in multipliers)

        # Apply large bet adjustment for bet/raise actions
        if action_lower in ("bet", "raise") and pot_relative_size > 0.75:
            adjusted = tuple(
                a * lb for a, lb in zip(adjusted, _LARGE_BET_MULTIPLIERS)
            )

        # Apply multipliers (monotonic: new value <= old value)
        self._ranges[player_token] = RangeEstimate(
            premium=min(current.premium, max(0.0, current.premium * adjusted[0])),
            strong=min(current.strong, max(0.0, current.strong * adjusted[1])),
            playable=min(current.playable, max(0.0, current.playable * adjusted[2])),
            marginal=min(current.marginal, max(0.0, current.marginal * adjusted[3])),
            speculative=min(
                current.speculative, max(0.0, current.speculative * adjusted[4])
            ),
            trash=min(current.trash, max(0.0, current.trash * adjusted[5])),
        )

    def get_range(self, player_token: str) -> RangeEstimate:
        """Get the current range estimate for a player.

        If the player has not been tracked yet, returns the full starting range.
        """
        if player_token not in self._ranges:
            self._ranges[player_token] = RangeEstimate()
        return self._ranges[player_token]

    def estimated_hand_strength(self, player_token: str) -> float:
        """Compute a weighted average hand strength estimate for a player.

        Returns a value between 0.0 and 1.0 representing the expected strength
        of the opponent's hand given their current range estimate.
        """
        range_est = self.get_range(player_token)

        # Weighted average: each category's probability * its strength weight
        total_weight = 0.0
        total_strength = 0.0

        categories = [
            ("premium", range_est.premium),
            ("strong", range_est.strong),
            ("playable", range_est.playable),
            ("marginal", range_est.marginal),
            ("speculative", range_est.speculative),
            ("trash", range_est.trash),
        ]

        for cat_name, prob in categories:
            total_weight += prob
            total_strength += prob * _CATEGORY_STRENGTHS[cat_name]

        if total_weight == 0.0:
            return 0.0

        return total_strength / total_weight


# ─── 169 Hand-Class Range Tracker ─────────────────────────────────────────────

# Position-based opening range tables (Task 4.4)
# When a player raises from a given position, only these hand classes are expected.
POSITION_OPENING_RANGES: dict[str, set[str]] = {
    "early": {
        "AA", "KK", "QQ", "JJ", "TT", "99",
        "AKs", "AKo", "AQs", "AQo", "AJs", "KQs",
    },
    "middle": {
        "AA", "KK", "QQ", "JJ", "TT", "99", "88",
        "AKs", "AKo", "AQs", "AQo", "AJs", "ATs",
        "KQs", "KQo", "KJs", "QJs",
    },
    "late": {
        "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "55",
        "AKs", "AKo", "AQs", "AQo", "AJs", "ATs", "A9s", "A8s", "A5s", "A4s",
        "KQs", "KQo", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s", "87s", "76s",
    },
    "blind": {
        "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77",
        "AKs", "AKo", "AQs", "AQo", "AJs", "ATs",
        "KQs", "KQo", "KJs", "QJs", "JTs",
    },
}


def _get_hand_category(hand_class: str) -> str:
    """Return the category name for a given hand class.

    Looks up which of the 6 categories (premium, strong, playable, marginal,
    speculative, trash) a hand class belongs to.
    """
    for category, hand_classes in CATEGORY_TO_HAND_CLASSES.items():
        if hand_class in hand_classes:
            return category
    return "trash"


class ComboRangeTracker:
    """Tracks opponent hand ranges at the 169 hand-class level.

    Per-player ComboRange starts with all weights at 1.0 (full range).
    Weights are narrowed based on observed preflop and postflop actions.
    Provides backward compatibility via get_range_estimate() that aggregates
    into the existing 6-category RangeEstimate format.
    """

    def __init__(self) -> None:
        self._ranges: dict[str, ComboRange] = {}

    def _init_range(self) -> ComboRange:
        """Create a new ComboRange with all 169 weights at 1.0."""
        return ComboRange(weights={hc: 1.0 for hc in HAND_CLASSES_169})

    def reset(self, player_token: str) -> None:
        """Reset a player's range to full (all 1.0)."""
        self._ranges[player_token] = self._init_range()

    def reset_all(self) -> None:
        """Reset all players' ranges."""
        for token in self._ranges:
            self._ranges[token] = self._init_range()

    def get_combo_range(self, player_token: str) -> ComboRange:
        """Get the current ComboRange for a player (creates if not tracked)."""
        if player_token not in self._ranges:
            self._ranges[player_token] = self._init_range()
        return self._ranges[player_token]

    def update_preflop_combo(
        self, player_token: str, action: str, position: str
    ) -> None:
        """Narrow weights based on preflop action + position.

        Args:
            player_token: Unique identifier for the player.
            action: The preflop action taken ("raise", "call", "3bet", "4bet").
            position: The player's position ("UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB").
        """
        combo_range = self.get_combo_range(player_token)
        pos_group = _position_group(position)

        action_lower = action.lower()

        if action_lower == "raise":
            opening_range = POSITION_OPENING_RANGES.get(pos_group, set())
            for hc in HAND_CLASSES_169:
                if hc not in opening_range:
                    combo_range.weights[hc] = 0.0  # Zero out non-opening hands
        elif action_lower == "call":
            # Callers typically don't have premium hands (they'd raise)
            for hc in ["AA", "KK", "QQ", "AKs"]:
                combo_range.weights[hc] *= 0.3  # Reduce but don't zero
        elif action_lower in ("3bet", "3-bet"):
            # Very tight range for 3-bets
            three_bet_range = {"AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"}
            for hc in HAND_CLASSES_169:
                if hc not in three_bet_range:
                    combo_range.weights[hc] *= 0.1  # Heavily reduce
        elif action_lower in ("4bet", "4-bet"):
            four_bet_range = {"AA", "KK", "QQ", "AKs"}
            for hc in HAND_CLASSES_169:
                if hc not in four_bet_range:
                    combo_range.weights[hc] *= 0.05

    def update_postflop_combo(
        self,
        player_token: str,
        action: str,
        street: str,
        board: list[str],
        pot_relative_size: float,
    ) -> None:
        """Narrow weights based on postflop action.

        Args:
            player_token: Unique identifier for the player.
            action: The postflop action taken ("bet", "raise", "check", "call").
            street: The current street ("flop", "turn", "river").
            board: Community cards on the board.
            pot_relative_size: Size of the action relative to pot (0.0+).
        """
        combo_range = self.get_combo_range(player_token)

        # Street tightening factor
        street_factor = {"flop": 1.0, "turn": 0.9, "river": 0.8}.get(street, 1.0)

        action_lower = action.lower()

        if action_lower in ("bet", "raise"):
            # Aggressive actions retain strong hands, reduce weak
            for hc in HAND_CLASSES_169:
                category = _get_hand_category(hc)
                if category in ("premium", "strong"):
                    combo_range.weights[hc] *= 0.95 * street_factor
                elif category == "playable":
                    combo_range.weights[hc] *= 0.80 * street_factor
                elif category == "marginal":
                    combo_range.weights[hc] *= 0.50 * street_factor
                else:
                    combo_range.weights[hc] *= 0.25 * street_factor
            # Large bet additional narrowing
            if pot_relative_size > 0.75:
                for hc in HAND_CLASSES_169:
                    category = _get_hand_category(hc)
                    if category in ("marginal", "speculative", "trash"):
                        combo_range.weights[hc] *= 0.5
        elif action_lower == "check":
            # Checking reduces strong hands (they'd usually bet)
            for hc in HAND_CLASSES_169:
                category = _get_hand_category(hc)
                if category in ("premium", "strong"):
                    combo_range.weights[hc] *= 0.70 * street_factor
        elif action_lower == "call":
            # Calling reduces both extremes
            for hc in HAND_CLASSES_169:
                category = _get_hand_category(hc)
                if category == "premium":
                    combo_range.weights[hc] *= 0.75 * street_factor  # Would raise
                elif category == "trash":
                    combo_range.weights[hc] *= 0.30 * street_factor  # Would fold

        # Ensure monotonic narrowing: clamp to [0.0, current]
        for hc in HAND_CLASSES_169:
            combo_range.weights[hc] = max(0.0, combo_range.weights[hc])

    def get_range_estimate(self, player_token: str) -> RangeEstimate:
        """Aggregate 169-class weights into 6-category RangeEstimate for backward compatibility.

        Computes the average weight within each category to produce a single
        representative value per category.
        """
        combo_range = self.get_combo_range(player_token)

        category_averages: dict[str, float] = {}
        for category, hand_classes in CATEGORY_TO_HAND_CLASSES.items():
            if hand_classes:
                avg = sum(
                    combo_range.weights.get(hc, 0.0) for hc in hand_classes
                ) / len(hand_classes)
            else:
                avg = 0.0
            category_averages[category] = avg

        return RangeEstimate(
            premium=category_averages["premium"],
            strong=category_averages["strong"],
            playable=category_averages["playable"],
            marginal=category_averages["marginal"],
            speculative=category_averages["speculative"],
            trash=category_averages["trash"],
        )
