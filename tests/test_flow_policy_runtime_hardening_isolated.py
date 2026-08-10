"""Negative regressions for SCRUM-394 runtime resolver hardening.

Covers three hardened invariants of ``resolve_compiled_flow_route``:

H1  The resolver recomputes the live Workflow projection with
    ``compile_workflow_projection(flow_profile)`` and fails closed when it
    differs from the compiled ``workflow_digest`` — including the case where a
    stale/tampered declared digest still matches the compiled one.
H2  A current-node bound gate resolved ``NOT_APPLICABLE`` is recorded in
    ``skipped_gates`` before traversal begins.
H3  A traversed ``REQUIRED`` gate is a hard boundary: the resolver returns
    ``ROUTE_SELECTED``/``NEXT_GATE_REQUIRED`` and stops. It never traverses
    through the gate and never enforces that future gate's authority /
    evidence / prohibited-action requirements in the same call. A gate-neutral
    current node followed by a ``REQUIRED`` successor must still stop at the
    successor (no bypass).

Fixtures are deep copies of the production ``full-flow-v3`` profile; the
production Flow and the compiler are never modified.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.node_architect.compile_flow_policy_profile import compile_flow_policy_profile
from tools.node_architect.resolve_gate_node_route import resolve_compiled_flow_route
from tools.node_architect.validate_flow_profile_workflow import compile_workflow_projection

ROOT = Path(__file__).resolve().parents[1]

ENTRY = "repo_delivery.ci-run-capture"
MIDDLE = "runtime_checkpoint.checkpoint-persist"
TERMINAL = "validation_quality.ci-evidence-capture"
EXTRA = "failure_recovery.timeout-recovery"


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _flow():
    profiles = _load("core/node-architect/profile-registry.json")
    return next(item for item in profiles["profiles"] if item["id"] == "full-flow-v3")


def _policy():
    return _load("core/node-architect/gate-applicability-policy-registry.json")


def _route_profile():
    return _load("core/node-architect/gate-node-route-profile.json")


def _recompile(flow, policy):
    flow = copy.deepcopy(flow)
    flow["compiled"] = dict(flow.get("compiled") or {})
    flow["compiled"]["workflow_digest"] = compile_workflow_projection(dict(flow))["workflow_digest"]
    profile = compile_flow_policy_profile(
        flow_profile=flow, policy_registry=policy,
        route_profile=_route_profile(), root=ROOT,
    )
    return flow, profile


def _context(**overrides):
    context = {
        "task_id": "SCRUM-394",
        "workflow_mode": "normal",
        "evidence": [{"evidence_type": "diff_readback", "verified": True}],
        "pr": {"state": "OPEN"},
    }
    context.update(overrides)
    return context


def _linear_flow(participants, *, terminal_node=TERMINAL, terminal_outcome="GREEN"):
    """Build a synthetic linear Flow over the given (participant, gate) chain."""
    flow = copy.deepcopy(_flow())
    flow["workflow"]["participants"] = [
        (
            {"participant": name, "participant_kind": "node", "gate_neutral": True}
            if gate is None
            else {"participant": name, "participant_kind": "node", "gate": gate}
        )
        for name, gate in participants
    ]
    names = [name for name, _ in participants]
    flow["workflow"]["edges"] = [
        {"source": source, "target": target, "kind": "runtime", "runtime_executable": True}
        for source, target in zip(names, names[1:])
    ]
    flow["workflow"]["terminal_nodes"] = (
        [{"node": terminal_node, "outcome": terminal_outcome}] if terminal_node else []
    )
    return flow


class LiveWorkflowProjectionTests(unittest.TestCase):
    """H1 — live Workflow recompute, fail closed on stale/tampered declared digest."""

    def test_h1_tampered_live_flow_with_consistent_declared_digest_blocks(self):
        flow, profile = _recompile(_flow(), _policy())
        # Live Flow composition moves after compile; the declared digest is
        # deliberately held stale so declared == compiled and the old
        # declared-vs-compiled check alone would pass.
        tampered = copy.deepcopy(flow)
        tampered["workflow"]["participants"].append({
            "participant": "failure_recovery.retry-orchestration",
            "participant_kind": "node", "gate_neutral": True,
        })
        self.assertEqual(
            tampered["compiled"]["workflow_digest"],
            profile["workflow"]["workflow_digest"],
            "declared digest must stay stale for this regression to be meaningful",
        )
        self.assertNotEqual(
            compile_workflow_projection(dict(tampered))["workflow_digest"],
            profile["workflow"]["workflow_digest"],
        )
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=tampered, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED", result["reason_codes"])
        self.assertIn("WORKFLOW_SOURCE_DIGEST_DRIFT", result["reason_codes"])

    def test_h1b_edge_only_live_mutation_blocks(self):
        flow, profile = _recompile(_flow(), _policy())
        tampered = copy.deepcopy(flow)
        tampered["workflow"]["edges"].append({
            "source": ENTRY, "target": TERMINAL,
            "kind": "runtime", "runtime_executable": True,
        })
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=tampered, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "BLOCKED", result["reason_codes"])
        self.assertIn("WORKFLOW_SOURCE_DIGEST_DRIFT", result["reason_codes"])

    def test_h1c_untampered_flow_still_resolves(self):
        flow, profile = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertNotIn("WORKFLOW_SOURCE_DIGEST_DRIFT", result["reason_codes"])


class CurrentGateSkipTests(unittest.TestCase):
    """H2 — current-node NOT_APPLICABLE gate is recorded before traversal."""

    def test_h2_current_not_applicable_gate_is_recorded_in_skipped_gates(self):
        flow = _linear_flow([
            (ENTRY, "G5_DEPLOY"),          # Policy default: NOT_APPLICABLE
            (MIDDLE, "G3_PR"),             # Policy default: REQUIRED
            (TERMINAL, "G3_PR"),
        ])
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result["reason_codes"])
        self.assertEqual(result["skipped_gates"][0], "G5_DEPLOY")
        self.assertEqual(result["next_gate"], "G3_PR")
        self.assertEqual(result["next_node"], MIDDLE)

    def test_h2b_current_not_applicable_precedes_traversal_skips(self):
        flow = _linear_flow([
            (ENTRY, "G5_DEPLOY"),              # current, NOT_APPLICABLE
            (MIDDLE, "G6_PRODUCTION_DATA"),    # traversed, NOT_APPLICABLE
            (TERMINAL, "G3_PR"),               # REQUIRED boundary
        ])
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(
            result["skipped_gates"], ["G5_DEPLOY", "G6_PRODUCTION_DATA"],
            "current-node skip must be ordered before traversal skips",
        )
        self.assertEqual(result["next_gate"], "G3_PR")

    def test_h2c_current_required_gate_is_not_recorded_as_skipped(self):
        flow, profile = _recompile(_flow(), _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertNotIn("G3_PR", result["skipped_gates"])


class RequiredGateBoundaryTests(unittest.TestCase):
    """H3 — a traversed REQUIRED gate is a boundary; no traverse-through, no
    future-gate enforcement in the same call."""

    def test_h3_traversal_stops_at_required_successor(self):
        flow = _linear_flow([
            (ENTRY, "G5_DEPLOY"),   # NOT_APPLICABLE
            (MIDDLE, "G3_PR"),      # REQUIRED — boundary
            (EXTRA, "G5_DEPLOY"),
            (TERMINAL, "G6_PRODUCTION_DATA"),
        ])
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result["reason_codes"])
        self.assertIn("NEXT_GATE_REQUIRED", result["reason_codes"])
        self.assertEqual(result["next_gate"], "G3_PR")
        self.assertFalse(result["terminal"])
        # Boundary proof: nothing beyond the REQUIRED node was traversed.
        self.assertEqual(result["traversed_nodes"], [MIDDLE])
        self.assertNotIn(EXTRA, result["traversed_nodes"])
        self.assertNotIn(TERMINAL, result["traversed_nodes"])
        self.assertNotIn("G6_PRODUCTION_DATA", result["skipped_gates"])

    def test_h3b_gate_neutral_current_node_stops_at_required_successor(self):
        flow = _linear_flow([
            (ENTRY, None),          # gate-neutral current node
            (MIDDLE, "G3_PR"),      # REQUIRED successor
            (TERMINAL, "G5_DEPLOY"),
        ])
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=_context(), root=ROOT,
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result["reason_codes"])
        self.assertEqual(result["next_gate"], "G3_PR")
        self.assertEqual(result["next_node"], MIDDLE)
        self.assertEqual(result["traversed_nodes"], [MIDDLE])
        self.assertNotEqual(result["outcome"], "TERMINAL")
        self.assertFalse(result["terminal"])

    def test_h3c_future_required_gate_requirements_are_not_enforced(self):
        """Unsatisfiable evidence for the *future* G3 gate must not block the
        current call; enforcement only happens once that gate is current."""
        flow = _linear_flow([
            (ENTRY, None),          # gate-neutral current node: nothing to enforce
            (MIDDLE, "G3_PR"),      # REQUIRED successor with evidence requirements
            (TERMINAL, "G5_DEPLOY"),
        ])
        flow, profile = _recompile(flow, _policy())
        empty_evidence = _context(evidence=[])
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=empty_evidence, root=ROOT,
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result["reason_codes"])
        self.assertNotIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", result["reason_codes"])
        self.assertNotIn("AUTHORITY_REQUIREMENTS_UNSATISFIED", result["reason_codes"])
        self.assertNotIn("POLICY_PROHIBITED_ACTION", result["reason_codes"])
        # Same unsatisfied evidence blocks once that gate is the current node.
        current = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=MIDDLE, context=empty_evidence, root=ROOT,
        )
        self.assertEqual(current["outcome"], "BLOCKED", current["reason_codes"])
        self.assertIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", current["reason_codes"])

    def test_h3d_prohibited_action_of_future_gate_is_not_enforced(self):
        flow = _linear_flow([
            (ENTRY, None),                # gate-neutral current node
            (MIDDLE, "G2_EXECUTION"),     # REQUIRED successor with prohibited actions
            (TERMINAL, "G5_DEPLOY"),
        ])
        flow, profile = _recompile(flow, _policy())
        context = _context(requested_action="write_outside_declared_scope")
        result = resolve_compiled_flow_route(
            compiled_profile=profile, flow_profile=flow, policy_registry=_policy(),
            current_node=ENTRY, context=context, root=ROOT,
        )
        self.assertNotIn("POLICY_PROHIBITED_ACTION", result["reason_codes"])
        self.assertEqual(result["next_gate"], "G2_EXECUTION")


if __name__ == "__main__":
    unittest.main()
