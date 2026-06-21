"""Property-based tests for Poker Table UX v2.

Feature: poker-table-ux-v2
"""

import re

from hypothesis import given, settings, strategies as st


# ─── Reference Implementations ───────────────────────────────────────────────

# Chip decomposition reference implementation
DENOMINATIONS = [1000, 500, 100, 25, 5, 1]
VALID_DENOMS = {1, 5, 25, 100, 500, 1000}


def decompose_chips(amount):
    """Greedy chip decomposition using minimum number of chips.

    Mirrors the JavaScript implementation in static/app.js:
        function decomposeChips(amount) {
            const result = [];
            let remaining = Math.max(0, Math.floor(amount));
            for (const denom of DENOMINATIONS) {
                if (remaining >= denom) {
                    const count = Math.floor(remaining / denom);
                    result.push({ denom, count });
                    remaining -= count * denom;
                }
                if (remaining === 0) break;
            }
            return result;
        }

    Args:
        amount: The chip amount to decompose into denominations.

    Returns:
        List of dicts with 'denom' and 'count' keys, in descending denomination order.
    """
    if not isinstance(amount, (int, float)) or amount != amount:  # NaN check
        return []
    remaining = max(0, int(amount))
    if remaining <= 0:
        return []
    result = []
    for denom in DENOMINATIONS:
        if remaining >= denom:
            count = remaining // denom
            result.append({'denom': denom, 'count': count})
            remaining -= count * denom
        if remaining == 0:
            break
    return result

def format_bb_mode(amount, big_blind):
    """Format amount in BB mode: 'X.X BB'"""
    if big_blind <= 0:
        return str(int(amount))
    value = amount / big_blind
    return f"{value:.1f} BB"


def format_token_bb_mode(raw_string, big_blind):
    """Format token string in BB mode: '+X.X BB'"""
    if big_blind <= 0:
        return raw_string
    numeric = float(''.join(c for c in raw_string if c.isdigit() or c == '.'))
    value = numeric / big_blind
    return f"+{value:.1f} BB"


# ─── Property 1: Chip Decomposition Correctness ─────────────────────────────
# Feature: poker-table-ux-v2, Property 1: Chip Decomposition Correctness


class TestChipDecompositionCorrectness:
    """Property 1: Chip Decomposition Correctness

    For any positive integer amount, the greedy chip decomposition SHALL produce
    denominations in strictly descending order, the sum of (denom × count) for all
    entries SHALL equal the original amount, and every denomination used SHALL be
    from the set {1, 5, 25, 100, 500, 1000}.
    """

    @settings(max_examples=200)
    @given(amount=st.integers(min_value=1, max_value=1_000_000))
    def test_chip_decomposition_correctness(self, amount: int):
        """**Validates: Requirements 1.1, 1.4**

        For any positive integer amount:
        1. Denominations appear in strictly descending order
        2. Sum of (denom × count) equals the original amount
        3. All denominations are from the valid set {1, 5, 25, 100, 500, 1000}
        """
        result = decompose_chips(amount)

        # Must produce a non-empty result for positive amounts
        assert len(result) > 0, (
            f"Expected non-empty decomposition for amount={amount}, got empty list"
        )

        # Property 1: Denominations in strictly descending order
        denoms = [entry['denom'] for entry in result]
        for i in range(len(denoms) - 1):
            assert denoms[i] > denoms[i + 1], (
                f"Denominations not in strictly descending order: "
                f"{denoms[i]} is not > {denoms[i + 1]} at index {i}. "
                f"Full decomposition: {result}"
            )

        # Property 2: Sum of (denom × count) equals original amount
        total = sum(entry['denom'] * entry['count'] for entry in result)
        assert total == amount, (
            f"Sum of decomposition ({total}) != original amount ({amount}). "
            f"Decomposition: {result}"
        )

        # Property 3: All denominations from valid set
        for entry in result:
            assert entry['denom'] in VALID_DENOMS, (
                f"Invalid denomination {entry['denom']} not in {VALID_DENOMS}. "
                f"Decomposition: {result}"
            )

        # Additional: all counts must be positive integers
        for entry in result:
            assert entry['count'] > 0, (
                f"Count must be positive, got {entry['count']} for denom {entry['denom']}. "
                f"Decomposition: {result}"
            )


