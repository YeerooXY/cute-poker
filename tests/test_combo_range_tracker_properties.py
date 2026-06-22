"""Property-based tests for the ComboRangeTracker.

Tests the 169 hand-class range tracker for:
- Monotonic narrowing (Property 10)
- Category aggregation consistency (Property 13)
- Late position wider than early position (Property 14)
"""

from hypothesis import given, settings, strategies as st

from poker.bot_ai.range_tracker import ComboRangeTracker, POSITION_OPENING_RANGES
from poker.odds import HAND_CLASSES_169, CATEGORY_TO_HAND_CLASSES


# ─── Strategies ────────────────────────────────────────────────────────────────

PREFLOP_ACTIONS = st.sampled_from(["raise", "call"])
POSTFLOP_ACTIONS = st.sampled_from(["bet", "raise", "check", "call"])
STREETS = st.sampled_from(["flop", "turn", "river"])
POSITIONS = st.sampled_from(["UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB"])
POT_RELATIVE_SIZES = st.floats(min_value=0.0, max_value=2.0)
SAMPLE_BOARD = ["AH", "KS", "2D"]


# ─── Property 10: Monotonic Range Narrowing ───────────────────────────────────
# **Validates: Requirements 9.5**


class TestMonotonicNarrowing:
    """Property 10: For any sequence of range updates within a hand,
    every hand class weight at step N+1 is <= the weight at step N.

    Weights can only decrease (or stay the same), never increase.
    """

    @settings(max_examples=100, deadline=None)
    @given(
        actions=st.lists(
            st.sampled_from(["raise", "call", "bet", "check", "raise"]),
            min_size=1,
            max_size=5,
        )
    )
    def test_monotonic_narrowing(self, actions):
        """**Validates: Requirements 9.5**

        For any sequence of preflop + postflop actions, all 169 hand class
        weights must be non-increasing at each step.
        """
        tracker = ComboRangeTracker()
        player = "test_player"

        # Preflop action
        tracker.update_preflop_combo(player, actions[0], "BTN")
        prev_weights = dict(tracker.get_combo_range(player).weights)

        # Postflop actions
        for action in actions[1:]:
            tracker.update_postflop_combo(
                player, action, "flop", SAMPLE_BOARD, 0.5
            )
            current_weights = tracker.get_combo_range(player).weights
            for hc, weight in current_weights.items():
                assert weight <= prev_weights[hc] + 1e-9, (
                    f"{hc} weight increased from {prev_weights[hc]} to {weight} "
                    f"after action '{action}'"
                )
            prev_weights = dict(current_weights)

    @settings(max_examples=100, deadline=None)
    @given(
        position=POSITIONS,
        postflop_actions=st.lists(POSTFLOP_ACTIONS, min_size=1, max_size=4),
        pot_sizes=st.lists(
            st.floats(min_value=0.1, max_value=2.0), min_size=1, max_size=4
        ),
        streets=st.lists(STREETS, min_size=1, max_size=4),
    )
    def test_monotonic_narrowing_varied_streets(
        self, position, postflop_actions, pot_sizes, streets
    ):
        """**Validates: Requirements 9.5**

        Monotonic narrowing holds across different streets and pot sizes.
        """
        tracker = ComboRangeTracker()
        player = "test_player"

        # Start with a raise from the given position
        tracker.update_preflop_combo(player, "raise", position)
        prev_weights = dict(tracker.get_combo_range(player).weights)

        # Apply postflop actions with varied streets and pot sizes
        n = min(len(postflop_actions), len(pot_sizes), len(streets))
        for i in range(n):
            tracker.update_postflop_combo(
                player, postflop_actions[i], streets[i], SAMPLE_BOARD, pot_sizes[i]
            )
            current_weights = tracker.get_combo_range(player).weights
            for hc, weight in current_weights.items():
                assert weight <= prev_weights[hc] + 1e-9, (
                    f"{hc} weight increased from {prev_weights[hc]} to {weight} "
                    f"on street '{streets[i]}' after '{postflop_actions[i]}'"
                )
            prev_weights = dict(current_weights)


# ─── Property 13: Category Aggregation Consistency ────────────────────────────
# **Validates: Requirements 9.6**


