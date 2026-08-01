from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/node_architect/validate_runtime_registry.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_runtime_registry", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimeRegistryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = load_validator()

    def test_canonical_registries_pass_cross_registry_validation(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", str(ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], "PASS")
        self.assertEqual(report["counts"]["nodes"], 81)
        self.assertEqual(report["counts"]["proposed_nodes"], 77)
        self.assertEqual(report["counts"]["explicit_nodes"], 4)
        self.assertEqual(report["counts"]["declared_scenarios"], 116)
        self.assertEqual(report["counts"]["materialized_scenarios"], 14)
        self.assertEqual(len(report["scenario_ids"]), 14)

    def test_every_slot_has_maturity_and_provenance(self) -> None:
        registry = json.loads(
            (ROOT / "core/node-architect/node-registry.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(registry["nodes"]), 81)
        self.assertEqual(
            {node["family"] for node in registry["nodes"]},
            {
                "intake_context",
                "gate_authority",
                "repo_delivery",
                "runtime_checkpoint",
                "validation_quality",
                "sync_projection",
                "package_export",
                "failure_recovery",
                "scale_control",
            },
        )
        for node in registry["nodes"]:
            self.assertIn(
                node["maturity"],
                {"experimental", "candidate", "pilot", "stable", "deprecated", "retired"},
            )
            self.assertIn("source_path", node["provenance"])
            self.assertIn("source_sha", node["provenance"])
            if node["source_status"] == "proposed_registry_slot":
                self.assertNotEqual(node["maturity"], "stable")

    def test_source_hash_normalizes_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "docs" / "line-endings.txt"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(b"alpha\r\nbeta\r\n")
            expected = hashlib.sha256(b"alpha\nbeta\n").hexdigest()
            self.assertEqual(expected, self._source_hash(root, "docs/line-endings.txt"))

    def _source_hash(self, repo_root: Path, relative: str) -> str | None:
        return self.validator.source_hash(repo_root, relative)

    def test_scenario_count_is_not_graph_edge_count(self) -> None:
        scenarios = json.loads(
            (ROOT / "core/node-architect/scenario-registry.json").read_text(encoding="utf-8")
        )
        graph = json.loads(
            (ROOT / "core/node-architect/runtime-graph-registry.json").read_text(encoding="utf-8")
        )
        self.assertEqual(scenarios["declared_scenario_count"], 116)
        self.assertEqual(scenarios["materialized_scenario_count"], 14)
        self.assertEqual(len(scenarios["scenarios"]), 14)
        self.assertNotEqual(scenarios["declared_scenario_count"], len(graph["edges"]))

    def test_visual_edges_are_non_executable(self) -> None:
        graph = json.loads(
            (ROOT / "core/node-architect/runtime-graph-registry.json").read_text(encoding="utf-8")
        )
        visual = [edge for edge in graph["edges"] if edge["edge_type"] == "visualization"]
        self.assertTrue(visual)
        self.assertTrue(all(edge["runtime_executable"] is False for edge in visual))

    def test_scenario_guards_and_route_policies_are_complete(self) -> None:
        scenarios = json.loads(
            (ROOT / "core/node-architect/scenario-registry.json").read_text(encoding="utf-8")
        )["scenarios"]
        for scenario in scenarios:
            activation_facts = set(scenario["activation_facts"])
            self.assertTrue(scenario["guards"])
            self.assertEqual(
                {guard["field"] for guard in scenario["guards"]} - activation_facts,
                set(),
            )
            self.assertIn(scenario["route_policy"]["start_node"], scenario["route_nodes"])
            self.assertEqual(
                set(scenario["route_policy"]["green_targets"]),
                set(scenario["green_targets"]),
            )


if __name__ == "__main__":
    unittest.main()
