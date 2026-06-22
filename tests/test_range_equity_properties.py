"""Property-based tests for range-aware equity system.

Tests the correctness properties of the range-aware equity calculator,
weight normalization, and 169 hand-class structure from poker.odds.
"""

from itertools import combinations

from hypothesis import given, settings, assume, strategies as st

from poker.odds import (
    FULL_DECK,
    HAND_CLASSES_169,
    SUITS,
    RANKS,
    _hand_class_to_combos,
    _normalize_weights,
    _sample_hand_from_range,
)


# ─── Strategies ───────────────────────────────────────────────────────────────

# Strategy for generating a valid hero hand (2 distinct cards from the deck)
st_card = st.sampled_from(FULL_DECK)


@st.composite
def st_hero_cards(draw):
    """Draw 2 distinct cards for hero's hole cards."""
    cards = draw(st.lists(st_card, min_size=2, max_size=2, unique=True))
    return cards


@st.composite
def st_board_cards(draw, hero_cards):
    """Draw 3-5 board cards that don't overlap with hero cards."""
    remaining = [c for c in FULL_DECK if c not in hero_cards]
    num_board = draw(st.integers(min_value=3, max_value=5))
    board = draw(
        st.lists(
            st.sampled_from(remaining),
            min_size=num_board,
            max_size=num_board,
            unique=True,
        )
    )
    return board


@st.composite
def st_game_cards(draw):
    """Draw hero cards + board cards with no overlap."""
    hero = draw(st.lists(st_card, min_size=2, max_size=2, unique=True))
    remaining = [c for c in FULL_DECK if c not in hero]
    num_board = draw(st.integers(min_value=3, max_value=5))
    board = draw(
        st.lists(
            st.sampled_from(remaining),
            min_size=num_board,
            max_size=num_board,
            unique=True,
        )
    )
    return hero, board


@st.composite
def st_combo_range_with_weights(draw, min_entries=10, max_entries=169):
    """Generate a combo_range dict with some non-zero weights."""
    num_entries = draw(st.integers(min_value=min_entries, max_value=max_entries))
    # Pick a subset of hand classes
    classes = draw(
        st.lists(
            st.sampled_from(HAND_CLASSES_169),
            min_size=num_entries,
            max_size=num_entries,
            unique=True,
        )
    )
    # Assign random positive weights
    combo_range = {}
    for hc in classes:
        weight = draw(st.floats(min_value=0.01, max_value=10.0))
        combo_range[hc] = weight
    return combo_range


# ─── Property 11: Blocker Filtering Invariant ─────────────────────────────────
# **Validates: Requirements 7.3**


class TestBlockerFilteringInvariant:
    """Property 11: No hand sampled from a combo_range shall contain any card
    present in the hero's hole cards or community cards."""

    @settings(max_examples=50, deadline=None)
    @given(data=st.data())
    def test_blocker_filtering_no_known_cards_in_sample(self, data):
        """**Validates: Requirements 7.3**

        For random hero cards, board cards, and a weighted combo_range,
        every hand sampled via _sample_hand_from_range must not contain
        any card from the known_cards set (hero + board).
        """
        hero_cards = data.draw(st.lists(st_card, min_size=2, max_size=2, unique=True))
        remaining_after_hero = [c for c in FULL_DECK if c not in hero_cards]
        num_board = data.draw(st.integers(min_value=3, max_value=5))
        board_cards = data.draw(
            st.lists(
                st.sampled_from(remaining_after_hero),
                min_size=num_board,
                max_size=num_board,
                unique=True,
            )
        )

        # Build a combo_range with some non-zero weights
        combo_range = data.draw(st_combo_range_with_weights(min_entries=10, max_entries=50))

        known_cards = set(hero_cards + board_cards)

        for _ in range(50):
            hand = _sample_hand_from_range(combo_range, known_cards)
            assert len(hand) == 2, f"Sampled hand should have 2 cards, got {len(hand)}"
            assert hand[0] not in known_cards, (
                f"Sampled card {hand[0]} is in known_cards {known_cards}"
            )
            assert hand[1] not in known_cards, (
                f"Sampled card {hand[1]} is in known_cards {known_cards}"
            )


# ─── Property 17: Weight Normalization Sums to 1.0 ───────────────────────────
# **Validates: Requirements 8.4**


