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
from poker.bot_ai.bluff_calculator import compute_bluff_score, compute_fold_equity
from poker.bot_ai.preflop_charts import get_preflop_decision
from poker.bot_ai.bet_sizer import compute_bet_size, compute_bet_size_with_equity_cap, add_sizing_noise, SizingContext
from poker.bot_ai.action_scorer import (
    compute_base_scores,
    apply_allin_cap,
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

    # 4b. Compute equity (range-aware if available)
    equity = _compute_equity_with_range(game_context, subsystems, opponent_range)

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

    # 4f-i. Compute fold probability from opponent stats via fold equity calculator.
    # Use a default bet_size_ratio of 0.7 (typical 70% pot bet) since the actual
    # bet size hasn't been determined yet at this point in the pipeline.
    fold_equity_bet_ratio = 0.7
    try:
        fold_probability = compute_fold_equity(
            opponent_stats, fold_equity_bet_ratio, game_context.phase
        )
    except Exception:
        fold_probability = 0.35  # Fallback to default

    # 4f-ii. Compute bet_amount, raise_amount, call_amount, num_opponents for EV calculator.
    # These populate the ScoringContext so compute_ev_scores has all inputs it needs.
    call_amount = max(0, game_context.current_bet - game_context.committed)
    num_opponents = max(1, game_context.num_opponents)

    # Compute bet_amount via bet_sizer using game context
    try:
        is_value_bet = equity > 0.55
        is_polarized = game_context.phase == "river"
        sizing_ctx = SizingContext(
            street=game_context.phase,
            board_texture=board_texture,
            range_advantage=range_advantage,
            pot=game_context.pot,
            is_value_bet=is_value_bet,
            is_polarized=is_polarized,
            personality=personality,
        )
        max_raise_amount = game_context.committed + game_context.stack
        min_raise_amount = game_context.min_raise
        bet_amount = compute_bet_size(sizing_ctx, min_raise_amount, max_raise_amount)
    except Exception:
        bet_amount = game_context.min_raise

    # Compute raise_amount: use a larger sizing (2.5× current bet, or bet_sizer with adjusted pot)
    try:
        # Raise amount is typically larger than a standard bet — model the pot as if
        # it already contains the opponent's bet (pot + call_amount) for sizing purposes.
        raise_pot = game_context.pot + call_amount
        raise_sizing_ctx = SizingContext(
            street=game_context.phase,
            board_texture=board_texture,
            range_advantage=range_advantage,
            pot=raise_pot,
            is_value_bet=is_value_bet,
            is_polarized=is_polarized,
            personality=personality,
        )
        raise_amount = compute_bet_size(raise_sizing_ctx, min_raise_amount, max_raise_amount)
        # Ensure raise_amount is at least as large as bet_amount
        raise_amount = max(raise_amount, bet_amount)
    except Exception:
        # Fallback: raise_amount = 2.5× current bet, clamped to [min_raise, max_raise]
        raise_amount = max(
            game_context.min_raise,
            min(int(game_context.current_bet * 2.5), game_context.committed + game_context.stack),
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
        fold_probability=fold_probability,
        bet_amount=bet_amount,
        raise_amount=raise_amount,
        call_amount=call_amount,
        num_opponents=num_opponents,
        pot=game_context.pot,
        difficulty_level=difficulty.name,  # Pass difficulty for gated EV behavior
    )

    # 4g. Compute base scores → apply all-in cap → apply noise → select action
    # NOTE: Personality modifiers are now embedded inside compute_base_scores via
    # compute_modifiers(). The separate apply_personality step has been removed to
    # avoid double-counting personality influence.
    scores = compute_base_scores(scoring_ctx, legal_actions)

    # Detect if raise would be all-in: when min_raise >= stack, any raise
    # commits the player's entire remaining stack.
    max_raise = game_context.committed + game_context.stack
    is_allin = game_context.min_raise >= game_context.stack or max_raise <= game_context.min_raise
    if is_allin:
        scores = apply_allin_cap(scores, equity)

    # Difficulty-gated noise scaling:
    # EASY: 2× exploitability → more random/exploitable play
    # MEDIUM: 1.5× exploitability → moderately noisy
    # HARD/EXPERT: 1× exploitability → normal noise
    noise_exploitability = personality.exploitability
    if difficulty == DifficultyLevel.EASY:
        noise_exploitability *= 2.0
    elif difficulty == DifficultyLevel.MEDIUM:
        noise_exploitability *= 1.5

    scores = apply_noise(scores, noise_exploitability, game_context.pot)
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
            bet_amount = compute_bet_size_with_equity_cap(
                sizing_ctx, game_context.min_raise, max_raise, equity
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


def _compute_equity_with_range(
    game_context: AIGameContext,
    subsystems: ActiveSubsystems,
    opponent_range: RangeEstimate,
) -> float:
    """Compute equity, using range-aware calculation when range data is available.

    When range_tracking is active and the opponent's range has been narrowed
    (at least one category weight < 0.9), uses estimate_equity_vs_range to
    sample opponent hands from the narrowed range distribution.

    Otherwise, falls back to the standard hybrid equity calculator.

    Args:
        game_context: Current game state.
        subsystems: Active AI subsystems (checked for range_tracking).
        opponent_range: The opponent's current RangeEstimate from the range tracker.

    Returns:
        Equity value between 0.0 and 1.0.
    """
    if subsystems.range_tracking and opponent_range is not None:
        try:
            from poker.odds import estimate_equity_vs_range, _range_estimate_to_combo_range

            # Convert 6-category range estimate to 169 hand-class combo_range
            combo_range = _range_estimate_to_combo_range(opponent_range)

            # Check if range has been meaningfully narrowed (not all weights near 1.0)
            if any(w < 0.9 for w in combo_range.values()):
                equity_result = estimate_equity_vs_range(
                    hero_cards=game_context.hole_cards,
                    board_cards=game_context.community,
                    combo_range=combo_range,
                    num_opponents=game_context.num_opponents,
                )
                return equity_result["equity"]
        except Exception:
            pass  # Fall through to standard equity calculation

    # Fallback: standard equity calculation
    return _compute_equity(game_context)


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

    The game server uses "raise to" semantics for bet_raise amounts:
      amount = total chips committed after the action
    So the minimum legal raise is: current_bet + min_raise
    """
    if action == "fold":
        return ("fold", {})
    elif action in ("check", "call"):
        return ("check_call", {})
    elif action in ("bet", "raise"):
        # Server uses "raise to" semantics: amount = total committed after action
        # Minimum legal raise-to = current_bet + min_raise
        min_raise_to = game_context.current_bet + game_context.min_raise
        max_raise_to = game_context.committed + game_context.stack

        # If player can't afford the minimum raise, go all-in
        if min_raise_to > max_raise_to:
            amount = max_raise_to
        else:
            # Clamp bet_amount to legal range [min_raise_to, max_raise_to]
            amount = max(min_raise_to, min(bet_amount, max_raise_to))
        return ("bet_raise", {"amount": amount})
    else:
        # Unknown action, default to check/call
        return ("check_call", {})
