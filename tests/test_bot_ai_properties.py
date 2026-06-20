"""Property-based tests for the Advanced Bot AI system.

Tests personality engine parameter validity, personality multiplier directionality,
preflop range assignment, postflop range narrowing monotonicity, and range tracking
isolation.
"""

from hypothesis import given, settings, strategies as st

from poker.bot_ai.personality_engine import (
    PREDEFINED_PROFILES,
    PokerPersonality,
    get_action_multipliers,
)
from poker.bot_ai.range_tracker import RangeTracker
from poker.bot_ai.models import ActionScores, RangeEstimate


# ─── Strategies ────────────────────────────────────────────────────────────────

# Strategy for generating PokerPersonality instances with parameters in [0, 1]
personality_strategy = st.builds(
    PokerPersonality,
    name=st.just("test"),
    vpip=st.floats(min_value=0.0, max_value=1.0),
    pfr=st.floats(min_value=0.0, max_value=1.0),
    three_bet=st.floats(min_value=0.0, max_value=1.0),
    aggression=st.floats(min_value=0.0, max_value=1.0),
    bluff_frequency=st.floats(min_value=0.0, max_value=1.0),
    call_down_looseness=st.floats(min_value=0.0, max_value=1.0),
    trap_frequency=st.floats(min_value=0.0, max_value=1.0),
    tilt_factor=st.floats(min_value=0.0, max_value=1.0),
    position_awareness=st.floats(min_value=0.0, max_value=1.0),
    exploitability=st.floats(min_value=0.0, max_value=1.0),
)

# All valid positions
positions = st.sampled_from(["UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB"])

# Preflop actions
preflop_actions = st.sampled_from(["raise", "call", "3bet", "4bet"])

# Postflop actions
postflop_actions = st.sampled_from(["bet", "raise", "check", "call", "fold"])

# Streets for postflop
postflop_streets = st.sampled_from(["flop", "turn", "river"])


# ─── Property 19: Personality parameter validity ──────────────────────────────
# **Validates: Requirements 6.1**


class TestPersonalityParameterValidity:
    """Property 19: For any PokerPersonality instance (all 8 predefined profiles),
    all parameters SHALL be in [0.0, 1.0]."""

    @settings(max_examples=50)
    @given(profile=st.sampled_from(list(PREDEFINED_PROFILES.values())))
    def test_predefined_profiles_parameters_in_range(self, profile: PokerPersonality):
        """**Validates: Requirements 6.1**"""
        assert 0.0 <= profile.vpip <= 1.0, f"{profile.name}.vpip={profile.vpip}"
        assert 0.0 <= profile.pfr <= 1.0, f"{profile.name}.pfr={profile.pfr}"
        assert 0.0 <= profile.three_bet <= 1.0, f"{profile.name}.three_bet={profile.three_bet}"
        assert 0.0 <= profile.aggression <= 1.0, f"{profile.name}.aggression={profile.aggression}"
        assert 0.0 <= profile.bluff_frequency <= 1.0, f"{profile.name}.bluff_frequency={profile.bluff_frequency}"
        assert 0.0 <= profile.call_down_looseness <= 1.0, f"{profile.name}.call_down_looseness={profile.call_down_looseness}"
        assert 0.0 <= profile.trap_frequency <= 1.0, f"{profile.name}.trap_frequency={profile.trap_frequency}"
        assert 0.0 <= profile.tilt_factor <= 1.0, f"{profile.name}.tilt_factor={profile.tilt_factor}"
        assert 0.0 <= profile.position_awareness <= 1.0, f"{profile.name}.position_awareness={profile.position_awareness}"
        assert 0.0 <= profile.exploitability <= 1.0, f"{profile.name}.exploitability={profile.exploitability}"


# ─── Property 20: Personality multipliers affect scores directionally ─────────
# **Validates: Requirements 6.4**


class TestPersonalityMultipliersDirectionality:
    """Property 20: For any base ActionScores and PokerPersonality, applying
    personality multipliers SHALL increase raise/bet score proportional to
    aggression and increase call score proportional to call_down_looseness."""

    @settings(max_examples=50)
    @given(
        aggression_low=st.floats(min_value=0.0, max_value=0.49),
        aggression_high=st.floats(min_value=0.5, max_value=1.0),
        call_looseness_low=st.floats(min_value=0.0, max_value=0.49),
        call_looseness_high=st.floats(min_value=0.5, max_value=1.0),
    )
    def test_higher_aggression_increases_raise_bet_multiplier(
        self,
        aggression_low: float,
        aggression_high: float,
        call_looseness_low: float,
        call_looseness_high: float,
    ):
        """**Validates: Requirements 6.4**"""
        # Create two personalities differing only in aggression
        personality_low_agg = PokerPersonality(
            name="low_agg",
            vpip=0.3,
            pfr=0.2,
            three_bet=0.1,
            aggression=aggression_low,
            bluff_frequency=0.2,
            call_down_looseness=0.4,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.5,
            exploitability=0.1,
        )
        personality_high_agg = PokerPersonality(
            name="high_agg",
            vpip=0.3,
            pfr=0.2,
            three_bet=0.1,
            aggression=aggression_high,
            bluff_frequency=0.2,
            call_down_looseness=0.4,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.5,
            exploitability=0.1,
        )

        mult_low = get_action_multipliers(personality_low_agg)
        mult_high = get_action_multipliers(personality_high_agg)

        # Higher aggression → higher raise/bet multipliers
        assert mult_high["raise"] >= mult_low["raise"], (
            f"raise: high_agg={mult_high['raise']} should >= low_agg={mult_low['raise']}"
        )
        assert mult_high["bet"] >= mult_low["bet"], (
            f"bet: high_agg={mult_high['bet']} should >= low_agg={mult_low['bet']}"
        )

        # Create two personalities differing only in call_down_looseness
        personality_low_call = PokerPersonality(
            name="low_call",
            vpip=0.3,
            pfr=0.2,
            three_bet=0.1,
            aggression=0.5,
            bluff_frequency=0.2,
            call_down_looseness=call_looseness_low,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.5,
            exploitability=0.1,
        )
        personality_high_call = PokerPersonality(
            name="high_call",
            vpip=0.3,
            pfr=0.2,
            three_bet=0.1,
            aggression=0.5,
            bluff_frequency=0.2,
            call_down_looseness=call_looseness_high,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.5,
            exploitability=0.1,
        )

        mult_low_call = get_action_multipliers(personality_low_call)
        mult_high_call = get_action_multipliers(personality_high_call)

        # Higher call_down_looseness → higher call multiplier
        assert mult_high_call["call"] >= mult_low_call["call"], (
            f"call: high_call={mult_high_call['call']} should >= low_call={mult_low_call['call']}"
        )


# ─── Property 1: Preflop range assignment reflects action strength ────────────
# **Validates: Requirements 1.1**


class TestPreflopRangeAssignment:
    """Property 1: For any action type and position, RangeTracker's resulting
    distribution SHALL weight premium/strong higher for stronger actions
    and all probabilities SHALL be non-negative."""

    @settings(max_examples=50)
    @given(position=positions)
    def test_stronger_actions_weight_premium_higher(self, position: str):
        """**Validates: Requirements 1.1**

        Stronger preflop actions (4bet > 3bet > raise > call) should assign
        more weight to premium hands relative to weaker categories.
        """
        tracker = RangeTracker()

        # Apply each action independently
        actions = ["call", "raise", "3bet", "4bet"]
        ranges = {}
        for action in actions:
            tracker_fresh = RangeTracker()
            tracker_fresh.update_preflop("player", action, position)
            ranges[action] = tracker_fresh.get_range("player")

        # For stronger actions, premium should be >= that of weaker actions
        # 4bet premium >= 3bet premium >= raise premium
        assert ranges["4bet"].premium >= ranges["3bet"].premium, (
            f"4bet premium ({ranges['4bet'].premium}) should >= 3bet premium ({ranges['3bet'].premium})"
        )
        assert ranges["3bet"].premium >= ranges["raise"].premium, (
            f"3bet premium ({ranges['3bet'].premium}) should >= raise premium ({ranges['raise'].premium})"
        )

        # All probabilities must be non-negative for every action
        for action in actions:
            r = ranges[action]
            assert r.premium >= 0.0, f"{action} premium < 0"
            assert r.strong >= 0.0, f"{action} strong < 0"
            assert r.playable >= 0.0, f"{action} playable < 0"
            assert r.marginal >= 0.0, f"{action} marginal < 0"
            assert r.speculative >= 0.0, f"{action} speculative < 0"
            assert r.trash >= 0.0, f"{action} trash < 0"

    @settings(max_examples=50)
    @given(action=preflop_actions, position=positions)
    def test_all_probabilities_non_negative(self, action: str, position: str):
        """**Validates: Requirements 1.1**

        All category probabilities must be non-negative after any preflop update.
        """
        tracker = RangeTracker()
        tracker.update_preflop("player", action, position)
        r = tracker.get_range("player")

        assert r.premium >= 0.0
        assert r.strong >= 0.0
        assert r.playable >= 0.0
        assert r.marginal >= 0.0
        assert r.speculative >= 0.0
        assert r.trash >= 0.0


# ─── Property 2: Postflop range narrowing is monotonic ────────────────────────
# **Validates: Requirements 1.2**


