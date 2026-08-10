from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPAT = _load_module(
    "flow_policy_compat",
    "tools/node_architect/validate_flow_policy_compatibility.py",
)
COMPILER = _load_module(
    "flow_policy_compiler",
    "tools/node_architect/compile_flow_policy_decision.py",
)


def _payloads():
    profiles = json.loads((ROOT / "core/node-architect/profile-registry.json").read_text())
    policy = json.loads(
        (ROOT / "core/node-architect/gate-applicability-policy-registry.json").read_text()
    )
    flow = next(item for item in profiles["profiles"] if item["id"] == "full-flow-v3")
    return flow, policy


def test_current_flow_and_policy_are_compatible():
    flow, policy = _payloads()
    decision = COMPAT.validate_flow_policy_compatibility(
        flow_profile=flow, policy_registry=policy
    )
    assert decision["compatible"] is True
    assert decision["reason_codes"] == ["FLOW_POLICY_COMPATIBLE"]
    assert decision["decision_digest"].startswith("sha256:")


def test_missing_policy_ref_fails_closed():
    flow, policy = _payloads()
    flow = json.loads(json.dumps(flow))
    flow["workflow"]["gate_bindings"][0]["policy_ref"] = "missing-policy"
    decision = COMPAT.validate_flow_policy_compatibility(
        flow_profile=flow, policy_registry=policy
    )
    assert decision["compatible"] is False
    assert "GATE_POLICY_MISSING" in decision["reason_codes"]


def test_compile_required_gate_continues_deterministically():
    flow, policy = _payloads()
    applicability = {
        "decision": "REQUIRED",
        "policy_ref": "g3-pr-required",
        "reason_code": "GATE_REQUIRED_BY_DEFAULT",
    }
    kwargs = dict(
        flow_profile=flow,
        policy_registry=policy,
        current_node="repo_delivery.ci-run-capture",
        current_gate="G3_PR",
        applicability_decision=applicability,
        context={"task_id": "T-1", "head_sha": "abc"},
        next_nodes=["runtime_checkpoint.checkpoint-persist"],
        evidence_requirements=["exact-head-ci"],
    )
    first = COMPILER.compile_flow_policy_decision(**kwargs)
    second = COMPILER.compile_flow_policy_decision(**kwargs)
    assert first["outcome"] == "CONTINUE"
    assert first["applicability"] == "REQUIRED"
    assert first["next_nodes"] == ["runtime_checkpoint.checkpoint-persist"]
    assert first["decision_digest"] == second["decision_digest"]


def test_not_applicable_is_explicit_terminal_not_pass():
    flow, policy = _payloads()
    result = COMPILER.compile_flow_policy_decision(
        flow_profile=flow,
        policy_registry=policy,
        current_node="repo_delivery.ci-run-capture",
        current_gate="G5_DEPLOY",
        applicability_decision={
            "decision": "NOT_APPLICABLE",
            "policy_ref": "g5-deploy-effect-driven",
            "reason_code": "GATE_NOT_APPLICABLE_BY_DEFAULT",
        },
        context={"effects": {}},
    )
    assert result["applicability"] == "NOT_APPLICABLE"
    assert result["outcome"] == "TERMINAL"
    assert result["terminal_disposition"] == "GATE_NOT_APPLICABLE"


def test_unknown_next_node_blocks():
    flow, policy = _payloads()
    result = COMPILER.compile_flow_policy_decision(
        flow_profile=flow,
        policy_registry=policy,
        current_node="repo_delivery.ci-run-capture",
        current_gate="G3_PR",
        applicability_decision={
            "decision": "REQUIRED",
            "policy_ref": "g3-pr-required",
            "reason_code": "GATE_REQUIRED_BY_DEFAULT",
        },
        context={},
        next_nodes=["not.a.workflow.node"],
    )
    assert result["outcome"] == "BLOCKED"
    assert "NEXT_NODE_NOT_IN_WORKFLOW" in result["reason_codes"]


def test_policy_binding_mismatch_blocks():
    flow, policy = _payloads()
    result = COMPILER.compile_flow_policy_decision(
        flow_profile=flow,
        policy_registry=policy,
        current_node="repo_delivery.ci-run-capture",
        current_gate="G4_MERGE",
        applicability_decision={
            "decision": "REQUIRED",
            "policy_ref": "g5-deploy-effect-driven",
            "reason_code": "GATE_REQUIRED_BY_DEFAULT",
        },
        context={},
        next_nodes=["runtime_checkpoint.checkpoint-persist"],
    )
    assert result["outcome"] == "BLOCKED"
    assert "POLICY_REF_MISMATCH" in result["reason_codes"]
