from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static(name: str) -> str:
    return (ROOT / "static" / name).read_text(encoding="utf-8")


def test_hand_history_markup_exists():
    html = read_static("index.html")

    assert 'id="handHistoryToggle"' in html
    assert 'id="handHistoryCount"' in html
    assert 'id="handHistoryPanel"' in html
    assert 'id="handHistoryClose"' in html
    assert 'id="handHistoryBody"' in html
    assert "History " in html


def test_hand_history_button_lives_in_left_hud_not_chat_side():
    html = read_static("index.html")

    left = html.split('<div class="hud-left">', 1)[1].split('<div class="hud-right">', 1)[0]
    right = html.split('<div class="hud-right">', 1)[1]

    assert 'id="handHistoryToggle"' in left
    assert 'id="handHistoryToggle"' not in right
    assert left.index('id="copyRoomBtn"') < left.index('id="handHistoryToggle"')


def test_compact_history_panel_renderer_is_wired():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function completedHandHistoryFromState(state)" in app
    assert "function renderHandHistory(state)" in app
    assert "summarizeHistoryWinners(winners)" in app
    assert "renderHistoryBoard(community)" in app
    assert "handHistoryCount" in app
    assert "handHistoryBody" in app
    assert ".hand-history-panel" in css
    assert ".hand-history-row" in css


def test_default_panels_auto_open_once_per_room():
    app = read_static("app.js")

    assert "let defaultPanelsRoomId" in app
    assert "function openDefaultPanelsForRoom(state)" in app
    assert "openDefaultPanelsForRoom(state);" in app
    assert "els.handHistoryPanel" in app
    assert "els.chatPanel" in app
    assert "els.actionLogPanel" in app
    assert "panelExpanded = true;" in app
    assert 'localStorage.setItem(PANEL_KEY, "true")' in app
    assert "const defaultExpanded = true" in app


def test_history_review_uses_post_hand_modal_instead_of_inline_expansion():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "hand_history_details" in app
    assert "selectedHistoryReviewKey" in app
    assert "function selectedHistoryReviewFromState(state)" in app
    assert "function hasCurrentHandComplete(state)" in app
    assert "data-history-review-key" in app
    assert "Open hand-complete review" in app
    assert "History review - Hand #" in app
    assert "Close review" in app
    assert "currentHandCompleteVisible" in app
    assert ".hand-history-review-btn" in css


def test_history_review_modal_has_overlay_and_close_controls():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function syncHistoryReviewChrome(visible)" in app
    assert "historyReviewCloseBtn" in app
    assert "Escape" in app
    assert "History review click-outside close" in app
    assert "pointerdown" in app
    assert "els.postHandPanel.contains(event.target)" in app
    assert "history-review-open" in app
    assert "body.history-review-open::before" in css
    assert ".history-review-close-btn" in css


def test_history_review_modal_renders_saved_board_and_keeps_close_clear_of_pot_badge():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "historyReviewDisplayState" in app
    assert "const cinemaState = historyReviewDisplayState || state" in app
    assert "renderShowdownTray(cinemaState)" in app
    assert 'const historyReviewBoard = "";' in app
    assert ".history-review-board-strip" in css
    assert "margin-right" in css


def test_history_review_infers_revealed_cards_without_leaking_hidden_cards():
    app = read_static("app.js")

    assert "function inferRevealModeFromHistoryCards(cards)" in app
    assert "function isHiddenHistoryCard(card)" in app
    assert 'card === "BACK"' in app
    assert "function normalizeHistoryReviewPlayer(player, hand)" in app
    assert "normalizeHistoryReviewPlayer(player, hand)" in app
    assert "can_reveal_folded_hand: false" in app
    assert "can_reveal_uncontested_hand: false" in app
    assert "!isHiddenHistoryCard(cards[0])" in app
    assert "!isHiddenHistoryCard(cards[1])" in app
    assert "historyWinnerIds(hand)" in app


def test_history_review_can_render_persisted_would_have_breakdowns():
    app = read_static("app.js")

    assert "renderFoldedWouldHaveBreakdown(p, state)" in app
    assert "would_have_best_cards" in app
    assert "would_have_hand_detail" in app
    assert "renderBestFiveBreakdownHtml" in app


