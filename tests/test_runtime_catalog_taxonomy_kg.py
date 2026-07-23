from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_VALIDATOR = ROOT / "tools" / "node_architect" / "validate_runtime_catalog_taxonomy.py"
KG_PROJECTOR = ROOT / "tools" / "node_architect" / "project_runtime_knowledge_graph.py"

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


def taxonomy():
    return {
        "schema_version": "1.0",
        "artifact_type": "runtime-catalog-taxonomy",
        "runtime_node_count": 81,
        "edge_scenario_count": 116,
        "canonical_terms": ["Gate", "Capability Family", "Runtime Node", "Edge Scenario", "Artifact"],
        "families": [
            {"id": family, "canonical_name": family.replace("_", " ").title(), "node_count": 9, "governed_gates": ["G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G5_DEPLOY"]}
            for family in FAMILIES
        ],
    }


class RuntimeCatalogTaxonomyKgTests(unittest.TestCase):
    def test_taxonomy_preserves_nine_families_and_81_runtime_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "taxonomy.json"
            path.write_text(json.dumps(taxonomy()), encoding="utf-8")
            result = subprocess.run([sys.executable, str(TAXONOMY_VALIDATOR), str(path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_taxonomy_rejects_node_count_drift(self):
        payload = taxonomy()
        payload["families"][0]["node_count"] = 10
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "taxonomy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run([sys.executable, str(TAXONOMY_VALIDATOR), str(path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("81", result.stdout)

    def test_kg_projection_uses_canonical_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "kg.json"
            result = subprocess.run([sys.executable, str(KG_PROJECTOR), "--output", str(output)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            graph = json.loads(output.read_text(encoding="utf-8"))
        relationships = {edge["relationship"] for edge in graph["edges"]}
        self.assertIn("BELONGS_TO_FAMILY", relationships)
        self.assertIn("GOVERNED_BY_GATE", relationships)
        self.assertIn("IMPLEMENTED_BY", relationships)
        self.assertIn("HANDLES_SCENARIO", relationships)
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("node:repo-delivery-ci-run-capture", node_ids)
        self.assertIn("artifact:core/G5_CI_VERIFICATION_CONTRACT_v1.0.md", node_ids)

    def test_contract_forbids_renaming_81_nodes_as_gates(self):
        text = (ROOT / "core" / "RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md").read_text(encoding="utf-8")
        self.assertIn("81 Runtime Nodes", text)
        self.assertIn("Capability Family", text)
        self.assertIn("Edge Scenario", text)
        self.assertIn("Artifact", text)
        self.assertIn("❌ 81 gates", text)


if __name__ == "__main__":
    unittest.main()
