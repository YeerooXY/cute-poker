"""Advanced Bot AI decision pipeline.

This package provides a multi-layered AI architecture for poker bot decisions,
including range tracking, opponent modeling, board texture analysis,
blocker-based bluffing, dynamic exploitation, and configurable difficulty levels.

The main entry point is `advanced_bot_decide`, which orchestrates:
  1. Difficulty-gated subsystem activation
  2. Analysis layer (range tracking, board analysis, opponent modeling, dynamic adjustment)
  3. Decision layer (preflop charts, bluff calculator, action scorer, bet sizer)
  4. Action mapping to (action, payload) format
"""

from __future__ import annotations

from poker.bot_ai.models import (
    AIGameContext,
    ActionContext,
    ActionScores,
    ActiveSubsystems,
    BluffScore,
    BoardTexture,
    DynamicAdjustments,
    ExploitAdjustments,
    HandSummary,
    RangeAdvantage,
    RangeEstimate,
    ScoringContext,
)
from poker.bot_ai.personality_engine import (
    PokerPersonality,
    get_action_multipliers,
    get_personality,
)
from poker.bot_ai.difficulty_controller import (
    DifficultyLevel,
    get_active_subsystems,
    get_personality_for_difficulty,
)
from poker.bot_ai.range_tracker import RangeTracker
from poker.bot_ai.board_analyzer import analyze_board, compute_range_advantage
from poker.bot_ai.opponent_model import OpponentModel, PlayerStats
from poker.bot_ai.dynamic_adjuster import DynamicAdjuster
from poker.bot_ai.bluff_calculator import compute_bluff_score
from poker.bot_ai.preflop_charts import get_preflop_decision
from poker.bot_ai.bet_sizer import compute_bet_size, add_sizing_noise, SizingContext
from poker.bot_ai.action_scorer import (
    compute_base_scores,
    apply_personality,
    apply_noise,
    select_action,
)