def test_history_review_modal_uses_hand_complete_sized_layout_without_snap():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "history-review-modal" in app
    assert "const historyReviewVisible = visible && historyReviewMode" in app
    assert 'classList.toggle("history-review-modal", historyReviewVisible)' in app
    assert "syncHistoryReviewChrome(historyReviewVisible)" in app
    assert "rerenderStatePreservingHistoryScroll" in app
    assert 'els.handHistoryPanel.classList.remove("hidden")' in app
    assert "previousHistoryScrollTop" in app
    assert "history-review-cinema" in app
    assert 'classList.toggle("hidden", !visible)' in app

    block = app.split("const historyReviewVisible = visible && historyReviewMode", 1)[1]
    block = block.split("if (!visible)", 1)[0]
    assert block.index('classList.toggle("history-review-modal", historyReviewVisible)') < block.index('classList.toggle("hidden", !visible)')

    assert "History review matched hand-complete sizing" in css
    assert "History review snap prevention" in css
    assert "History review uses live hand-complete cinema layout" in css
    assert "body.history-review-open.history-review-cinema #postHandPanel.post-hand-modal.history-review-modal" in css
    assert "width: min(980px" in css
    assert "transform: translateX(-50%)" in css
    assert "max-height: min(72vh, 680px)" in css
    assert "postHandResultStageGrow" in css
    assert "body.history-review-open.history-review-cinema #showdownTray" in css


def test_static_assets_are_cache_busted():
    html = read_static("index.html")

    assert "/static/styles.css?v=" in html
    assert "/static/app.js?v=" in html


def test_right_rail_stacks_action_log_and_chat():
    css = read_static("styles.css")

    assert "--right-rail-width: 220px" in css
    assert "Right rail: smaller action log with chat underneath" in css
    assert "body.action-log-open .chat-panel" in css
    assert "top: calc(48vh + 58px)" in css
    assert "width: var(--right-rail-width)" in css


def test_history_review_drives_action_log_from_selected_hand():
    app = read_static("app.js")

    assert "const cinemaState = historyReviewDisplayState || state" in app
    assert "renderActionLog(cinemaState)" in app
    assert "state.hand_number || state.hands_played || 0" in app


def test_table_seats_are_clustered_around_bigger_felt():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'const SEAT_POSITIONS = [' in app
    assert '{ top: "80%", left: "50%" }' in app
    assert '{ top: "49%", left: "24%" }' in app
    assert '{ top: "49%", left: "76%" }' in app
    assert '{ top: "18%", left: "50%" }' in app

    assert "Table seating layout polish: players sit around the felt" in css
    assert "width: min(940px" in css
    assert "calc(100vw - 560px)" in css
    assert "border-radius: 48% / 38%" in css


def test_right_rail_does_not_shift_table_and_seats_are_readable():
    css = read_static("styles.css")

    assert "Rail stability + readable player seats polish" in css
    assert "body.action-log-open .poker-table" in css
    assert "padding: 54px 250px 118px 250px" in css
    assert ".action-log-toggle.panel-collapsed" in css
    assert "top: 58px" in css
    assert "width: 172px" in css
    assert "height: 130px" in css
    assert "width: 36px" in css
    assert "height: 52px" in css


def test_right_rail_has_no_floating_toggle_and_chat_is_bottom_right():
    css = read_static("styles.css")

    assert "Fixed right rail without floating action-log tab" in css
    assert ".action-log-toggle" in css
    assert "display: none !important" in css
    assert ".action-log-panel.collapsed" in css
    assert "transform: none !important" in css
    assert "opacity: 1 !important" in css
    assert "bottom: 10px !important" in css
    assert "height: min(36vh, 360px)" in css


def test_admin_panel_is_bottom_left_management_dock():
    html = read_static("index.html")
    css = read_static("styles.css")

    assert 'class="admin-side-panel admin-dock hidden"' in html
    assert "Table tools" in html
    assert "Bot level" in html
    assert "Kick problem players between hands." in html
    assert "Bottom-left admin dock" in css
    assert "left: 12px !important" in css
    assert "bottom: 12px !important" in css
    assert "right: auto !important" in css
    assert ".admin-dock-bot-row" in css


def test_admin_dock_uses_plain_text_controls_not_emoji():
    html = read_static("index.html")

    assert ">Reset<" in html
    assert ">Pause<" in html
    assert ">+ Bot<" in html
    assert ">- Bot<" not in html
    assert "removeBotBtn" not in html
    assert "??" not in html
    assert "? Reset" not in html
    assert "? Pause" not in html


