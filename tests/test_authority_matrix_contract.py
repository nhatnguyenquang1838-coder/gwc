from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "authority" / "dw-super-app-source-of-truth-authority-matrix.md"


def test_authority_matrix_declares_projection_boundaries():
    text = MATRIX.read_text(encoding="utf-8")
    assert "Jira is work-tracking projection only" in text
    assert "Slack approval text does not grant gate authority" in text
    assert "CI success is evidence, not merge/deploy authority" in text


def test_authority_matrix_covers_provider_and_consumer_ownership():
    text = MATRIX.read_text(encoding="utf-8")
    for term in ["GWC", "UA", "Task-Me", "BMAD", "Consumer-owned", "provider-owned"]:
        assert term in text


def test_authority_matrix_has_single_owner_language():
    text = MATRIX.read_text(encoding="utf-8")
    assert "Every artifact or state has exactly one canonical authority" in text
    assert "provider package must not include consumer runtime data" in text
