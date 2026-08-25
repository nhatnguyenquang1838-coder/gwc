from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.shadow_orchestrator import run_shadow_event


def registry():
    return {"nodes": [
        {"id": "repo_delivery.a", "family": "repo_delivery", "version": "1", "maturity": "candidate", "effect_class": "read_only", "suspension": {"suspendable": False, "resume_metadata": []}},
        {"id": "validation_quality.b", "family": "validation_quality", "version": "1", "maturity": "candidate", "effect_class": "read_only", "suspension": {"suspendable": False, "resume_metadata": []}},
        {"id": "gate_authority.c", "family": "gate_authority", "version": "1", "maturity": "experimental", "effect_class": "external_write", "suspension": {"suspendable": True, "resume_metadata": ["task"]}},
    ]}


def activation(enabled=True, kill=False):
    return {"schema_version": "1.0", "enabled": enabled, "kill_switch_engaged": kill, "mode": "shadow_readonly", "authority": "none", "exact_revision_binding": True}


def event(revision="abc"):
    return {"task_id": "SCRUM-X", "run_id": "r1", "gate": "G3_PR", "exact_revision": revision, "scenario": "standard_pr_delivery", "input_payload": {"ci": "success"}}


def test_valid_event_selects_only_applicable_route_nodes():
    out = run_shadow_event(event(), registry(), activation(), observed_revision="abc")
    assert out["status"] == "SHADOW_EXECUTED"
    assert {r["node_id"] for r in out["results"]} == {"repo_delivery.a", "validation_quality.b"}
    assert out["authoritative_effect"] == "NONE"
    assert out["decision_authority"] is False


def test_kill_switch_fail_closes():
    out = run_shadow_event(event(), registry(), activation(kill=True), observed_revision="abc")
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_KILL_SWITCH_ENGAGED"


def test_revision_drift_fail_closes():
    out = run_shadow_event(event("abc"), registry(), activation(), observed_revision="def")
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_REVISION_DRIFT"


def test_unknown_scenario_is_typed_noop():
    e = event(); e["scenario"] = "unknown"
    out = run_shadow_event(e, registry(), activation(), observed_revision="abc")
    assert out["status"] == "SHADOW_NO_APPLICABLE_ROUTE"
    assert out["results"] == []
