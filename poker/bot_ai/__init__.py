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
    BALANCED_PROFILE,
    PokerPersonality,
    get_action_multipliers,
    get_personality,
)
from poker.bot_ai.difficulty_controller import (
    DifficultyLevel,
    get_active_subsystems,
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
from poker.bot_ai.sanity_gates import (
    GateContext,
    PREMIUM_HANDS,
    apply_sanity_gates,
    validate_selection,
    _get_hand_representation,
)
from poker.bot_ai.exploit_metrics import ExploitMetrics, record_decision

# Thread-local-ish debug storage — populated by advanced_bot_decide, read by caller
_last_decision_debug: dict = {}

# ─── Exploit metrics singleton (Patch 1) ──────────────────────────────────────
# Persists across decisions within a session/simulation.
_exploit_metrics = ExploitMetrics()


def get_exploit_metrics() -> ExploitMetrics:
    """Return the current session-level exploit metrics instance."""
    return _exploit_metrics


def reset_exploit_metrics() -> None:
    """Reset exploit metrics to zero (for testing and new simulations)."""
    global _exploit_metrics
    _exploit_metrics = ExploitMetrics()


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
    import time as _time
    _t0 = _time.perf_counter()
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
    _t1 = _time.perf_counter()
    equity = _compute_equity_with_range(game_context, subsystems, opponent_range)
    _t2 = _time.perf_counter()
    print(f"  [TIMING] equity={equity:.3f} took {(_t2-_t1)*1000:.0f}ms (phase={game_context.phase})")

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
            personality=BALANCED_PROFILE,
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
            personality=BALANCED_PROFILE,
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
        personality=BALANCED_PROFILE,  # Always use balanced profile in normal gameplay
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
    _t3 = _time.perf_counter()
    scores = compute_base_scores(scoring_ctx, legal_actions)
    _t4 = _time.perf_counter()
    print(f"  [TIMING] scoring took {(_t4-_t3)*1000:.0f}ms")

    # Capture pre-noise scores for logging
    from dataclasses import asdict
    try:
        base_scores_snapshot = asdict(scores)
    except Exception:
        base_scores_snapshot = {}

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
    noise_exploitability = BALANCED_PROFILE.exploitability
    if difficulty == DifficultyLevel.EASY:
        noise_exploitability *= 2.0
    elif difficulty == DifficultyLevel.MEDIUM:
        noise_exploitability *= 1.5

    scores = apply_noise(scores, noise_exploitability, game_context.pot)

    # ─── NEW (Patch 1): Apply sanity gates after noise, before selection ───
    # Build GateContext from available pipeline data
    _hand_repr = _get_hand_representation(game_context.hole_cards)
    _is_premium = _hand_repr in PREMIUM_HANDS

    # Compute hand_class from terminology classifier (postflop only)
    _hand_class = "trash"  # Default for preflop or if classification fails
    if game_context.phase != "preflop" and game_context.community:
        try:
            from poker.terminology import classify_hand as _classify
            _classify_result = _classify(game_context.hole_cards, game_context.community)
            _made_hand = _classify_result.get("made_hand", "")
            # Map terminology labels to HAND_CLASS_ORDER keys
            _terminology_to_hand_class = {
                "Straight Flush!": "straight_flush",
                "Quads": "quads",
                "Full House": "full_house",
                "Flush (both cards)": "flush",
                "Flush (one card)": "flush",
                "Board Flush": "flush",
                "Straight": "straight",
                "Set": "set",
                "Trips": "set",
                "Three of a Kind": "set",
                "Two Pair": "two_pair",
                "Overpair": "overpair",
                "Top Pair": "top_pair",
                "Middle Pair": "middle_pair",
                "Bottom Pair": "bottom_pair",
                "Board Pair": "trash",
                "Two Overcards": "trash",
                "One Overcard": "trash",
                "High Card": "trash",
            }
            _hand_class = _terminology_to_hand_class.get(_made_hand, "trash")
        except Exception:
            _hand_class = "trash"

    # Compute hand_percentile: use equity as a proxy (0.0 = best)
    # Equity of 1.0 → percentile 0.0, equity of 0.0 → percentile 1.0
    _hand_percentile = 1.0 - equity

    # Compute effective_stack_bb
    _effective_stack_bb = (
        game_context.stack / game_context.big_blind
        if game_context.big_blind > 0
        else 100.0
    )

    # Compute SPR (stack-to-pot ratio)
    _spr = (
        game_context.stack / game_context.pot
        if game_context.pot > 0
        else 20.0
    )

    # Determine would_be_all_in: True if raising commits full remaining stack
    _would_be_all_in = is_allin

    # Derive has_strong_draw from terminology draws (flush draw + pair, or OESFD)
    _has_strong_draw = False
    if game_context.phase != "preflop" and game_context.community:
        try:
            from poker.terminology import classify_hand as _classify2
            _draw_result = _classify2(game_context.hole_cards, game_context.community)
            _draws = _draw_result.get("draws", [])
            _has_flush_draw = any("flush draw" in d.lower() for d in _draws)
            _has_oesd = any("open-ended" in d.lower() for d in _draws)
            _has_pair = _hand_class in ("bottom_pair", "middle_pair", "top_pair", "overpair")
            # Strong draw: flush draw + pair, or open-ended straight flush draw
            _has_strong_draw = (_has_flush_draw and _has_pair) or (_has_flush_draw and _has_oesd)
        except Exception:
            _has_strong_draw = False

    gate_context = GateContext(
        hole_cards=game_context.hole_cards,
        hand_percentile=_hand_percentile,
        is_premium=_is_premium,
        effective_stack_bb=_effective_stack_bb,
        facing_action=game_context.facing_action,
        phase=game_context.phase,
        hand_class=_hand_class,
        board_texture=board_texture,
        equity=equity,
        pot_odds=pot_odds,
        pot=game_context.pot,
        spr=_spr,
        has_strong_draw=_has_strong_draw,
        remaining_stack=game_context.stack,
        would_be_all_in=_would_be_all_in,
        raises_faced_this_street=game_context.raises_faced_this_street,
        legal_actions=legal_actions,
    )

    scores = apply_sanity_gates(scores, gate_context)

    # ─── Select action ─────────────────────────────────────────────────────
    chosen_action = select_action(scores)

    # ─── NEW (Patch 1): Validate selection against forbidden gates ─────────
    chosen_action = validate_selection(chosen_action, scores, legal_actions)

    # ─── NEW (Patch 1): Record decision for exploit metrics ────────────────
    record_decision(_exploit_metrics, chosen_action, gate_context)

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
                personality=BALANCED_PROFILE,
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
    final_action, final_payload = _map_action_to_game(chosen_action, bet_amount, game_context)
    _t5 = _time.perf_counter()
    print(f"  [TIMING] total decision: {(_t5-_t0)*1000:.0f}ms -> {final_action} (equity calc={(_t2-_t1)*1000:.0f}ms)")

    # Store debug info for logging (accessed by caller)
    try:
        final_scores_dict = asdict(scores)
    except Exception:
        final_scores_dict = {}
    _last_decision_debug.update({
        "equity": round(equity, 4),
        "pot_odds": round(pot_odds, 4),
        "base_scores": {k: round(v, 4) for k, v in base_scores_snapshot.items()} if isinstance(base_scores_snapshot, dict) else {},
        "final_scores": {k: round(v, 4) for k, v in final_scores_dict.items()},
        "chosen_internal_action": chosen_action,
        "final_action": final_action,
        "bet_amount": bet_amount,
        "personality_style": personality.name if hasattr(personality, 'name') else str(personality),
        "difficulty": difficulty.name,
        "legal_actions": legal_actions,
        "bluff_score_total": round(bluff_score.total, 4) if hasattr(bluff_score, 'total') else 0,
        "position": game_context.position,
        "facing_action": game_context.facing_action,
        "is_preflop_aggressor": game_context.is_preflop_aggressor,
        "noise_exploitability": round(noise_exploitability, 4),
    })

    return final_action, final_payload


# ─── Private helpers ───────────────────────────────────────────────────────────


def _compute_equity(game_context: AIGameContext) -> float:
    """Compute equity using Monte Carlo with reduced simulations for fast bot decisions."""
    try:
        from poker.odds import estimate_equity, preflop_equity_lookup

        board = game_context.community
        if len(board) == 0:
            # Preflop: instant lookup
            result = preflop_equity_lookup(game_context.hole_cards, game_context.num_opponents)
        else:
            # Postflop: always use Monte Carlo (150 sims) — fast enough for bot decisions
            # Avoids the expensive exact enumeration on turn that takes 3-5 seconds
            result = estimate_equity(
                game_context.hole_cards,
                board,
                game_context.num_opponents,
                simulations=150,
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