# ─── Property 3: BB Mode Formatting ─────────────────────────────────────────
# Feature: poker-table-ux-v2, Property 3: BB Mode Formatting


class TestBBModeFormatting:
    """Property 3: BB Mode Formatting

    For any non-negative integer amount and any positive integer bigBlind,
    formatting in BB mode SHALL produce a string matching the pattern `X.X BB`
    where X.X equals `(amount / bigBlind).toFixed(1)`, and for token amounts
    SHALL produce `+X.X BB` format.
    """

    @settings(max_examples=200)
    @given(
        amount=st.integers(min_value=0, max_value=1_000_000),
        big_blind=st.integers(min_value=1, max_value=10_000),
    )
    def test_bb_mode_format_matches_pattern(self, amount: int, big_blind: int):
        """**Validates: Requirements 2.1, 2.2**

        Verifies that format_bb_mode produces output matching 'X.X BB' pattern
        where X.X equals (amount / big_blind) rounded to 1 decimal place.
        """
        result = format_bb_mode(amount, big_blind)

        # Must match the pattern: optional minus, digits, dot, one digit, space, BB
        assert re.fullmatch(r"-?\d+\.\d BB", result), (
            f"Expected pattern 'X.X BB', got '{result}' "
            f"for amount={amount}, big_blind={big_blind}"
        )

        # The numeric value must equal (amount / big_blind) rounded to 1 decimal
        expected_value = round(amount / big_blind, 1)
        expected = f"{expected_value:.1f} BB"
        assert result == expected, (
            f"Expected '{expected}', got '{result}' "
            f"for amount={amount}, big_blind={big_blind}"
        )

    @settings(max_examples=200)
    @given(
        amount=st.integers(min_value=0, max_value=1_000_000),
        big_blind=st.integers(min_value=1, max_value=10_000),
    )
    def test_token_bb_mode_format_matches_pattern(self, amount: int, big_blind: int):
        """**Validates: Requirements 2.1, 2.2**

        Verifies that format_token_bb_mode produces output matching '+X.X BB'
        pattern for token amounts in BB mode.
        """
        raw_string = f"!{amount}"
        result = format_token_bb_mode(raw_string, big_blind)

        # Must match the pattern: plus sign, optional minus, digits, dot, one digit, space, BB
        assert re.fullmatch(r"\+\-?\d+\.\d BB", result), (
            f"Expected pattern '+X.X BB', got '{result}' "
            f"for raw_string='{raw_string}', big_blind={big_blind}"
        )

        # The numeric value must equal (amount / big_blind) rounded to 1 decimal
        expected_value = round(amount / big_blind, 1)
        expected = f"+{expected_value:.1f} BB"
        assert result == expected, (
            f"Expected '{expected}', got '{result}' "
            f"for raw_string='{raw_string}', big_blind={big_blind}"
        )


# ─── Property 4: Chips Mode Formatting ──────────────────────────────────────
# Feature: poker-table-ux-v2, Property 4: Chips Mode Formatting


# Position calculator reference implementation
POSITION_MAP = {
    2: ['BTN', 'BB'],
    3: ['BTN', 'SB', 'BB'],
    4: ['BTN', 'SB', 'BB', 'UTG'],
    5: ['BTN', 'SB', 'BB', 'UTG', 'CO'],
    6: ['BTN', 'SB', 'BB', 'UTG', 'MP', 'CO'],
    7: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'CO'],
    8: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'MP+1', 'CO'],
}

POSITION_COLORS = {
    'BTN': 'green', 'CO': 'green',
    'MP': 'yellow', 'MP+1': 'yellow',
    'UTG': 'red', 'UTG+1': 'red',
    'SB': 'blue', 'BB': 'blue',
}


def get_position_name(active_player_count, seat_offset_from_dealer):
    """Get position name and color group for a seat.

    Mirrors the JavaScript PositionCalculator in static/app.js.

    Args:
        active_player_count: Number of active players at table (2-8).
        seat_offset_from_dealer: Clockwise offset from dealer (0 = dealer).

    Returns:
        Dict with 'name' and 'colorGroup' keys, or None if invalid input.
    """
    positions = POSITION_MAP.get(active_player_count)
    if not positions or seat_offset_from_dealer < 0 or seat_offset_from_dealer >= len(positions):
        return None
    name = positions[seat_offset_from_dealer]
    return {'name': name, 'colorGroup': POSITION_COLORS[name]}


