from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dynamic_button_classes_have_css_hooks():
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    expected_classes = {
        "history-review-close-btn",
        "post-hand-actions",
        "post-hand-recovery-btn",
        "folded-reveal-actions",
        "folded-reveal-btn",
        "hand-history-review-btn",
        "admin-player-action-btn",
        "admin-kick-btn",
        "action-log-toggle",
        "hand-history-toggle",
        "auto-deal-toggle",
        "hotkeys-toggle",
        "btn-auto-check-fold",
    }

    missing = sorted(cls for cls in expected_classes if f".{cls}" not in css)
    assert not missing, f"Missing CSS selectors for button UI classes: {missing}"
