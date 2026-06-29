from poker import bot_ai
from poker.bot import _advanced_profile_for_style
from poker.bot_ai import advanced_bot_decide
from poker.bot_ai.difficulty_controller import DifficultyLevel
from poker.bot_ai.models import AIGameContext
from poker.bot_ai.personality_engine import BALANCED_PROFILE, get_personality


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