def test_admin_dock_renders_player_list_and_kick_controls():
    html = read_static("index.html")
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'id="adminPlayerList"' in html
    assert "Kick problem players between hands." in html
    assert "function renderAdminPlayerList(state)" in app
    assert "adminPlayerStatusLabels(player, viewerIsAdmin)" in app
    assert 'action("kick_player", { target_player_id: targetId })' in app
    assert "data-admin-kick-id" in app
    assert "Kick" in app
    assert "Admin dock player management list" in css
    assert ".admin-player-row.is-admin" in css
    assert ".admin-kick-btn" in css


def test_backend_exposes_player_admin_fields_and_transfer_action():
    game = (ROOT / "poker" / "game.py").read_text(encoding="utf-8")

    assert 'if action == "transfer_admin":' in game
    assert 'target_player_id = str(payload.get("target_player_id", "")).strip()' in game
    assert 'Bots cannot become table admin.' in game
    assert 'room.creator_token = target.token' in game
    assert '"is_admin": p.token == room.creator_token' in game
    assert '"bot_difficulty": self.bots[p.player_id].difficulty if p.player_id in self.bots else ""' in game


def test_admin_player_rows_are_name_and_actions_without_stack_transfer_to_self():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "Mock" in app
    assert "DM" in app
    assert "Kick" in app
    assert "Mock action coming soon" in app
    assert "Direct messages coming soon" in app
    assert "!isSelf" in app
    assert "viewerIsAdmin && player.is_you" in app
    assert "admin-player-seat" in app
    assert "admin-player-stack" in app

    assert "Cleaner admin player action rows" in css
    assert ".admin-player-stack" in css
    assert "display: none !important" in css
    assert ".admin-player-action-btn" in css
    assert ".admin-kick-btn" in css


def test_admin_can_kick_specific_non_self_players_between_hands():
    game = (ROOT / "poker" / "game.py").read_text(encoding="utf-8")
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'if action == "kick_player":' in game
    assert 'Kick players between hands only.' in game
    assert 'You cannot kick yourself.' in game
    assert 'room.players.pop(target.player_id, None)' in game
    assert 'self.bots.pop(target.player_id, None)' in game

    assert "data-admin-kick-id" in app
    assert 'action("kick_player", { target_player_id: targetId })' in app
    assert "canKickTarget = viewerIsAdmin && !isCurrentAdmin && !isSelf" in app
    assert "Kick" in app

    assert "Admin kick player action" in css
    assert ".admin-kick-btn" in css


def test_admin_player_list_is_kick_only_no_manage_button():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "safeKickPhase" in app
    assert "Kick after hand" in app
    assert "data-admin-kick-id" in app
    assert 'action("kick_player", { target_player_id: targetId })' in app
    assert "removeBotBtn" not in app
    assert 'action("remove_bot")' not in app
    assert "data-admin-transfer-id" not in app
    assert "Make Admin" not in app
    assert "Manage" not in app

    assert "Kick-only admin player actions" in css
    assert ".admin-kick-btn.disabled" in css


def test_admin_dock_has_fixed_size_player_scroll_region():
    css = read_static("styles.css")

    assert "Fixed-size admin dock layout" in css
    assert "height: 430px !important" in css
    assert "max-height: 430px !important" in css
    assert ".admin-player-list" in css
    assert "overflow-y: auto !important" in css


def test_admin_dock_rows_stay_compact_inside_fixed_panel():
    css = read_static("styles.css")

    assert "Compact fixed admin dock rows" in css
    assert "height: 360px !important" in css
    assert "grid-auto-rows: max-content !important" in css
    assert "align-self: start !important" in css
    assert "height: 21px !important" in css


def test_admin_self_row_has_no_action_buttons():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "const isSelf = Boolean(player.is_you)" in app
    assert "const mockHtml = isSelf" in app
    assert "const dmHtml = isSelf" in app
    assert "!isSelf" in app
    assert "is-self" in app
    assert "Admin self row has no action buttons" in css
    assert ".admin-self-note" in css


