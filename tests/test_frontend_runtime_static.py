from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static_js() -> str:
    return (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def test_frontend_runtime_registry_exists_for_gradual_module_extraction():
    app = read_static_js()

    assert "window.CutePoker = window.CutePoker || {};" in app
    assert "const frontendRuntime = window.CutePoker.frontend || (window.CutePoker.frontend = {});" in app
    assert "frontendRuntime.modules = frontendRuntime.modules || {};" in app
    assert "frontendRuntime.helpers = frontendRuntime.helpers || {};" in app
    assert "frontendRuntime.registerModule = function registerFrontendModule(name, api)" in app
    assert "function syncFrontendRuntimeBindings()" in app
    assert "syncFrontendRuntimeBindings();" in app


def test_frontend_runtime_exposes_history_and_panel_accessors():
    app = read_static_js()

    assert "getSelectedHistoryHandNumber: () => selectedHistoryHandNumber" in app
    assert "setSelectedHistoryHandNumber: value =>" in app
    assert "getSelectedHistoryReviewKey: () => selectedHistoryReviewKey" in app
    assert "setSelectedHistoryReviewKey: value =>" in app
    assert "getDefaultPanelsRoomId: () => defaultPanelsRoomId" in app
    assert "setDefaultPanelsRoomId: value =>" in app
    assert "getPanelExpanded: () => panelExpanded" in app
    assert "setPanelExpanded: value =>" in app
    assert "applyPanelState: () => applyPanelState()" in app
    assert "getPanelStorageKey: () => PANEL_KEY" in app


def test_frontend_runtime_exports_helper_seams_for_future_modules():
    app = read_static_js()

    assert "Object.assign(frontendRuntime.helpers, {" in app
    assert "esc," in app
    assert "makeCardHtml," in app
    assert "numberOrZero," in app
    assert "actionEntryText," in app
    assert "directPlayerDelta," in app
    assert "formatHandDelta," in app
    assert "handDeltaClass," in app
    assert "renderBestFiveBreakdownHtml," in app
    assert "completedHandHistoryFromState," in app
    assert "fullHandHistoryDetailsFromState," in app
    assert "historyHandKey," in app
    assert "hasCurrentHandComplete," in app


def test_desktop_readiness_doc_exists_and_mentions_runtime_seam():
    text = (ROOT / "docs" / "DESKTOP_READINESS.md").read_text(encoding="utf-8")

    assert "Desktop Readiness Plan" in text
    assert "window.CutePoker.frontend" in text
    assert "Tauri" in text
    assert "Electron" in text
    assert "ui/history" in text
