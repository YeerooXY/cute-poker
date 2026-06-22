"""Unit tests for _hand_class_to_combos in poker/odds.py.

Verifies that canonical hand classes are correctly expanded into
all specific card combinations.
"""

import pytest
from poker.odds import _hand_class_to_combos, FULL_DECK, SUITS, RANKS


FULL_DECK_SET = set(FULL_DECK)


class TestPocketPairExpansion:
    """Pocket pairs (e.g., 'AA', '22') should produce exactly 6 combos (4 choose 2)."""

    def test_aa_produces_6_combos(self):
        combos = _hand_class_to_combos("AA")
        assert len(combos) == 6

    def test_22_produces_6_combos(self):
        combos = _hand_class_to_combos("22")
        assert len(combos) == 6

    def test_kk_produces_6_combos(self):
        combos = _hand_class_to_combos("KK")
        assert len(combos) == 6

    def test_pocket_pair_all_cards_valid(self):
        combos = _hand_class_to_combos("AA")
        for c1, c2 in combos:
            assert c1 in FULL_DECK_SET, f"Card {c1} not in FULL_DECK"
            assert c2 in FULL_DECK_SET, f"Card {c2} not in FULL_DECK"

    def test_pocket_pair_no_duplicate_combos(self):
        combos = _hand_class_to_combos("AA")
        # Normalize: sort each combo tuple so order doesn't matter
        normalized = set(tuple(sorted(c)) for c in combos)
        assert len(normalized) == 6

    def test_pocket_pair_cards_are_different(self):
        combos = _hand_class_to_combos("AA")
        for c1, c2 in combos:
            assert c1 != c2, f"Duplicate card in combo: {c1}, {c2}"

    def test_pocket_pair_same_rank(self):
        combos = _hand_class_to_combos("TT")
        for c1, c2 in combos:
            assert c1[0] == "T"
            assert c2[0] == "T"
            # Suits must differ
            assert c1[1] != c2[1]

    def test_all_pocket_pairs(self):
        """Every rank produces exactly 6 combos for pocket pairs."""
        for rank in RANKS:
            hand_class = rank + rank
            combos = _hand_class_to_combos(hand_class)
            assert len(combos) == 6, f"{hand_class} produced {len(combos)} combos, expected 6"


class TestSuitedHandExpansion:
    """Suited hands (e.g., 'AKs') should produce exactly 4 combos (one per suit)."""

    def test_aks_produces_4_combos(self):
        combos = _hand_class_to_combos("AKs")
        assert len(combos) == 4

    def test_suited_all_cards_valid(self):
        combos = _hand_class_to_combos("AKs")
        for c1, c2 in combos:
            assert c1 in FULL_DECK_SET, f"Card {c1} not in FULL_DECK"
            assert c2 in FULL_DECK_SET, f"Card {c2} not in FULL_DECK"

    def test_suited_no_duplicate_combos(self):
        combos = _hand_class_to_combos("AKs")
        normalized = set(tuple(sorted(c)) for c in combos)
        assert len(normalized) == 4

    def test_suited_cards_are_different(self):
        combos = _hand_class_to_combos("AKs")
        for c1, c2 in combos:
            assert c1 != c2, f"Duplicate card in combo: {c1}, {c2}"

    def test_suited_same_suit(self):
        """Each combo in a suited hand must have matching suits."""
        combos = _hand_class_to_combos("AKs")
        for c1, c2 in combos:
            assert c1[1] == c2[1], f"Suited combo has different suits: {c1}, {c2}"

    def test_suited_correct_ranks(self):
        combos = _hand_class_to_combos("AKs")
        for c1, c2 in combos:
            assert c1[0] == "A", f"Expected rank A, got {c1[0]}"
            assert c2[0] == "K", f"Expected rank K, got {c2[0]}"

    def test_suited_covers_all_suits(self):
        combos = _hand_class_to_combos("AKs")
        suits_used = set(c1[1] for c1, _ in combos)
        assert suits_used == {"S", "H", "D", "C"}

    def test_t9s_produces_4_combos(self):
        combos = _hand_class_to_combos("T9s")
        assert len(combos) == 4
        for c1, c2 in combos:
            assert c1[0] == "T"
            assert c2[0] == "9"
            assert c1[1] == c2[1]


