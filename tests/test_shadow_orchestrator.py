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
    return {
        "schema_version": "1.0",
        "artifact_type": "shadow-runtime-activation",
        "enabled": enabled,
        "kill_switch_engaged": kill,
        "mode": "shadow_readonly",
        "authority": "none",
        "output_effect": "observe_only",
        "decision_authority": False,
        "automatic_gate_advance": False,
        "fail_closed": True,
        "exact_revision_binding": True,
        "canonical_population": "canonical_81",
        "route_source": "tools/node_architect/canonical_shadow_route.py",
        "adapter_source": "tools/node_architect/shadow_adapters.py",
        "registry_source": "core/node-architect/node-registry.json",
    }


def event(revision="abc"):
    return {"task_id": "SCRUM-X", "run_id": "r1", "gate": "G3_PR", "exact_revision": revision, "scenario": "standard_pr_delivery", "input_payload": {"ci": "success"}}


def test_default_runtime_without_canonical_context_fails_closed():
    out = run_shadow_event(event(), registry(), activation(), observed_revision="abc")
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_RUNTIME_CONTEXT_MISSING"
    assert out["results"] == []


def test_kill_switch_fail_closes_before_context_resolution():
    out = run_shadow_event(event(), registry(), activation(kill=True), observed_revision="abc")
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_KILL_SWITCH_ENGAGED"


def test_revision_drift_fail_closes_before_context_resolution():
    out = run_shadow_event(event("abc"), registry(), activation(), observed_revision="def")
    assert out["status"] == "SHADOW_DISABLED_FAIL_CLOSED"
    assert out["reason_code"] == "SHADOW_REVISION_DRIFT"


def test_historical_envelope_replay_requires_explicit_compatibility_flag():
    out = run_shadow_event(
        event(),
        registry(),
        activation(),
        observed_revision="abc",
        compatibility_replay=True,
    )
    assert out["status"] == "SHADOW_ENVELOPE_REPLAYED"
    assert {r["node_id"] for r in out["results"]} == {"repo_delivery.a", "validation_quality.b"}
    assert out["authoritative_effect"] == "NONE"
    assert out["decision_authority"] is False
    assert out["semantic_execution"] is False