def compute_deal_order(player_count, dealer_index):
    """Compute deal order clockwise from left-of-dealer.

    Mirrors the JavaScript DealAnimator logic in static/app.js.

    Args:
        player_count: Number of active players (2-8)
        dealer_index: Index of dealer in the player list (0-indexed)

    Returns:
        List of player indices in dealing order (one round = one card each
        clockwise from left-of-dealer)
    """
    order = []
    for i in range(1, player_count + 1):
        order.append((dealer_index + i) % player_count)
    return order


def compute_actual_deal_duration(player_count, stagger_ms, card_travel_ms, max_total=5000):
    """Compute total deal animation duration with dynamic stagger cap.

    The implementation dynamically caps stagger to fit within max_total.

    Mirrors the JavaScript DealAnimator logic in static/app.js:
        total_cards = 2 * player_count
        max_stagger = (max_total - card_travel_ms) // (total_cards - 1)
        actual_stagger = min(stagger_ms, max_stagger)
        duration = (total_cards - 1) * actual_stagger + card_travel_ms

    Args:
        player_count: Number of active players (2-8).
        stagger_ms: Delay between each successive card (80-150ms).
        card_travel_ms: Travel time for each card (200-400ms).
        max_total: Maximum allowed total duration (5000ms).

    Returns:
        Total deal animation duration in milliseconds.
    """
    total_cards = 2 * player_count
    if total_cards <= 1:
        return card_travel_ms
    max_stagger = (max_total - card_travel_ms) // (total_cards - 1)
    actual_stagger = min(stagger_ms, max_stagger)
    duration = (total_cards - 1) * actual_stagger + card_travel_ms
    return duration


def format_chips_mode(amount):
    """Format amount in chips mode: integer string, no BB suffix."""
    return str(int(amount))


def format_spectator_result(name, hand_classification, net_chip_change):
    """Format a single player's result for the spectator panel.

    Mirrors the JavaScript SpectatorResultsPanel formatting logic in static/app.js.

    Args:
        name: Player name string.
        hand_classification: Hand ranking string (e.g., "Two Pair", "Flush").
        net_chip_change: Integer chip change (positive for winners, negative for losers).

    Returns:
        Dict with formatted fields: name, handClassification, netChangeFormatted.
    """
    if net_chip_change >= 0:
        sign = "+"
    else:
        sign = "\u2212"  # Unicode minus
    formatted_change = sign + str(abs(net_chip_change))
    return {
        'name': name,
        'handClassification': hand_classification,
        'netChangeFormatted': formatted_change,
    }


class TestChipsModeFormatting:
    """Property 4: Chips Mode Formatting

    For any non-negative integer amount and any bigBlind value (including zero),
    formatting in chips mode SHALL return a string equal to
    `Math.floor(amount).toString()` without any "BB" suffix.
    """

    @settings(max_examples=200)
    @given(amount=st.integers(min_value=0, max_value=10_000_000))
    def test_chips_mode_output_is_digit_string_no_bb_suffix(self, amount: int):
        """**Validates: Requirements 2.4**

        Verifies that chips mode output:
        1. Is a string of digits (no "BB" suffix)
        2. Equals str(int(amount))
        """
        result = format_chips_mode(amount)

        # 1. Output is a string of digits only (no "BB" suffix, no letters)
        assert re.fullmatch(r"\d+", result), (
            f"Expected pure digit string, got '{result}' for amount={amount}"
        )
        assert "BB" not in result, (
            f"Output should not contain 'BB' suffix, got '{result}' for amount={amount}"
        )

        # 2. Output equals str(int(amount))
        expected = str(int(amount))
        assert result == expected, (
            f"Expected '{expected}', got '{result}' for amount={amount}"
        )



# ─── Property 7: Position Name and Color Assignment ─────────────────────────
# Feature: poker-table-ux-v2, Property 7: Position Name and Color Assignment


