"""Property-based tests for bot config invariants.

Feature: gameplay-improvements-tier1, Property 1: Bot config invariants

Verifies that when bots are created via the same logic used by add_bot(),
the resulting BotConfig always has use_advanced_ai=True, a valid difficulty,
and a valid style.
"""

import random

from hypothesis import given, settings, strategies as st

from poker.bot import create_bot_config, BotConfig


# Valid bot styles (same set used in game.py add_bot)
VALID_STYLES = ["tight_aggressive", "loose_aggressive", "calling_station", "maniac"]

# Valid difficulties assigned by add_bot()
VALID_DIFFICULTIES = ["medium", "hard", "expert"]

# Strategy: generate a random style from the valid set
style_strategy = st.sampled_from(VALID_STYLES)

# Strategy: generate a random difficulty from the valid set (mimics random.choice in add_bot)
difficulty_strategy = st.sampled_from(VALID_DIFFICULTIES)


class TestBotConfigInvariants:
    """Property 1: Bot config invariants

    For any bot creation via add_bot(), the resulting BotConfig SHALL have
    use_advanced_ai set to True, difficulty drawn from {medium, hard, expert},
    and style drawn from {tight_aggressive, loose_aggressive, calling_station, maniac}.
    """

    @settings(max_examples=100)
    @given(style=style_strategy, difficulty=difficulty_strategy)
    def test_bot_config_invariants(self, style: str, difficulty: str):
        """**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

        Mimics the add_bot() call path:
            difficulty = random.choice(["medium", "hard", "expert"])
            config = create_bot_config(style, use_advanced_ai=True, difficulty=difficulty)

        Asserts:
        - use_advanced_ai is always True
        - difficulty is in {medium, hard, expert}
        - style is in {tight_aggressive, loose_aggressive, calling_station, maniac}
        """
        # Replicate the exact call from add_bot()
        config = create_bot_config(style, use_advanced_ai=True, difficulty=difficulty)

        # Requirement 1.1: use_advanced_ai must be True
        assert config.use_advanced_ai is True, (
            f"Expected use_advanced_ai=True, got {config.use_advanced_ai}"
        )

        # Requirement 1.2: difficulty must be in the valid set
        assert config.difficulty in VALID_DIFFICULTIES, (
            f"Expected difficulty in {VALID_DIFFICULTIES}, got '{config.difficulty}'"
        )

        # Requirement 1.4: style must be in the valid set
        assert config.style in VALID_STYLES, (
            f"Expected style in {VALID_STYLES}, got '{config.style}'"
        )

        # Verify the config is a proper BotConfig instance
        assert isinstance(config, BotConfig)

        # Verify name and avatar are non-empty (basic sanity)
        assert config.name, "Bot name should not be empty"
        assert config.avatar, "Bot avatar should not be empty"