def advanced_bot_decide(
    game_context: AIGameContext,
    personality: PokerPersonality,
    difficulty: DifficultyLevel,
    range_tracker: RangeTracker | None = None,
    opponent_model: OpponentModel | None = None,
    dynamic_adjuster: DynamicAdjuster | None = None,
) -> tuple[str, dict]:
    """Execute the full advanced bot AI decision pipeline.

    Orchestrates subsystem activation based on difficulty, runs the analysis
    layer, then the decision layer, and returns the final (action, payload).

    Args:
        game_context: Complete game state information.
        personality: The bot's personality profile.
        difficulty: Current difficulty level controlling subsystem activation.
        range_tracker: Optional range tracker instance for opponent range estimates.
        opponent_model: Optional opponent model instance for statistical exploitation.
        dynamic_adjuster: Optional dynamic adjuster for table-level adjustments.

    Returns:
        (action, payload) where action is one of "fold", "check_call", "bet_raise"
        and payload is a dict (e.g., {"amount": 150} for bet_raise, {} otherwise).
    """
    # ─── Step 1: Get active subsystems from difficulty controller ───────────
    subsystems = get_active_subsystems(difficulty)

    # ─── Step 2: Analysis Layer ────────────────────────────────────────────
    # Each subsystem wrapped in try/except for graceful degradation.

    # Range tracking
    opponent_range = RangeEstimate()
    if subsystems.range_tracking and range_tracker is not None:
        try:
            # Use a generic opponent token — in a real game this would be specific
            opponent_range = range_tracker.get_range("opponent")
        except Exception:
            opponent_range = RangeEstimate()

    # Board analysis
    board_texture = BoardTexture()
    range_advantage = RangeAdvantage()
    if subsystems.board_texture:
        try:
            board_texture = analyze_board(game_context.community)
        except Exception:
            board_texture = BoardTexture()
        try:
            range_advantage = compute_range_advantage(
                game_context.community, game_context.is_preflop_aggressor
            )
        except Exception:
            range_advantage = RangeAdvantage()

    # Opponent modeling
    exploit_adjustments = ExploitAdjustments(active=False)
    opponent_stats = PlayerStats()
    if subsystems.opponent_modeling and opponent_model is not None:
        try:
            opponent_stats = opponent_model.get_stats("opponent")
        except Exception:
            opponent_stats = PlayerStats()
        try:
            exploit_adjustments = opponent_model.get_exploit_adjustments("opponent")
        except Exception:
            exploit_adjustments = ExploitAdjustments(active=False)

    # Dynamic adjustment
    dynamic_adjustments = DynamicAdjustments()
    if subsystems.dynamic_adjustment and dynamic_adjuster is not None:
        try:
            bot_stack_bb = (
                game_context.stack / game_context.big_blind
                if game_context.big_blind > 0
                else 100.0
            )
            dynamic_adjustments = dynamic_adjuster.get_adjustments(
                bot_stack_bb=bot_stack_bb, opponent_token="opponent"
            )
        except Exception:
            dynamic_adjustments = DynamicAdjustments()

    # ─── Step 3: Handle push-fold mode ─────────────────────────────────────
    if dynamic_adjustments.push_fold_mode:
        return _push_fold_decision(game_context, personality)

    # ─── Step 4: Decision Layer ────────────────────────────────────────────

    # 4a. Preflop chart decision (if preflop and charts active)
    if game_context.phase == "preflop" and subsystems.preflop_charts:
        try:
            preflop_action, preflop_payload = get_preflop_decision(
                hole_cards=game_context.hole_cards,
                position=game_context.position,
                personality=personality,
                facing_action=game_context.facing_action,
                big_blind=game_context.big_blind,
            )
            # Map preflop chart action to game action format
            result = _map_preflop_action(preflop_action, preflop_payload, game_context)
            if result is not None:
                return result
        except Exception:
            pass  # Fall through to full scoring pipeline

    # 4b. Compute equity
    equity = _compute_equity(game_context)

    # 4c. Compute pot odds
    pot_odds = _compute_pot_odds(game_context)

    # 4d. Compute bluff score (if bluff_calculator active)
    bluff_score = BluffScore(0.0, 0.0, 0.0, 0.0, 0.0)
    if subsystems.bluff_calculator:
        try:
            bet_size_ratio = (
                game_context.current_bet / game_context.pot
                if game_context.pot > 0
                else 0.0
            )
            bluff_score = compute_bluff_score(
                hole_cards=game_context.hole_cards,
                community=game_context.community,
                opponent_stats=opponent_stats,
                range_advantage=range_advantage,
                equity=equity,
                bet_size_ratio=bet_size_ratio,
                street=game_context.phase,
            )
        except Exception:
            bluff_score = BluffScore(0.0, 0.0, 0.0, 0.0, 0.0)

    # 4e. Determine legal actions
    legal_actions = _determine_legal_actions(game_context)

    # 4f. Build ScoringContext
    stack_to_pot = (
        game_context.stack / game_context.pot
        if game_context.pot > 0
        else 20.0
    )

    scoring_ctx = ScoringContext(
        equity=equity,
        pot_odds=pot_odds,
        opponent_range=opponent_range,
        board_texture=board_texture,
        range_advantage=range_advantage,
        position=game_context.position,
        street=game_context.phase,
        bluff_score=bluff_score,
        exploit_adjustments=exploit_adjustments,
        dynamic_adjustments=dynamic_adjustments,
        personality=personality,
        stack_to_pot=stack_to_pot,
        is_preflop_aggressor=game_context.is_preflop_aggressor,
    )

    # 4g. Compute base scores → apply personality → apply noise → select action
    scores = compute_base_scores(scoring_ctx, legal_actions)
    scores = apply_personality(scores, personality)
    scores = apply_noise(scores, personality.exploitability)
    chosen_action = select_action(scores)

    # 4h. If bet/raise selected, compute proper bet size
    bet_amount = 0
    if chosen_action in ("bet", "raise") and subsystems.bet_sizing:
        try:
            is_value = equity > 0.55
            is_polarized = (
                game_context.phase == "river" and (equity > 0.8 or equity < 0.3)
            )
            sizing_ctx = SizingContext(
                street=game_context.phase,
                board_texture=board_texture,
                range_advantage=range_advantage,
                pot=game_context.pot,
                is_value_bet=is_value,
                is_polarized=is_polarized,
                personality=personality,
            )
            max_raise = game_context.committed + game_context.stack
            bet_amount = compute_bet_size(
                sizing_ctx, game_context.min_raise, max_raise
            )
            bet_amount = add_sizing_noise(bet_amount)
            # Re-clamp after noise
            bet_amount = max(game_context.min_raise, min(bet_amount, max_raise))
        except Exception:
            # Fallback: use min_raise
            bet_amount = game_context.min_raise
    elif chosen_action in ("bet", "raise"):
        # Bet sizing subsystem not active: use min_raise as default
        bet_amount = game_context.min_raise

    # ─── Step 5: Map internal actions to game actions ──────────────────────
    return _map_action_to_game(chosen_action, bet_amount, game_context)


