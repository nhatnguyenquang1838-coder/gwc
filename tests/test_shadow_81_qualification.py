import tempfile
import unittest
from pathlib import Path

from tools.node_architect.run_shadow_e1_canary import run_canary
from tools.node_architect.shadow_81_qualification import build_qualification_report

FAMILIES = [
    "intake_context",
    "gate_authority",
    "repo_delivery",
    "runtime_checkpoint",
    "validation_quality",
    "sync_projection",
    "package_export",
    "failure_recovery",
    "scale_control",
]


def registry(count: int = 81) -> dict:
    nodes = []
    for index in range(count):
        family = FAMILIES[index % len(FAMILIES)]
        nodes.append(
            {
                "id": f"{family}.node-{index:02d}",
                "family": family,
                "version": "1.0.0",
                "maturity": "experimental",
                "effect_class": "read_only",
                "suspension": {"suspendable": True, "resume_metadata": ["task", "revision"]},
                "provenance": {"source_path": f"missing/{index}.json"},
            }
        )
    return {"declared_slot_count": count, "nodes": nodes}


def activation() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "shadow-runtime-activation",
        "enabled": True,
        "kill_switch_engaged": False,
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


class QualificationTests(unittest.TestCase):
    def test_exact_81_are_adapter_route_and_replay_proven(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = build_qualification_report(
                registry(), activation(), revision="a" * 40, root=Path(temp)
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["summary"]["shadow_enabled_count"], 81)
        self.assertEqual(report["summary"]["descriptor_only_count"], 81)
        self.assertEqual(report["gate_matrix"]["G4_MERGE"]["status"], "TYPED_NON_APPLICABLE")
        self.assertEqual(report["gate_matrix"]["G6_PRODUCTION_DATA"]["status"], "TYPED_NON_APPLICABLE")
        self.assertTrue(all(report["adversarial_checks"].values()))

    def test_slot_82_cannot_satisfy_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = build_qualification_report(
                registry(82), activation(), revision="a" * 40, root=Path(temp)
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CANONICAL_NODE_COUNT_MISMATCH", report["errors"])

    def test_e1_canary_exercises_all_route_packs_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = run_canary(
                registry(),
                activation(),
                revision="a" * 40,
                ledger=Path(temp) / "canary.jsonl",
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            set(report["route_packs_seen"]),
            {"RP-01", "RP-02", "RP-03", "RP-04", "RP-05", "RP-06"},
        )
        self.assertTrue(report["safe"])

    def test_live_observed_is_separate_from_replay_proof(self) -> None:
        baseline = registry()
        observed = {baseline["nodes"][0]["id"]}
        with tempfile.TemporaryDirectory() as temp:
            report = build_qualification_report(
                baseline,
                activation(),
                revision="a" * 40,
                root=Path(temp),
                live_observed_node_ids=observed,
            )
        self.assertEqual(report["summary"]["observed_live_count"], 1)
        record = next(item for item in report["records"] if item["node_id"] in observed)
        self.assertEqual(record["executability_level"], "E5_OBSERVED")


if __name__ == "__main__":
    unittest.main()
