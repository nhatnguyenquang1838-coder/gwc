"""Flow x Policy compiled-profile + canonical runtime resolver E2E (SCRUM-394 P1-C).

Covers the 14 required regressions from Jira SCRUM-394 comment 11268 (E1..E14)
plus legacy route-profile parity and 81-node cardinality.

Synthetic Flow fixtures are deep copies of the production ``full-flow-v3``
profile with the minimum graph / gate-binding mutation needed for a case. They
reuse the real schema and the real validator/evaluator semantics; the
production Flow (Flow lane ownership, SCRUM-392) is never modified.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.compile_flow_policy_profile import (
    COMPILER_VERSION,
    compile_flow_policy_profile,
)
from tools.node_architect.evaluate_gate_applicability import evaluate_gate_applicability
from tools.node_architect.resolve_active_flow_policy_profile import (
    resolve_active_compiled_profile,
)
from tools.node_architect.resolve_gate_node_route import resolve_compiled_flow_route
from tools.node_architect.validate_flow_policy_compatibility import (
    validate_flow_policy_compatibility,
)
from tools.node_architect.validate_flow_profile_workflow import (
    compile_workflow_projection,
    validate_flow_profile_workflow,
)

ROOT = Path(__file__).resolve().parents[1]

ENTRY = "repo_delivery.ci-run-capture"
MIDDLE = "runtime_checkpoint.checkpoint-persist"
TERMINAL = "validation_quality.ci-evidence-capture"


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _flow():
    profiles = _load("core/node-architect/profile-registry.json")
    return next(item for item in profiles["profiles"] if item["id"] == "full-flow-v3")


def _policy():
    return _load("core/node-architect/gate-applicability-policy-registry.json")


def _route_profile():
    return _load("core/node-architect/gate-node-route-profile.json")


def _rebind_policy(flow, policy):
    """Re-pin the Flow's exact policy registry binding after a synthetic Policy mutation.

    Uses the same canonical digest function the compatibility validator uses, so
    the fixture stays inside real validator semantics instead of bypassing them.
    """
    import hashlib

    flow = copy.deepcopy(flow)
    digest = "sha256:" + hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    for binding in flow.get("registry_bindings", []):
        if binding.get("registry") == "policy":
            binding["digest"] = digest
            binding["revision"] = policy.get("revision")
            binding["schema_version"] = policy.get("schema_version")
    return flow


def _recompile(flow, policy, route=None):
    """Compile a (possibly synthetic) pair, keeping declared workflow digest exact."""
    flow = copy.deepcopy(flow)
    flow["compiled"] = dict(flow.get("compiled") or {})
    flow["compiled"]["workflow_digest"] = compile_workflow_projection(dict(flow))["workflow_digest"]
    return flow, compile_flow_policy_profile(
        flow_profile=flow, policy_registry=policy,
        route_profile=route or _route_profile(), root=ROOT,
    )


def _g3_context(**overrides):
    context = {
        "task_id": "SCRUM-394",
        "workflow_mode": "normal",
        "evidence": [{"evidence_type": "diff_readback", "verified": True}],
        "pr": {"state": "OPEN"},
    }
    context.update(overrides)
    return context


class CompiledIdentityTests(unittest.TestCase):
    """E1..E3 — compiled identity separation."""

    def test_e1_policy_only_revision_keeps_workflow_digest_stable(self):
        flow, base = _recompile(_flow(), _policy())
        policy = copy.deepcopy(_policy())
        policy["revision"] = "policy-contract-v2-20260811-r1-synthetic"
        rebound = _rebind_policy(flow, policy)
        mutated = compile_flow_policy_profile(
            flow_profile=rebound, policy_registry=policy,
            route_profile=_route_profile(), root=ROOT,
        )
        self.assertEqual(
            base["workflow"]["workflow_digest"], mutated["workflow"]["workflow_digest"],
            "Policy-only revision must not mutate Workflow identity",
        )
        self.assertNotEqual(base["policy"]["registry_digest"], mutated["policy"]["registry_digest"])
        self.assertNotEqual(base["compiled_digest"], mutated["compiled_digest"])

    def test_e2_flow_composition_revision_changes_workflow_and_compiled_digest(self):
        _, base = _recompile(_flow(), _policy())
        flow = copy.deepcopy(_flow())
        flow["workflow"]["participants"].append({
            "participant": "failure_recovery.retry-orchestration",
            "participant_kind": "node", "gate_neutral": True,
        })
        _, mutated = _recompile(flow, _policy())
        self.assertNotEqual(base["workflow"]["workflow_digest"], mutated["workflow"]["workflow_digest"])
        self.assertNotEqual(base["compiled_digest"], mutated["compiled_digest"])

    def test_e3_policy_ref_change_changes_workflow_and_compiled_digest(self):
        _, base = _recompile(_flow(), _policy())
        flow = copy.deepcopy(_flow())
        for binding in flow["workflow"]["gate_bindings"]:
            if binding["gate"] == "G5_DEPLOY":
                binding["policy_ref"] = "g6-production-effect-driven"
        _, mutated = _recompile(flow, _policy())
        self.assertNotEqual(base["workflow"]["workflow_digest"], mutated["workflow"]["workflow_digest"])
        self.assertNotEqual(base["compiled_digest"], mutated["compiled_digest"])


class NotApplicableTraversalTests(unittest.TestCase):
    """E4..E5 — NOT_APPLICABLE is an explicit gate skip, never terminal by itself."""

    def _synthetic_na_chain(self, gates):
        """Bind intermediate nodes to gates whose Policy default is NOT_APPLICABLE."""
        flow = copy.deepcopy(_flow())
        chain = [MIDDLE, "failure_recovery.timeout-recovery"]
        for participant in flow["workflow"]["participants"]:
            name = participant["participant"]
            if name in chain and chain.index(name) < len(gates):
                participant.pop("gate_neutral", None)
                participant["gate"] = gates[chain.index(name)]
        return flow

    def test_e4_not_applicable_with_legal_successor_continues(self):
        flow = self._synthetic_na_chain(["G5_DEPLOY"])
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        # The N/A gate is skipped and traversal continues; it is never terminal
        # merely because the gate was not applicable.
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result["reason_codes"])
        self.assertEqual(result["skipped_gates"], ["G5_DEPLOY"])
        self.assertEqual(result["next_gate"], "G3_PR")
        self.assertEqual(result["next_node"], MIDDLE)
        self.assertFalse(result["terminal"])

    def test_e5_not_applicable_chain_reaches_next_required_gate(self):
        flow = copy.deepcopy(_flow())
        # G5 (N/A) -> G6 (N/A) -> G4 (REQUIRED) chain over a synthetic linear graph.
        flow["workflow"]["participants"] = [
            {"participant": ENTRY, "participant_kind": "node", "gate": "G3_PR"},
            {"participant": MIDDLE, "participant_kind": "node", "gate": "G5_DEPLOY"},
            {"participant": "failure_recovery.timeout-recovery", "participant_kind": "node", "gate": "G6_PRODUCTION_DATA"},
            {"participant": TERMINAL, "participant_kind": "node", "gate": "G4_MERGE"},
        ]
        flow["workflow"]["edges"] = [
            {"source": ENTRY, "target": MIDDLE, "kind": "runtime", "runtime_executable": True},
            {"source": MIDDLE, "target": "failure_recovery.timeout-recovery", "kind": "runtime", "runtime_executable": True},
            {"source": "failure_recovery.timeout-recovery", "target": TERMINAL, "kind": "runtime", "runtime_executable": True},
        ]
        flow["workflow"]["terminal_nodes"] = [{"node": TERMINAL, "outcome": "GREEN"}]
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["skipped_gates"], ["G5_DEPLOY", "G6_PRODUCTION_DATA"])
        self.assertEqual(result["next_gate"], "G4_MERGE")
        self.assertEqual(result["next_node"], MIDDLE)
        self.assertNotEqual(result["outcome"], "TERMINAL")


class TerminalAcceptanceTests(unittest.TestCase):
    """E6..E7 — real Workflow terminal is Policy-gated."""

    def test_e6_terminal_with_policy_acceptance_pass_is_terminal(self):
        flow, profile = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=TERMINAL, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "TERMINAL", result["reason_codes"])
        self.assertTrue(result["terminal"])
        self.assertEqual(result["terminal_reason"], "GREEN")

    def test_e7_terminal_with_policy_acceptance_fail_is_blocked(self):
        flow, profile = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=TERMINAL, context=_g3_context(pr={"state": "CLOSED"}), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("TERMINAL_ACCEPTANCE_UNMET", result["reason_codes"])

    def test_e7b_terminal_without_declared_acceptance_is_blocked_unknown(self):
        policy = copy.deepcopy(_policy())
        for item in policy["policies"]:
            if item["id"] == "g3-pr-required":
                item.pop("terminal_acceptance", None)
        flow, profile = _recompile(_rebind_policy(_flow(), policy), policy)
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=policy,
            current_node=TERMINAL, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED", result["reason_codes"])
        self.assertIn("TERMINAL_ACCEPTANCE_UNKNOWN", result["reason_codes"])


class RouteDerivationTests(unittest.TestCase):
    """E8..E9 — routes come from Flow, and stale bindings fail closed."""

    def test_e8_ambiguous_flow_routes_block_and_caller_cannot_choose(self):
        flow = copy.deepcopy(_flow())
        flow["workflow"]["edges"].append({
            "source": ENTRY, "target": TERMINAL,
            "kind": "runtime", "runtime_executable": True,
        })
        flow, profile = _recompile(flow, _policy())
        context = _g3_context(next_nodes=[MIDDLE], terminal_disposition="GREEN")
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=context, root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_NEXT_ROUTE_AMBIGUOUS", result["reason_codes"])
        self.assertIsNone(result["next_node"])

    def test_e8b_dead_end_non_terminal_node_blocks(self):
        flow = copy.deepcopy(_flow())
        flow["workflow"]["edges"] = [
            edge for edge in flow["workflow"]["edges"] if edge["source"] != ENTRY
        ]
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_NEXT_ROUTE_DEAD_END", result["reason_codes"])

    def test_e8c_traversal_loop_fails_closed(self):
        flow = copy.deepcopy(_flow())
        flow["workflow"]["participants"] = [
            {"participant": ENTRY, "participant_kind": "node", "gate": "G3_PR"},
            {"participant": MIDDLE, "participant_kind": "node", "gate": "G5_DEPLOY"},
            {"participant": TERMINAL, "participant_kind": "node", "gate": "G6_PRODUCTION_DATA"},
        ]
        flow["workflow"]["edges"] = [
            {"source": ENTRY, "target": MIDDLE, "kind": "runtime", "runtime_executable": True},
            {"source": MIDDLE, "target": TERMINAL, "kind": "runtime", "runtime_executable": True},
            {"source": TERMINAL, "target": MIDDLE, "kind": "runtime", "runtime_executable": True},
        ]
        flow["workflow"]["terminal_nodes"] = []
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("WORKFLOW_TRAVERSAL_LOOP", result["reason_codes"])

    def test_e9_stale_compiled_binding_blocks(self):
        flow, profile = _recompile(_flow(), _policy())
        stale = copy.deepcopy(profile)
        stale["policy"]["registry_digest"] = "sha256:" + "0" * 64
        result = resolve_compiled_flow_route(
            compiled_profile=stale, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("COMPILED_PROFILE_DIGEST_DRIFT", result["reason_codes"])

    def test_e9b_missing_compiled_profile_blocks(self):
        flow, _ = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile={}, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("COMPILED_PROFILE_MISSING", result["reason_codes"])


class PolicyEnforcementTests(unittest.TestCase):
    """E10..E11 — Policy outcomes are consumed, not reimplemented."""

    def test_e10_required_gate_with_unsatisfied_evidence_blocks(self):
        flow, profile = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(evidence=[]), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", result["reason_codes"])

    def test_e10b_required_gate_with_unsatisfied_authority_blocks(self):
        flow = copy.deepcopy(_flow())
        for participant in flow["workflow"]["participants"]:
            if participant["participant"] == ENTRY:
                participant["gate"] = "G2_EXECUTION"
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(gate="G2_EXECUTION"), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("AUTHORITY_REQUIREMENTS_UNSATISFIED", result["reason_codes"])

    def test_e11_prohibited_action_blocks(self):
        flow = copy.deepcopy(_flow())
        for participant in flow["workflow"]["participants"]:
            if participant["participant"] == ENTRY:
                participant["gate"] = "G2_EXECUTION"
        flow, profile = _recompile(flow, _policy())
        context = _g3_context(gate="G2_EXECUTION", requested_action="write_outside_declared_scope")
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=context, root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("POLICY_PROHIBITED_ACTION", result["reason_codes"])

    def test_blocked_policy_decision_blocks_runtime(self):
        policy = copy.deepcopy(_policy())
        for item in policy["policies"]:
            if item["id"] == "g3-pr-required":
                item["default"] = "BLOCKED"
        flow, profile = _recompile(_rebind_policy(_flow(), policy), policy)
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=policy,
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED", result["reason_codes"])
        self.assertIn("GATE_APPLICABILITY_BLOCKED", result["reason_codes"])


class CompatibilityAndCardinalityTests(unittest.TestCase):
    """E12..E14 — legacy parity, single runtime truth, 81 canonical nodes."""

    def test_e12_legacy_route_profile_parity_preserved(self):
        route = _route_profile()
        flow = _flow()
        self.assertEqual(route["workflow_profile_ref"], flow["id"])
        self.assertEqual(route["artifact_type"], "gate-node-route-profile")
        schema = _load("schemas/node-architect/gate-node-route-profile.schema.json")
        Draft202012Validator(schema).validate(route)
        _, profile = _recompile(flow, _policy())
        self.assertEqual(
            profile["compiled"]["legacy_route_projection_revision"], route["revision"],
        )

    def test_e12b_legacy_resolver_decisions_still_validate(self):
        from tools.node_architect.resolve_gate_node_route import _base_payload

        schema = _load("schemas/node-architect/gate-node-route-decision.schema.json")
        payload = _base_payload(
            task_id="SCRUM-394", gate="G2_EXECUTION",
            requested_action="repository_write", mode="normal",
        )
        payload.update({
            "outcome": "BLOCKED", "reason_code": "NODE_ROUTE_MISSING",
            "reason_codes": ["NODE_ROUTE_MISSING"],
            "decision_digest": "sha256:" + "a" * 64,
        })
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_e13_no_second_runtime_decision_artifact_exists(self):
        for path in (
            "schemas/runtime/workflow-policy-decision.schema.json",
            "tools/node_architect/resolve_flow_policy_runtime.py",
            "tools/node_architect/compile_flow_policy_decision.py",
            "tools/node_architect/validate_flow_policy_runtime.py",
            "core/node-architect/flow-policy-runtime-profile.json",
            "schemas/runtime/flow-policy-runtime-profile.schema.json",
        ):
            self.assertFalse((ROOT / path).exists(), f"duplicate runtime truth still present: {path}")

    def test_e14_canonical_node_cardinality_unchanged(self):
        registry = _load("core/node-architect/node-registry.json")
        self.assertEqual(len(registry["nodes"]), 81)


class CompiledProfileContractTests(unittest.TestCase):
    """Static artifact + activation pointer contract."""

    def test_committed_compiled_profile_matches_schema_and_recompilation(self):
        committed = _load("core/node-architect/flow-policy-compiled-profile.json")
        schema = _load("schemas/runtime/flow-policy-compiled-profile.schema.json")
        errors = list(Draft202012Validator(schema).iter_errors(committed))
        self.assertEqual(errors, [], [error.message for error in errors])

        fresh = compile_flow_policy_profile(
            flow_profile=_flow(), policy_registry=_policy(),
            route_profile=_route_profile(), root=ROOT,
        )
        self.assertEqual(committed["compiled_digest"], fresh["compiled_digest"])
        self.assertEqual(committed["result"]["status"], "COMPATIBLE")
        self.assertEqual(committed["compiler_version"], COMPILER_VERSION)

    def test_compiled_profile_workflow_digest_is_the_locked_flow_digest(self):
        committed = _load("core/node-architect/flow-policy-compiled-profile.json")
        self.assertEqual(
            committed["workflow"]["workflow_digest"],
            "sha256:e3035693e32a39ba649d61ec94d0896a013dd85d1adb8052245385504322e1f9",
        )

    def test_activation_registry_resolves_active_profile(self):
        registry = _load("core/node-architect/flow-policy-activation-registry.json")
        schema = _load("schemas/runtime/flow-policy-activation-registry.schema.json")
        errors = list(Draft202012Validator(schema).iter_errors(registry))
        self.assertEqual(errors, [], [error.message for error in errors])
        result = resolve_active_compiled_profile(activation_registry=registry, root=ROOT)
        self.assertEqual(result["outcome"], "ACTIVE", result["reason_codes"])

    def test_activation_pointer_to_unregistered_digest_blocks(self):
        registry = copy.deepcopy(_load("core/node-architect/flow-policy-activation-registry.json"))
        registry["active_compiled_profile"] = "sha256:" + "9" * 64
        result = resolve_active_compiled_profile(activation_registry=registry, root=ROOT)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("ACTIVE_COMPILED_PROFILE_UNREGISTERED", result["reason_codes"])

    def test_production_flow_and_policy_remain_statically_compatible(self):
        result = validate_flow_policy_compatibility(
            flow_profile=_flow(), policy_registry=_policy(),
        )
        self.assertTrue(result["compatible"], result["reason_codes"])
        workflow = validate_flow_profile_workflow(dict(_flow()), root=ROOT)
        self.assertEqual(workflow["outcome"], "PASS", workflow)

    def test_runtime_decisions_validate_against_canonical_schema(self):
        flow, profile = _recompile(_flow(), _policy())
        schema = _load("schemas/node-architect/gate-node-route-decision.schema.json")
        validator = Draft202012Validator(schema)
        for node, context in (
            (ENTRY, _g3_context()),
            (TERMINAL, _g3_context()),
            (TERMINAL, _g3_context(pr={"state": "CLOSED"})),
        ):
            decision = resolve_compiled_flow_route(
                compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
                current_node=node, context=context, root=ROOT,
            )
            errors = list(validator.iter_errors(decision))
            self.assertEqual(errors, [], [error.message for error in errors])

    def test_runtime_decision_is_replay_stable(self):
        flow, profile = _recompile(_flow(), _policy())
        kwargs = dict(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        first = resolve_compiled_flow_route(**kwargs)
        second = resolve_compiled_flow_route(**kwargs)
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    def test_runtime_never_grants_authority(self):
        flow, profile = _recompile(_flow(), _policy())
        decision = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_g3_context(), root=ROOT,
        )
        for field in (
            "authority_granted", "write_authority_granted", "pr_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(decision[field], field)

    def test_gate_applicability_decision_is_policy_owned(self):
        decision = evaluate_gate_applicability(
            flow_profile=_flow(), policy_registry=_policy(),
            gate="G5_DEPLOY", context={"effects": {}},
        )
        self.assertEqual(decision["decision"], "NOT_APPLICABLE")
        self.assertTrue(decision["decision_digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