# ─── Private helpers ───────────────────────────────────────────────────────────


def _compute_equity(game_context: AIGameContext) -> float:
    """Compute equity using hybrid calculator (lookup/exact/MC) with fallback to 0.5."""
    try:
        from poker.odds import calculate_equity_hybrid

        result = calculate_equity_hybrid(
            game_context.hole_cards,
            game_context.community,
            game_context.num_opponents,
        )
        return result["equity"]
    except Exception:
        return 0.5


def _compute_pot_odds(game_context: AIGameContext) -> float:
    """Compute pot odds: to_call / (pot + to_call). Returns 0.0 if no call needed."""
    to_call = game_context.current_bet - game_context.committed
    if to_call <= 0:
        return 0.0
    denominator = game_context.pot + to_call
    if denominator <= 0:
        return 0.0
    return to_call / denominator


def _determine_legal_actions(game_context: AIGameContext) -> list[str]:
    """Determine legal actions based on game state.

    - If current_bet > committed: legal = ["fold", "call", "raise"]
    - If current_bet <= committed: legal = ["check", "bet"]
    - Exclude fold when checking is free
    """
    to_call = game_context.current_bet - game_context.committed
    if to_call > 0:
        # Facing a bet/raise
        return ["fold", "call", "raise"]
    else:
        # No bet to face — can check or bet
        return ["check", "bet"]


def _push_fold_decision(
    game_context: AIGameContext, personality: PokerPersonality
) -> tuple[str, dict]:
    """Push-fold mode: only allow all-in or fold.

    Uses a simplified equity-based decision: shove with decent equity or fold.
    """
    equity = _compute_equity(game_context)

    # Threshold based on personality aggression
    threshold = 0.45 - (personality.aggression * 0.15)

    all_in_amount = game_context.committed + game_context.stack

    if equity >= threshold:
        return ("bet_raise", {"amount": all_in_amount})
    else:
        # If checking is free, check instead of folding
        to_call = game_context.current_bet - game_context.committed
        if to_call <= 0:
            return ("check_call", {})
        return ("fold", {})


def _map_preflop_action(
    action: str, payload: dict, game_context: AIGameContext
) -> tuple[str, dict] | None:
    """Map preflop chart action to game action format.

    Returns None if the action can't be mapped (fallthrough to scoring pipeline).
    """
    if action == "fold":
        # Don't fold when checking is free
        to_call = game_context.current_bet - game_context.committed
        if to_call <= 0:
            return ("check_call", {})
        return ("fold", {})
    elif action == "call":
        return ("check_call", {})
    elif action == "raise":
        amount = payload.get("amount", game_context.min_raise)
        # Convert to raise-to format
        raise_to = game_context.current_bet + amount
        max_raise = game_context.committed + game_context.stack
        min_raise_to = game_context.current_bet + game_context.min_raise
        raise_to = max(min_raise_to, min(raise_to, max_raise))
        return ("bet_raise", {"amount": raise_to})
    return None


def _map_action_to_game(
    action: str, bet_amount: int, game_context: AIGameContext
) -> tuple[str, dict]:
    """Map internal scoring action to game (action, payload) format.

    Internal actions: "fold", "check", "call", "bet", "raise"
    Game actions: "fold", "check_call", "bet_raise"
    """
    if action == "fold":
        return ("fold", {})
    elif action in ("check", "call"):
        return ("check_call", {})
    elif action in ("bet", "raise"):
        # Ensure bet_amount is at least min_raise and at most all-in
        max_raise = game_context.committed + game_context.stack
        amount = max(game_context.min_raise, min(bet_amount, max_raise))
        return ("bet_raise", {"amount": amount})
    else:
        # Unknown action, default to check/call
        return ("check_call", {})