class TestPositionNameAndColorAssignment:
    """Property 7: Position Name and Color Assignment

    For any active player count from 2 to 8 and any seat offset from 0 to
    (count − 1), the position calculator SHALL return a name matching the defined
    mapping table and a color group matching the defined color scheme.
    """

    @settings(max_examples=200)
    @given(data=st.data())
    def test_position_name_matches_mapping_table(self, data):
        """**Validates: Requirements 5.1, 5.2, 5.5**

        For any player count 2-8 and offset 0 to count-1:
        1. Returned name matches the expected name from POSITION_MAP
        2. Color group matches the expected color from POSITION_COLORS
        3. Result is never None for valid inputs
        """
        player_count = data.draw(
            st.integers(min_value=2, max_value=8),
            label="player_count",
        )
        offset = data.draw(
            st.integers(min_value=0, max_value=player_count - 1),
            label="seat_offset",
        )

        result = get_position_name(player_count, offset)

        # Result must not be None for valid inputs
        assert result is not None, (
            f"Expected a valid result for player_count={player_count}, "
            f"offset={offset}, but got None"
        )

        # Name must match the defined mapping table
        expected_name = POSITION_MAP[player_count][offset]
        assert result['name'] == expected_name, (
            f"Expected name '{expected_name}' for player_count={player_count}, "
            f"offset={offset}, but got '{result['name']}'"
        )

        # Color group must match the defined color scheme
        expected_color = POSITION_COLORS[expected_name]
        assert result['colorGroup'] == expected_color, (
            f"Expected colorGroup '{expected_color}' for position '{expected_name}' "
            f"(player_count={player_count}, offset={offset}), "
            f"but got '{result['colorGroup']}'"
        )


# ─── Property 5: Deal Order Clockwise from Dealer ────────────────────────────
# Feature: poker-table-ux-v2, Property 5: Deal Order Clockwise from Dealer


class TestDealOrderClockwiseFromDealer:
    """Property 5: Deal Order Clockwise from Dealer

    For any set of active player seats (2–8 players) and any valid dealer seat
    among them, the computed deal order SHALL start with the first player clockwise
    (to the left) of the dealer and proceed clockwise, dealing one card to each
    player before repeating for the second card.
    """

    @settings(max_examples=200)
    @given(
        player_count=st.integers(min_value=2, max_value=8),
        data=st.data(),
    )
    def test_deal_order_clockwise_from_dealer(self, player_count: int, data):
        """**Validates: Requirements 4.1**

        For any player count 2-8 and valid dealer index:
        1. Deal order starts with the player immediately to the left (clockwise)
           of the dealer
        2. Deal order visits all players exactly once per round
        3. Deal order proceeds clockwise (each successive player is the next
           clockwise seat)
        4. Full two-card deal is the same order repeated twice
        """
        dealer_index = data.draw(
            st.integers(min_value=0, max_value=player_count - 1),
            label="dealer_index",
        )

        order = compute_deal_order(player_count, dealer_index)

        # 1. Starts with the player immediately to the left (clockwise) of dealer
        expected_first = (dealer_index + 1) % player_count
        assert order[0] == expected_first, (
            f"Deal order should start at index {expected_first} "
            f"(left of dealer at {dealer_index}), "
            f"but starts at {order[0]}. "
            f"player_count={player_count}, dealer_index={dealer_index}"
        )

        # 2. Visits all players exactly once per round
        assert len(order) == player_count, (
            f"Deal order should have {player_count} entries (one per player), "
            f"but has {len(order)}. "
            f"player_count={player_count}, dealer_index={dealer_index}"
        )
        assert set(order) == set(range(player_count)), (
            f"Deal order should contain each player index exactly once. "
            f"Got {order}, expected set {set(range(player_count))}. "
            f"player_count={player_count}, dealer_index={dealer_index}"
        )

        # 3. Proceeds clockwise (each successive player is the next clockwise seat)
        for i in range(len(order) - 1):
            expected_next = (order[i] + 1) % player_count
            assert order[i + 1] == expected_next, (
                f"Deal order should proceed clockwise: after index {order[i]}, "
                f"expected {expected_next} but got {order[i + 1]}. "
                f"Full order: {order}. "
                f"player_count={player_count}, dealer_index={dealer_index}"
            )

        # 4. Full two-card deal is the same order repeated twice
        full_deal = order + order
        assert len(full_deal) == 2 * player_count, (
            f"Full two-card deal should have {2 * player_count} entries, "
            f"got {len(full_deal)}. "
            f"player_count={player_count}, dealer_index={dealer_index}"
        )
        assert full_deal[:player_count] == full_deal[player_count:], (
            f"Full two-card deal should be the same order repeated. "
            f"First round: {full_deal[:player_count]}, "
            f"Second round: {full_deal[player_count:]}. "
            f"player_count={player_count}, dealer_index={dealer_index}"
        )


