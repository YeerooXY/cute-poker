from poker import bot_ai
from poker import bot as bot_module
from poker.bot_ai import _should_slowplay_trap, advanced_bot_decide
from poker.bot_ai.difficulty_controller import DifficultyLevel
from poker.bot_ai.models import AIGameContext, BoardTexture
from poker.bot_ai.personality_engine import get_personality
from poker.bot_ai.preflop_charts import get_preflop_decision, maybe_mix_preflop_decision


def make_preflop_context() -> AIGameContext:
    return AIGameContext(
        hole_cards=["7D", "2C"],
        community=[],
        phase="preflop",
        pot=45,
        current_bet=30,
        committed=10,
        stack=990,
        big_blind=10,
        min_raise=20,
        position="UTG",
        num_opponents=3,
        is_preflop_aggressor=False,
        facing_action="raise",
        raises_faced_this_street=1,
    )


def make_tiny_price_speculative_context() -> AIGameContext:
    return AIGameContext(
        hole_cards=["2S", "4S"],
        community=[],
        phase="preflop",
        pot=15,
        current_bet=10,
        committed=5,
        stack=995,
        big_blind=10,
        min_raise=20,
        position="SB",
        num_opponents=3,
        is_preflop_aggressor=False,
        facing_action="unopened",
        raises_faced_this_street=0,
    )


def test_legacy_bot_styles_do_not_route_to_distinct_advanced_profiles():
    assert not hasattr(bot_module, "_ADVANCED_STYLE_PROFILE_MAPPING")
    assert not hasattr(bot_module, "_advanced_profile_for_style")

    source_names = set(bot_module._advanced_ai_decide.__code__.co_names)
    assert "_advanced_profile_for_style" not in source_names
    assert "get_personality" not in source_names
    assert "BALANCED_PROFILE" in source_names


def test_preflop_chart_early_return_refreshes_debug_for_current_decision():
    bot_ai._last_decision_debug.clear()
    bot_ai._last_decision_debug.update({
        "final_action": "check_call",
        "chart_action": "stale",
        "phase": "river",
    })

    action, payload = advanced_bot_decide(
        make_preflop_context(),
        get_personality("TAG"),
        DifficultyLevel.HARD,
    )

    debug = bot_ai._last_decision_debug
    assert action == "fold"
    assert payload == {}
    assert debug["phase"] == "preflop"
    assert debug["street"] == "preflop"
    assert debug["personality_style"] == "TAG"
    assert debug["legal_actions"] == ["fold", "call", "raise"]
    assert debug["facing_amount"] == 20
    assert debug["chart_action"] == "fold"


def test_preflop_chart_debug_final_action_matches_returned_action():
    action, payload = advanced_bot_decide(
        make_preflop_context(),
        get_personality("LAG"),
        DifficultyLevel.HARD,
    )

    debug = bot_ai._last_decision_debug
    assert action == debug["final_action"]
    assert debug["bet_amount"] == payload.get("amount", 0)
    assert debug["chart_action"] == debug["chosen_internal_action"]


def test_weak_offsuit_trash_still_folds_versus_meaningful_raise():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["JH", "3C"],
        position="SB",
        facing_action="raise",
        big_blind=10,
        current_bet=50,
        committed=5,
        stack=995,
        pot=65,
        chart_action="fold",
        chart_payload={},
        rng=lambda: 0.0,
    )

    assert (action, payload, reason) == ("fold", {}, None)


def test_weak_offsuit_trash_does_not_continue_vs_large_pressure():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["TC", "2S"],
        position="BB",
        facing_action="4bet",
        big_blind=10,
        current_bet=120,
        committed=10,
        stack=995,
        pot=130,
        chart_action="call",
        chart_payload={},
        rng=lambda: 0.0,
    )

    assert (action, payload, reason) == ("fold", {}, None)


def test_low_pair_does_not_huge_raise_versus_large_pressure():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["3H", "3D"],
        position="CO",
        facing_action="raise",
        big_blind=50,
        current_bet=850,
        committed=50,
        stack=4950,
        pot=900,
        chart_action="raise",
        chart_payload={"amount": 200},
        rng=lambda: 0.0,
    )

    assert action in {"fold", "call"}
    assert action != "raise"
    assert payload == {}
    assert reason is None


