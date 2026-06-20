"""Opponent statistical modeling for the Advanced Bot AI system.

Tracks player statistics across hands and computes exploitation adjustments
based on observed tendencies. Each player is identified by a unique token
and their stats accumulate across multiple hands.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

from dataclasses import dataclass, field

from poker.bot_ai.models import ActionContext, ExploitAdjustments


@dataclass
class PlayerStats:
    """Statistical profile for a single opponent.

    Tracks raw counts and provides computed ratio properties for each
    tracked statistic. All ratios return 0.0 when their denominator
    (opportunities) is zero, avoiding division-by-zero errors.
    """

    hands_observed: int = 0
    vpip_count: int = 0
    pfr_count: int = 0
    fold_to_3bet_opportunities: int = 0
    fold_to_3bet_count: int = 0
    cbet_opportunities: int = 0
    cbet_count: int = 0
    fold_to_cbet_opportunities: int = 0
    fold_to_cbet_count: int = 0
    postflop_bets: int = 0
    postflop_calls: int = 0
    postflop_raises: int = 0
    river_call_opportunities: int = 0
    river_call_count: int = 0

    @property
    def vpip(self) -> float:
        """Voluntarily Put money In Pot percentage."""
        if self.hands_observed == 0:
            return 0.0
        return self.vpip_count / self.hands_observed

    @property
    def pfr(self) -> float:
        """Preflop Raise percentage."""
        if self.hands_observed == 0:
            return 0.0
        return self.pfr_count / self.hands_observed

    @property
    def fold_to_3bet(self) -> float:
        """Fold to 3-bet percentage."""
        if self.fold_to_3bet_opportunities == 0:
            return 0.0
        return self.fold_to_3bet_count / self.fold_to_3bet_opportunities

    @property
    def cbet_frequency(self) -> float:
        """Continuation bet frequency."""
        if self.cbet_opportunities == 0:
            return 0.0
        return self.cbet_count / self.cbet_opportunities

    @property
    def fold_to_cbet(self) -> float:
        """Fold to continuation bet percentage."""
        if self.fold_to_cbet_opportunities == 0:
            return 0.0
        return self.fold_to_cbet_count / self.fold_to_cbet_opportunities

    @property
    def aggression_factor(self) -> float:
        """Postflop aggression factor: (bets + raises) / max(calls, 1)."""
        return (self.postflop_bets + self.postflop_raises) / max(self.postflop_calls, 1)

    @property
    def river_call_frequency(self) -> float:
        """River call frequency."""
        if self.river_call_opportunities == 0:
            return 0.0
        return self.river_call_count / self.river_call_opportunities

    @property
    def is_exploitable(self) -> bool:
        """Whether enough data exists to activate exploitation adjustments."""
        return self.hands_observed >= 10


class OpponentModel:
    """Tracks and exploits opponent tendencies across hands.

    Maintains per-player statistics and computes exploitation adjustments
    when sufficient data has been collected (>= 10 hands observed).
    """

    def __init__(self) -> None:
        self._stats: dict[str, PlayerStats] = {}

    def _ensure_player(self, player_token: str) -> PlayerStats:
        """Get or create stats for a player."""
        if player_token not in self._stats:
            self._stats[player_token] = PlayerStats()
        return self._stats[player_token]

    def record_action(self, player_token: str, action: str, context: ActionContext) -> None:
        """Record an observed action and update the player's statistics.

        Args:
            player_token: Unique identifier for the player.
            action: The action taken ("fold", "call", "raise", "check", "bet").
            context: Additional context about the action situation.
        """
        stats = self._ensure_player(player_token)

        # Preflop VPIP: any voluntary money in (call, raise, bet)
        if context.street == "preflop" and action in ("call", "raise", "bet"):
            stats.vpip_count += 1

        # Preflop raise frequency
        if context.street == "preflop" and action == "raise":
            stats.pfr_count += 1

        # Fold to 3-bet tracking
        if context.is_3bet_situation:
            stats.fold_to_3bet_opportunities += 1
            if action == "fold":
                stats.fold_to_3bet_count += 1

        # Continuation bet tracking (player is the one who could cbet)
        if context.is_cbet_situation:
            stats.cbet_opportunities += 1
            if action in ("bet", "raise"):
                stats.cbet_count += 1

        # Fold to continuation bet tracking (player is facing a cbet)
        if context.facing_bet and context.is_cbet_situation:
            stats.fold_to_cbet_opportunities += 1
            if action == "fold":
                stats.fold_to_cbet_count += 1

        # Postflop aggression tracking
        if context.street != "preflop":
            if action == "bet":
                stats.postflop_bets += 1
            elif action == "call":
                stats.postflop_calls += 1
            elif action == "raise":
                stats.postflop_raises += 1

        # River call frequency
        if context.street == "river" and context.facing_bet:
            stats.river_call_opportunities += 1
            if action == "call":
                stats.river_call_count += 1

    def increment_hand(self, player_token: str) -> None:
        """Increment the hand counter for a player (called at start of new hand).

        Args:
            player_token: Unique identifier for the player.
        """
        stats = self._ensure_player(player_token)
        stats.hands_observed += 1

    def get_stats(self, player_token: str) -> PlayerStats:
        """Get the current statistics for a player.

        Returns a default PlayerStats if the player has not been observed.

        Args:
            player_token: Unique identifier for the player.

        Returns:
            The player's accumulated statistics.
        """
        return self._ensure_player(player_token)

    def get_exploit_adjustments(self, player_token: str) -> ExploitAdjustments:
        """Compute exploitation adjustments based on observed player tendencies.

        Adjustments only activate when hands_observed >= 10 (Req 2.5).
        When active:
        - fold_to_3bet > 70% → three_bet_bluff_boost (Req 2.2)
        - fold_to_cbet > 60% → cbet_frequency_boost (Req 2.3)
        - vpip > 50% → bluff_frequency_reduction + value_bet_boost (Req 2.4)

        The boost values increase monotonically with the underlying stat.

        Args:
            player_token: Unique identifier for the player.

        Returns:
            ExploitAdjustments with computed boosts and active flag.
        """
        stats = self._ensure_player(player_token)

        # Exploitation only activates after minimum sample size
        if not stats.is_exploitable:
            return ExploitAdjustments(active=False)

        three_bet_bluff_boost = 0.0
        cbet_frequency_boost = 0.0
        bluff_frequency_reduction = 0.0
        value_bet_boost = 0.0

        # Req 2.2: When fold_to_3bet > 70%, boost 3-bet bluffs
        # Monotonically increasing: linear scale from 0 at 70% to max at 100%
        if stats.fold_to_3bet > 0.70:
            # Scale linearly: (fold_to_3bet - 0.70) / 0.30 gives 0.0 to 1.0
            # Multiply by max boost of 0.5 for a reasonable range
            three_bet_bluff_boost = ((stats.fold_to_3bet - 0.70) / 0.30) * 0.5

        # Req 2.3: When fold_to_cbet > 60%, boost cbet frequency
        # Monotonically increasing: linear scale from 0 at 60% to max at 100%
        if stats.fold_to_cbet > 0.60:
            # Scale linearly: (fold_to_cbet - 0.60) / 0.40 gives 0.0 to 1.0
            # Multiply by max boost of 0.5 for a reasonable range
            cbet_frequency_boost = ((stats.fold_to_cbet - 0.60) / 0.40) * 0.5

        # Req 2.4: When vpip > 50%, reduce bluffs and boost value bets
        if stats.vpip > 0.50:
            # Scale linearly: (vpip - 0.50) / 0.50 gives 0.0 to 1.0
            scale = (stats.vpip - 0.50) / 0.50
            bluff_frequency_reduction = scale * 0.4
            value_bet_boost = scale * 0.4

        return ExploitAdjustments(
            three_bet_bluff_boost=three_bet_bluff_boost,
            cbet_frequency_boost=cbet_frequency_boost,
            bluff_frequency_reduction=bluff_frequency_reduction,
            value_bet_boost=value_bet_boost,
            active=True,
        )
