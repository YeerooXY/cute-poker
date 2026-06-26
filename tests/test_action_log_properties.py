"""Property-based tests for backend action_log sanitization.

Feature: poker-ui-action-log, Property 1: Broadcast action_log schema invariant

Verifies that _sanitize_action_log strips all internal/debug fields and outputs
only the allowed public fields for every entry, regardless of what arbitrary keys
the raw log contains.
"""

from hypothesis import given, settings, strategies as st

from poker.game import _sanitize_action_log


# Fields that are allowed in the sanitized output
ALLOWED_FIELDS = {"player", "action", "amount", "phase", "is_all_in"}

# Internal fields that must NEVER appear in output
INTERNAL_FIELDS = {
    "hole_cards", "ai_debug", "community", "is_bot",
    "current_bet", "committed", "stack", "to_call", "note",
}

# Strategy: generate an arbitrary action_log entry dict that may contain
# both allowed fields and internal/debug fields with random values.
arbitrary_action_entry = st.fixed_dictionaries(
    {},
    optional={
        # Allowed fields with realistic-ish values
        "player": st.text(min_size=0, max_size=20),
        "action": st.sampled_from(["fold", "check_call", "bet_raise", "small_blind", "big_blind", ""]),
        "amount": st.integers(min_value=0, max_value=10000),
        "phase": st.sampled_from(["preflop", "flop", "turn", "river", ""]),
        "is_all_in": st.booleans(),
        # Internal fields that should be stripped
        "hole_cards": st.lists(st.text(min_size=2, max_size=3), min_size=0, max_size=2),
        "ai_debug": st.dictionaries(st.text(max_size=5), st.text(max_size=10), max_size=3),
        "community": st.lists(st.text(min_size=2, max_size=3), min_size=0, max_size=5),
        "is_bot": st.booleans(),
        "current_bet": st.integers(min_value=0, max_value=10000),
        "committed": st.integers(min_value=0, max_value=10000),
        "stack": st.integers(min_value=0, max_value=10000),
        "to_call": st.integers(min_value=0, max_value=10000),
        "note": st.text(max_size=50),
    },
)

# Strategy: generate a list of arbitrary action_log entries (simulating a raw log)
arbitrary_action_log = st.lists(arbitrary_action_entry, min_size=0, max_size=20)


class TestBroadcastActionLogSchemaInvariant:
    """Property 1: Broadcast action_log schema invariant

    For any room state with any combination of action_log entries (including
    those with debug fields from bot actions), the sanitized broadcast action_log
    SHALL contain only the allowed public fields (player, action, amount, phase,
    is_all_in) for every entry, and SHALL never contain internal fields
    (hole_cards, ai_debug, community, is_bot, current_bet, committed, stack,
    to_call, note).
    """

    @settings(max_examples=200)
    @given(raw_log=arbitrary_action_log)
    def test_sanitized_output_contains_only_allowed_keys(self, raw_log: list[dict]):
        """**Validates: Requirements 1.1, 1.2, 1.4**

        Asserts:
        - Every entry in sanitized output has exactly the allowed keys
        - No internal/debug fields leak through
        - Output length matches input length (no entries dropped)
        """
        sanitized = _sanitize_action_log(raw_log)

        # Output length must match input length (one sanitized entry per raw entry)
        assert len(sanitized) == len(raw_log)

        for entry in sanitized:
            # Every output entry must have exactly the allowed keys
            assert set(entry.keys()) == ALLOWED_FIELDS, (
                f"Entry keys {set(entry.keys())} != allowed {ALLOWED_FIELDS}"
            )

            # No internal field should ever appear
            for field in INTERNAL_FIELDS:
                assert field not in entry, (
                    f"Internal field '{field}' leaked into sanitized output"
                )
