"""Tests for the CF provenance verifier (Controller COMMAND #86, Option B).

These tests are evidence checks, not gate authority: they prove the verifier
accepts the recorded binding and rejects a tampered one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import scrum781_cf_provenance_verify as verifier

ROOT = Path(__file__).resolve().parents[1]


def test_red_phase_verifies_recorded_binding() -> None:
    result = verifier.verify(ROOT, "red")
    assert result["result"] == "CF_PROVENANCE_VERIFIED", result["blocking_checks"]
    assert result["checks"]["failing_statement_present"] is True
    assert result["checks"]["reexec_empty_input_sha256"] is True
    assert result["checks"]["misbinding_recorded"] is True
    assert result["authority_granted"] is False


def test_fix_phase_verifies_recorded_binding() -> None:
    result = verifier.verify(ROOT, "fix")
    assert result["result"] == "CF_PROVENANCE_VERIFIED", result["blocking_checks"]
    assert result["checks"]["verified_fix_ancestor"] is True
    assert result["checks"]["current_module_matches_fix"] is True
    assert result["checks"]["declared_fix_contains_module"] is False


def test_tampered_fix_module_yields_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    original = verifier._show

    def tampered(root: Path, commit: str, path: str) -> bytes:
        if path == verifier.FIX_MODULE:
            return b"# tampered module\n"
        return original(root, commit, path)

    monkeypatch.setattr(verifier, "_show", tampered)
    result = verifier.verify(ROOT, "fix")
    assert result["result"] == "CF_PROVENANCE_GAP"
    assert "verified_fix_module_matches_binding" in result["blocking_checks"] or (
        "current_module_matches_fix" in result["blocking_checks"]
    )
    assert result["authority_granted"] is False
