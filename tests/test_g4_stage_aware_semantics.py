from pathlib import Path

W = Path(".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")


def test_draft_is_pre_g4_and_non_blocking():
    assert "if (pr.draft)" in W
    assert "G4 is not active while the PR is Draft" in W


def test_stage_transitions_retrigger_check():
    assert "ready_for_review" in W
    assert "converted_to_draft" in W


def test_ready_without_receipt_fails_closed():
    assert "this PR is Ready for Review but no trusted gwc:g4-authority-receipt" in W


def test_receipt_is_exact_head_and_unexpired():
    assert "parsed[2] !== pr.head.sha" in W
    assert "expiresAt <= new Date()" in W


def test_autonomous_preprod_bypass_preserved():
    assert "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN" in W
    assert "Standing pre-prod authority applies" in W
