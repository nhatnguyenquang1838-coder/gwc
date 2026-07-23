"""Tests for the GWC node-architect runtime validator harness."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPILE = ROOT / "tools/node_architect/compile_node_registry.py"
VALIDATE = ROOT / "tools/node_architect/validate_node_registry.py"
SIMULATE = ROOT / "tools/node_architect/simulate_gate_runtime.py"
CATALOG = ROOT / "core/node-architect/node-catalog"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class NodeArchitectRuntimeValidationTests(unittest.TestCase):
    def test_compile_validate_and_simulate_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            nodes = work / "nodes"
            registry = work / "registry.json"

            write_json(
                nodes / "g2.node.json",
                {
                    "node_id": "gate.g2",
                    "node_type": "gate",
                    "title": "G2 execution",
                    "canonical": "canonical",
                    "authority_boundary": "g2_required",
                    "gates": ["G2_EXECUTION"],
                },
            )
            write_json(
                nodes / "g4.node.json",
                {
                    "node_id": "gate.g4",
                    "node_type": "gate",
                    "title": "G4 merge",
                    "canonical": "canonical",
                    "authority_boundary": "g4_required",
                    "gates": ["G4_MERGE"],
                },
            )
            write_json(
                nodes / "jira.node.json",
                {
                    "node_id": "audit.jira",
                    "node_type": "projection",
                    "title": "Jira audit projection",
                    "canonical": "audit_projection",
                    "authority_boundary": "read_only",
                    "gates": [],
                    "edges": [{"source": "gate.g2", "target": "audit.jira", "relation": "projects_to"}],
                },
            )

            compiled = run_tool(str(COMPILE), "--input-dir", str(nodes), "--output", str(registry))
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            validated = run_tool(str(VALIDATE), "--registry", str(registry))
            self.assertEqual(validated.returncode, 0, validated.stdout)
            self.assertEqual(json.loads(validated.stdout)["outcome"], "PASS")

            simulated = run_tool(str(SIMULATE), "--registry", str(registry), "--requested-action", "merge")
            self.assertEqual(simulated.returncode, 0, simulated.stdout)
            self.assertEqual(json.loads(simulated.stdout)["required_gate"], "G4_MERGE")

    def test_full_repository_catalog_compiles_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "registry.json"

            compiled = run_tool(
                str(COMPILE),
                "--input-dir",
                str(CATALOG),
                "--output",
                str(registry),
                "--registry-id",
                "gwc-81-node-catalog",
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            payload = json.loads(registry.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["nodes"]), 81)
            self.assertEqual(len({node["node_id"] for node in payload["nodes"]}), 81)

            validated = run_tool(str(VALIDATE), "--registry", str(registry))
            self.assertEqual(validated.returncode, 0, validated.stdout)
            self.assertEqual(json.loads(validated.stdout)["outcome"], "PASS")

    def test_validate_fails_duplicate_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "registry.json"
            write_json(
                registry,
                {
                    "schema_version": "0.1",
                    "registry_id": "duplicate-test",
                    "nodes": [
                        {
                            "node_id": "gate.g2",
                            "node_type": "gate",
                            "title": "G2",
                            "canonical": "canonical",
                            "authority_boundary": "g2_required",
                            "gates": ["G2_EXECUTION"],
                        },
                        {
                            "node_id": "gate.g2",
                            "node_type": "gate",
                            "title": "Duplicate G2",
                            "canonical": "canonical",
                            "authority_boundary": "g2_required",
                            "gates": ["G2_EXECUTION"],
                        },
                    ],
                    "edges": [],
                },
            )

            validated = run_tool(str(VALIDATE), "--registry", str(registry))
            self.assertEqual(validated.returncode, 1)
            self.assertIn("NODE_ID_DUPLICATE", validated.stdout)

    def test_simulation_blocks_merge_without_g4_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "registry.json"
            write_json(
                registry,
                {
                    "schema_version": "0.1",
                    "registry_id": "missing-g4-test",
                    "nodes": [
                        {
                            "node_id": "gate.g2",
                            "node_type": "gate",
                            "title": "G2",
                            "canonical": "canonical",
                            "authority_boundary": "g2_required",
                            "gates": ["G2_EXECUTION"],
                        }
                    ],
                    "edges": [],
                },
            )

            simulated = run_tool(str(SIMULATE), "--registry", str(registry), "--requested-action", "merge")
            self.assertEqual(simulated.returncode, 1)
            self.assertIn("REQUIRED_GATE_MISSING", simulated.stdout)

    def test_projection_cannot_be_canonical_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "registry.json"
            write_json(
                registry,
                {
                    "schema_version": "0.1",
                    "registry_id": "projection-test",
                    "nodes": [
                        {
                            "node_id": "projection.tc",
                            "node_type": "projection",
                            "title": "TC projection",
                            "canonical": "canonical",
                            "authority_boundary": "read_only",
                            "gates": [],
                        }
                    ],
                    "edges": [],
                },
            )

            simulated = run_tool(str(SIMULATE), "--registry", str(registry), "--requested-action", "repository_write")
            self.assertEqual(simulated.returncode, 1)
            self.assertIn("PROJECTION_MARKED_CANONICAL", simulated.stdout)


if __name__ == "__main__":
    unittest.main()