def test_table_roster_visible_for_all_with_admin_controls_gated():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'els.adminActions.classList.remove("hidden")' in app
    assert 'els.adminActions.classList.toggle("is-table-admin", viewerIsAdmin)' in app
    assert 'dockTitle.textContent = viewerIsAdmin ? "Admin" : "Table"' in app
    assert 'dockSubtitle.textContent = viewerIsAdmin ? "Table roster" : "Players"' in app
    assert "canKickTarget = viewerIsAdmin && !isCurrentAdmin && !isSelf" in app
    assert "is-self" in app

    assert "Messenger-style table roster panel" in css
    assert ".admin-dock:not(.is-table-admin) .admin-dock-grid" in css
    assert "width: 330px !important" in css
    assert "grid-template-columns: minmax(0, 1fr) auto !important" in css
    assert ".admin-player-row.is-self .admin-player-actions" in css


def test_roster_distinguishes_bots_players_and_styles_scrollbar():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'labels.push("Player")' in app
    assert 'player.is_bot ? " is-bot" : " is-human"' in app
    assert "Roster human/bot distinction and scrollbar polish" in css
    assert ".admin-player-row.is-human" in css
    assert ".admin-player-row.is-bot" in css
    assert 'content: "BOT"' in css
    assert 'content: "PLAYER"' in css
    assert ".admin-player-list::-webkit-scrollbar" in css
    assert "scrollbar-color" in css

def test_auto_deal_toggle_visible_to_admin_even_during_hand():
    app = read_static("app.js")

    assert "const viewerIsAdmin = Boolean(state && state.viewer && state.viewer.is_admin)" in app
    assert "setAutoDealToggleState(viewerIsAdmin)" in app
    assert "setAutoDealToggleState(canDeal)" not in app


def test_auto_deal_frontend_uses_backend_state():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function syncAutoDeal(state)" in app
    assert "state.auto_deal_enabled" in app
    assert "state.auto_deal_active" in app
    assert "state.auto_deal_remaining_seconds" in app
    assert 'action("toggle_auto_deal", { enabled: !autoDealEnabled })' in app
    assert "Auto-deal in" in app
    assert "Dealing next hand..." in app
    assert "Waiting for next hand..." not in app
    assert "autoDealTimerId" not in app
    assert "autoDealStateKey" not in app
    assert "AUTO_DEAL_STORAGE_KEY" not in app
    assert "AUTO_DEAL_DELAY_SECONDS" not in app
    assert "autoDealDeadlineMs = Date.now()" not in app
    assert "Visible post-hand auto-deal countdown" in css
    assert "Public auto-deal countdown visibility" in css


def test_auto_deal_countdown_surface_is_public_not_admin_only():
    app = read_static("app.js")

    assert "function ensureAutoDealCountdownSurface()" in app
    assert "autoDealPostHandCountdown" in app
    assert "postHandPanel.insertBefore(postHandCountdown, anchor)" in app
    assert "postHandActions.prepend(postHandCountdown)" not in app


def test_action_timer_frontend_uses_backend_state_only():
    app = read_static("app.js")

    assert "function actionTimerText(state, isMyTurn)" in app
    assert "state.action_timer_active" in app
    assert "state.action_timer_player_id" in app
    assert "state.action_timer_regular_remaining_seconds" in app
    assert "state.action_timer_timebank_remaining_seconds" in app
    assert "state.action_timer_using_timebank" in app
    assert "state.action_timer_remaining_seconds" not in app.split("function actionTimerText", 1)[1].split("function numberOrZero", 1)[0]
    assert "viewer.timebank_seconds" in app
    assert "thinking -" in app
    assert "action_timer_regular_remaining_seconds" in app
    assert "action_timer_timebank_remaining_seconds" in app
    assert "action_timer_using_timebank" in app
    assert "setTimeout" not in app.split("function actionTimerText", 1)[1].split("function numberOrZero", 1)[0]
    assert 'action("fold")' not in app.split("function actionTimerText", 1)[1].split("function numberOrZero", 1)[0]
    assert 'action("check_call")' not in app.split("function actionTimerText", 1)[1].split("function numberOrZero", 1)[0]


def test_timeout_action_log_labels_render_safely():
    app = read_static("app.js")

    assert 'case "timeout_check": return `${player} times out and checks`;' in app
    assert 'case "timeout_fold":  return `${player} times out and folds`;' in app


