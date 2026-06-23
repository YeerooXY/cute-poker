"""Unit tests for simplified DifficultyConfig (Patch 1).

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

import pytest
from dataclasses import fields

from poker.bot_ai.models import DifficultyConfig, DifficultyLevel, ActiveSubsystems
from poker.bot_ai.difficulty_controller import get_difficulty_config, get_active_subsystems


class TestDifficultyConfigStructure:
    def test_exactly_three_fields(self):
        """DifficultyConfig has exactly 3 fields (Req 9.1)."""
        assert len(fields(DifficultyConfig)) == 3

    def test_field_names(self):
        """DifficultyConfig fields are: level, equity_error_max, active_subsystems."""
        field_names = [f.name for f in fields(DifficultyConfig)]
        assert field_names == ["level", "equity_error_max", "active_subsystems"]


class TestEquityErrorMax:
    def test_easy_error_max(self):
        """Easy level has equity_error_max = 0.15 (Req 9.2)."""
        config = get_difficulty_config(DifficultyLevel.EASY)
        assert config.equity_error_max == 0.15

    def test_medium_error_max(self):
        """Medium level has equity_error_max = 0.08 (Req 9.3)."""
        config = get_difficulty_config(DifficultyLevel.MEDIUM)
        assert config.equity_error_max == 0.08

    def test_hard_error_max(self):
        """Hard level has equity_error_max = 0.04 (Req 9.4)."""
        config = get_difficulty_config(DifficultyLevel.HARD)
        assert config.equity_error_max == 0.04

    def test_expert_error_max(self):
        """Expert level has equity_error_max = 0.02 (Req 9.5)."""
        config = get_difficulty_config(DifficultyLevel.EXPERT)
        assert config.equity_error_max == 0.02


class TestMonotonicSubsystems:
    def test_monotonic_inclusion(self):
        """Each higher level includes all subsystems from the level below (Req 9.6)."""
        levels = [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD, DifficultyLevel.EXPERT]
        for i in range(len(levels) - 1):
            lower = get_active_subsystems(levels[i])
            higher = get_active_subsystems(levels[i + 1])
            for field in fields(ActiveSubsystems):
                if getattr(lower, field.name):
                    assert getattr(higher, field.name), (
                        f"Level {levels[i+1].name} missing subsystem {field.name} "
                        f"that is active at {levels[i].name}"
                    )


class TestGetDifficultyConfig:
    def test_returns_config_for_each_level(self):
        """get_difficulty_config returns a DifficultyConfig for each level."""
        for level in DifficultyLevel:
            config = get_difficulty_config(level)
            assert isinstance(config, DifficultyConfig)
            assert config.level == level

    def test_active_subsystems_type(self):
        """Each config has an ActiveSubsystems instance."""
        for level in DifficultyLevel:
            config = get_difficulty_config(level)
            assert isinstance(config.active_subsystems, ActiveSubsystems)
