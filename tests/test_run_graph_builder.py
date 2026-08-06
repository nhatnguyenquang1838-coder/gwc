from __future__ import annotations

import copy
import unittest

from tools.node_architect.build_run_graph import RunGraphError, build_run_graph, render_mermaid

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def manifest() -> dict:
    return {
        "run_id": "run-scrum-271-fixture-1",
        "task_id": "SCRUM-271",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_ref": "auto/run-scrum-271/SCRUM-271",
        "head_sha": HEAD_SHA,
        "graph_revision": "scrum-271-v0.1",
        "events": [
            {
                "event_id": "evt-g0-context",
                "sequence": 0,
                "gate": "G0_CONTEXT",
                "participant_type": "runtime_node",
                "participant_id": "intake_context.context-snapshot",
                "purpose": "materialize exact context",
                "status": "passed",
                "entry_evidence": ["jira:SCRUM-271", f"git:{BASE_SHA}"],
                "action": "read_context",
                "outcome": "CONTEXT_READY",
                "evidence_refs": [".gwc/tasks/SCRUM-271/g0/context-snapshot.yaml"],
                "next_event_id": "evt-g1-decision",
                "edge_type": "runtime",
                "route_provenance": "route:g0-to-g1",
            },
            {
                "event_id": "evt-g1-decision",
                "sequence": 1,
                "gate": "G1_ALIGNMENT",
                "participant_type": "gate_action",
                "participant_id": "g1-alignment-decision",
                "purpose": "select approved option",
                "status": "passed",
                "entry_evidence": ["g0:ready"],
                "action": "select_option",
                "outcome": "OPT_1_SELECTED",
                "evidence_refs": [".gwc/tasks/SCRUM-271/g1/decision/g1-decision-record.yaml"],
                "next_event_id": "evt-g2-route",
                "edge_type": "authority",
                "route_provenance": "decision:OPT-1",
            },
            {
                "event_id": "evt-g2-route",
                "sequence": 2,
                "gate": "G2_EXECUTION",
                "participant_type": "runtime_node",
                "participant_id": "gate_authority.gate-state-resolution",
                "purpose": "resolve G2 execution route",
                "status": "executed",
                "entry_evidence": ["g1:pass", "g2:approval"],
                "action": "resolve_execution_node",
                "outcome": "ROUTE_RESOLVED",
                "evidence_refs": ["route:g2-resolve-execution-node"],
                "next_event_id": None,
                "edge_type": "runtime",
                "route_provenance": "gate-node-route-profile:g2-resolve-execution-node",
            },
        ],
    }


class RunGraphBuilderTests(unittest.TestCase):
    def test_graph_is_deterministic_and_head_bound(self):
        first = build_run_graph(manifest())
        second = build_run_graph(copy.deepcopy(manifest()))
        self.assertEqual(first, second)
        self.assertEqual(HEAD_SHA, first["head_sha"])
        self.assertEqual("PASS", first["terminal_status"])
        self.assertTrue(first["graph_digest"].startswith("sha256:"))
        self.assertEqual(3, len(first["nodes"]))
        self.assertEqual(2, len(first["edges"]))

    def test_gate_action_is_not_invented_as_runtime_node(self):
        graph = build_run_graph(manifest())
        decision = graph["nodes"][1]
        self.assertEqual("gate_action", decision["participant_type"])
        self.assertEqual("g1-alignment-decision", decision["canonical_id"])
        mermaid = render_mermaid(graph)
        self.assertIn('{"G1_ALIGNMENT · g1-alignment-decision', mermaid)
        self.assertIn('["G0_CONTEXT · intake_context.context-snapshot', mermaid)

    def test_duplicate_event_id_fails_closed(self):
        value = manifest()
        value["events"][1]["event_id"] = value["events"][0]["event_id"]
        with self.assertRaises(RunGraphError) as raised:
            build_run_graph(value)
        self.assertEqual("AUTONOMOUS_GRAPH_EVENT_DUPLICATE", raised.exception.reason_code)

    def test_unknown_route_target_fails_closed(self):
        value = manifest()
        value["events"][0]["next_event_id"] = "evt-missing"
        with self.assertRaises(RunGraphError) as raised:
            build_run_graph(value)
        self.assertEqual("AUTONOMOUS_GRAPH_ROUTE_TARGET_MISSING", raised.exception.reason_code)

    def test_missing_events_fail_closed(self):
        value = manifest()
        value["events"] = []
        with self.assertRaises(RunGraphError) as raised:
            build_run_graph(value)
        self.assertEqual("AUTONOMOUS_GRAPH_EVENT_MISSING", raised.exception.reason_code)


if __name__ == "__main__":
    unittest.main()