def test_timer_timebank_ui_is_separated_and_seat_visible():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "Action ${regular}s" in app
    assert "Timebank ${actingBank}s" in app
    assert "Bank ${viewerBank}s" in app
    assert "YOUR ACTION - ${clockText}" in app
    assert "const bankHtml =" in app
    assert "seat-timebank" in app
    assert "Timer/timebank clarity pass" in css
    assert ".seat-timebank" in css


def test_hand_history_scrollbar_is_styled():
    css = read_static("styles.css")

    assert "Hand history scrollbar polish" in css
    assert ".hand-history-body::-webkit-scrollbar" in css
    assert ".hand-history-body::-webkit-scrollbar-thumb" in css
    assert "scrollbar-color" in css


def test_action_console_bank_and_explicit_sit_controls_ui():
    app = read_static("app.js")
    html = read_static("index.html")
    css = read_static("styles.css")

    assert "function syncActionConsoleBank(state)" in app
    assert "actionConsoleBank" in app
    assert "syncActionConsoleBank(state);" in app
    assert "Sit Out Next" not in app
    assert "Cancel Sit Out" not in app
    assert "sit_out_next_hand" not in app
    assert "SIT NEXT" not in app
    assert 'id="sitOutBtn"' in html
    assert 'id="sitInBtn"' in html
    assert 'id="rebuyBtn"' in html
    assert 'action("sit_out", { sitting_out: true })' in app
    assert 'action("sit_out", { sitting_out: false })' in app
    assert 'action("rebuy", {})' in app
    assert "Action console timebank pill" in css
    assert ".action-console-bank" in css


def test_showdown_modal_compact_row_repair_css_exists():
    css = read_static("styles.css")

    assert "Showdown modal compact row repair" in css
    assert ".post-hand-panel.post-hand-modal .post-hand-row" in css
    assert ".post-hand-panel.post-hand-modal .post-hand-cards .playing-card" in css


def test_sit_out_sit_in_and_rebuy_are_separate_buttons():
    app = read_static("app.js")

    assert 'els.sitOutBtn.textContent = "Sit Out"' in app
    assert 'els.sitInBtn.textContent = "Sit In"' in app
    assert 'els.rebuyBtn.textContent = `Rebuy #${nextBuyIn}`' in app
    assert 'els.sitInBtn.disabled = Boolean(!viewerData.sitting_out || numberOrZero(viewerData.stack) <= 0);' in app
    assert 'const canRebuy = Boolean(viewerData.can_rebuy || (state.viewer && state.viewer.can_rebuy));' in app
    assert "sit_out_next_hand" not in app
    assert "Sit Out Next" not in app
    assert "Cancel Sit Out" not in app
    assert "SIT NEXT" not in app

def test_create_lobby_exposes_timer_timebank_settings():
    html = read_static("index.html")
    app = read_static("app.js")

    assert 'id="autoDealDelayInput"' in html
    assert 'id="actionTimeInput"' in html
    assert 'id="startingTimebankInput"' in html
    assert 'id="timebankGainInput"' in html
    assert "Auto-deal delay" in html
    assert "Action timer" in html
    assert "Starting timebank" in html
    assert "Timebank gain / hand" in html

    assert '"autoDealDelayInput"' in app
    assert '"actionTimeInput"' in app
    assert '"startingTimebankInput"' in app
    assert '"timebankGainInput"' in app
    assert "function numberInputValue(input, fallback)" in app
    assert "const autoDealDelay = numberInputValue(els.autoDealDelayInput, 5);" in app
    assert "const actionTime = numberInputValue(els.actionTimeInput, 10);" in app
    assert "const startingTimebank = numberInputValue(els.startingTimebankInput, 100);" in app
    assert "const timebankGain = numberInputValue(els.timebankGainInput, 1);" in app
    assert "auto_deal_delay_seconds: autoDealDelay" in app
    assert "action_time_seconds: actionTime" in app
    assert "starting_timebank_seconds: startingTimebank" in app
    assert "timebank_gain_per_hand: timebankGain" in app

def test_room_settings_chevron_tracks_expanded_state():
    app = read_static("app.js")

    assert "const syncSettingsExpanded = () =>" in app
    assert 'settHeader.setAttribute("aria-expanded", expanded ? "true" : "false")' in app
    assert "const toggleSettingsExpanded = () =>" in app
    assert 'event.key === "Enter" || event.key === " "' in app
    assert "toggleSettingsExpanded();" in app