def test_low_suited_speculative_hand_can_continue_only_for_tiny_blind_price():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["2S", "4S"],
        position="SB",
        facing_action="unopened",
        big_blind=10,
        current_bet=10,
        committed=5,
        stack=995,
        pot=15,
        chart_action="fold",
        chart_payload={},
        rng=lambda: 0.0,
    )

    assert (action, payload, reason) == ("call", {}, "speculative_defend")


def test_low_suited_speculative_hand_folds_versus_large_raise_pressure():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["2S", "4S"],
        position="SB",
        facing_action="3bet",
        big_blind=10,
        current_bet=90,
        committed=5,
        stack=995,
        pot=105,
        chart_action="fold",
        chart_payload={},
        rng=lambda: 0.0,
    )

    assert (action, payload, reason) == ("fold", {}, None)


def test_medium_playable_hand_can_call_instead_of_only_raise_or_fold():
    action, payload = get_preflop_decision(
        hole_cards=["8H", "8D"],
        position="BB",
        personality=get_personality("TAG"),
        facing_action="raise",
        big_blind=10,
    )

    assert (action, payload) == ("call", {})


def test_premium_hand_usually_raises_but_has_controlled_flat_path():
    flat = maybe_mix_preflop_decision(
        hole_cards=["AS", "AH"],
        position="BB",
        facing_action="raise",
        big_blind=10,
        current_bet=30,
        committed=10,
        stack=990,
        pot=45,
        chart_action="raise",
        chart_payload={"amount": 30},
        rng=lambda: 0.0,
    )
    normal = maybe_mix_preflop_decision(
        hole_cards=["AS", "AH"],
        position="BB",
        facing_action="raise",
        big_blind=10,
        current_bet=30,
        committed=10,
        stack=990,
        pot=45,
        chart_action="raise",
        chart_payload={"amount": 30},
        rng=lambda: 0.99,
    )

    assert flat == ("call", {}, "premium_flat_mix")
    assert normal == ("raise", {"amount": 30}, None)


def test_aks_with_zero_to_call_is_not_labeled_speculative_defend():
    action, payload, reason = maybe_mix_preflop_decision(
        hole_cards=["AS", "KS"],
        position="BB",
        facing_action="unopened",
        big_blind=10,
        current_bet=10,
        committed=10,
        stack=990,
        pot=15,
        chart_action="raise",
        chart_payload={"amount": 25},
        rng=lambda: 0.0,
    )

    assert action == "raise"
    assert payload == {"amount": 25}
    assert reason is None


def test_very_strong_postflop_hand_has_possible_check_trap_path():
    assert _should_slowplay_trap(
        chosen_action="bet",
        legal_actions=["check", "bet"],
        phase="flop",
        hand_class="straight",
        board_texture=BoardTexture(is_wet=False),
        equity=0.95,
        has_strong_draw=False,
        rng=lambda: 0.0,
    )


def test_strong_postflop_hand_does_not_always_choose_check():
    assert not _should_slowplay_trap(
        chosen_action="bet",
        legal_actions=["check", "bet"],
        phase="flop",
        hand_class="straight",
        board_texture=BoardTexture(is_wet=False),
        equity=0.95,
        has_strong_draw=False,
        rng=lambda: 0.99,
    )


def test_preflop_mixed_decision_debug_final_action_matches_returned_action(monkeypatch):
    monkeypatch.setattr("poker.bot_ai.preflop_charts.random.random", lambda: 0.0)

    action, payload = advanced_bot_decide(
        make_tiny_price_speculative_context(),
        get_personality("TAG"),
        DifficultyLevel.HARD,
    )

    debug = bot_ai._last_decision_debug
    assert action == "check_call"
    assert payload == {}
    assert debug["decision_reason"] == "speculative_defend"
    assert debug["final_action"] == action
    assert debug["bet_amount"] == payload.get("amount", 0)