class TestPostflopRangeNarrowingMonotonicity:
    """Property 2: For any existing RangeEstimate and any postflop action,
    the updated estimate SHALL have category probabilities <= prior values."""

    @settings(max_examples=50)
    @given(
        action=postflop_actions,
        street=postflop_streets,
        pot_relative_size=st.floats(min_value=0.0, max_value=3.0),
    )
    def test_postflop_action_never_expands_range(
        self, action: str, street: str, pot_relative_size: float
    ):
        """**Validates: Requirements 1.2**

        After any postflop action, each category probability must be <= its prior value.
        """
        tracker = RangeTracker()
        # Get starting range (all 1.0)
        before = tracker.get_range("player")

        # Apply a postflop action
        tracker.update_postflop("player", action, street, pot_relative_size)
        after = tracker.get_range("player")

        assert after.premium <= before.premium, (
            f"premium expanded: {before.premium} -> {after.premium}"
        )
        assert after.strong <= before.strong, (
            f"strong expanded: {before.strong} -> {after.strong}"
        )
        assert after.playable <= before.playable, (
            f"playable expanded: {before.playable} -> {after.playable}"
        )
        assert after.marginal <= before.marginal, (
            f"marginal expanded: {before.marginal} -> {after.marginal}"
        )
        assert after.speculative <= before.speculative, (
            f"speculative expanded: {before.speculative} -> {after.speculative}"
        )
        assert after.trash <= before.trash, (
            f"trash expanded: {before.trash} -> {after.trash}"
        )

    @settings(max_examples=50)
    @given(
        preflop_action=preflop_actions,
        preflop_position=positions,
        postflop_action=postflop_actions,
        street=postflop_streets,
        pot_relative_size=st.floats(min_value=0.0, max_value=3.0),
    )
    def test_postflop_narrowing_after_preflop(
        self,
        preflop_action: str,
        preflop_position: str,
        postflop_action: str,
        street: str,
        pot_relative_size: float,
    ):
        """**Validates: Requirements 1.2**

        Even after a preflop action has already narrowed the range, a subsequent
        postflop action must still only narrow (never expand) probabilities.
        """
        tracker = RangeTracker()
        # First narrow via preflop
        tracker.update_preflop("player", preflop_action, preflop_position)
        before = tracker.get_range("player")

        # Then narrow via postflop
        tracker.update_postflop("player", postflop_action, street, pot_relative_size)
        after = tracker.get_range("player")

        assert after.premium <= before.premium
        assert after.strong <= before.strong
        assert after.playable <= before.playable
        assert after.marginal <= before.marginal
        assert after.speculative <= before.speculative
        assert after.trash <= before.trash


# ─── Property 3: Range tracking isolation ─────────────────────────────────────
# **Validates: Requirements 1.3**


class TestRangeTrackingIsolation:
    """Property 3: For any two distinct player tokens, updating one player
    SHALL leave the other's RangeEstimate unchanged."""

    @settings(max_examples=50)
    @given(
        action=preflop_actions,
        position=positions,
    )
    def test_preflop_update_does_not_affect_other_player(
        self, action: str, position: str
    ):
        """**Validates: Requirements 1.3**

        Updating player_a's range via preflop action should not change player_b's range.
        """
        tracker = RangeTracker()

        # Initialize both players
        range_b_before = tracker.get_range("player_b")

        # Update only player_a
        tracker.update_preflop("player_a", action, position)

        # player_b should be unchanged
        range_b_after = tracker.get_range("player_b")

        assert range_b_after.premium == range_b_before.premium
        assert range_b_after.strong == range_b_before.strong
        assert range_b_after.playable == range_b_before.playable
        assert range_b_after.marginal == range_b_before.marginal
        assert range_b_after.speculative == range_b_before.speculative
        assert range_b_after.trash == range_b_before.trash

    @settings(max_examples=50)
    @given(
        action=postflop_actions,
        street=postflop_streets,
        pot_relative_size=st.floats(min_value=0.0, max_value=3.0),
    )
    def test_postflop_update_does_not_affect_other_player(
        self, action: str, street: str, pot_relative_size: float
    ):
        """**Validates: Requirements 1.3**

        Updating player_a's range via postflop action should not change player_b's range.
        """
        tracker = RangeTracker()

        # Give player_b a known state by doing a preflop update first
        tracker.update_preflop("player_b", "raise", "UTG")
        range_b_before = tracker.get_range("player_b")

        # Update only player_a
        tracker.update_postflop("player_a", action, street, pot_relative_size)

        # player_b should be unchanged
        range_b_after = tracker.get_range("player_b")

        assert range_b_after.premium == range_b_before.premium
        assert range_b_after.strong == range_b_before.strong
        assert range_b_after.playable == range_b_before.playable
        assert range_b_after.marginal == range_b_before.marginal
        assert range_b_after.speculative == range_b_before.speculative
        assert range_b_after.trash == range_b_before.trash


# ─── Additional imports and strategies for tasks 3.5, 4.2, 4.3, 5.2, 5.3 ──────

from collections import Counter

from poker.bot_ai.board_analyzer import analyze_board, compute_range_advantage
from poker.bot_ai.opponent_model import OpponentModel, PlayerStats
from poker.bot_ai.models import ActionContext, ExploitAdjustments, RangeAdvantage

# Standard deck for card generation
RANKS = "23456789TJQKA"
SUITS = "HDCS"
ALL_CARDS = [f"{r}{s}" for r in RANKS for s in SUITS]


# Strategy for generating valid community cards (3-5 unique cards)
def community_cards_strategy(min_cards=3, max_cards=5):
    return st.lists(
        st.sampled_from(ALL_CARDS),
        min_size=min_cards,
        max_size=max_cards,
        unique=True,
    )


# ─── Property 4: Range reset produces full starting range ─────────────────────
# **Validates: Requirements 1.4**


