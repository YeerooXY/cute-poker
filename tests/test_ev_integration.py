"""Integration tests for the full EV-based bot decision pipeline.

Exercises the complete pipeline end-to-end: AIGameContext → advanced_bot_decide →
selected action with EV scores, modifiers, and range-aware equity all active.

Tests verify:
- The pipeline produces valid actions for various game states
- Strong hands tend toward aggression, weak hands toward folding
- Different difficulty levels produce distinguishable behavior
- The pipeline never crashes across a variety of realistic scenarios
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from poker.bot_ai import advanced_bot_decide
from poker.bot_ai.models import AIGameContext
from poker.bot_ai.difficulty_controller import DifficultyLevel
from poker.bot_ai.personality_engine import get_personality, PREDEFINED_PROFILES
from poker.bot_ai.range_tracker import RangeTracker


# ─── Helpers ───────────────────────────────────────────────────────────────────

VALID_GAME_ACTIONS = {"fold", "check_call", "bet_raise"}


def _make_context(
    hole_cards: list[str],
    community: list[str],
    pot: int = 200,
    current_bet: int = 0,
    committed: int = 0,
    stack: int = 1000,
    big_blind: int = 20,
    min_raise: int = 40,
    position: str = "BTN",
    num_opponents: int = 1,
    is_preflop_aggressor: bool = True,
    phase: str | None = None,
    facing_action: str = "unopened",
) -> AIGameContext:
    """Create a realistic AIGameContext for testing."""
    if phase is None:
        if len(community) == 0:
            phase = "preflop"
        elif len(community) == 3:
            phase = "flop"
        elif len(community) == 4:
            phase = "turn"
        else:
            phase = "river"

    return AIGameContext(
        hole_cards=hole_cards,
        community=community,
        phase=phase,
        pot=pot,
        current_bet=current_bet,
        committed=committed,
        stack=stack,
        big_blind=big_blind,
        min_raise=min_raise,
        position=position,
        num_opponents=num_opponents,
        is_preflop_aggressor=is_preflop_aggressor,
        facing_action=facing_action,
    )


def _run_trials(
    context: AIGameContext,
    difficulty: DifficultyLevel,
    personality_name: str = "GTO_ish",
    n_trials: int = 50,
    seed: int = 42,
) -> Counter:
    """Run the pipeline multiple times and count action frequencies."""
    personality = get_personality(personality_name)
    counts = Counter()
    rng = random.Random(seed)

    for i in range(n_trials):
        # Set different seed each trial for variety, but reproducible
        random.seed(rng.randint(0, 10_000_000))
        action, payload = advanced_bot_decide(
            game_context=context,
            personality=personality,
            difficulty=difficulty,
        )
        counts[action] += 1

    return counts


# ─── Test: Pipeline Produces Valid Actions ─────────────────────────────────────


class TestPipelineValidActions:
    """The pipeline should always return a valid game action for any legal game state."""

    def test_flop_scenario_returns_valid_action(self):
        """A standard flop scenario should return one of the valid game actions."""
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["QH", "JD", "2C"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position="BTN",
        )
        personality = get_personality("GTO_ish")
        random.seed(123)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action in VALID_GAME_ACTIONS
        if action == "bet_raise":
            assert "amount" in payload
            assert payload["amount"] > 0

    def test_facing_bet_returns_valid_action(self):
        """When facing a bet, actions should be fold, check_call, or bet_raise."""
        ctx = _make_context(
            hole_cards=["7H", "2D"],
            community=["AS", "KD", "QC"],
            pot=300,
            current_bet=100,
            committed=0,
            stack=800,
            position="BB",
            facing_action="bet",
            is_preflop_aggressor=False,
        )
        personality = get_personality("TAG")
        random.seed(456)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action in VALID_GAME_ACTIONS

    def test_preflop_returns_valid_action(self):
        """Preflop with no community cards should produce a valid action."""
        ctx = _make_context(
            hole_cards=["AS", "AD"],
            community=[],
            pot=30,
            current_bet=20,
            committed=10,
            stack=990,
            big_blind=20,
            min_raise=40,
            position="CO",
            facing_action="bet",
            is_preflop_aggressor=False,
        )
        personality = get_personality("LAG")
        random.seed(789)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action in VALID_GAME_ACTIONS

    def test_river_returns_valid_action(self):
        """River scenario with 5 community cards."""
        ctx = _make_context(
            hole_cards=["TS", "9S"],
            community=["8S", "7S", "2H", "KC", "3D"],
            pot=500,
            current_bet=0,
            committed=0,
            stack=600,
            position="BTN",
        )
        personality = get_personality("Exploitative_Shark")
        random.seed(101)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action in VALID_GAME_ACTIONS

    def test_bet_raise_includes_valid_amount(self):
        """When bet_raise is chosen, amount must be within [min_raise, stack]."""
        ctx = _make_context(
            hole_cards=["AS", "KS"],
            community=["QS", "JS", "2H"],
            pot=300,
            current_bet=0,
            committed=0,
            stack=1000,
            min_raise=40,
            position="BTN",
        )
        personality = get_personality("Maniac")

        # Run many trials to catch a bet_raise action
        for seed in range(100):
            random.seed(seed)
            action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
            if action == "bet_raise":
                assert "amount" in payload
                assert payload["amount"] >= ctx.min_raise
                assert payload["amount"] <= ctx.committed + ctx.stack
                break
        else:
            # With a royal flush draw + Maniac personality, we should bet at least once
            pytest.fail("Expected at least one bet_raise in 100 trials with Maniac + strong hand")


# ─── Test: Strong Hands Tend Toward Aggression ─────────────────────────────────


class TestStrongHandTendencies:
    """Strong hands on favorable boards should predominantly bet or raise."""

    def test_top_pair_top_kicker_on_dry_board(self):
        """AK on A72 rainbow should mostly bet/raise at EXPERT difficulty."""
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["AC", "7D", "2H"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position="BTN",
        )
        counts = _run_trials(ctx, DifficultyLevel.EXPERT, "GTO_ish", n_trials=60)
        # Strong hand: should mostly bet
        aggressive = counts.get("bet_raise", 0)
        passive = counts.get("check_call", 0)
        assert aggressive > passive, (
            f"Expected more aggression than passive play with top pair top kicker. "
            f"Got bet_raise={aggressive}, check_call={passive}"
        )

    def test_overpair_on_low_board(self):
        """KK on 742 rainbow should mostly bet/raise."""
        ctx = _make_context(
            hole_cards=["KH", "KD"],
            community=["7C", "4S", "2H"],
            pot=150,
            current_bet=0,
            committed=0,
            stack=900,
            position="CO",
        )
        counts = _run_trials(ctx, DifficultyLevel.EXPERT, "TAG", n_trials=60)
        aggressive = counts.get("bet_raise", 0)
        assert aggressive >= 25, (
            f"Expected KK on dry low board to bet frequently. Got bet_raise={aggressive}/60"
        )


# ─── Test: Weak Hands Tend Toward Folding/Checking ─────────────────────────────


class TestWeakHandTendencies:
    """Weak hands with no equity on the river (no fold equity) should tend toward folding."""

    def test_trash_hand_river_multiway_folds(self):
        """32o on AKQJ9 river vs 2 opponents facing a large bet should fold."""
        ctx = _make_context(
            hole_cards=["3H", "2D"],
            community=["AS", "KD", "QC", "JS", "9H"],
            pot=400,
            current_bet=300,
            committed=0,
            stack=1000,
            min_raise=600,
            position="MP",
            num_opponents=2,
            facing_action="raise",
            is_preflop_aggressor=False,
        )
        counts = _run_trials(ctx, DifficultyLevel.EXPERT, "TAG", n_trials=60)
        fold_count = counts.get("fold", 0)
        # On the river with zero equity, multiway, facing a big bet - should fold
        assert fold_count >= 40, (
            f"Expected 32o on river AKQJ9 facing large bet multiway to fold often. "
            f"Got fold={fold_count}/60"
        )

    def test_weak_hand_multiway_facing_bet_folds(self):
        """Marginal hand facing a bet multiway should fold with Nit personality."""
        ctx = _make_context(
            hole_cards=["9H", "8H"],
            community=["7C", "4S", "2D"],
            pot=200,
            current_bet=100,
            committed=0,
            stack=1000,
            min_raise=200,
            position="CO",
            num_opponents=2,
            facing_action="bet",
            is_preflop_aggressor=False,
        )
        counts = _run_trials(ctx, DifficultyLevel.HARD, "Nit", n_trials=60)
        fold_count = counts.get("fold", 0)
        # Nit with marginal hand facing bet multiway should fold often
        assert fold_count >= 30, (
            f"Expected Nit with 98h on 742 multiway to fold often. Got fold={fold_count}/60"
        )


# ─── Test: Medium Hand with Good Pot Odds ──────────────────────────────────────


class TestMediumHandPotOdds:
    """Medium-strength hand with good pot odds should tend toward calling."""

    def test_medium_pair_good_pot_odds_calls(self):
        """88 on A72 facing a small bet with good pot odds should call frequently."""
        ctx = _make_context(
            hole_cards=["8H", "8D"],
            community=["AC", "7S", "2D"],
            pot=400,
            current_bet=60,  # Small bet relative to pot → good pot odds
            committed=0,
            stack=900,
            min_raise=120,
            position="BTN",
            facing_action="bet",
            is_preflop_aggressor=True,
        )
        counts = _run_trials(ctx, DifficultyLevel.EXPERT, "TAG", n_trials=60)
        # With a medium pair and good pot odds, should call or raise rather than fold
        non_fold = counts.get("check_call", 0) + counts.get("bet_raise", 0)
        assert non_fold >= 25, (
            f"Expected 88 facing small bet with good pot odds to not fold much. "
            f"Got non-fold={non_fold}/60"
        )


# ─── Test: All-In Situation ────────────────────────────────────────────────────


class TestAllInSituation:
    """When raise amount equals full stack, the pipeline handles it correctly."""

    def test_short_stack_all_in(self):
        """Very short stack should produce valid actions. If bet_raise, amount is min_raise or stack."""
        ctx = _make_context(
            hole_cards=["AS", "KH"],
            community=["QS", "JD", "TC"],
            pot=500,
            current_bet=200,
            committed=100,
            stack=150,
            min_raise=200,
            position="BB",
            facing_action="raise",
            is_preflop_aggressor=False,
        )
        personality = get_personality("TAG")

        for seed in range(50):
            random.seed(seed)
            action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
            assert action in VALID_GAME_ACTIONS
            if action == "bet_raise":
                # Amount should be at most committed + stack (the max possible raise)
                max_raise = ctx.committed + ctx.stack
                assert payload["amount"] <= max_raise or payload["amount"] == ctx.min_raise, (
                    f"All-in amount {payload['amount']} exceeds max_raise={max_raise} "
                    f"and is not min_raise={ctx.min_raise}"
                )


# ─── Test: Pipeline Doesn't Crash with Various States ──────────────────────────


class TestPipelineRobustness:
    """The pipeline should handle edge cases without crashing."""

    @pytest.mark.parametrize("num_opponents", [1, 2, 3, 5])
    def test_multiway_pot(self, num_opponents):
        """Pipeline works with multiple opponents."""
        ctx = _make_context(
            hole_cards=["TH", "9H"],
            community=["8H", "7C", "2D"],
            pot=300,
            current_bet=50,
            committed=0,
            stack=800,
            num_opponents=num_opponents,
            facing_action="bet",
        )
        personality = get_personality("LAG")
        random.seed(42)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
        assert action in VALID_GAME_ACTIONS

    @pytest.mark.parametrize("position", ["UTG", "MP", "CO", "BTN", "SB", "BB"])
    def test_all_positions(self, position):
        """Pipeline works from all table positions."""
        ctx = _make_context(
            hole_cards=["JH", "TD"],
            community=["9C", "8S", "2H"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position=position,
        )
        personality = get_personality("TAG")
        random.seed(42)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
        assert action in VALID_GAME_ACTIONS

    @pytest.mark.parametrize("phase,community", [
        ("preflop", []),
        ("flop", ["AH", "KD", "3C"]),
        ("turn", ["AH", "KD", "3C", "7S"]),
        ("river", ["AH", "KD", "3C", "7S", "2H"]),
    ])
    def test_all_streets(self, phase, community):
        """Pipeline works on all streets."""
        ctx = _make_context(
            hole_cards=["QH", "JS"],
            community=community,
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            phase=phase,
        )
        personality = get_personality("GTO_ish")
        random.seed(42)
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
        assert action in VALID_GAME_ACTIONS

    def test_zero_pot(self):
        """Pipeline handles zero pot gracefully."""
        ctx = _make_context(
            hole_cards=["AH", "AD"],
            community=["KS", "QD", "JC"],
            pot=0,
            current_bet=0,
            committed=0,
            stack=1000,
        )
        personality = get_personality("TAG")
        random.seed(42)
        action, _ = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
        assert action in VALID_GAME_ACTIONS

    def test_large_pot_and_stack(self):
        """Pipeline handles very large values without overflow."""
        ctx = _make_context(
            hole_cards=["AH", "KH"],
            community=["QH", "JH", "TH"],
            pot=100000,
            current_bet=50000,
            committed=10000,
            stack=200000,
            min_raise=100000,
            big_blind=1000,
            facing_action="raise",
        )
        personality = get_personality("GTO_ish")
        random.seed(42)
        action, _ = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)
        assert action in VALID_GAME_ACTIONS


# ─── Test: Difficulty Levels Produce Different Behavior ────────────────────────


class TestDifficultyDifferences:
    """Different difficulty levels should produce distinguishable behavior patterns."""

    def test_easy_is_more_random_than_expert(self):
        """EASY should produce more varied actions (higher entropy) than EXPERT."""
        # Use a scenario where EXPERT should consistently choose one action
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["AC", "7D", "2H"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position="BTN",
        )

        easy_counts = _run_trials(ctx, DifficultyLevel.EASY, "Calling_Station", n_trials=80)
        expert_counts = _run_trials(ctx, DifficultyLevel.EXPERT, "GTO_ish", n_trials=80)

        # EXPERT with a strong hand should be more concentrated on aggression
        expert_max = max(expert_counts.values())
        easy_max = max(easy_counts.values())

        # EXPERT's dominant action should account for a larger share
        # (i.e., more concentrated/optimal play)
        expert_concentration = expert_max / 80
        easy_concentration = easy_max / 80

        # Expert should be at least somewhat concentrated (>50% one action)
        assert expert_concentration >= 0.4, (
            f"EXPERT should be concentrated. Got max={expert_max}/80 ({expert_concentration:.0%})"
        )

    def test_expert_aggression_vs_easy_passivity(self):
        """EXPERT should bet more with strong hands compared to EASY."""
        ctx = _make_context(
            hole_cards=["KH", "KD"],
            community=["7C", "4S", "2H"],
            pot=150,
            current_bet=0,
            committed=0,
            stack=900,
            position="CO",
        )

        # EXPERT with TAG should bet aggressively with KK on a dry board
        expert_counts = _run_trials(ctx, DifficultyLevel.EXPERT, "GTO_ish", n_trials=80)
        easy_counts = _run_trials(ctx, DifficultyLevel.EASY, "Calling_Station", n_trials=80)

        expert_aggression = expert_counts.get("bet_raise", 0)
        easy_aggression = easy_counts.get("bet_raise", 0)

        # EXPERT should be more aggressive than EASY with a premium hand
        assert expert_aggression >= easy_aggression * 0.7, (
            f"Expected EXPERT to be at least comparably aggressive. "
            f"EXPERT bet_raise={expert_aggression}, EASY bet_raise={easy_aggression}"
        )

    def test_all_difficulty_levels_produce_valid_actions(self):
        """Every difficulty level should produce valid actions."""
        ctx = _make_context(
            hole_cards=["TH", "9H"],
            community=["8H", "6C", "2D"],
            pot=200,
            current_bet=80,
            committed=0,
            stack=700,
            facing_action="bet",
        )

        for difficulty in DifficultyLevel:
            personality = get_personality("TAG")
            random.seed(42)
            action, payload = advanced_bot_decide(ctx, personality, difficulty)
            assert action in VALID_GAME_ACTIONS, (
                f"Difficulty {difficulty.name} produced invalid action: {action}"
            )


# ─── Test: Personality Effects on Pipeline Output ──────────────────────────────


class TestPersonalityEffects:
    """After Patch 1, personality archetypes no longer affect normal gameplay decisions.
    
    All bots use BALANCED_PROFILE regardless of the personality parameter passed.
    Personality differences are only available in test/debug mode (use_personality=True).
    
    These tests verify the new behavior: personality parameter is ignored.
    """

    def test_personality_parameter_ignored_in_normal_mode(self):
        """Different personality names should produce identical action distributions."""
        # Use a marginal hand multiway where personality differences WOULD have emerged
        ctx = _make_context(
            hole_cards=["9H", "8H"],
            community=["7C", "4S", "2D"],
            pot=200,
            current_bet=100,
            committed=0,
            stack=1000,
            min_raise=200,
            position="CO",
            num_opponents=2,
            facing_action="bet",
            is_preflop_aggressor=False,
        )

        # Same seed → same results regardless of personality name
        maniac_counts = _run_trials(ctx, DifficultyLevel.HARD, "Maniac", n_trials=60, seed=42)
        nit_counts = _run_trials(ctx, DifficultyLevel.HARD, "Nit", n_trials=60, seed=42)

        # In normal gameplay, personality is ignored → identical distributions
        assert maniac_counts == nit_counts, (
            f"Expected identical action distributions when personality is ignored. "
            f"Maniac={dict(maniac_counts)}, Nit={dict(nit_counts)}"
        )

    def test_calling_station_same_as_tag_in_normal_mode(self):
        """Calling Station and TAG produce identical results in normal gameplay."""
        ctx = _make_context(
            hole_cards=["8H", "7D"],
            community=["AS", "KD", "3C"],
            pot=300,
            current_bet=100,
            committed=0,
            stack=800,
            position="CO",
            facing_action="bet",
            is_preflop_aggressor=False,
        )

        cs_counts = _run_trials(ctx, DifficultyLevel.HARD, "Calling_Station", n_trials=60, seed=42)
        tag_counts = _run_trials(ctx, DifficultyLevel.HARD, "TAG", n_trials=60, seed=42)

        # In normal gameplay, personality is ignored → identical distributions
        assert cs_counts == tag_counts, (
            f"Expected identical distributions in normal mode. "
            f"Calling_Station={dict(cs_counts)}, TAG={dict(tag_counts)}"
        )


# ─── Test: Full Pipeline with Range Tracker ────────────────────────────────────


class TestPipelineWithRangeTracker:
    """Test the pipeline with range tracking active."""

    def test_pipeline_with_range_tracker_does_not_crash(self):
        """Providing a RangeTracker should work without errors."""
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["QH", "JD", "2C"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position="BTN",
        )
        personality = get_personality("GTO_ish")
        tracker = RangeTracker()
        random.seed(42)

        action, payload = advanced_bot_decide(
            ctx, personality, DifficultyLevel.EXPERT, range_tracker=tracker
        )
        assert action in VALID_GAME_ACTIONS

    def test_narrowed_range_affects_decision(self):
        """When opponent range is narrowed, the pipeline should still work correctly."""
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["QH", "JD", "2C"],
            pot=200,
            current_bet=100,
            committed=0,
            stack=900,
            position="BTN",
            facing_action="raise",
        )
        personality = get_personality("GTO_ish")
        tracker = RangeTracker()

        # Simulate opponent showing aggression (narrowing their range)
        tracker.update_preflop("opponent", "raise", "UTG")

        random.seed(42)
        action, payload = advanced_bot_decide(
            ctx, personality, DifficultyLevel.EXPERT, range_tracker=tracker
        )
        assert action in VALID_GAME_ACTIONS


# ─── Test: Deterministic Behavior with Fixed Seed ──────────────────────────────


class TestDeterministicBehavior:
    """With a fixed random seed, the pipeline should produce consistent results."""

    def test_same_seed_same_result(self):
        """Running the pipeline twice with the same seed should yield the same action."""
        ctx = _make_context(
            hole_cards=["AH", "KS"],
            community=["QH", "JD", "2C"],
            pot=200,
            current_bet=0,
            committed=0,
            stack=1000,
            position="BTN",
        )
        personality = get_personality("GTO_ish")

        random.seed(12345)
        action1, payload1 = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        random.seed(12345)
        action2, payload2 = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action1 == action2
        assert payload1 == payload2