class TestCategoryAggregationConsistency:
    """Property 13: get_range_estimate() correctly aggregates 169-class weights
    into 6-category averages matching manual computation.
    """

    @settings(max_examples=100, deadline=None)
    @given(
        weight_values=st.lists(
            st.floats(min_value=0.0, max_value=1.0),
            min_size=169,
            max_size=169,
        )
    )
    def test_aggregation_matches_manual_computation(self, weight_values):
        """**Validates: Requirements 9.6**

        For any random 169-class weight assignment, the 6-category averages
        from get_range_estimate() must match manual category-mean computation.
        """
        tracker = ComboRangeTracker()
        player = "test_player"

        # Build weights dict from the generated list
        weights = {hc: w for hc, w in zip(HAND_CLASSES_169, weight_values)}

        # Directly set weights
        combo_range = tracker.get_combo_range(player)
        combo_range.weights = dict(weights)

        # Get the aggregated range estimate
        range_est = tracker.get_range_estimate(player)

        # Manually compute expected category averages
        for category, hand_classes in CATEGORY_TO_HAND_CLASSES.items():
            if hand_classes:
                expected_avg = sum(
                    weights.get(hc, 0.0) for hc in hand_classes
                ) / len(hand_classes)
            else:
                expected_avg = 0.0

            actual = getattr(range_est, category)
            assert abs(actual - expected_avg) < 1e-9, (
                f"Category '{category}': expected avg={expected_avg:.6f}, "
                f"got {actual:.6f}"
            )

    @settings(max_examples=50, deadline=None)
    @given(
        preflop_action=PREFLOP_ACTIONS,
        position=POSITIONS,
    )
    def test_aggregation_after_preflop_update(self, preflop_action, position):
        """**Validates: Requirements 9.6**

        Category aggregation remains consistent after preflop range narrowing.
        """
        tracker = ComboRangeTracker()
        player = "test_player"

        tracker.update_preflop_combo(player, preflop_action, position)

        # Verify aggregation matches manual
        combo_range = tracker.get_combo_range(player)
        range_est = tracker.get_range_estimate(player)

        for category, hand_classes in CATEGORY_TO_HAND_CLASSES.items():
            if hand_classes:
                expected_avg = sum(
                    combo_range.weights.get(hc, 0.0) for hc in hand_classes
                ) / len(hand_classes)
            else:
                expected_avg = 0.0

            actual = getattr(range_est, category)
            assert abs(actual - expected_avg) < 1e-9, (
                f"Category '{category}' after {preflop_action} from {position}: "
                f"expected avg={expected_avg:.6f}, got {actual:.6f}"
            )


# ─── Property 14: Late Position Wider Than Early Position ─────────────────────
# **Validates: Requirements 10.3**


class TestLatePositionWiderThanEarly:
    """Property 14: After a raise action, late position retains more non-zero
    hand classes than early position.
    """

    @settings(max_examples=100, deadline=None)
    @given(data=st.data())
    def test_late_wider_than_early_after_raise(self, data):
        """**Validates: Requirements 10.3**

        After applying a raise, the count of non-zero hand classes for a late
        position (BTN) must be >= the count for an early position (UTG).
        """
        tracker = ComboRangeTracker()

        # Apply raise from early position (UTG)
        tracker.update_preflop_combo("early_player", "raise", "UTG")
        early_range = tracker.get_combo_range("early_player")
        early_nonzero = sum(1 for w in early_range.weights.values() if w > 0)

        # Apply raise from late position (BTN)
        tracker.update_preflop_combo("late_player", "raise", "BTN")
        late_range = tracker.get_combo_range("late_player")
        late_nonzero = sum(1 for w in late_range.weights.values() if w > 0)

        assert late_nonzero >= early_nonzero, (
            f"Late position (BTN) has {late_nonzero} non-zero hand classes "
            f"but early position (UTG) has {early_nonzero}. "
            f"Expected late >= early."
        )

    @settings(max_examples=50, deadline=None)
    @given(
        early_pos=st.sampled_from(["UTG", "UTG1"]),
        late_pos=st.sampled_from(["CO", "BTN"]),
    )
    def test_late_wider_than_early_various_positions(self, early_pos, late_pos):
        """**Validates: Requirements 10.3**

        For any early position vs any late position, raise retains more
        non-zero hand classes for the late position.
        """
        tracker = ComboRangeTracker()

        tracker.update_preflop_combo("early_player", "raise", early_pos)
        early_range = tracker.get_combo_range("early_player")
        early_nonzero = sum(1 for w in early_range.weights.values() if w > 0)

        tracker.update_preflop_combo("late_player", "raise", late_pos)
        late_range = tracker.get_combo_range("late_player")
        late_nonzero = sum(1 for w in late_range.weights.values() if w > 0)

        assert late_nonzero >= early_nonzero, (
            f"Late position ({late_pos}) has {late_nonzero} non-zero hand classes "
            f"but early position ({early_pos}) has {early_nonzero}. "
            f"Expected late >= early."
        )
