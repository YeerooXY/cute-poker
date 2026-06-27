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


def test_static_assets_are_cache_busted():
    html = read_static("index.html")

    assert "/static/styles.css?v=" in html
    assert "/static/app.js?v=" in html


def test_history_review_modal_has_large_overlay_and_close_controls():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function syncHistoryReviewChrome(visible)" in app
    assert "historyReviewCloseBtn" in app
    assert "Escape" in app
    assert "history-review-open" in app
    assert "body.history-review-open::before" in css
    assert ".history-review-close-btn" in css
    assert "width: min(1120px" in css


def test_history_review_modal_renders_saved_board_and_keeps_close_clear_of_pot_badge():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function renderHistoryReviewBoard(state)" in app
    assert "history-review-board-strip" in app
    assert "renderHistoryReviewBoard(state)" in app
    assert ".history-review-board-strip" in css
    assert "history-review-board-cards" in css
    assert "margin-right: 52px" in css


def test_history_review_infers_revealed_cards_and_uses_spacious_modal():
    app = read_static("app.js")
    css = read_static("styles.css")

    assert "function inferRevealModeFromHistoryCards(cards)" in app
    assert 'card === "🂠"' in app
    assert "function normalizeHistoryReviewPlayer(player, hand)" in app
    assert "normalizeHistoryReviewPlayer(player, hand)" in app
    assert "can_reveal_folded_hand: false" in app
    assert "can_reveal_uncontested_hand: false" in app
    assert "!isHiddenHistoryCard(cards[0])" in app
    assert "!isHiddenHistoryCard(cards[1])" in app
    assert "historyWinnerIds(hand)" in app
    assert "not a tiny debug drawer" in css
    assert "width: min(1280px" in css
    assert "min-height: 112px" in css
    assert "max-height: none" in css
    assert "overflow-y: visible" in css


def test_history_review_can_render_persisted_would_have_breakdowns():
    app = read_static("app.js")

    assert "renderFoldedWouldHaveBreakdown(p, state)" in app
    assert "would_have_best_cards" in app
    assert "would_have_hand_detail" in app
    assert "renderBestFiveBreakdownHtml" in app
