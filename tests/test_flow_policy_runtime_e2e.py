from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.compile_flow_policy_decision import compile_flow_policy_decision
from tools.node_architect.evaluate_gate_applicability import evaluate_gate_applicability
from tools.node_architect.resolve_flow_policy_runtime import resolve_flow_policy_runtime
from tools.node_architect.validate_flow_policy_compatibility import validate_flow_policy_compatibility
from tools.node_architect.validate_flow_policy_runtime import validate_flow_policy_runtime

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _artifacts():
    profiles = _load("core/node-architect/profile-registry.json")
    flow = next(item for item in profiles["profiles"] if item["id"] == "full-flow-v3")
    return (
        flow,
        _load("core/node-architect/gate-applicability-policy-registry.json"),
        _load("core/node-architect/gate-node-route-profile.json"),
        _load("core/node-architect/flow-policy-runtime-profile.json"),
    )


def _g3_context(pr_state: str = "OPEN", with_evidence: bool = True):
    evidence = [{"evidence_type": "diff_readback", "verified": True}] if with_evidence else []
    return {"evidence": evidence, "pr": {"state": pr_state}}


class FlowPolicyRuntimeE2ETests(unittest.TestCase):
    def test_static_flow_policy_compatibility_passes(self):
        flow, policy, _, _ = _artifacts()
        result = validate_flow_policy_compatibility(flow_profile=flow, policy_registry=policy)
        self.assertTrue(result["compatible"], result)
        self.assertEqual(result["reason_codes"], ["FLOW_POLICY_COMPATIBLE"])

    def test_activation_profile_exact_bindings_are_activatable(self):
        flow, policy, route, runtime = _artifacts()
        result = validate_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, root=ROOT,
        )
        self.assertEqual(result["outcome"], "ACTIVATABLE", result)

    def test_activation_blocks_stale_policy_digest(self):
        flow, policy, route, runtime = _artifacts()
        runtime = copy.deepcopy(runtime)
        runtime["policy"]["registry_digest"] = "sha256:" + "0" * 64
        result = validate_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("RUNTIME_POLICY_DIGEST_DRIFT", result["reason_codes"])

    def test_runtime_continues_on_valid_g3_evidence(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="repo_delivery.ci-run-capture",
            current_gate="G3_PR", context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "CONTINUE", result)
        decision = result["workflow_policy_decision"]
        self.assertEqual(decision["applicability"], "REQUIRED")
        self.assertEqual(decision["next_nodes"], ["runtime_checkpoint.checkpoint-persist"])

    def test_required_gate_blocks_when_evidence_is_missing(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="repo_delivery.ci-run-capture",
            current_gate="G3_PR", context=_g3_context(with_evidence=False), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", result["reason_codes"])

    def test_terminal_acceptance_is_policy_owned_and_fail_closed(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="validation_quality.ci-evidence-capture",
            current_gate="G3_PR", context=_g3_context(pr_state="CLOSED"), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("TERMINAL_ACCEPTANCE_UNMET", result["reason_codes"])

    def test_terminal_green_when_policy_accepts_terminal(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="validation_quality.ci-evidence-capture",
            current_gate="G3_PR", context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "TERMINAL", result)
        self.assertEqual(result["workflow_policy_decision"]["terminal_disposition"], "GREEN")

    def test_participant_gate_mismatch_blocks_before_policy_execution(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="repo_delivery.ci-run-capture",
            current_gate="G5_DEPLOY", context={}, root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_GATE_CONTEXT_MISMATCH", result["reason_codes"])

    def test_not_applicable_remains_explicit_policy_evidence(self):
        flow, policy, _, _ = _artifacts()
        result = evaluate_gate_applicability(
            flow_profile=flow, policy_registry=policy, gate="G5_DEPLOY", context={"effects": {}}
        )
        self.assertEqual(result["decision"], "NOT_APPLICABLE")
        self.assertEqual(result["reason_code"], "GATE_NOT_APPLICABLE_BY_DEFAULT")
        self.assertTrue(result["decision_digest"].startswith("sha256:"))

    def test_g2_unsatisfied_authority_and_evidence_compile_blocked(self):
        flow, policy, _, _ = _artifacts()
        applicability = evaluate_gate_applicability(
            flow_profile=flow, policy_registry=policy, gate="G2_EXECUTION", context={}
        )
        result = compile_flow_policy_decision(
            flow_profile=flow, policy_registry=policy,
            current_node="repo_delivery.ci-run-capture", current_gate="G2_EXECUTION",
            applicability_decision=applicability, context={},
            next_nodes=["runtime_checkpoint.checkpoint-persist"],
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("AUTHORITY_REQUIREMENTS_UNSATISFIED", result["reason_codes"])
        self.assertIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", result["reason_codes"])

    def test_prohibited_action_fails_closed(self):
        flow, policy, _, _ = _artifacts()
        context = {"requested_action": "write_outside_declared_scope"}
        applicability = evaluate_gate_applicability(
            flow_profile=flow, policy_registry=policy, gate="G2_EXECUTION", context=context
        )
        result = compile_flow_policy_decision(
            flow_profile=flow, policy_registry=policy,
            current_node="repo_delivery.ci-run-capture", current_gate="G2_EXECUTION",
            applicability_decision=applicability, context=context,
            next_nodes=["runtime_checkpoint.checkpoint-persist"],
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("POLICY_PROHIBITED_ACTION", result["reason_codes"])

    def test_policy_decision_digest_mismatch_fails_closed(self):
        flow, policy, _, _ = _artifacts()
        applicability = evaluate_gate_applicability(
            flow_profile=flow, policy_registry=policy, gate="G3_PR", context=_g3_context()
        )
        applicability = copy.deepcopy(applicability)
        applicability["policy_registry_digest"] = "sha256:" + "f" * 64
        result = compile_flow_policy_decision(
            flow_profile=flow, policy_registry=policy,
            current_node="repo_delivery.ci-run-capture", current_gate="G3_PR",
            applicability_decision=applicability, context=_g3_context(),
            next_nodes=["runtime_checkpoint.checkpoint-persist"],
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("POLICY_REGISTRY_DIGEST_MISMATCH", result["reason_codes"])

    def test_replay_is_digest_stable(self):
        flow, policy, route, runtime = _artifacts()
        kwargs = dict(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="repo_delivery.ci-run-capture",
            current_gate="G3_PR", context=_g3_context(), root=ROOT,
        )
        first = resolve_flow_policy_runtime(**kwargs)
        second = resolve_flow_policy_runtime(**kwargs)
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(
            first["workflow_policy_decision"]["decision_digest"],
            second["workflow_policy_decision"]["decision_digest"],
        )

    def test_runtime_decision_schema_accepts_compiled_decision(self):
        flow, policy, route, runtime = _artifacts()
        result = resolve_flow_policy_runtime(
            runtime_profile=runtime, flow_profile=flow, policy_registry=policy,
            route_profile=route, current_node="repo_delivery.ci-run-capture",
            current_gate="G3_PR", context=_g3_context(), root=ROOT,
        )
        schema = _load("schemas/runtime/workflow-policy-decision.schema.json")
        errors = list(Draft202012Validator(schema).iter_errors(result["workflow_policy_decision"]))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_legacy_route_profile_remains_bound_as_compatibility_projection(self):
        flow, _, route, runtime = _artifacts()
        self.assertEqual(route["workflow_profile_ref"], flow["id"])
        self.assertEqual(runtime["route_profile"]["profile_id"], route["profile_id"])
        self.assertEqual(runtime["route_profile"]["revision"], route["revision"])


if __name__ == "__main__":
    unittest.main()