# ─── Property 5: Deal Order Clockwise from Dealer ────────────────────────────
# Feature: poker-table-ux-v2, Property 5: Deal Order Clockwise from Dealer


class TestDealOrderClockwiseFromDealer:
    """Property 5: Deal Order Clockwise from Dealer

    For any set of 2–8 active player seats and valid dealer seat: computed deal
    order starts left-of-dealer and proceeds clockwise, one card each then repeat.
    """

    @settings(max_examples=200)
    @given(data=st.data())
    def test_deal_order_starts_left_of_dealer_and_is_clockwise(self, data):
        """**Validates: Requirements 4.1**

        For any player count 2-8 and any valid dealer index:
        1. First player dealt to is immediately clockwise from dealer
        2. Order proceeds clockwise through all players
        3. All players appear exactly once per round
        """
        player_count = data.draw(
            st.integers(min_value=2, max_value=8),
            label="player_count",
        )
        dealer_index = data.draw(
            st.integers(min_value=0, max_value=player_count - 1),
            label="dealer_index",
        )

        order = compute_deal_order(player_count, dealer_index)

        # Must have exactly player_count entries (one round)
        assert len(order) == player_count, (
            f"Expected {player_count} entries in deal order, got {len(order)}"
        )

        # First player is left-of-dealer (clockwise)
        expected_first = (dealer_index + 1) % player_count
        assert order[0] == expected_first, (
            f"Expected first player to be {expected_first} (left of dealer {dealer_index}), "
            f"got {order[0]}"
        )

        # Order is clockwise (each subsequent index is +1 mod player_count from dealer)
        for i, player_idx in enumerate(order):
            expected = (dealer_index + 1 + i) % player_count
            assert player_idx == expected, (
                f"Expected player at position {i} to be {expected}, got {player_idx}. "
                f"dealer_index={dealer_index}, player_count={player_count}"
            )

        # All players appear exactly once
        assert set(order) == set(range(player_count)), (
            f"Not all players represented. order={order}, player_count={player_count}"
        )


# ─── Property 6: Deal Duration Cap ──────────────────────────────────────────
# Feature: poker-table-ux-v2, Property 6: Deal Duration Cap


class TestDealDurationCap:
    """Property 6: Deal Duration Cap

    For any player count from 2 to 8 and any stagger delay within the allowed
    range (80–150ms) and card travel time within range (200–400ms), the total deal
    animation duration SHALL not exceed 5000 milliseconds.
    """

    @settings(max_examples=200)
    @given(
        player_count=st.integers(min_value=2, max_value=8),
        stagger_ms=st.integers(min_value=80, max_value=150),
        card_travel_ms=st.integers(min_value=200, max_value=400),
    )
    def test_deal_duration_never_exceeds_5000ms(
        self, player_count: int, stagger_ms: int, card_travel_ms: int
    ):
        """**Validates: Requirements 4.6**

        For any valid combination of player count, stagger delay, and card travel
        time, the computed deal duration (with dynamic stagger capping) must not
        exceed 5000ms.
        """
        duration = compute_actual_deal_duration(player_count, stagger_ms, card_travel_ms)

        assert duration <= 5000, (
            f"Deal duration {duration}ms exceeds 5000ms cap. "
            f"player_count={player_count}, stagger_ms={stagger_ms}, "
            f"card_travel_ms={card_travel_ms}"
        )

    @settings(max_examples=200)
    @given(
        player_count=st.integers(min_value=2, max_value=8),
        stagger_ms=st.integers(min_value=80, max_value=150),
        card_travel_ms=st.integers(min_value=200, max_value=400),
    )
    def test_deal_duration_is_non_negative(
        self, player_count: int, stagger_ms: int, card_travel_ms: int
    ):
        """**Validates: Requirements 4.6**

        The deal duration must always be a non-negative value.
        """
        duration = compute_actual_deal_duration(player_count, stagger_ms, card_travel_ms)

        assert duration >= 0, (
            f"Deal duration {duration}ms is negative. "
            f"player_count={player_count}, stagger_ms={stagger_ms}, "
            f"card_travel_ms={card_travel_ms}"
        )