class TestWeightNormalization:
    """Property 17: After _normalize_weights is applied, the result always sums
    to 1.0 within floating point tolerance of 1e-9."""

    @settings(max_examples=200)
    @given(data=st.data())
    def test_normalized_weights_sum_to_one(self, data):
        """**Validates: Requirements 8.4**

        For any combo_range with 10-169 entries and random positive float values,
        after normalization the weights must sum to 1.0 (tolerance 1e-9).
        """
        num_entries = data.draw(st.integers(min_value=10, max_value=169))
        classes = data.draw(
            st.lists(
                st.sampled_from(HAND_CLASSES_169),
                min_size=num_entries,
                max_size=num_entries,
                unique=True,
            )
        )
        combo_range = {}
        for hc in classes:
            weight = data.draw(st.floats(min_value=0.001, max_value=1000.0))
            combo_range[hc] = weight

        normalized = _normalize_weights(combo_range)

        total = sum(normalized.values())
        assert abs(total - 1.0) < 1e-9, (
            f"Normalized weights sum to {total}, expected 1.0 "
            f"(original sum was {sum(combo_range.values())})"
        )

    @settings(max_examples=50)
    @given(data=st.data())
    def test_normalized_weights_all_zero_gives_uniform(self, data):
        """**Validates: Requirements 8.4**

        When all weights are zero, normalization returns a uniform distribution
        that still sums to 1.0.
        """
        num_entries = data.draw(st.integers(min_value=10, max_value=169))
        classes = data.draw(
            st.lists(
                st.sampled_from(HAND_CLASSES_169),
                min_size=num_entries,
                max_size=num_entries,
                unique=True,
            )
        )
        combo_range = {hc: 0.0 for hc in classes}

        normalized = _normalize_weights(combo_range)

        total = sum(normalized.values())
        assert abs(total - 1.0) < 1e-9, (
            f"Normalized zero-weight range should sum to 1.0, got {total}"
        )
        # Each weight should be 1/n
        expected_weight = 1.0 / num_entries
        for hc, w in normalized.items():
            assert abs(w - expected_weight) < 1e-9, (
                f"Expected uniform weight {expected_weight}, got {w} for {hc}"
            )


# ─── Property 12: 169 Hand Classes Form Complete Partition ───────────────────
# **Validates: Requirements 9.1**


class TestHandClassPartition:
    """Property 12: The 169 hand classes, when expanded via _hand_class_to_combos,
    cover all 1326 possible 2-card combos from a 52-card deck with no overlaps."""

    def test_total_combo_count_equals_1326(self):
        """**Validates: Requirements 9.1**

        The total number of unique combos across all 169 hand classes must equal
        1326 (which is C(52, 2) = 52 × 51 / 2).
        """
        total = 0
        for hc in HAND_CLASSES_169:
            combos = _hand_class_to_combos(hc)
            total += len(combos)

        assert total == 1326, (
            f"Total combo count across all 169 hand classes is {total}, expected 1326"
        )

    def test_no_combo_appears_in_two_hand_classes(self):
        """**Validates: Requirements 9.1**

        No specific 2-card combo (as a frozenset for order-independence)
        should appear in more than one hand class expansion.
        """
        seen = {}  # frozenset(combo) -> hand_class that produced it
        for hc in HAND_CLASSES_169:
            combos = _hand_class_to_combos(hc)
            for combo in combos:
                key = frozenset(combo)
                assert key not in seen, (
                    f"Combo {combo} appears in both '{seen[key]}' and '{hc}'"
                )
                seen[key] = hc

    def test_every_possible_combo_maps_to_a_hand_class(self):
        """**Validates: Requirements 9.1**

        Every possible 2-card combination from the 52-card FULL_DECK must
        appear in exactly one hand class expansion.
        """
        # Build the set of all combos produced by hand classes
        all_class_combos = set()
        for hc in HAND_CLASSES_169:
            combos = _hand_class_to_combos(hc)
            for combo in combos:
                all_class_combos.add(frozenset(combo))

        # Build the set of all possible 2-card combos from the deck
        all_possible_combos = set()
        for combo in combinations(FULL_DECK, 2):
            all_possible_combos.add(frozenset(combo))

        assert len(all_possible_combos) == 1326, (
            f"Expected 1326 possible combos, got {len(all_possible_combos)}"
        )

        # Every possible combo must be in the hand class expansion
        missing = all_possible_combos - all_class_combos
        assert len(missing) == 0, (
            f"{len(missing)} combos are not covered by any hand class. "
            f"Examples: {list(missing)[:5]}"
        )

        # No extra combos in hand classes that aren't in possible combos
        extra = all_class_combos - all_possible_combos
        assert len(extra) == 0, (
            f"{len(extra)} combos in hand classes are not valid deck combos. "
            f"Examples: {list(extra)[:5]}"
        )