def test_table_center_cluster_polish_css_exists():
    css = read_static("styles.css")

    assert "Table center cluster polish v1" in css
    assert ".community-cards:empty" in css
    assert ".community-cards:not(:empty)" in css
    assert ".seat-bet-marker" in css
    assert ".seat-bet-label" in css
    assert "calc(100vw - 560px)" in css
    assert "border-radius: 48% / 38%" in css
    assert "transform: scale(0.82)" in css

def test_center_pot_chips_use_displayed_amount_and_hide_empty_state():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "const centerPotAmount = displayedCenterPotAmount(state);" in app
    assert "renderChipStackHtml(centerPotAmount" in app
    assert 'els.potChips.classList.toggle("is-empty", centerPotAmount <= 0);' in app
    assert ".pot-chips.is-empty" in css
    assert "min-height: 0" in css

def test_bet_markers_are_clamped_to_felt_geometry():
    app = read_static("app.js")

    assert "function feltClampedBetMarkerPosition(seatEl, visualSeat)" in app
    assert "getBoundingClientRect()" in app
    assert 'document.querySelector(".table-felt")' in app
    assert "clampNumber(pageX" in app
    assert "clampNumber(pageY" in app
    assert "fallbackBetMarkerPosition(visualSeat)" in app
    assert "renderSeatBetMarker(p, visualSeat, seat)" in app
    assert 'left: `${pageX - containerRect.left}px`' in app
    assert 'top: `${pageY - containerRect.top}px`' in app

def test_showdown_compact_mode_has_responsive_scrollable_body():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "const visibleResultRowCount = revealedPlayers.length + foldedPlayers.length;" in app
    assert "const densePostHandRows = visibleResultRowCount >= 3;" in app
    assert "const manyPlayerPostHandRows = visibleResultRowCount >= 5;" in app
    assert "window.innerHeight <= 720" in app
    assert 'els.postHandPanel.classList.toggle("post-hand-small", visibleResultRowCount > 0 && visibleResultRowCount <= 2);' in app
    assert 'els.postHandPanel.classList.toggle("post-hand-dense", densePostHandRows);' in app
    assert 'els.postHandPanel.classList.toggle("post-hand-many-players", manyPlayerPostHandRows);' in app
    assert 'els.postHandPanel.classList.toggle("post-hand-compact", compactPostHandRows);' in app

    assert "Responsive showdown dense-result mode" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-compact" in css
    assert "max-height: calc(100vh - clamp(72px, 12vh, 132px))" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-compact .post-hand-body" in css
    assert "overflow-y: auto !important" in css
    assert "overscroll-behavior: contain" in css
    assert "@media (max-height: 720px)" in css
    assert "@media (max-width: 600px)" in css
    assert "grid-template-columns: minmax(86px, 1fr) minmax(76px, auto) auto" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-compact .post-hand-actions" in css

def test_adaptive_post_hand_density_modes_keep_small_showdowns_rich():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "post-hand-small" in app
    assert "post-hand-dense" in app
    assert "post-hand-many-players" in app
    assert "const showBestFiveBreakdown = !els.postHandPanel.classList.contains(\"post-hand-dense\")" in app
    assert "p.is_you && !els.postHandPanel.classList.contains(\"post-hand-many-players\")" in app
    assert "const breakdown = showBestFiveBreakdown ? renderBestFiveBreakdownHtml(p, state) : \"\";" in app

    assert "Adaptive showdown result density" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-small .post-hand-breakdown" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-dense .post-hand-row:not(.winner)" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-dense .post-hand-row:not(.winner) .post-hand-breakdown" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-many-players .post-hand-row.mucked" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-many-players .post-hand-row.mucked .post-hand-cards" in css
    assert "display: none !important" in css

def test_compact_post_hand_winner_rows_have_stable_card_layout():
    css = read_static("styles.css")

    assert "Compact post-hand winner row stability" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-compact .post-hand-title" in css
    assert "-webkit-line-clamp: 2" in css
    assert "font-size: clamp(15px, 1.45vw, 19px)" in css
    assert "grid-template-columns: minmax(104px, 0.78fr) minmax(134px, auto) minmax(0, 1fr) minmax(46px, auto)" in css
    assert "min-height: 50px !important" in css
    assert "max-width: 146px" in css
    assert "height: 38px !important" in css
    assert "flex: 0 0 26px !important" in css
    assert "grid-column: auto !important" in css
    assert "max-height: 38px !important" in css
    assert "@media (max-height: 720px), (max-width: 600px)" in css
    assert "grid-template-columns: minmax(78px, 0.9fr) minmax(112px, auto) minmax(0, 1fr) minmax(38px, auto)" in css
    assert "height: 31px !important" in css

