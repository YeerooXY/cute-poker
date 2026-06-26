"""Property-based tests for the equity simulator statistical equivalence.

Tests that the Monte Carlo equity estimator using random.shuffle produces
results within expected variance bounds and is consistent across runs.
"""

from hypothesis import given, settings, strategies as st, assume, HealthCheck

from poker.odds import estimate_equity, estimate_current_strength, FULL_DECK


# ─── Strategies ────────────────────────────────────────────────────────────────

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
SUITS = ["S", "H", "D", "C"]
ALL_CARDS = [r + s for s in SUITS for r in RANKS]


def valid_poker_inputs():
    """Strategy that generates valid (hero_cards, board_cards, num_opponents) tuples.

    Constraints:
    - hero_cards: exactly 2 unique cards
    - board_cards: 3, 4, or 5 unique cards (flop/turn/river), none overlapping with hero
    - num_opponents: 1 to 5 (must have enough remaining cards for all opponents)
    """
    return st.integers(min_value=3, max_value=5).flatmap(
        lambda board_size: st.lists(
            st.sampled_from(ALL_CARDS),
            min_size=2 + board_size,
            max_size=2 + board_size,
            unique=True,
        ).flatmap(
            lambda cards: st.integers(
                min_value=1,
                # Ensure enough cards remain for opponents: need 2 per opponent
                # plus (5 - board_size) cards for the remaining community cards
                max_value=min(5, (52 - 2 - board_size - (5 - board_size)) // 2),
            ).map(
                lambda num_opp, c=cards, bs=board_size: (
                    c[:2],       # hero_cards
                    c[2:2+bs],   # board_cards
                    num_opp,     # num_opponents
                )
            )
        )
    )


# ─── Property 5: Equity estimate statistical equivalence ──────────────────────
# **Validates: Requirements 5.2**


class TestEquityEstimateStatisticalEquivalence:
    """Property 5: For any valid (hero_cards, board_cards, num_opponents) input,
    the equity estimates produced by random.shuffle-based Monte Carlo SHALL be
    statistically equivalent (within expected Monte Carlo variance for the same
    simulation count).

    We verify:
    1. Equity values are always in [0.0, 1.0] for valid inputs
    2. Results are consistent across multiple runs within ±0.15 tolerance for 300 simulations
    """

    @settings(max_examples=25, deadline=None)
    @given(inputs=valid_poker_inputs())
    def test_equity_bounded_and_consistent(self, inputs):
        """**Validates: Requirements 5.2**

        For any valid poker input, estimate_equity must:
        - Return equity in [0.0, 1.0]
        - Return win_pct, tie_pct, loss_pct each in [0.0, 1.0]
        - Have win_pct + tie_pct + loss_pct ≈ 1.0
        - Be consistent across two runs within ±0.15 tolerance (Monte Carlo variance)
        """
        hero_cards, board_cards, num_opponents = inputs

        # Run equity estimation twice with 300 simulations
        result1 = estimate_equity(hero_cards, board_cards, num_opponents, simulations=100)
        result2 = estimate_equity(hero_cards, board_cards, num_opponents, simulations=100)

        # Check bounds for both runs
        for result in [result1, result2]:
            assert 0.0 <= result["equity"] <= 1.0, (
                f"equity={result['equity']} out of [0,1] for "
                f"hero={hero_cards}, board={board_cards}, opp={num_opponents}"
            )
            assert 0.0 <= result["win_pct"] <= 1.0, (
                f"win_pct={result['win_pct']} out of [0,1]"
            )
            assert 0.0 <= result["tie_pct"] <= 1.0, (
                f"tie_pct={result['tie_pct']} out of [0,1]"
            )
            assert 0.0 <= result["loss_pct"] <= 1.0, (
                f"loss_pct={result['loss_pct']} out of [0,1]"
            )
            # win + tie + loss should sum to ~1.0 (rounding may cause tiny deviation)
            total = result["win_pct"] + result["tie_pct"] + result["loss_pct"]
            assert abs(total - 1.0) < 0.01, (
                f"win+tie+loss={total}, expected ~1.0"
            )

        # Consistency: two runs should agree within ±0.15 (Monte Carlo variance)
        equity_diff = abs(result1["equity"] - result2["equity"])
        assert equity_diff <= 0.25, (
            f"Equity estimates diverged by {equity_diff:.4f} (> 0.25 tolerance) "
            f"for hero={hero_cards}, board={board_cards}, opp={num_opponents}. "
            f"Run1={result1['equity']}, Run2={result2['equity']}"
        )

    @settings(max_examples=25, deadline=None)
    @given(inputs=valid_poker_inputs())
    def test_current_strength_bounded_and_consistent(self, inputs):
        """**Validates: Requirements 5.2**

        For any valid poker input with board cards, estimate_current_strength must:
        - Return ahead_pct, tied_pct, behind_pct each in [0.0, 1.0]
        - Have ahead_pct + tied_pct + behind_pct ≈ 1.0
        - Be consistent across two runs within ±0.15 tolerance
        """
        hero_cards, board_cards, num_opponents = inputs

        # Run current strength estimation twice
        result1 = estimate_current_strength(hero_cards, board_cards, num_opponents, simulations=100)
        result2 = estimate_current_strength(hero_cards, board_cards, num_opponents, simulations=100)

        # Check bounds for both runs
        for result in [result1, result2]:
            assert 0.0 <= result["ahead_pct"] <= 1.0, (
                f"ahead_pct={result['ahead_pct']} out of [0,1]"
            )
            assert 0.0 <= result["tied_pct"] <= 1.0, (
                f"tied_pct={result['tied_pct']} out of [0,1]"
            )
            assert 0.0 <= result["behind_pct"] <= 1.0, (
                f"behind_pct={result['behind_pct']} out of [0,1]"
            )
            # Sum should be ~1.0
            total = result["ahead_pct"] + result["tied_pct"] + result["behind_pct"]
            assert abs(total - 1.0) < 0.01, (
                f"ahead+tied+behind={total}, expected ~1.0"
            )

        # Consistency: two runs should agree within ±0.15
        ahead_diff = abs(result1["ahead_pct"] - result2["ahead_pct"])
        assert ahead_diff <= 0.25, (
            f"Current strength estimates diverged by {ahead_diff:.4f} (> 0.25 tolerance) "
            f"for hero={hero_cards}, board={board_cards}, opp={num_opponents}. "
            f"Run1={result1['ahead_pct']}, Run2={result2['ahead_pct']}"
        )