class TestOffsuitHandExpansion:
    """Offsuit hands (e.g., 'AKo') should produce exactly 12 combos."""

    def test_ako_produces_12_combos(self):
        combos = _hand_class_to_combos("AKo")
        assert len(combos) == 12

    def test_offsuit_all_cards_valid(self):
        combos = _hand_class_to_combos("AKo")
        for c1, c2 in combos:
            assert c1 in FULL_DECK_SET, f"Card {c1} not in FULL_DECK"
            assert c2 in FULL_DECK_SET, f"Card {c2} not in FULL_DECK"

    def test_offsuit_no_duplicate_combos(self):
        combos = _hand_class_to_combos("AKo")
        normalized = set(tuple(sorted(c)) for c in combos)
        assert len(normalized) == 12

    def test_offsuit_cards_are_different(self):
        combos = _hand_class_to_combos("AKo")
        for c1, c2 in combos:
            assert c1 != c2, f"Duplicate card in combo: {c1}, {c2}"

    def test_offsuit_different_suits(self):
        """Each combo in an offsuit hand must have different suits."""
        combos = _hand_class_to_combos("AKo")
        for c1, c2 in combos:
            assert c1[1] != c2[1], f"Offsuit combo has same suit: {c1}, {c2}"

    def test_offsuit_correct_ranks(self):
        combos = _hand_class_to_combos("AKo")
        for c1, c2 in combos:
            assert c1[0] == "A", f"Expected rank A, got {c1[0]}"
            assert c2[0] == "K", f"Expected rank K, got {c2[0]}"

    def test_72o_produces_12_combos(self):
        combos = _hand_class_to_combos("72o")
        assert len(combos) == 12
        for c1, c2 in combos:
            assert c1[0] == "7"
            assert c2[0] == "2"
            assert c1[1] != c2[1]


class TestEdgeCases:
    """Edge cases and invalid inputs."""

    def test_invalid_hand_class_returns_empty(self):
        combos = _hand_class_to_combos("")
        assert combos == []

    def test_single_char_returns_empty(self):
        combos = _hand_class_to_combos("A")
        assert combos == []

    def test_four_char_returns_empty(self):
        combos = _hand_class_to_combos("AKso")
        assert combos == []

    def test_total_combo_count_all_169_classes(self):
        """All 169 canonical hand classes together should cover all 1326 combos."""
        total_combos = 0
        # 13 pocket pairs × 6 = 78
        for rank in RANKS:
            total_combos += len(_hand_class_to_combos(rank + rank))

        # 78 suited hands × 4 = 312
        for i, r1 in enumerate(RANKS):
            for r2 in RANKS[i + 1:]:
                total_combos += len(_hand_class_to_combos(r1 + r2 + "s"))

        # 78 offsuit hands × 12 = 936
        for i, r1 in enumerate(RANKS):
            for r2 in RANKS[i + 1:]:
                total_combos += len(_hand_class_to_combos(r1 + r2 + "o"))

        # Total: 78 + 312 + 936 = 1326
        assert total_combos == 1326, f"Expected 1326 total combos, got {total_combos}"

    def test_no_overlap_between_classes(self):
        """All combos across all 169 classes are unique (no overlap)."""
        all_combos = set()
        for rank in RANKS:
            for c in _hand_class_to_combos(rank + rank):
                normalized = tuple(sorted(c))
                assert normalized not in all_combos, f"Duplicate combo {c} in {rank+rank}"
                all_combos.add(normalized)

        for i, r1 in enumerate(RANKS):
            for r2 in RANKS[i + 1:]:
                for c in _hand_class_to_combos(r1 + r2 + "s"):
                    normalized = tuple(sorted(c))
                    assert normalized not in all_combos, f"Duplicate combo {c} in {r1+r2}s"
                    all_combos.add(normalized)

                for c in _hand_class_to_combos(r1 + r2 + "o"):
                    normalized = tuple(sorted(c))
                    assert normalized not in all_combos, f"Duplicate combo {c} in {r1+r2}o"
                    all_combos.add(normalized)

        assert len(all_combos) == 1326