def test_acting_player_outline_is_robust_and_visible():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function isPlayerCurrentlyActing(player, state)" in app
    assert "player.is_action" in app
    assert "player.is_turn" in app
    assert "state.action_seat" in app
    assert "state.action_timer_player_id" in app
    assert "const isActing = isPlayerCurrentlyActing(p, state);" in app
    assert 'if (isActing) cls += " active-turn";' in app

    assert "Acting player outline clarity v1" in css
    assert ".player-seat.active-turn::after" in css
    assert "content: attr(data-action-label)" in css
    assert "outline: 3px solid" in css
    assert ".player-seat.is-you.active-turn" in css

def test_acting_player_label_distinguishes_hero_from_others():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert 'seat.dataset.actionLabel = p.is_you ? "YOUR ACTION" : "ACTION";' in app
    assert "content: attr(data-action-label)" in css
    assert '.player-seat.active-turn[data-action-label="YOUR ACTION"]::after' in css

def test_sit_in_button_is_prominent_during_auto_deal_countdown():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "const showSitInDuringCountdown = Boolean(" in app
    assert "viewerData.sitting_out" in app
    assert 'state.phase === "showdown"' in app
    assert "state.auto_deal_active" in app
    assert 'els.actionBar.classList.toggle("show-sit-in-during-countdown", showSitInDuringCountdown)' in app
    assert 'els.sitInBtn.classList.toggle("sit-in-urgent", showSitInDuringCountdown)' in app

    assert "Sit In during auto-deal countdown" in css
    assert ".action-bar.show-sit-in-during-countdown" in css
    assert "#sitInBtn.sit-in-urgent" in css
    assert 'content: "next hand"' in css

def test_post_hand_recovery_buttons_are_available_during_auto_deal_countdown():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function syncPostHandRecoveryButtons(state, viewerData)" in app
    assert '"postHandSitInBtn"' in app
    assert '"postHandRebuyBtn"' in app
    assert '"Sit In next hand"' in app
    assert '`Rebuy #${rebuyCount}`' in app
    assert 'action("sit_out", { sitting_out: false })' in app
    assert 'action("rebuy", {})' in app
    assert "viewerData.sitting_out" in app
    assert "viewerData.can_rebuy" in app
    assert "state.auto_deal_active" in app
    assert "syncPostHandRecoveryButtons(state, viewerData);" in app

    assert "Post-hand Sit In recovery button" in css
    assert ".post-hand-panel.has-post-hand-recovery .post-hand-actions" in css
    assert ".post-hand-recovery-btn" in css

def test_buy_in_count_can_rebuy_and_busted_labels_are_used_in_frontend():
    app = read_static("app.js")
    game = (ROOT / "poker" / "game.py").read_text(encoding="utf-8")

    assert "numberOrZero(player.buy_in_count) > 1" in app
    assert "Buy-ins ${numberOrZero(player.buy_in_count)}" in app
    assert "numberOrZero(p.buy_in_count) > 1" in app
    assert "Buy-in ${numberOrZero(p.buy_in_count)}" in app
    assert "Busted" in app
    assert "BUST" in app
    assert "viewerData.can_rebuy" in app
    assert '"buy_in_count": max(1, int(getattr(p, "buy_in_count", 1)))' in game
    assert '"can_rebuy": viewer_can_rebuy if viewer else False' in game

def test_stack_zero_live_all_in_players_are_not_labeled_busted_frontend():
    app = read_static("app.js")
    game = (ROOT / "poker" / "game.py").read_text(encoding="utf-8")

    assert "function playerIsLiveInCurrentHand(player, state = lastState)" in app
    assert "player.is_live_in_hand" in app
    assert "function playerIsBusted(player, state = lastState)" in app
    assert "&& !playerIsLiveInCurrentHand(player, state)" in app
    assert "playerIsBusted(player)" in app
    assert "playerIsBusted(p, state)" in app
    assert '"is_live_in_hand": is_live_in_hand' in game
    assert "and not is_live_in_hand" in game
    assert "and not self.player_is_live_in_current_hand(room, viewer)" in game

