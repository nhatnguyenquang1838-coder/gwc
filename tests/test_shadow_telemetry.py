import tempfile
import unittest
from pathlib import Path

from tools.node_architect.compare_shadow_authoritative import compare_decisions
from tools.node_architect.shadow_moa import synthesize
from tools.node_architect.shadow_telemetry import append_telemetry, build_telemetry_event
from tools.node_architect.shadow_telemetry_from_output import emit_output_telemetry


class ShadowTelemetryTests(unittest.TestCase):
    def result(self) -> dict:
        return {
            "task_id": "SCRUM-591",
            "run_id": "r1",
            "gate": "G3_PR",
            "exact_revision": "a" * 40,
            "node_id": "validation_quality.ci-evidence-capture",
            "node_version": "1.0.0",
            "maturity": "candidate",
            "executability_level": "E3_ROUTE_BOUND",
            "applicability": "APPLICABLE",
            "outcome": "ALLOW",
            "reason_code": "OK",
            "result_digest": "sha256:" + "1" * 64,
            "proposed_effects": [],
            "executed_effects": [],
            "authority_granted": False,
            "checkpoint": {"recommended": False, "resume_metadata": []},
        }

    def test_event_identity_is_deterministic_and_graph_bound(self) -> None:
        first = build_telemetry_event(self.result(), route_pack="RP-01", graph_revision="graph-v1")
        second = build_telemetry_event(self.result(), route_pack="RP-01", graph_revision="graph-v1")
        self.assertEqual(first, second)
        self.assertEqual(first["graph_revision"], "graph-v1")
        self.assertEqual(first["node_version"], "1.0.0")
        self.assertEqual(first["maturity"], "candidate")

    def test_ledger_dedupes_identical_replay(self) -> None:
        event = build_telemetry_event(self.result(), route_pack="RP-01")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.jsonl"
            self.assertTrue(append_telemetry(path, event))
            self.assertFalse(append_telemetry(path, event))
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_ledger_rejects_nondeterministic_same_invocation(self) -> None:
        event = build_telemetry_event(self.result(), route_pack="RP-01")
        changed = dict(event)
        changed["reason_code"] = "DIFFERENT"
        changed["event_digest"] = "sha256:" + "f" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.jsonl"
            append_telemetry(path, event)
            with self.assertRaisesRegex(ValueError, "NON_DETERMINISTIC"):
                append_telemetry(path, changed)

    def test_unsafe_shadow_effect_is_rejected(self) -> None:
        result = self.result()
        result["executed_effects"] = [{"mutation": "x"}]
        with self.assertRaisesRegex(ValueError, "EXECUTED_EFFECT"):
            build_telemetry_event(result, route_pack="RP-01")

    def test_comparison_is_exact_identity_bound_and_false_allow_is_explicit(self) -> None:
        shadow = build_telemetry_event(self.result(), route_pack="RP-01")
        authoritative = {
            "task_id": "SCRUM-591",
            "run_id": "r1",
            "gate": "G3_PR",
            "exact_revision": "a" * 40,
            "decision": "BLOCK",
        }
        self.assertEqual(compare_decisions(shadow, authoritative)["classification"], "SHADOW_MORE_PERMISSIVE_DENIED")
        authoritative["exact_revision"] = "b" * 40
        self.assertEqual(compare_decisions(shadow, authoritative)["classification"], "NOT_COMPARABLE")

    def test_observer_output_emits_append_only_ledger(self) -> None:
        event = {"task_id": "SCRUM-591", "run_id": "r1", "gate": "G3_PR", "exact_revision": "a" * 40}
        output = {"route_pack": "RP-01", "results": [self.result()]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.jsonl"
            first = emit_output_telemetry(event, output, path)
            second = emit_output_telemetry(event, output, path)
            self.assertEqual(first["appended"], 1)
            self.assertEqual(second["duplicates"], 1)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_moa_preserves_minority_contradiction(self) -> None:
        evidence = [
            {"classification": "AGREEMENT", "source": "a"},
            {"classification": "AGREEMENT", "source": "b"},
            {"classification": "SHADOW_MORE_PERMISSIVE_DENIED", "source": "c"},
        ]
        output = synthesize(evidence)
        self.assertEqual(output["outcome"], "CONTRADICTION_UNRESOLVED")
        self.assertEqual([item["source"] for item in output["evidence"]], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