# ─── Property 8: Spectator Panel Results Completeness ────────────────────────
# Feature: poker-table-ux-v2, Property 8: Spectator Panel Results Completeness

# Strategy for hand classification strings
HAND_CLASSIFICATIONS = [
    "High Card", "Pair", "Two Pair", "Three of a Kind",
    "Straight", "Flush", "Full House", "Four of a Kind",
    "Straight Flush", "Royal Flush",
]


class TestSpectatorPanelResultsCompleteness:
    """Property 8: Spectator Panel Results Completeness

    For any non-empty list of showdown player results, the rendered spectator panel
    output SHALL contain each player's name, hand classification string, and a net
    chip change value formatted with "+" prefix for positive values and "\u2212"
    prefix for negative values.
    """

    @settings(max_examples=200)
    @given(
        results=st.lists(
            st.tuples(
                st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
                    min_size=1,
                    max_size=20,
                ),
                st.sampled_from(HAND_CLASSIFICATIONS),
                st.integers(min_value=-100_000, max_value=100_000),
            ),
            min_size=1,
            max_size=8,
        )
    )
    def test_spectator_panel_contains_all_player_data(self, results):
        """**Validates: Requirements 6.2, 6.3**

        For any non-empty list of showdown results:
        1. Each player's name is present in the formatted output
        2. Each player's hand classification is present in the formatted output
        3. Net chip change has correct sign prefix ("+" for positive/zero,
           "\u2212" for negative)
        """
        formatted_results = [
            format_spectator_result(name, hand_class, net_change)
            for name, hand_class, net_change in results
        ]

        for i, (name, hand_class, net_change) in enumerate(results):
            formatted = formatted_results[i]

            # 1. Player name is present in the output
            assert formatted['name'] == name, (
                f"Expected name '{name}' in result {i}, "
                f"got '{formatted['name']}'"
            )

            # 2. Hand classification is present in the output
            assert formatted['handClassification'] == hand_class, (
                f"Expected hand classification '{hand_class}' in result {i}, "
                f"got '{formatted['handClassification']}'"
            )

            # 3. Net chip change has correct sign prefix
            net_formatted = formatted['netChangeFormatted']
            if net_change >= 0:
                assert net_formatted.startswith("+"), (
                    f"Expected '+' prefix for non-negative net_change={net_change}, "
                    f"got '{net_formatted}' in result {i}"
                )
                expected_value = "+" + str(abs(net_change))
                assert net_formatted == expected_value, (
                    f"Expected '{expected_value}' for net_change={net_change}, "
                    f"got '{net_formatted}' in result {i}"
                )
            else:
                assert net_formatted.startswith("\u2212"), (
                    f"Expected '\u2212' (Unicode minus) prefix for negative "
                    f"net_change={net_change}, got '{net_formatted}' in result {i}"
                )
                expected_value = "\u2212" + str(abs(net_change))
                assert net_formatted == expected_value, (
                    f"Expected '{expected_value}' for net_change={net_change}, "
                    f"got '{net_formatted}' in result {i}"
                )

    @settings(max_examples=200)
    @given(
        results=st.lists(
            st.tuples(
                st.text(
                    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
                    min_size=1,
                    max_size=20,
                ),
                st.sampled_from(HAND_CLASSIFICATIONS),
                st.integers(min_value=-100_000, max_value=100_000),
            ),
            min_size=1,
            max_size=8,
        )
    )
    def test_spectator_panel_result_count_matches_input(self, results):
        """**Validates: Requirements 6.2, 6.3**

        The number of formatted results SHALL equal the number of input showdown
        results (every player is represented).
        """
        formatted_results = [
            format_spectator_result(name, hand_class, net_change)
            for name, hand_class, net_change in results
        ]

        assert len(formatted_results) == len(results), (
            f"Expected {len(results)} formatted results, "
            f"got {len(formatted_results)}"
        )