class TestRangeReset:
    """Property 4: For any prior state of the RangeTracker (after arbitrary
    sequences of updates), calling reset_all SHALL produce RangeEstimates equal
    to the full starting distribution (all 1.0) for all tracked players."""

    @settings(max_examples=50)
    @given(
        actions=st.lists(
            st.tuples(
                st.sampled_from(["player_a", "player_b", "player_c"]),
                st.sampled_from(["preflop", "postflop"]),
                st.sampled_from(["raise", "call", "3bet", "4bet", "bet", "check", "fold"]),
                positions,
                postflop_streets,
                st.floats(min_value=0.0, max_value=3.0),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_reset_all_restores_full_range(self, actions):
        """**Validates: Requirements 1.4**

        After arbitrary sequences of preflop/postflop updates, reset_all must
        restore all tracked players to the full starting distribution (all 1.0).
        """
        tracker = RangeTracker()

        # Apply arbitrary sequence of updates
        for player, phase, action, position, street, pot_size in actions:
            if phase == "preflop" and action in ("raise", "call", "3bet", "4bet"):
                tracker.update_preflop(player, action, position)
            elif phase == "postflop" and action in ("bet", "raise", "check", "call", "fold"):
                tracker.update_postflop(player, action, street, pot_size)

        # Reset all ranges
        tracker.reset_all()

        # Verify all tracked players have full starting range (all 1.0)
        for player in ["player_a", "player_b", "player_c"]:
            r = tracker.get_range(player)
            assert r.premium == 1.0, f"{player} premium={r.premium} after reset_all"
            assert r.strong == 1.0, f"{player} strong={r.strong} after reset_all"
            assert r.playable == 1.0, f"{player} playable={r.playable} after reset_all"
            assert r.marginal == 1.0, f"{player} marginal={r.marginal} after reset_all"
            assert r.speculative == 1.0, f"{player} speculative={r.speculative} after reset_all"
            assert r.trash == 1.0, f"{player} trash={r.trash} after reset_all"


# ─── Property 10: Board texture classification consistency ────────────────────
# **Validates: Requirements 3.1**


class TestBoardTextureClassification:
    """Property 10: For any valid set of 3-5 community cards, 3+ cards of same
    suit → is_monotone=True; pair on board → is_paired=True; 3+ consecutive
    ranks → is_connected=True."""

    @settings(max_examples=50)
    @given(community=community_cards_strategy())
    def test_monotone_when_three_plus_same_suit(self, community: list[str]):
        """**Validates: Requirements 3.1**

        If 3 or more cards share the same suit, is_monotone must be True.
        """
        texture = analyze_board(community)
        suits = [c[1] for c in community]
        suit_counts = Counter(suits)
        max_suited = max(suit_counts.values())

        if max_suited >= 3:
            assert texture.is_monotone, (
                f"Expected is_monotone=True for {community} with {max_suited} same-suit cards"
            )

    @settings(max_examples=50)
    @given(community=community_cards_strategy())
    def test_paired_when_duplicate_rank(self, community: list[str]):
        """**Validates: Requirements 3.1**

        If any rank appears 2+ times, is_paired must be True.
        """
        texture = analyze_board(community)
        ranks = [c[0] for c in community]
        rank_counts = Counter(ranks)
        has_pair = any(cnt >= 2 for cnt in rank_counts.values())

        if has_pair:
            assert texture.is_paired, (
                f"Expected is_paired=True for {community} with duplicate rank"
            )

    @settings(max_examples=50)
    @given(community=community_cards_strategy())
    def test_connected_when_three_consecutive_ranks(self, community: list[str]):
        """**Validates: Requirements 3.1**

        If 3+ consecutive ranks are present, is_connected must be True.
        """
        texture = analyze_board(community)
        rank_order = "23456789TJQKA"
        rank_to_val = {r: i + 2 for i, r in enumerate(rank_order)}
        rank_values = [rank_to_val[c[0]] for c in community]
        unique = sorted(set(rank_values))

        # Check standard consecutive sequences
        has_consecutive = False
        for i in range(len(unique) - 2):
            if unique[i + 2] - unique[i] == 2:
                has_consecutive = True
                break

        # Check Ace-low (wheel): A-2-3
        if not has_consecutive and 14 in unique:
            low_unique = sorted(set([1 if v == 14 else v for v in rank_values]))
            for i in range(len(low_unique) - 2):
                if low_unique[i + 2] - low_unique[i] == 2:
                    has_consecutive = True
                    break

        if has_consecutive:
            assert texture.is_connected, (
                f"Expected is_connected=True for {community} with 3+ consecutive ranks"
            )


# ─── Property 11: Range advantage bounded ────────────────────────────────────
# **Validates: Requirements 3.4**


class TestRangeAdvantageBounded:
    """Property 11: For any valid community card set, the computed
    range_advantage.aggressor_advantage SHALL be in [0.0, 1.0]."""

    @settings(max_examples=50)
    @given(
        community=community_cards_strategy(),
        is_preflop_aggressor=st.booleans(),
    )
    def test_aggressor_advantage_in_unit_interval(
        self, community: list[str], is_preflop_aggressor: bool
    ):
        """**Validates: Requirements 3.4**

        The aggressor_advantage value must always be clamped to [0.0, 1.0].
        """
        result = compute_range_advantage(community, is_preflop_aggressor)
        assert 0.0 <= result.aggressor_advantage <= 1.0, (
            f"aggressor_advantage={result.aggressor_advantage} out of [0,1] "
            f"for community={community}, is_aggressor={is_preflop_aggressor}"
        )


# ─── Property 5: Opponent statistics match mathematical definitions ───────────
# **Validates: Requirements 2.1**


class TestOpponentStatisticsCorrectness:
    """Property 5: For any sequence of recorded ActionContexts for a player,
    the computed VPIP, PFR, Fold_to_3bet, etc. SHALL equal the ratio of the
    respective count to opportunities."""

    @settings(max_examples=50)
    @given(
        num_hands=st.integers(min_value=1, max_value=30),
        actions=st.lists(
            st.tuples(
                st.sampled_from(["fold", "call", "raise", "check", "bet"]),
                st.sampled_from(["preflop", "flop", "turn", "river"]),
                st.booleans(),  # is_3bet_situation
                st.booleans(),  # is_cbet_situation
                st.booleans(),  # facing_bet
                st.floats(min_value=0.0, max_value=2.0),
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_stats_equal_count_over_opportunities(
        self, num_hands: int, actions
    ):
        """**Validates: Requirements 2.1**

        Manually compute expected stats from the same sequence and verify
        they match the OpponentModel's computed properties.
        """
        model = OpponentModel()
        player = "test_player"

        # Record hands
        for _ in range(num_hands):
            model.increment_hand(player)

        # Track expected counts manually
        expected_vpip_count = 0
        expected_pfr_count = 0
        expected_fold_to_3bet_opp = 0
        expected_fold_to_3bet_count = 0
        expected_cbet_opp = 0
        expected_cbet_count = 0
        expected_fold_to_cbet_opp = 0
        expected_fold_to_cbet_count = 0
        expected_postflop_bets = 0
        expected_postflop_calls = 0
        expected_postflop_raises = 0
        expected_river_call_opp = 0
        expected_river_call_count = 0

        for action, street, is_3bet, is_cbet, facing_bet, pot_size in actions:
            ctx = ActionContext(
                street=street,
                action=action,
                position="UTG",
                is_3bet_situation=is_3bet,
                is_cbet_situation=is_cbet,
                facing_bet=facing_bet,
                pot_relative_size=pot_size,
            )
            model.record_action(player, action, ctx)

            # Replicate the same logic as OpponentModel.record_action
            if street == "preflop" and action in ("call", "raise", "bet"):
                expected_vpip_count += 1
            if street == "preflop" and action == "raise":
                expected_pfr_count += 1
            if is_3bet:
                expected_fold_to_3bet_opp += 1
                if action == "fold":
                    expected_fold_to_3bet_count += 1
            if is_cbet:
                expected_cbet_opp += 1
                if action in ("bet", "raise"):
                    expected_cbet_count += 1
            if facing_bet and is_cbet:
                expected_fold_to_cbet_opp += 1
                if action == "fold":
                    expected_fold_to_cbet_count += 1
            if street != "preflop":
                if action == "bet":
                    expected_postflop_bets += 1
                elif action == "call":
                    expected_postflop_calls += 1
                elif action == "raise":
                    expected_postflop_raises += 1
            if street == "river" and facing_bet:
                expected_river_call_opp += 1
                if action == "call":
                    expected_river_call_count += 1

        stats = model.get_stats(player)

        # Verify VPIP
        expected_vpip = expected_vpip_count / num_hands if num_hands > 0 else 0.0
        assert stats.vpip == expected_vpip, (
            f"VPIP: expected {expected_vpip}, got {stats.vpip}"
        )

        # Verify PFR
        expected_pfr = expected_pfr_count / num_hands if num_hands > 0 else 0.0
        assert stats.pfr == expected_pfr, (
            f"PFR: expected {expected_pfr}, got {stats.pfr}"
        )

        # Verify Fold to 3-bet
        expected_f3b = (
            expected_fold_to_3bet_count / expected_fold_to_3bet_opp
            if expected_fold_to_3bet_opp > 0
            else 0.0
        )
        assert stats.fold_to_3bet == expected_f3b, (
            f"Fold_to_3bet: expected {expected_f3b}, got {stats.fold_to_3bet}"
        )

        # Verify C-bet frequency
        expected_cbet_freq = (
            expected_cbet_count / expected_cbet_opp
            if expected_cbet_opp > 0
            else 0.0
        )
        assert stats.cbet_frequency == expected_cbet_freq, (
            f"Cbet_frequency: expected {expected_cbet_freq}, got {stats.cbet_frequency}"
        )

        # Verify Fold to C-bet
        expected_fold_cbet = (
            expected_fold_to_cbet_count / expected_fold_to_cbet_opp
            if expected_fold_to_cbet_opp > 0
            else 0.0
        )
        assert stats.fold_to_cbet == expected_fold_cbet, (
            f"Fold_to_cbet: expected {expected_fold_cbet}, got {stats.fold_to_cbet}"
        )

        # Verify Aggression Factor
        expected_af = (
            (expected_postflop_bets + expected_postflop_raises)
            / max(expected_postflop_calls, 1)
        )
        assert stats.aggression_factor == expected_af, (
            f"Aggression_factor: expected {expected_af}, got {stats.aggression_factor}"
        )

        # Verify River call frequency
        expected_rcf = (
            expected_river_call_count / expected_river_call_opp
            if expected_river_call_opp > 0
            else 0.0
        )
        assert stats.river_call_frequency == expected_rcf, (
            f"River_call_frequency: expected {expected_rcf}, got {stats.river_call_frequency}"
        )


# ─── Property 6: Exploit threshold activation ────────────────────────────────
# **Validates: Requirements 2.5**


class TestExploitThresholdActivation:
    """Property 6: Exploitation adjustments SHALL be inactive when
    hands_observed < 10, and active when hands_observed >= 10."""

    @settings(max_examples=50)
    @given(num_hands=st.integers(min_value=0, max_value=50))
    def test_exploit_inactive_below_threshold(self, num_hands: int):
        """**Validates: Requirements 2.5**

        Exploitation adjustments must be inactive when hands_observed < 10,
        and active when hands_observed >= 10.
        """
        model = OpponentModel()
        player = "threshold_test"

        for _ in range(num_hands):
            model.increment_hand(player)

        adjustments = model.get_exploit_adjustments(player)

        if num_hands < 10:
            assert adjustments.active is False, (
                f"Expected active=False with {num_hands} hands, got active=True"
            )
        else:
            assert adjustments.active is True, (
                f"Expected active=True with {num_hands} hands, got active=False"
            )

# ─── Additional imports for tasks 5.4, 5.5, 5.6, 7.2, 7.3 ───────────────────

from poker.bot_ai.bluff_calculator import compute_blocker_score, compute_bluff_score


# ─── Property 7: Fold-to-3bet exploitation monotonicity ──────────────────────
# **Validates: Requirements 2.2**


class TestFoldTo3BetExploitationMonotonicity:
    """Property 7: For any player with fold_to_3bet > 70% and active exploitation
    (hands >= 10), the three_bet_bluff_boost SHALL be positive and SHALL increase
    monotonically as fold_to_3bet increases."""

    @settings(max_examples=100)
    @given(
        fold_to_3bet_low=st.floats(min_value=0.71, max_value=0.84),
        fold_to_3bet_high=st.floats(min_value=0.85, max_value=1.0),
    )
    def test_three_bet_bluff_boost_monotonic(
        self, fold_to_3bet_low: float, fold_to_3bet_high: float
    ):
        """**Validates: Requirements 2.2**

        Two fold_to_3bet values both > 70% where one is higher must produce
        a higher three_bet_bluff_boost for the larger value.
        """
        # Create two models with different fold_to_3bet rates
        model_low = OpponentModel()
        model_low._stats["p"] = PlayerStats(
            hands_observed=20,
            fold_to_3bet_opportunities=100,
            fold_to_3bet_count=int(fold_to_3bet_low * 100),
        )

        model_high = OpponentModel()
        model_high._stats["p"] = PlayerStats(
            hands_observed=20,
            fold_to_3bet_opportunities=100,
            fold_to_3bet_count=int(fold_to_3bet_high * 100),
        )

        adj_low = model_low.get_exploit_adjustments("p")
        adj_high = model_high.get_exploit_adjustments("p")

        # Both must be active
        assert adj_low.active is True
        assert adj_high.active is True

        # Both boosts must be positive
        assert adj_low.three_bet_bluff_boost > 0.0, (
            f"Expected positive boost for fold_to_3bet={fold_to_3bet_low}, "
            f"got {adj_low.three_bet_bluff_boost}"
        )
        assert adj_high.three_bet_bluff_boost > 0.0, (
            f"Expected positive boost for fold_to_3bet={fold_to_3bet_high}, "
            f"got {adj_high.three_bet_bluff_boost}"
        )

        # Monotonicity: higher fold_to_3bet → higher boost
        assert adj_high.three_bet_bluff_boost >= adj_low.three_bet_bluff_boost, (
            f"Monotonicity violated: fold_to_3bet {fold_to_3bet_high} "
            f"(boost={adj_high.three_bet_bluff_boost}) should >= "
            f"fold_to_3bet {fold_to_3bet_low} (boost={adj_low.three_bet_bluff_boost})"
        )


# ─── Property 8: Fold-to-cbet exploitation monotonicity ──────────────────────
# **Validates: Requirements 2.3**


class TestFoldToCBetExploitationMonotonicity:
    """Property 8: For any player with fold_to_cbet > 60% and active exploitation
    (hands >= 10), the cbet_frequency_boost SHALL be positive and SHALL increase
    monotonically as fold_to_cbet increases."""

    @settings(max_examples=100)
    @given(
        fold_to_cbet_low=st.floats(min_value=0.61, max_value=0.79),
        fold_to_cbet_high=st.floats(min_value=0.80, max_value=1.0),
    )
    def test_cbet_frequency_boost_monotonic(
        self, fold_to_cbet_low: float, fold_to_cbet_high: float
    ):
        """**Validates: Requirements 2.3**

        Two fold_to_cbet values both > 60% where one is higher must produce
        a higher cbet_frequency_boost for the larger value.
        """
        model_low = OpponentModel()
        model_low._stats["p"] = PlayerStats(
            hands_observed=20,
            fold_to_cbet_opportunities=100,
            fold_to_cbet_count=int(fold_to_cbet_low * 100),
        )

        model_high = OpponentModel()
        model_high._stats["p"] = PlayerStats(
            hands_observed=20,
            fold_to_cbet_opportunities=100,
            fold_to_cbet_count=int(fold_to_cbet_high * 100),
        )

        adj_low = model_low.get_exploit_adjustments("p")
        adj_high = model_high.get_exploit_adjustments("p")

        # Both must be active
        assert adj_low.active is True
        assert adj_high.active is True

        # Both boosts must be positive
        assert adj_low.cbet_frequency_boost > 0.0, (
            f"Expected positive boost for fold_to_cbet={fold_to_cbet_low}, "
            f"got {adj_low.cbet_frequency_boost}"
        )
        assert adj_high.cbet_frequency_boost > 0.0, (
            f"Expected positive boost for fold_to_cbet={fold_to_cbet_high}, "
            f"got {adj_high.cbet_frequency_boost}"
        )

        # Monotonicity: higher fold_to_cbet → higher boost
        assert adj_high.cbet_frequency_boost >= adj_low.cbet_frequency_boost, (
            f"Monotonicity violated: fold_to_cbet {fold_to_cbet_high} "
            f"(boost={adj_high.cbet_frequency_boost}) should >= "
            f"fold_to_cbet {fold_to_cbet_low} (boost={adj_low.cbet_frequency_boost})"
        )


# ─── Property 9: Loose player exploitation ───────────────────────────────────
# **Validates: Requirements 2.4**


class TestLoosePlayerExploitation:
    """Property 9: For any player with vpip > 50% and active exploitation
    (hands >= 10), the bluff_frequency_reduction SHALL be positive and
    value_bet_boost SHALL be positive."""

    @settings(max_examples=100)
    @given(
        vpip_pct=st.floats(min_value=0.51, max_value=1.0),
    )
    def test_loose_player_gets_positive_adjustments(self, vpip_pct: float):
        """**Validates: Requirements 2.4**

        A player with vpip > 50% must trigger positive bluff_frequency_reduction
        and positive value_bet_boost.
        """
        # Construct PlayerStats with vpip > 50%
        # vpip = vpip_count / hands_observed
        hands = 20
        vpip_count = int(vpip_pct * hands)
        # Ensure vpip_count/hands > 0.50
        if vpip_count / hands <= 0.50:
            vpip_count = hands // 2 + 1

        model = OpponentModel()
        model._stats["p"] = PlayerStats(
            hands_observed=hands,
            vpip_count=vpip_count,
        )

        adj = model.get_exploit_adjustments("p")

        assert adj.active is True, "Expected active=True with 20 hands"

        # Verify vpip is actually > 50%
        stats = model.get_stats("p")
        assert stats.vpip > 0.50, f"Setup error: vpip={stats.vpip} not > 0.50"

        # Both adjustments must be positive
        assert adj.bluff_frequency_reduction > 0.0, (
            f"Expected positive bluff_frequency_reduction for vpip={stats.vpip}, "
            f"got {adj.bluff_frequency_reduction}"
        )
        assert adj.value_bet_boost > 0.0, (
            f"Expected positive value_bet_boost for vpip={stats.vpip}, "
            f"got {adj.value_bet_boost}"
        )


# ─── Property 12: Bluff score formula correctness ────────────────────────────
# **Validates: Requirements 4.1**


class TestBluffScoreFormulaCorrectness:
    """Property 12: For any blocker_score, fold_equity, range_advantage,
    backup_equity in [0.0, 1.0], the computed total_score SHALL equal
    blocker_score × 0.3 + fold_equity × 0.3 + range_advantage × 0.2 +
    backup_equity × 0.2."""

    @settings(max_examples=100)
    @given(
        hole_cards=st.just(["AH", "KD"]),
        community=st.just(["QH", "JH", "TH"]),
        bet_size_ratio=st.floats(min_value=0.0, max_value=3.0),
        equity=st.floats(min_value=0.0, max_value=1.0),
        aggressor_advantage=st.floats(min_value=0.0, max_value=1.0),
        street=st.sampled_from(["preflop", "flop", "turn", "river"]),
    )
    def test_total_score_equals_weighted_formula(
        self,
        hole_cards: list[str],
        community: list[str],
        bet_size_ratio: float,
        equity: float,
        aggressor_advantage: float,
        street: str,
    ):
        """**Validates: Requirements 4.1**

        The total_score returned by compute_bluff_score must equal the weighted
        sum of its component scores: blocker×0.3 + fold_equity×0.3 +
        range_advantage×0.2 + backup_equity×0.2.
        """
        # Use a PlayerStats with < 10 hands so fold_equity defaults to 0.35
        opponent_stats = PlayerStats(hands_observed=5)
        range_advantage = RangeAdvantage(aggressor_advantage=aggressor_advantage)

        result = compute_bluff_score(
            hole_cards=hole_cards,
            community=community,
            opponent_stats=opponent_stats,
            range_advantage=range_advantage,
            equity=equity,
            bet_size_ratio=bet_size_ratio,
            street=street,
        )

        # Verify total_score = component formula
        expected_total = (
            result.blocker_score * 0.3
            + result.fold_equity * 0.3
            + result.range_advantage * 0.2
            + result.backup_equity * 0.2
        )

        assert abs(result.total_score - expected_total) < 1e-9, (
            f"Formula mismatch: total_score={result.total_score}, "
            f"expected={expected_total} from components "
            f"blocker={result.blocker_score}, fold_eq={result.fold_equity}, "
            f"range_adv={result.range_advantage}, backup_eq={result.backup_equity}"
        )


# ─── Property 13: Blocker score ordering ─────────────────────────────────────
# **Validates: Requirements 4.2**


class TestBlockerScoreOrdering:
    """Property 13: For any board where a flush is possible (3+ same suit),
    holding a card of the flush suit (especially the Ace) SHALL produce a
    higher blocker_score than holding cards of non-flush suits."""

    @settings(max_examples=100)
    @given(
        flush_suit=st.sampled_from(["H", "D", "C", "S"]),
    )
    def test_flush_suit_card_has_higher_blocker_score(self, flush_suit: str):
        """**Validates: Requirements 4.2**

        Holding a card of the flush suit must produce higher blocker_score than
        holding cards of non-flush suits on a monotone board that doesn't allow
        straights or pairs (isolating the flush-blocker effect).
        """
        # Create monotone board with gapped ranks (no straight possible, no pair)
        # 2, 5, 9 of the flush suit — not consecutive, not paired
        community = [f"2{flush_suit}", f"5{flush_suit}", f"9{flush_suit}"]

        # Pick non-flush suits
        all_suits = ["H", "D", "C", "S"]
        non_flush_suits = [s for s in all_suits if s != flush_suit]

        # Hole cards with a card of flush suit (blocker)
        flush_blocker_cards = [f"7{flush_suit}", f"3{non_flush_suits[0]}"]

        # Hole cards with ONLY non-flush suit cards (no blockers possible)
        # Use ranks not on board to avoid paired-board blocker hits
        non_blocker_cards = [f"3{non_flush_suits[0]}", f"4{non_flush_suits[1]}"]

        score_with_flush_card = compute_blocker_score(flush_blocker_cards, community)
        score_without_flush_card = compute_blocker_score(non_blocker_cards, community)

        assert score_with_flush_card > score_without_flush_card, (
            f"Flush suit card should produce higher blocker score: "
            f"flush_card_score={score_with_flush_card}, "
            f"non_flush_score={score_without_flush_card}, "
            f"community={community}, flush_cards={flush_blocker_cards}, "
            f"non_flush_cards={non_blocker_cards}"
        )

    @settings(max_examples=100)
    @given(
        flush_suit=st.sampled_from(["H", "D", "C", "S"]),
    )
    def test_ace_of_flush_suit_higher_than_low_card(self, flush_suit: str):
        """**Validates: Requirements 4.2**

        The Ace of the flush suit must produce a higher blocker_score than
        a low card of the flush suit.
        """
        # Monotone board (3 cards of flush suit, but not Ace or 2)
        community = [f"K{flush_suit}", f"Q{flush_suit}", f"J{flush_suit}"]

        all_suits = ["H", "D", "C", "S"]
        non_flush_suit = [s for s in all_suits if s != flush_suit][0]

        # Ace of flush suit
        ace_cards = [f"A{flush_suit}", f"3{non_flush_suit}"]
        # Low card of flush suit
        low_cards = [f"2{flush_suit}", f"3{non_flush_suit}"]

        score_ace = compute_blocker_score(ace_cards, community)
        score_low = compute_blocker_score(low_cards, community)

        assert score_ace > score_low, (
            f"Ace of flush suit should score higher than low card: "
            f"ace_score={score_ace}, low_score={score_low}, "
            f"community={community}"
        )


# ─── Additional imports for tasks 7.4, 8.2, 8.3, 8.4, 8.5 ───────────────────

from poker.bot_ai.dynamic_adjuster import DynamicAdjuster
from poker.bot_ai.action_scorer import compute_base_scores, apply_personality
from poker.bot_ai.models import (
    BluffScore,
    BoardTexture,
    DynamicAdjustments,
    HandSummary,
    ScoringContext,
)


# ─── Property 14: Bluff threshold personality ordering ────────────────────────
# **Validates: Requirements 4.4**


class TestBluffThresholdPersonalityOrdering:
    """Property 14: For any two personalities where one has higher aggression
    and bluff_frequency, the action_scorer should give a higher bet/raise score
    to the more aggressive personality given the same bluff-favorable context."""

    @settings(max_examples=100)
    @given(
        aggression_low=st.floats(min_value=0.1, max_value=0.4),
        aggression_high=st.floats(min_value=0.6, max_value=1.0),
        bluff_freq_low=st.floats(min_value=0.05, max_value=0.2),
        bluff_freq_high=st.floats(min_value=0.3, max_value=0.6),
    )
    def test_aggressive_personality_scores_bet_raise_higher(
        self,
        aggression_low: float,
        aggression_high: float,
        bluff_freq_low: float,
        bluff_freq_high: float,
    ):
        """**Validates: Requirements 4.4**

        Given a bluff-favorable ScoringContext (low equity, good fold equity),
        the more aggressive personality should produce higher bet/raise scores
        after personality multipliers are applied.
        """
        # Create passive personality
        passive = PokerPersonality(
            name="passive",
            vpip=0.2,
            pfr=0.15,
            three_bet=0.05,
            aggression=aggression_low,
            bluff_frequency=bluff_freq_low,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.0,
        )

        # Create aggressive personality
        aggressive = PokerPersonality(
            name="aggressive",
            vpip=0.4,
            pfr=0.3,
            three_bet=0.15,
            aggression=aggression_high,
            bluff_frequency=bluff_freq_high,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.0,
        )

        # Bluff-favorable context: low equity, good fold equity, decent bluff score
        bluff_score = BluffScore(
            blocker_score=0.5,
            fold_equity=0.6,
            range_advantage=0.6,
            backup_equity=0.15,
            total_score=0.5 * 0.3 + 0.6 * 0.3 + 0.6 * 0.2 + 0.15 * 0.2,
        )

        ctx_passive = ScoringContext(
            equity=0.25,
            pot_odds=0.3,
            opponent_range=RangeEstimate(),
            board_texture=BoardTexture(is_dry=True),
            range_advantage=RangeAdvantage(aggressor_advantage=0.6),
            position="CO",
            street="flop",
            bluff_score=bluff_score,
            exploit_adjustments=ExploitAdjustments(),
            dynamic_adjustments=DynamicAdjustments(),
            personality=passive,
            stack_to_pot=10.0,
            is_preflop_aggressor=True,
        )

        ctx_aggressive = ScoringContext(
            equity=0.25,
            pot_odds=0.3,
            opponent_range=RangeEstimate(),
            board_texture=BoardTexture(is_dry=True),
            range_advantage=RangeAdvantage(aggressor_advantage=0.6),
            position="CO",
            street="flop",
            bluff_score=bluff_score,
            exploit_adjustments=ExploitAdjustments(),
            dynamic_adjustments=DynamicAdjustments(),
            personality=aggressive,
            stack_to_pot=10.0,
            is_preflop_aggressor=True,
        )

        legal_actions = ["fold", "check", "bet", "raise"]

        # Compute base scores (personality affects base via aggression in raise)
        base_passive = compute_base_scores(ctx_passive, legal_actions)
        base_aggressive = compute_base_scores(ctx_aggressive, legal_actions)

        # Apply personality multipliers
        final_passive = apply_personality(base_passive, passive)
        final_aggressive = apply_personality(base_aggressive, aggressive)

        # The aggressive personality should have higher bet and raise scores
        assert final_aggressive.bet >= final_passive.bet, (
            f"Aggressive bet ({final_aggressive.bet}) should >= passive bet ({final_passive.bet})"
        )
        assert final_aggressive.raise_ >= final_passive.raise_, (
            f"Aggressive raise ({final_aggressive.raise_}) should >= passive raise ({final_passive.raise_})"
        )


# ─── Property 15: Table fold frequency adjustments ───────────────────────────
# **Validates: Requirements 5.1**


class TestTableFoldFrequencyAdjustments:
    """Property 15: For any hand history where fold frequency over last 20 hands
    > 65%, DynamicAdjustments SHALL have steal_frequency_boost > 0 and
    open_range_expansion > 0. When fold frequency < 65%, both SHALL be 0."""

    @settings(max_examples=100)
    @given(
        num_folders=st.integers(min_value=3, max_value=4),
        num_callers=st.integers(min_value=0, max_value=1),
    )
    def test_high_fold_frequency_activates_steal_boost(
        self, num_folders: int, num_callers: int
    ):
        """**Validates: Requirements 5.1**

        When fold frequency > 65%, steal_frequency_boost and open_range_expansion
        must be positive.
        """
        adjuster = DynamicAdjuster()

        # Create 20 hands with controlled fold frequency
        # Each hand: num_folders fold, num_callers call, remainder raise
        num_raisers = max(0, 4 - num_folders - num_callers)
        for _ in range(20):
            hand = HandSummary(
                players_who_folded=[f"p{i}" for i in range(num_folders)],
                players_who_called=[f"c{i}" for i in range(num_callers)],
                players_who_raised=[f"r{i}" for i in range(num_raisers)],
                went_to_showdown=False,
                winner_token="p0",
                pot_size=100,
            )
            adjuster.record_hand_result(hand)

        # Compute expected fold frequency
        total_actions = num_folders + num_callers + num_raisers
        if total_actions == 0:
            return  # Skip degenerate case
        fold_freq = num_folders / total_actions

        adjustments = adjuster.get_adjustments(bot_stack_bb=50.0)

        if fold_freq > 0.65:
            assert adjustments.steal_frequency_boost > 0.0, (
                f"Expected steal_frequency_boost > 0 with fold_freq={fold_freq}, "
                f"got {adjustments.steal_frequency_boost}"
            )
            assert adjustments.open_range_expansion > 0.0, (
                f"Expected open_range_expansion > 0 with fold_freq={fold_freq}, "
                f"got {adjustments.open_range_expansion}"
            )
        else:
            assert adjustments.steal_frequency_boost == 0.0, (
                f"Expected steal_frequency_boost == 0 with fold_freq={fold_freq}, "
                f"got {adjustments.steal_frequency_boost}"
            )
            assert adjustments.open_range_expansion == 0.0, (
                f"Expected open_range_expansion == 0 with fold_freq={fold_freq}, "
                f"got {adjustments.open_range_expansion}"
            )


# ─── Property 16: Table call frequency adjustments ───────────────────────────
# **Validates: Requirements 5.2**


class TestTableCallFrequencyAdjustments:
    """Property 16: For any hand history where call frequency over last 20 hands
    > 50%, DynamicAdjustments SHALL have bluff_frequency_adjustment < 0 and
    value_bet_sizing_boost > 0. When call frequency < 50%, both SHALL be 0."""

    @settings(max_examples=100)
    @given(
        num_callers=st.integers(min_value=0, max_value=4),
        num_folders=st.integers(min_value=0, max_value=2),
    )
    def test_high_call_frequency_activates_value_boost(
        self, num_callers: int, num_folders: int
    ):
        """**Validates: Requirements 5.2**

        When call frequency > 50%, bluff_frequency_adjustment must be negative
        and value_bet_sizing_boost must be positive.
        """
        adjuster = DynamicAdjuster()

        # Ensure total actions > 0
        num_raisers = max(1, 4 - num_callers - num_folders)
        total_in_hand = num_callers + num_folders + num_raisers

        for _ in range(20):
            hand = HandSummary(
                players_who_folded=[f"f{i}" for i in range(num_folders)],
                players_who_called=[f"c{i}" for i in range(num_callers)],
                players_who_raised=[f"r{i}" for i in range(num_raisers)],
                went_to_showdown=False,
                winner_token="c0",
                pot_size=100,
            )
            adjuster.record_hand_result(hand)

        call_freq = num_callers / total_in_hand

        adjustments = adjuster.get_adjustments(bot_stack_bb=50.0)

        if call_freq > 0.50:
            assert adjustments.bluff_frequency_adjustment < 0.0, (
                f"Expected bluff_frequency_adjustment < 0 with call_freq={call_freq}, "
                f"got {adjustments.bluff_frequency_adjustment}"
            )
            assert adjustments.value_bet_sizing_boost > 0.0, (
                f"Expected value_bet_sizing_boost > 0 with call_freq={call_freq}, "
                f"got {adjustments.value_bet_sizing_boost}"
            )
        else:
            assert adjustments.bluff_frequency_adjustment == 0.0, (
                f"Expected bluff_frequency_adjustment == 0 with call_freq={call_freq}, "
                f"got {adjustments.bluff_frequency_adjustment}"
            )
            assert adjustments.value_bet_sizing_boost == 0.0, (
                f"Expected value_bet_sizing_boost == 0 with call_freq={call_freq}, "
                f"got {adjustments.value_bet_sizing_boost}"
            )


# ─── Property 17: Opponent 3-bet counter-adjustments ─────────────────────────
# **Validates: Requirements 5.3**


class TestOpponent3BetCounterAdjustments:
    """Property 17: For any opponent with 3-bet frequency > 12% over last 30
    hands, DynamicAdjustments SHALL have four_bet_frequency_boost > 0 and
    trap_frequency_boost > 0."""

    @settings(max_examples=100)
    @given(
        raise_count=st.integers(min_value=0, max_value=30),
    )
    def test_high_3bet_triggers_counter_adjustments(self, raise_count: int):
        """**Validates: Requirements 5.3**

        When an opponent appears in players_who_raised in > 12% of last 30 hands,
        four_bet_frequency_boost and trap_frequency_boost must be positive.
        """
        adjuster = DynamicAdjuster()
        opponent = "villain"

        # Create 30 hands, controlling how many times opponent raised
        for i in range(30):
            if i < raise_count:
                hand = HandSummary(
                    players_who_folded=["p1"],
                    players_who_called=["p2"],
                    players_who_raised=[opponent],
                    went_to_showdown=False,
                    winner_token="p1",
                    pot_size=100,
                )
            else:
                hand = HandSummary(
                    players_who_folded=["p1"],
                    players_who_called=["p2", opponent],
                    players_who_raised=[],
                    went_to_showdown=False,
                    winner_token="p1",
                    pot_size=100,
                )
            adjuster.record_hand_result(hand)

        three_bet_freq = raise_count / 30.0

        adjustments = adjuster.get_adjustments(bot_stack_bb=50.0, opponent_token=opponent)

        if three_bet_freq > 0.12:
            assert adjustments.four_bet_frequency_boost > 0.0, (
                f"Expected four_bet_frequency_boost > 0 with 3bet_freq={three_bet_freq}, "
                f"got {adjustments.four_bet_frequency_boost}"
            )
            assert adjustments.trap_frequency_boost > 0.0, (
                f"Expected trap_frequency_boost > 0 with 3bet_freq={three_bet_freq}, "
                f"got {adjustments.trap_frequency_boost}"
            )
        else:
            assert adjustments.four_bet_frequency_boost == 0.0, (
                f"Expected four_bet_frequency_boost == 0 with 3bet_freq={three_bet_freq}, "
                f"got {adjustments.four_bet_frequency_boost}"
            )
            assert adjustments.trap_frequency_boost == 0.0, (
                f"Expected trap_frequency_boost == 0 with 3bet_freq={three_bet_freq}, "
                f"got {adjustments.trap_frequency_boost}"
            )


# ─── Property 18: Push-fold mode ─────────────────────────────────────────────
# **Validates: Requirements 5.4**


class TestPushFoldMode:
    """Property 18: For any game state where bot's stack < 15 big blinds,
    push_fold_mode SHALL be True."""

    @settings(max_examples=100)
    @given(
        bot_stack_bb=st.floats(min_value=0.5, max_value=50.0),
    )
    def test_push_fold_mode_threshold(self, bot_stack_bb: float):
        """**Validates: Requirements 5.4**

        push_fold_mode must be True when bot_stack_bb < 15, and False otherwise.
        """
        adjuster = DynamicAdjuster()

        adjustments = adjuster.get_adjustments(bot_stack_bb=bot_stack_bb)

        if bot_stack_bb < 15.0:
            assert adjustments.push_fold_mode is True, (
                f"Expected push_fold_mode=True with stack={bot_stack_bb}bb, "
                f"got push_fold_mode=False"
            )
        else:
            assert adjustments.push_fold_mode is False, (
                f"Expected push_fold_mode=False with stack={bot_stack_bb}bb, "
                f"got push_fold_mode=True"
            )


# ─── Additional imports for tasks 9.2, 9.3, 10.2, 10.3, 10.4 ────────────────

from poker.bot_ai.preflop_charts import (
    POSITION_CHARTS,
    adjust_ranges_for_personality,
    PositionRange,
)
from poker.bot_ai.bet_sizer import compute_bet_size, SizingContext


# ─── Property 21: Positional range monotonicity ──────────────────────────────
# **Validates: Requirements 7.4, 7.5**


class TestPositionalRangeMonotonicity:
    """Property 21: For any two positions where one is strictly later
    (UTG < UTG1 < MP < HJ < CO < BTN), the later position's opening range
    SHALL be a superset of (or equal to) the earlier position's opening range."""

    POSITION_ORDER = ["UTG", "UTG1", "MP", "HJ", "CO", "BTN"]

    @settings(max_examples=50)
    @given(
        idx=st.integers(min_value=0, max_value=4),
    )
    def test_later_position_has_wider_or_equal_open_range(self, idx: int):
        """**Validates: Requirements 7.4, 7.5**

        For consecutive positions in the order UTG < UTG1 < MP < HJ < CO < BTN,
        the later position's open_range set must be a superset of (or equal to)
        the earlier position's open_range set.
        """
        earlier_pos = self.POSITION_ORDER[idx]
        later_pos = self.POSITION_ORDER[idx + 1]

        earlier_range = POSITION_CHARTS[earlier_pos].open_range
        later_range = POSITION_CHARTS[later_pos].open_range

        assert later_range >= earlier_range, (
            f"{later_pos} open_range (size={len(later_range)}) should be a superset of "
            f"{earlier_pos} open_range (size={len(earlier_range)}). "
            f"Missing hands: {earlier_range - later_range}"
        )


# ─── Property 22: Personality range adjustment ───────────────────────────────
# **Validates: Requirements 7.6**


class TestPersonalityRangeAdjustment:
    """Property 22: For any two PokerPersonality instances where one has higher
    vpip, the personality with higher vpip SHALL produce a wider (or equal)
    adjusted opening range for any given position."""

    @settings(max_examples=100)
    @given(
        vpip_low=st.floats(min_value=0.05, max_value=0.30),
        vpip_high=st.floats(min_value=0.35, max_value=0.80),
        position=st.sampled_from(["UTG", "UTG1", "MP", "HJ", "CO", "BTN"]),
    )
    def test_higher_vpip_produces_wider_open_range(
        self, vpip_low: float, vpip_high: float, position: str
    ):
        """**Validates: Requirements 7.6**

        A personality with higher vpip must produce a wider (or equal) adjusted
        opening range than a personality with lower vpip, for any position.
        """
        personality_low = PokerPersonality(
            name="low_vpip",
            vpip=vpip_low,
            pfr=0.18,
            three_bet=0.08,
            aggression=0.5,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        personality_high = PokerPersonality(
            name="high_vpip",
            vpip=vpip_high,
            pfr=0.18,
            three_bet=0.08,
            aggression=0.5,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        base_range = POSITION_CHARTS[position]

        adjusted_low = adjust_ranges_for_personality(base_range, personality_low)
        adjusted_high = adjust_ranges_for_personality(base_range, personality_high)

        assert len(adjusted_high.open_range) >= len(adjusted_low.open_range), (
            f"Higher vpip ({vpip_high}) should produce wider open_range than "
            f"lower vpip ({vpip_low}) for position {position}. "
            f"Got high={len(adjusted_high.open_range)}, low={len(adjusted_low.open_range)}"
        )


# ─── Property 23: Dry board cbet sizing ──────────────────────────────────────
# **Validates: Requirements 8.1**


class TestDryBoardCbetSizing:
    """Property 23: For any dry board SizingContext with a given pot, the
    computed cbet SHALL be between 25% and 40% of pot (before noise, clamped
    to [min_raise, max_raise])."""

    @settings(max_examples=100)
    @given(
        aggression=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_dry_board_cbet_between_25_and_40_pct(self, aggression: float):
        """**Validates: Requirements 8.1**

        On a dry board flop/turn, compute_bet_size must return a value between
        25% and 40% of pot when min/max don't interfere.
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = SizingContext(
            street="flop",
            board_texture=BoardTexture(is_dry=True, is_wet=False),
            range_advantage=RangeAdvantage(aggressor_advantage=0.5, nut_advantage=False),
            pot=1000,
            is_value_bet=True,
            is_polarized=False,
            personality=personality,
        )

        amount = compute_bet_size(ctx, min_raise=10, max_raise=5000)
        pct = amount / 1000.0

        assert 0.25 <= pct <= 0.40, (
            f"Dry board cbet should be 25%-40% of pot. "
            f"Got {amount} ({pct*100:.1f}%) with aggression={aggression}"
        )


# ─── Property 24: Wet board cbet sizing ──────────────────────────────────────
# **Validates: Requirements 8.2**


class TestWetBoardCbetSizing:
    """Property 24: For any wet board SizingContext with a given pot, the
    computed cbet SHALL be between 55% and 75% of pot (before noise, clamped
    to [min_raise, max_raise])."""

    @settings(max_examples=100)
    @given(
        aggression=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_wet_board_cbet_between_55_and_75_pct(self, aggression: float):
        """**Validates: Requirements 8.2**

        On a wet board flop/turn, compute_bet_size must return a value between
        55% and 75% of pot when min/max don't interfere.
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = SizingContext(
            street="flop",
            board_texture=BoardTexture(is_dry=False, is_wet=True),
            range_advantage=RangeAdvantage(aggressor_advantage=0.5, nut_advantage=False),
            pot=1000,
            is_value_bet=True,
            is_polarized=False,
            personality=personality,
        )

        amount = compute_bet_size(ctx, min_raise=10, max_raise=5000)
        pct = amount / 1000.0

        assert 0.55 <= pct <= 0.75, (
            f"Wet board cbet should be 55%-75% of pot. "
            f"Got {amount} ({pct*100:.1f}%) with aggression={aggression}"
        )


# ─── Property 25: Polarized river sizing ─────────────────────────────────────
# **Validates: Requirements 8.3**


class TestPolarizedRiverSizing:
    """Property 25: For any river SizingContext where is_polarized=True, the
    computed bet SHALL be between 75% and 150% of pot (before noise, clamped
    to [min_raise, max_raise])."""

    @settings(max_examples=100)
    @given(
        aggression=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_polarized_river_bet_between_75_and_150_pct(self, aggression: float):
        """**Validates: Requirements 8.3**

        On a polarized river, compute_bet_size must return a value between
        75% and 150% of pot when min/max don't interfere.
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = SizingContext(
            street="river",
            board_texture=BoardTexture(is_dry=True, is_wet=False),
            range_advantage=RangeAdvantage(aggressor_advantage=0.5, nut_advantage=False),
            pot=1000,
            is_value_bet=True,
            is_polarized=True,
            personality=personality,
        )

        amount = compute_bet_size(ctx, min_raise=10, max_raise=5000)
        pct = amount / 1000.0

        assert 0.75 <= pct <= 1.50, (
            f"Polarized river bet should be 75%-150% of pot. "
            f"Got {amount} ({pct*100:.1f}%) with aggression={aggression}"
        )


# ─── Additional imports for tasks 10.5, 10.6, 12.2, 12.3, 12.4 ──────────────

import math
import statistics

from poker.bot_ai.bet_sizer import add_sizing_noise
from poker.bot_ai.action_scorer import apply_noise


# ─── Property 26: Nut advantage overbet ──────────────────────────────────────
# **Validates: Requirements 8.4**


class TestNutAdvantageOverbet:
    """Property 26: For any SizingContext where nut_advantage=True, the computed
    bet SHALL exceed 100% of pot (clamped to max_raise)."""

    @settings(max_examples=100)
    @given(
        aggression=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_nut_advantage_exceeds_100_pct_pot(self, aggression: float):
        """**Validates: Requirements 8.4**

        When nut_advantage is True, compute_bet_size must return a value
        exceeding 100% of pot (i.e., an overbet).
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = SizingContext(
            street="flop",
            board_texture=BoardTexture(is_dry=True, is_wet=False),
            range_advantage=RangeAdvantage(aggressor_advantage=0.8, nut_advantage=True),
            pot=1000,
            is_value_bet=True,
            is_polarized=False,
            personality=personality,
        )

        amount = compute_bet_size(ctx, min_raise=10, max_raise=5000)
        pct = amount / 1000.0

        assert pct > 1.0, (
            f"Nut advantage bet should exceed 100% of pot. "
            f"Got {amount} ({pct*100:.1f}%) with aggression={aggression}"
        )


# ─── Property 27: Bet sizing noise bounds ────────────────────────────────────
# **Validates: Requirements 8.5**


class TestBetSizingNoiseBounds:
    """Property 27: For any base bet size, add_sizing_noise SHALL produce a value
    within ±10% of the base size."""

    @settings(max_examples=100)
    @given(
        base_size=st.integers(min_value=20, max_value=10000),
    )
    def test_noise_within_10_percent(self, base_size: int):
        """**Validates: Requirements 8.5**

        Run add_sizing_noise many times and verify ALL results are within
        [base * 0.89, base * 1.11 + 1] (allowing for int rounding).
        """
        lower_bound = int(base_size * 0.89)
        upper_bound = int(base_size * 1.11) + 1

        for _ in range(200):
            result = add_sizing_noise(base_size)
            assert lower_bound <= result <= upper_bound, (
                f"add_sizing_noise({base_size}) = {result} is outside "
                f"[{lower_bound}, {upper_bound}]"
            )


# ─── Property 28: Finite action scores ──────────────────────────────────────
# **Validates: Requirements 9.1**


class TestFiniteActionScores:
    """Property 28: For any valid ScoringContext and set of legal actions,
    compute_base_scores SHALL return finite (non-NaN, non-infinite) scores
    for every legal action."""

    @settings(max_examples=100)
    @given(
        equity=st.floats(min_value=0.0, max_value=1.0),
        pot_odds=st.floats(min_value=0.0, max_value=1.0),
        aggressor_advantage=st.floats(min_value=0.0, max_value=1.0),
        bluff_total=st.floats(min_value=0.0, max_value=1.0),
        aggression=st.floats(min_value=0.0, max_value=1.0),
        position=st.sampled_from(["UTG", "UTG1", "MP", "HJ", "CO", "BTN", "SB", "BB"]),
        street=st.sampled_from(["preflop", "flop", "turn", "river"]),
        is_preflop_aggressor=st.booleans(),
        stack_to_pot=st.floats(min_value=0.1, max_value=100.0),
    )
    def test_all_scores_are_finite(
        self,
        equity: float,
        pot_odds: float,
        aggressor_advantage: float,
        bluff_total: float,
        aggression: float,
        position: str,
        street: str,
        is_preflop_aggressor: bool,
        stack_to_pot: float,
    ):
        """**Validates: Requirements 9.1**

        Generate random ScoringContexts with varying equity, pot_odds, etc.
        and verify all returned scores are finite.
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = ScoringContext(
            equity=equity,
            pot_odds=pot_odds,
            opponent_range=RangeEstimate(),
            board_texture=BoardTexture(is_dry=True, is_wet=False),
            range_advantage=RangeAdvantage(
                aggressor_advantage=aggressor_advantage, nut_advantage=False
            ),
            position=position,
            street=street,
            bluff_score=BluffScore(
                blocker_score=0.5,
                fold_equity=0.5,
                range_advantage=0.5,
                backup_equity=0.3,
                total_score=bluff_total,
            ),
            exploit_adjustments=ExploitAdjustments(),
            dynamic_adjustments=DynamicAdjustments(),
            personality=personality,
            stack_to_pot=stack_to_pot,
            is_preflop_aggressor=is_preflop_aggressor,
        )

        legal_actions = ["fold", "check", "call", "bet", "raise"]
        scores = compute_base_scores(ctx, legal_actions)

        assert math.isfinite(scores.fold), f"fold score is not finite: {scores.fold}"
        assert math.isfinite(scores.check), f"check score is not finite: {scores.check}"
        assert math.isfinite(scores.call), f"call score is not finite: {scores.call}"
        assert math.isfinite(scores.bet), f"bet score is not finite: {scores.bet}"
        assert math.isfinite(scores.raise_), f"raise_ score is not finite: {scores.raise_}"


# ─── Property 29: Noise scaling with exploitability ──────────────────────────
# **Validates: Requirements 9.3**


class TestNoiseScalingWithExploitability:
    """Property 29: For any two exploitability values where one is higher,
    applying noise with higher exploitability SHALL produce greater score
    variance (measured over multiple applications)."""

    @settings(max_examples=50)
    @given(
        base_bet_score=st.floats(min_value=0.5, max_value=2.0),
    )
    def test_higher_exploitability_produces_greater_variance(self, base_bet_score: float):
        """**Validates: Requirements 9.3**

        Apply noise 500 times at low exploitability (0.05) and 500 times at
        high (0.45), compare variance of bet scores.
        """
        low_exploitability = 0.05
        high_exploitability = 0.45
        iterations = 500

        base_scores = ActionScores(
            fold=0.1,
            check=0.4,
            call=0.3,
            bet=base_bet_score,
            raise_=0.2,
        )

        # Collect bet scores with low exploitability
        low_bet_scores = []
        for _ in range(iterations):
            noisy = apply_noise(base_scores, low_exploitability)
            low_bet_scores.append(noisy.bet)

        # Collect bet scores with high exploitability
        high_bet_scores = []
        for _ in range(iterations):
            noisy = apply_noise(base_scores, high_exploitability)
            high_bet_scores.append(noisy.bet)

        low_variance = statistics.variance(low_bet_scores)
        high_variance = statistics.variance(high_bet_scores)

        assert high_variance > low_variance, (
            f"Higher exploitability ({high_exploitability}) should produce greater variance "
            f"than lower ({low_exploitability}). Got high_var={high_variance:.6f}, "
            f"low_var={low_variance:.6f}"
        )


# ─── Property 30: Valid bet/raise amounts ────────────────────────────────────
# **Validates: Requirements 9.4**


class TestValidBetRaiseAmounts:
    """Property 30: compute_bet_size always returns a value in [min_raise, max_raise]
    for any valid SizingContext."""

    @settings(max_examples=100)
    @given(
        street=st.sampled_from(["preflop", "flop", "turn", "river"]),
        is_dry=st.booleans(),
        nut_advantage=st.booleans(),
        is_polarized=st.booleans(),
        aggression=st.floats(min_value=0.0, max_value=1.0),
        pot=st.integers(min_value=50, max_value=50000),
        min_raise=st.integers(min_value=10, max_value=200),
        max_raise=st.integers(min_value=500, max_value=100000),
    )
    def test_bet_size_always_in_min_max_range(
        self,
        street: str,
        is_dry: bool,
        nut_advantage: bool,
        is_polarized: bool,
        aggression: float,
        pot: int,
        min_raise: int,
        max_raise: int,
    ):
        """**Validates: Requirements 9.4**

        For any valid SizingContext, compute_bet_size must return a value
        in [min_raise, max_raise].
        """
        personality = PokerPersonality(
            name="test",
            vpip=0.25,
            pfr=0.20,
            three_bet=0.08,
            aggression=aggression,
            bluff_frequency=0.2,
            call_down_looseness=0.3,
            trap_frequency=0.1,
            tilt_factor=0.1,
            position_awareness=0.7,
            exploitability=0.1,
        )

        ctx = SizingContext(
            street=street,
            board_texture=BoardTexture(is_dry=is_dry, is_wet=not is_dry),
            range_advantage=RangeAdvantage(
                aggressor_advantage=0.6, nut_advantage=nut_advantage
            ),
            pot=pot,
            is_value_bet=True,
            is_polarized=is_polarized,
            personality=personality,
        )

        amount = compute_bet_size(ctx, min_raise=min_raise, max_raise=max_raise)

        assert min_raise <= amount <= max_raise, (
            f"compute_bet_size returned {amount} which is outside "
            f"[{min_raise}, {max_raise}] for street={street}, pot={pot}, "
            f"is_dry={is_dry}, nut_advantage={nut_advantage}, "
            f"is_polarized={is_polarized}, aggression={aggression}"
        )


# ─── Additional imports for tasks 12.5, 13.2, 13.3, 14.3 ─────────────────────

from poker.bot_ai.action_scorer import select_action, _ILLEGAL_SCORE
from poker.bot_ai.difficulty_controller import (
    DifficultyLevel,
    get_active_subsystems,
    get_personality_for_difficulty,
)
from poker.bot_ai import advanced_bot_decide, AIGameContext
from poker.bot_ai.models import ActiveSubsystems
from poker.bot_ai.personality_engine import get_personality


# ─── Property 31: Tied action randomization ───────────────────────────────────
# **Validates: Requirements 9.5**


class TestTiedActionRandomization:
    """Property 31: For any ActionScores where two or more actions have scores
    within 5% of the maximum, running select_action many times SHALL select each
    tied action at least once (non-deterministic selection among ties)."""

    def test_tied_actions_both_selected_over_many_runs(self):
        """**Validates: Requirements 9.5**

        Create ActionScores where bet=1.0 and check=0.96 (within 5%) and run
        select_action 500 times, verify both actions appear.
        """
        scores = ActionScores(
            fold=_ILLEGAL_SCORE,
            check=0.96,
            call=_ILLEGAL_SCORE,
            bet=1.0,
            raise_=_ILLEGAL_SCORE,
        )

        results = set()
        for _ in range(500):
            chosen = select_action(scores)
            results.add(chosen)

        assert "bet" in results, (
            "Expected 'bet' to be selected at least once among 500 runs"
        )
        assert "check" in results, (
            "Expected 'check' to be selected at least once among 500 runs"
        )

    @settings(max_examples=20)
    @given(
        score_a=st.floats(min_value=0.5, max_value=2.0),
        delta=st.floats(min_value=0.0, max_value=0.04),
    )
    def test_any_two_tied_actions_are_both_reachable(self, score_a: float, delta: float):
        """**Validates: Requirements 9.5**

        For any pair of scores within 5% of each other (the second score is
        max * (1 - delta) where delta < 5%), both actions should be selectable.
        """
        score_b = score_a * (1.0 - delta)  # within 5% of score_a

        scores = ActionScores(
            fold=_ILLEGAL_SCORE,
            check=score_b,
            call=_ILLEGAL_SCORE,
            bet=score_a,
            raise_=_ILLEGAL_SCORE,
        )

        results = set()
        for _ in range(500):
            chosen = select_action(scores)
            results.add(chosen)

        assert "bet" in results, (
            f"Expected 'bet' (score={score_a}) to appear in 500 runs"
        )
        assert "check" in results, (
            f"Expected 'check' (score={score_b}) to appear in 500 runs"
        )


# ─── Property 32: Difficulty subsystem monotonic inclusion ────────────────────
# **Validates: Requirements 10.2, 10.3, 10.4, 10.5**


def _subsystem_fields_set(subsystems: ActiveSubsystems) -> set[str]:
    """Convert ActiveSubsystems to a set of field names where value is True."""
    fields = [
        "hand_strength",
        "pot_odds",
        "preflop_charts",
        "bet_sizing",
        "range_tracking",
        "board_texture",
        "opponent_modeling",
        "bluff_calculator",
        "dynamic_adjustment",
        "full_action_scoring",
    ]
    return {f for f in fields if getattr(subsystems, f)}


class TestDifficultySubsystemMonotonicInclusion:
    """Property 32: For any two difficulty levels where one is higher
    (Easy < Medium < Hard < Expert), the higher difficulty's ActiveSubsystems
    SHALL be a superset of the lower level's active subsystems."""

    def test_all_consecutive_levels_superset(self):
        """**Validates: Requirements 10.2, 10.3, 10.4, 10.5**

        Check all pairs of consecutive levels. Convert ActiveSubsystems to a
        set of True fields and verify superset relationship.
        """
        levels = [
            DifficultyLevel.EASY,
            DifficultyLevel.MEDIUM,
            DifficultyLevel.HARD,
            DifficultyLevel.EXPERT,
        ]

        for i in range(len(levels) - 1):
            lower = levels[i]
            higher = levels[i + 1]

            lower_subs = _subsystem_fields_set(get_active_subsystems(lower))
            higher_subs = _subsystem_fields_set(get_active_subsystems(higher))

            assert higher_subs >= lower_subs, (
                f"{higher.name} subsystems {higher_subs} should be superset of "
                f"{lower.name} subsystems {lower_subs}. "
                f"Missing: {lower_subs - higher_subs}"
            )

    @settings(max_examples=20)
    @given(
        lower_idx=st.integers(min_value=0, max_value=2),
    )
    def test_any_pair_monotonic_inclusion(self, lower_idx: int):
        """**Validates: Requirements 10.2, 10.3, 10.4, 10.5**

        For any pair of consecutive difficulty levels, the higher level's
        active subsystems must be a superset of the lower level's.
        """
        levels = [
            DifficultyLevel.EASY,
            DifficultyLevel.MEDIUM,
            DifficultyLevel.HARD,
            DifficultyLevel.EXPERT,
        ]

        lower = levels[lower_idx]
        higher = levels[lower_idx + 1]

        lower_subs = _subsystem_fields_set(get_active_subsystems(lower))
        higher_subs = _subsystem_fields_set(get_active_subsystems(higher))

        assert higher_subs >= lower_subs, (
            f"{higher.name} should be superset of {lower.name}. "
            f"Missing: {lower_subs - higher_subs}"
        )


# ─── Property 33: Difficulty personality exploitability ordering ──────────────
# **Validates: Requirements 10.6**


class TestDifficultyPersonalityExploitabilityOrdering:
    """Property 33: For any two difficulty levels where one is higher, the
    personality profiles assigned to the higher difficulty level SHALL have
    lower (or equal) exploitability values."""

    @settings(max_examples=30)
    @given(
        style=st.sampled_from([
            "TAG", "LAG", "Nit", "Calling_Station", "Maniac",
            "Trapper", "GTO_ish", "Exploitative_Shark",
            "tight_aggressive", "loose_aggressive", "calling_station", "maniac",
        ]),
        lower_idx=st.integers(min_value=0, max_value=2),
    )
    def test_higher_difficulty_has_lower_exploitability(
        self, style: str, lower_idx: int
    ):
        """**Validates: Requirements 10.6**

        For each pair of consecutive levels, calling get_personality_for_difficulty
        with the same style should yield lower exploitability for higher levels.
        """
        levels = [
            DifficultyLevel.EASY,
            DifficultyLevel.MEDIUM,
            DifficultyLevel.HARD,
            DifficultyLevel.EXPERT,
        ]

        lower_level = levels[lower_idx]
        higher_level = levels[lower_idx + 1]

        lower_personality = get_personality_for_difficulty(lower_level, style)
        higher_personality = get_personality_for_difficulty(higher_level, style)

        assert higher_personality.exploitability <= lower_personality.exploitability, (
            f"For style='{style}': {higher_level.name} exploitability "
            f"({higher_personality.exploitability}) should be <= "
            f"{lower_level.name} exploitability ({lower_personality.exploitability})"
        )


# ─── Unit tests: Full pipeline integration ───────────────────────────────────
# _Requirements: 6.3, 10.1, 9.1_


class TestFullPipelineIntegration:
    """Unit tests for the full advanced_bot_decide pipeline integration."""

    def _make_game_context(self, **overrides) -> AIGameContext:
        """Helper to create a basic AIGameContext with sensible defaults."""
        defaults = dict(
            hole_cards=["AH", "KH"],
            community=[],
            phase="preflop",
            pot=150,
            current_bet=100,
            committed=50,
            stack=2000,
            big_blind=50,
            min_raise=100,
            position="BTN",
            num_opponents=2,
            is_preflop_aggressor=False,
            facing_action="raise",
        )
        defaults.update(overrides)
        return AIGameContext(**defaults)

    def test_returns_valid_action_and_payload_preflop(self):
        """**Validates: Requirements 9.1**

        advanced_bot_decide returns a valid (action, payload) for preflop state.
        """
        ctx = self._make_game_context()
        personality = get_personality("TAG")
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.MEDIUM)

        assert action in ("fold", "check_call", "bet_raise"), (
            f"Unexpected action: {action}"
        )
        assert isinstance(payload, dict), f"Payload should be dict, got {type(payload)}"

    def test_returns_valid_action_and_payload_postflop(self):
        """**Validates: Requirements 9.1**

        advanced_bot_decide returns a valid (action, payload) for postflop state.
        """
        ctx = self._make_game_context(
            phase="flop",
            community=["7H", "8D", "JS"],
            current_bet=0,
            committed=100,
            facing_action="unopened",
        )
        personality = get_personality("LAG")
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.HARD)

        assert action in ("fold", "check_call", "bet_raise"), (
            f"Unexpected action: {action}"
        )
        assert isinstance(payload, dict)

    def test_returns_valid_action_river(self):
        """**Validates: Requirements 9.1**

        advanced_bot_decide returns a valid (action, payload) for river state.
        """
        ctx = self._make_game_context(
            phase="river",
            community=["7H", "8D", "JS", "QC", "2S"],
            current_bet=200,
            committed=100,
            facing_action="bet",
        )
        personality = get_personality("Nit")
        action, payload = advanced_bot_decide(ctx, personality, DifficultyLevel.EXPERT)

        assert action in ("fold", "check_call", "bet_raise")
        assert isinstance(payload, dict)

    def test_expert_uses_more_subsystems_than_easy(self):
        """**Validates: Requirements 10.1**

        Difficulty level switching produces different behavior — Expert uses
        more subsystems than Easy.
        """
        easy_subs = get_active_subsystems(DifficultyLevel.EASY)
        expert_subs = get_active_subsystems(DifficultyLevel.EXPERT)

        easy_count = sum(
            1 for f in [
                easy_subs.hand_strength, easy_subs.pot_odds, easy_subs.preflop_charts,
                easy_subs.bet_sizing, easy_subs.range_tracking, easy_subs.board_texture,
                easy_subs.opponent_modeling, easy_subs.bluff_calculator,
                easy_subs.dynamic_adjustment, easy_subs.full_action_scoring,
            ] if f
        )
        expert_count = sum(
            1 for f in [
                expert_subs.hand_strength, expert_subs.pot_odds, expert_subs.preflop_charts,
                expert_subs.bet_sizing, expert_subs.range_tracking, expert_subs.board_texture,
                expert_subs.opponent_modeling, expert_subs.bluff_calculator,
                expert_subs.dynamic_adjustment, expert_subs.full_action_scoring,
            ] if f
        )

        assert expert_count > easy_count, (
            f"Expert should have more active subsystems ({expert_count}) "
            f"than Easy ({easy_count})"
        )

    def test_backward_compatibility_old_style_strings(self):
        """**Validates: Requirements 6.3**

        Old style strings (tight_aggressive, loose_aggressive, calling_station,
        maniac) produce valid decisions through the pipeline.
        """
        old_styles = ["tight_aggressive", "loose_aggressive", "calling_station", "maniac"]

        for style in old_styles:
            ctx = self._make_game_context()
            personality = get_personality(style)
            action, payload = advanced_bot_decide(
                ctx, personality, DifficultyLevel.MEDIUM
            )

            assert action in ("fold", "check_call", "bet_raise"), (
                f"Style '{style}' produced invalid action: {action}"
            )
            assert isinstance(payload, dict), (
                f"Style '{style}' produced non-dict payload: {type(payload)}"
            )

    def test_bet_raise_includes_amount(self):
        """**Validates: Requirements 9.1**

        When action is bet_raise, the payload should contain an 'amount' key.
        """
        # Use an aggressive personality and favorable situation to encourage betting
        ctx = self._make_game_context(
            phase="flop",
            community=["AH", "KD", "2S"],
            current_bet=0,
            committed=100,
            facing_action="unopened",
            is_preflop_aggressor=True,
        )
        personality = get_personality("Maniac")

        # Run several times to get a bet_raise action
        got_bet_raise = False
        for _ in range(50):
            action, payload = advanced_bot_decide(
                ctx, personality, DifficultyLevel.MEDIUM
            )
            if action == "bet_raise":
                got_bet_raise = True
                assert "amount" in payload, (
                    "bet_raise action should have 'amount' in payload"
                )
                assert isinstance(payload["amount"], (int, float))
                break

        # It's acceptable if the aggressive bot sometimes checks; we just
        # verify the payload format when it does bet.
        if not got_bet_raise:
            # Verify it still returned valid actions
            action, payload = advanced_bot_decide(
                ctx, personality, DifficultyLevel.MEDIUM
            )
            assert action in ("fold", "check_call", "bet_raise")
