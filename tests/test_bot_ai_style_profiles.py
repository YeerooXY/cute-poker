from poker import bot_ai
from poker.bot import _advanced_profile_for_style
from poker.bot_ai import _should_slowplay_trap, advanced_bot_decide
from poker.bot_ai.difficulty_controller import DifficultyLevel
from poker.bot_ai.models import AIGameContext, BoardTexture
from poker.bot_ai.personality_engine import BALANCED_PROFILE, get_personality
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


def test_legacy_bot_styles_map_to_distinct_advanced_profiles():
    expected = {
        "tight_aggressive": "TAG",
        "loose_aggressive": "LAG",
        "calling_station": "Calling_Station",
        "maniac": "Maniac",
    }

    for style, profile_name in expected.items():
        assert _advanced_profile_for_style(style).name == profile_name


def test_unknown_and_balanced_styles_fall_back_to_balanced_profile():
    assert _advanced_profile_for_style("balanced") is BALANCED_PROFILE
    assert _advanced_profile_for_style("unknown_style") is BALANCED_PROFILE
    assert _advanced_profile_for_style("") is BALANCED_PROFILE


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
        hole_cards=["7D", "2C"],
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