def test_center_pot_cleanup_prevents_shadow_overlap():
    css = read_static("styles.css")

    assert "Center pot cleanup v2" in css
    assert ".table-felt .pot-area" in css
    assert "isolation: isolate" in css
    assert "content: none !important" in css
    assert ".table-felt .pot-chips:empty" in css
    assert "transform: scale(.78)" in css
    assert ".table-felt .community-cards" in css
    assert "--center-pot-clearance" in css

def test_board_tray_shadow_is_separated_from_center_pot():
    css = read_static("styles.css")

    assert "Board tray / pot visual separation v2" in css
    assert ".table-felt .community-cards" in css
    assert "linear-gradient(" in css
    assert "inset 0 -8px 14px" in css
    assert ".table-felt .pot-area + .community-cards" in css
    assert "margin-bottom: clamp(10px, 1.5vw, 18px)" in css

def test_board_cards_float_without_extra_center_shadow_layers():
    css = read_static("styles.css")

    assert "Clean floating board cards v1" in css
    assert ".table-felt .community-cards" in css
    assert "background: transparent !important" in css
    assert "box-shadow: none !important" in css
    assert ".community-cards::before" in css
    assert "content: none !important" in css
    assert ".table-felt .community-cards .playing-card" in css

def test_legacy_table_felt_center_tray_is_disabled():
    css = read_static("styles.css")

    assert "Remove legacy center tray pseudo-element" in css
    assert ".table-felt::after" in css
    assert "content: none !important" in css
    assert "display: none !important" in css
    assert "width: fit-content !important" in css
    assert "justify-content: center !important" in css

def test_timebank_turn_badge_is_outside_felt():
    css = read_static("styles.css")

    assert "Move timebank / turn badge outside felt" in css
    assert ".table-felt .turn-indicator" in css
    assert "position: absolute" in css
    assert "bottom: clamp(-38px, -3.2vw, -28px)" in css
    assert "transform: translateX(-50%)" in css
    assert ".table-felt .turn-indicator:empty" in css
    assert "Hide redundant under-table bank badge" in css
    assert ".table-felt .turn-indicator:not(.your-turn):not(.thinking)" in css
    assert "display: none !important" in css

def test_showdown_winner_matching_uses_player_identity_not_names_only():
    app = read_static("app.js")

    assert "function playerKey(player)" in app
    assert "function winnerKey(winner)" in app
    assert "function winnerMatchesPlayer(winner, player)" in app
    assert "function winnerForPlayer(player, winners = [])" in app
    assert "function winnerAmountForPlayer(player, winners = [])" in app
    assert "winner.player_id" in app
    assert "player.player_id" in app
    assert "winnerForPlayer(p, winners)" in app
    assert "winnerAmountForPlayer(p, winners)" in app
    assert "winnerNames" not in app
    assert "winnerByName" not in app
    assert "winnerAmountByName" not in app

def test_showdown_winner_amount_uses_winners_list_with_net_secondary():
    app = read_static("app.js")

    assert 'const winAmount = winnerAmountForPlayer(p, winners);' in app
    assert 'const amount = isWinner ? `+${winAmount}` : formatHandDelta(delta);' in app
    assert 'const amountClass = isWinner ? "gain winner-amount" : handDeltaClass(delta);' in app
    assert "post-hand-net" in app
    assert 'title="${isWinner ? "Winner share" : "Net result this hand"}"' in app

def test_showdown_winner_showcase_css_prevents_card_clipping():
    css = read_static("styles.css")

    assert "Old-style showdown winner showcase rows" in css
    assert ".post-hand-panel.post-hand-modal .post-hand-row.winner" in css
    assert "grid-template-columns: minmax(118px, 0.85fr) minmax(170px, auto) minmax(0, 1fr) minmax(72px, auto)" in css
    assert ".post-hand-panel.post-hand-modal .post-hand-row.winner .post-hand-cards" in css
    assert "overflow: visible" in css
    assert ".post-hand-panel.post-hand-modal.post-hand-compact .post-hand-row.winner .post-hand-breakdown" in css
    assert "display: none !important" in css
    assert ".post-hand-net" in css
