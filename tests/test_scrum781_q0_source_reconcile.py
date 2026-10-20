"""Q0 precheck: protected-main drift must not hijack a bound v2 plan."""
import json
from pathlib import Path

import pytest

from scripts.scrum781_q0_source_reconcile import (
    ROOT, FIXTURE, PLAN, POLICY, RUNBOOK,
    SourceBindingError, reconcile,
)


def sandbox(tmp_path: Path) -> Path:
    for name in (FIXTURE, PLAN, POLICY, RUNBOOK):
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_live_q0_binding_keeps_immutable_runtimeplan():
    result = reconcile(ROOT)
    assert result["binding"] == "Q0_SOURCE_BOUND"
    assert result["current_runtimeplan_sha256"] == (
        "sha256:ac8e8b855d5564ec9e503f965cd73deb60b546caf70a7304c43140a315422500"
    )
    assert result["replan_required"] is False
    assert result["native_gate_receipt"] is None
    assert result["q0_l3_qualified"] is False


def test_protected_main_drift_is_informational(tmp_path):
    q0 = sandbox(tmp_path / "q0")
    main = tmp_path / "main"
    for path in (POLICY, RUNBOOK):
        target = main / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Protected-main independent governance contents")
    result = reconcile(q0, main)
    assert result["binding"] == "Q0_SOURCE_BOUND"
    assert result["protected_main"]["status"] == "PROTECTED_MAIN_DIVERGENCE_NONBLOCKING"
    assert result["protected_main"]["nonblocking"] is True
    assert result["replan_required"] is False


def test_main_policy_cannot_override_q0_source(tmp_path):
    q0 = sandbox(tmp_path)
    (q0 / POLICY).write_text("No Q0 override here")
    with pytest.raises(SourceBindingError, match="Q0_BRANCH_POLICY_BINDING_INVALID"):
        reconcile(q0)


def test_immutable_plan_content_change_requires_recheck(tmp_path):
    q0 = sandbox(tmp_path)
    plan = json.loads((q0 / PLAN).read_text())
    plan["goal"] = "changed source"
    (q0 / PLAN).write_text(json.dumps(plan))
    with pytest.raises(SourceBindingError, match="Q0_IMMUTABLE_PLAN_DIGEST_DRIFT"):
        reconcile(q0)


def test_run_identity_drift_fails_closed(tmp_path):
    q0 = sandbox(tmp_path)
    plan = json.loads((q0 / PLAN).read_text())
    plan["branch"] = "main"
    (q0 / PLAN).write_text(json.dumps(plan))
    with pytest.raises(SourceBindingError, match="Q0_RUNTIMEPLAN_IDENTITY_INVALID"):
        reconcile(q0)


def test_reconstructed_fixture_cannot_claim_original(tmp_path):
    q0 = sandbox(tmp_path)
    fixture = json.loads((q0 / FIXTURE).read_text())
    fixture["incident"]["provenance_class"] = "ORIGINAL_RECOVERED"
    (q0 / FIXTURE).write_text(json.dumps(fixture))
    with pytest.raises(SourceBindingError, match="Q0_RECONSTRUCTED_PROVENANCE_INVALID"):
        reconcile(q0)


def test_missing_branch_source_fails_only_affected_precheck(tmp_path):
    q0 = sandbox(tmp_path)
    (q0 / POLICY).unlink()
    with pytest.raises(SourceBindingError, match="Q0_REQUIRED_SOURCE_MISSING:AGENTS.md"):
        reconcile(q0)
