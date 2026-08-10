"""Runtime hardening contract cases for SCRUM-394 P1-C.

This module is intentionally staged before it is wired into focused CI. It
locks the runtime boundary semantics independently of implementation details.
"""
from __future__ import annotations

import copy
import unittest

from tests.test_flow_policy_runtime_e2e import (
    ENTRY,
    MIDDLE,
    TERMINAL,
    _flow,
    _g3_context,
    _policy,
    _recompile,
)
from tools.node_architect.resolve_gate_node_route import resolve_compiled_flow_route


class FlowPolicyRuntimeHardeningTests(unittest.TestCase):
    def test_live_workflow_projection_drift_fails_closed_even_with_stale_declared_digest(self):
        flow, profile = _recompile(_flow(), _policy())
        mutated = copy.deepcopy(flow)
        # Change live Flow composition while deliberately leaving the declared
        # compiled.workflow_digest untouched. Runtime must recompute the live
        # projection instead of trusting that stale declaration.
        for edge in mutated["workflow"]["edges"]:
            if edge["source"] == MIDDLE and edge["target"] == TERMINAL:
                edge["condition_id"] = "runtime-hardening-source-drift"
                break
        result = resolve_compiled_flow_route(
            compiled_profile=profile,
            flow_profile=mutated,
            policy_registry=_policy(),
            current_node=ENTRY,
            context=_g3_context(),
            root=__import__("pathlib").Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result["outcome"], "BLOCKED", result)
        self.assertIn("WORKFLOW_SOURCE_DIGEST_DRIFT", result["reason_codes"])

    def test_current_not_applicable_gate_is_recorded_as_explicit_skip(self):
        flow = copy.deepcopy(_flow())
        for participant in flow["workflow"]["participants"]:
            if participant["participant"] == ENTRY:
                participant["gate"] = "G5_DEPLOY"
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile,
            flow_profile=flow,
            policy_registry=_policy(),
            current_node=ENTRY,
            context=_g3_context(),
            root=__import__("pathlib").Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result)
        self.assertIn("G5_DEPLOY", result["skipped_gates"])
        self.assertEqual(result["next_gate"], "G3_PR")

    def test_traversed_required_gate_is_boundary_not_future_gate_enforcement(self):
        flow = copy.deepcopy(_flow())
        for participant in flow["workflow"]["participants"]:
            if participant["participant"] == ENTRY:
                participant.pop("gate", None)
                participant["gate_neutral"] = True
            elif participant["participant"] == MIDDLE:
                participant.pop("gate_neutral", None)
                participant["gate"] = "G2_EXECUTION"
        flow, profile = _recompile(flow, _policy())
        result = resolve_compiled_flow_route(
            compiled_profile=profile,
            flow_profile=flow,
            policy_registry=_policy(),
            current_node=ENTRY,
            # No G2 authority/evidence is supplied on purpose. The future gate
            # is a boundary; its requirements are enforced only when current.
            context=_g3_context(),
            root=__import__("pathlib").Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result["outcome"], "ROUTE_SELECTED", result)
        self.assertEqual(result["next_gate"], "G2_EXECUTION")
        self.assertEqual(result["next_node"], MIDDLE)
        self.assertIn("NEXT_GATE_REQUIRED", result["reason_codes"])
        self.assertNotIn("AUTHORITY_REQUIREMENTS_UNSATISFIED", result["reason_codes"])
        self.assertNotIn("EVIDENCE_REQUIREMENTS_UNSATISFIED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
