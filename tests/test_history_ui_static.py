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
