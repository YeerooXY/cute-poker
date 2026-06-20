"""Dynamic table-level strategic adjustments based on recent play.

Tracks hand history and computes adjustments to steal frequency, bluff
frequency, value sizing, and push-fold mode based on observed table tendencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from poker.bot_ai.models import DynamicAdjustments, HandSummary


@dataclass
class TableTendencies:
    """Aggregated table tendencies over recent hands."""

    recent_fold_frequency: float = 0.0  # Over last 20 hands
    recent_call_frequency: float = 0.0  # Over last 20 hands
    hand_history: list[HandSummary] = field(default_factory=list)


class DynamicAdjuster:
    """Tracks table-level tendencies and adjusts strategy dynamically.

    Records completed hand results and computes strategic adjustments
    based on recent fold/call frequencies, opponent 3-bet rates, and
    the bot's stack depth.
    """

    def __init__(self) -> None:
        self._tendencies = TableTendencies()

    def record_hand_result(self, hand_summary: HandSummary) -> None:
        """Append a completed hand summary to history."""
        self._tendencies.hand_history.append(hand_summary)

    def get_adjustments(
        self, bot_stack_bb: float, opponent_token: str | None = None
    ) -> DynamicAdjustments:
        """Calculate dynamic adjustments based on current table state.

        Uses the last 20 hands to compute fold/call frequencies and
        applies threshold-based rules to produce adjustments.

        Args:
            bot_stack_bb: The bot's current stack in big blinds.
            opponent_token: Optional specific opponent to check 3-bet freq for.

        Returns:
            DynamicAdjustments with all relevant boosts/reductions.
        """
        adjustments = DynamicAdjustments()

        # Compute table-level frequencies from the last 20 hands
        recent_hands = self._tendencies.hand_history[-20:]

        if recent_hands:
            fold_freq = self._compute_fold_frequency(recent_hands)
            call_freq = self._compute_call_frequency(recent_hands)

            # Update cached tendencies
            self._tendencies.recent_fold_frequency = fold_freq
            self._tendencies.recent_call_frequency = call_freq

            # Req 5.1: fold_frequency > 65% → boost steal and open range
            if fold_freq > 0.65:
                adjustments.steal_frequency_boost = min(
                    (fold_freq - 0.65) * 2.0, 0.30
                )
                adjustments.open_range_expansion = min(
                    (fold_freq - 0.65) * 1.5, 0.20
                )

            # Req 5.2: call_frequency > 50% → reduce bluffs, boost value sizing
            if call_freq > 0.50:
                adjustments.bluff_frequency_adjustment = -min(
                    (call_freq - 0.50) * 1.5, 0.25
                )
                adjustments.value_bet_sizing_boost = min(
                    (call_freq - 0.50) * 2.0, 0.30
                )

        # Req 5.3: opponent 3-bet > 12% over last 30 hands → boost 4-bet and trap
        if opponent_token is not None:
            three_bet_freq = self.get_opponent_3bet_frequency(opponent_token, last_n=30)
            if three_bet_freq > 0.12:
                adjustments.four_bet_frequency_boost = min(
                    (three_bet_freq - 0.12) * 2.5, 0.30
                )
                adjustments.trap_frequency_boost = min(
                    (three_bet_freq - 0.12) * 2.0, 0.25
                )

        # Req 5.4: bot stack < 15 big blinds → push-fold mode
        if bot_stack_bb < 15.0:
            adjustments.push_fold_mode = True

        return adjustments

    def get_opponent_3bet_frequency(
        self, player_token: str, last_n: int = 30
    ) -> float:
        """Compute how often a player appeared in players_who_raised.

        This approximates 3-bet frequency by counting how many of the
        last N hands the player was among those who raised.

        Args:
            player_token: The player identifier to look up.
            last_n: Number of recent hands to consider.

        Returns:
            Frequency as a float between 0.0 and 1.0.
        """
        recent_hands = self._tendencies.hand_history[-last_n:]
        if not recent_hands:
            return 0.0

        raised_count = sum(
            1 for hand in recent_hands if player_token in hand.players_who_raised
        )
        return raised_count / len(recent_hands)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_fold_frequency(hands: list[HandSummary]) -> float:
        """Compute fold frequency: total folds / total actions."""
        total_folded = 0
        total_actions = 0
        for hand in hands:
            folded = len(hand.players_who_folded)
            called = len(hand.players_who_called)
            raised = len(hand.players_who_raised)
            total_folded += folded
            total_actions += folded + called + raised
        if total_actions == 0:
            return 0.0
        return total_folded / total_actions

    @staticmethod
    def _compute_call_frequency(hands: list[HandSummary]) -> float:
        """Compute call frequency: total calls / total actions."""
        total_called = 0
        total_actions = 0
        for hand in hands:
            folded = len(hand.players_who_folded)
            called = len(hand.players_who_called)
            raised = len(hand.players_who_raised)
            total_called += called
            total_actions += folded + called + raised
        if total_actions == 0:
            return 0.0
        return total_called / total_actions
