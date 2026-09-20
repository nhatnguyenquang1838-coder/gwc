from __future__ import annotations

import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/q0-live-fix-receipt.schema.json").read_text())
BRANCHING = (ROOT / "core/engineering/Q0_LIVE_QUALIFICATION_BRANCHING_STRATEGY_v1.0.md").read_text()
RUNBOOK = (ROOT / "core/runbooks/Q0_LIVE_QUALIFICATION_RUNBOOK_v1.0.md").read_text()


def _receipt(status="RUNTIME_FIXED", replay_result="PASS", state="NEXT_LEGAL_STATE"):
    sha = "a" * 40
    return {
        "schema_version": "1.0",
        "artifact_type": "q0-live-fix-receipt",
        "task_id": "SCRUM-781",
        "defect_id": "Q0-03-producer-liveness",
        "fix_base_sha": "b" * 40,
        "candidate_fix_sha": sha,
        "q0_baseline_sha": "b" * 40,
        "branch": "fix/SCRUM-781-q0-03-producer-liveness",
        "worktree": "/worktrees/gwc/SCRUM-781/03-producer-liveness",
        "worktree_head": sha,
        "runtime_activation": {
            "activation_id": "act-003",
            "process_or_session_id": "worker-003",
            "source_root": "/worktrees/gwc/SCRUM-781/03-producer-liveness",
            "loaded_source_sha": sha,
        },
        "loaded_surfaces": {
            "instructions": ["AGENTS.md"],
            "modules": ["tools/node_architect/example.py"],
            "controller_contract_digest": "sha256:" + "c" * 64,
        },
        "invalidated": ["runtime_plan:r7"],
        "regenerated": [{"artifact": "runtime_plan:r8", "digest": "sha256:" + "d" * 64}],
        "incident": {"fixture_digest": "sha256:" + "e" * 64, "previous_failure_state": "PLAN_PRECHECK"},
        "replay": {"result": replay_result, "exact_readback": replay_result == "PASS", "first_state_beyond_failure": state},
        "verification": {"broader_regression": "PASS", "exact_readback": "PASS", "evidence_digest": "sha256:" + "f" * 64},
        "status": status,
    }


def validate_semantics(receipt):
    jsonschema.validate(receipt, SCHEMA)
    rank = {"FIX_IMPLEMENTED": 0, "FIX_LOADED": 1, "FIX_REPLAY_VERIFIED": 2, "RUNTIME_FIXED": 3}
    if rank[receipt["status"]] >= 1:
        assert receipt["runtime_activation"]["loaded_source_sha"] == receipt["candidate_fix_sha"]
        assert receipt["worktree_head"] == receipt["candidate_fix_sha"]
    if rank[receipt["status"]] >= 2:
        assert receipt["replay"]["result"] == "PASS"
        assert receipt["replay"]["exact_readback"] is True
        assert receipt["replay"]["first_state_beyond_failure"]
    if rank[receipt["status"]] >= 3:
        assert receipt["regenerated"] or receipt["invalidated"] == []
        assert receipt["verification"]["broader_regression"] == "PASS"
        assert receipt["verification"]["exact_readback"] == "PASS"
        assert receipt["verification"]["evidence_digest"]


def test_runtime_fixed_receipt_requires_exact_loaded_candidate_identity():
    r = _receipt()
    validate_semantics(r)
    r["runtime_activation"]["loaded_source_sha"] = "f" * 40
    try:
        validate_semantics(r)
    except (AssertionError, jsonschema.ValidationError):
        pass
    else:
        raise AssertionError("stale loaded source was accepted")


def test_replay_verified_requires_advance_beyond_old_failure():
    r = _receipt(status="FIX_REPLAY_VERIFIED", state=None)
    try:
        validate_semantics(r)
    except (AssertionError, jsonschema.ValidationError):
        pass
    else:
        raise AssertionError("replay without forward progress was accepted")


def test_runtime_fixed_rejects_failed_original_incident_replay():
    r = _receipt(replay_result="FAIL", state=None)
    try:
        validate_semantics(r)
    except (AssertionError, jsonschema.ValidationError):
        pass
    else:
        raise AssertionError("failed replay was accepted")


def test_branching_contract_names_linear_chained_model_and_no_history_rewrite():
    assert "Linear Chained Defect Branches + SHA-based Q0 Baseline" in BRANCHING
    assert "NO_HISTORY_REWRITE_AFTER_EVIDENCE" in BRANCHING
    assert "NO_AUTOMATIC_REBASE_ON_MAIN_DRIFT" in BRANCHING


def test_runbook_requires_load_proof_and_original_incident_replay():
    assert "RELOAD_OR_RESTART_RUNTIME_ON_FIX" in RUNBOOK
    assert "LOAD_PROOF" in RUNBOOK
    assert "REPLAY_ORIGINAL_INCIDENT" in RUNBOOK
    assert "ADVANCE_BEYOND_PREVIOUS_FAILURE" in RUNBOOK


def test_runbook_separates_fix_statuses():
    for state in ("FIX_IMPLEMENTED", "FIX_LOADED", "FIX_REPLAY_VERIFIED", "RUNTIME_FIXED", "FIX_CERTIFIED"):
        assert state in RUNBOOK


def test_runbook_requires_clean_final_certification_activation():
    assert "fresh clean source/worktree" in RUNBOOK
    assert "fresh runtime activation" in RUNBOOK


def test_runtime_loaded_rejects_stale_worktree_head():
    r = _receipt(status="FIX_LOADED")
    r["worktree_head"] = "0" * 40
    try:
        validate_semantics(r)
    except (AssertionError, jsonschema.ValidationError):
        pass
    else:
        raise AssertionError("stale worktree head was accepted")


def test_runtime_fixed_requires_broader_regression_and_final_readback():
    r = _receipt()
    r["verification"]["broader_regression"] = "FAIL"
    try:
        validate_semantics(r)
    except (AssertionError, jsonschema.ValidationError):
        pass
    else:
        raise AssertionError("RUNTIME_FIXED accepted failed broader regression")


def test_fix_implemented_allows_progressive_receipt_without_future_runtime_evidence():
    r = _receipt(status="FIX_IMPLEMENTED")
    for key in ("worktree_head", "runtime_activation", "loaded_surfaces", "invalidated", "regenerated", "replay", "verification"):
        r.pop(key)
    jsonschema.validate(r, SCHEMA)


def test_fix_loaded_schema_requires_runtime_activation():
    r = _receipt(status="FIX_LOADED")
    r.pop("runtime_activation")
    try:
        jsonschema.validate(r, SCHEMA)
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("FIX_LOADED without runtime activation was accepted")


def test_fix_loaded_schema_requires_worktree_head():
    r = _receipt(status="FIX_LOADED")
    r.pop("worktree_head")
    try:
        jsonschema.validate(r, SCHEMA)
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("FIX_LOADED without worktree_head was accepted")
