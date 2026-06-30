from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_workflow_doc_exists_and_names_current_workflow():
    doc = ROOT / "docs" / "AGENT_WORKFLOW.md"
    assert doc.exists()

    text = doc.read_text(encoding="utf-8")
    assert "Patch-first workflow" in text
    assert "logic-core-hardening" in text
    assert "scripts/safe_commit.ps1" in text
    assert "python -m pytest -q" in text
    assert "Does not push" in text
    assert "Documentation is part of the codebase now" in text


def test_safe_commit_script_exists_and_excludes_generated_debug_data():
    script = ROOT / "scripts" / "safe_commit.ps1"
    assert script.exists()

    text = script.read_text(encoding="utf-8")
    assert "logic-core-hardening" in text
    assert "git add -- $allowed" in text
    assert "'^logs/'" in text
    assert "'(^|/)__pycache__/'" in text
    assert "tests/test_workflow_docs.py" in text
    assert "python" in text
    assert "pytest" in text
