from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_in_game_hand_history_markup_exists():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="handHistoryToggle"' in html
    assert "History " in html
    assert 'id="handHistoryCount"' in html
    assert 'id="handHistoryPanel"' in html
    assert 'id="handHistoryClose"' in html
    assert 'id="handHistoryBody"' in html


def test_hand_history_renderer_is_wired_to_state_payload():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "function renderHandHistory(state)" in app
    assert "state.hand_history" in app
    assert "renderHandHistory(state);" in app
    assert "handHistoryToggle.onclick" in app
    assert "handHistoryPanel.classList.toggle" in app
    assert "completedHandHistoryFromState(state)" in app
    assert "latest_hand_result" in app
    assert "window.__pokerLastState = state;" in app


def test_hand_history_styles_exist():
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".hand-history-panel" in css
    assert ".hand-history-row" in css
    assert ".hand-history-board" in css
    assert ".hand-history-toggle.has-history" in css
