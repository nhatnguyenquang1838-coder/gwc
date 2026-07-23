from __future__ import annotations
import json
from pathlib import Path
import unittest
import yaml
from tools.node_architect.validate_node_catalog_scale_control import REQUIRED_SEMANTICS, validate_family


class ScaleControlTests(unittest.TestCase):
    def test_repository_family_passes(self):
        root = Path(__file__).resolve().parents[1]
        validate_family(
            root / "core/node-architect/node-catalog/scale_control",
            root / "projects/gwc/package.yaml",
            root / "core/node-architect/failure-simulation-matrix.json",
        )

    def test_exactly_nine_semantics(self):
        root = Path(__file__).resolve().parents[1]
        stems = {
            p.name.removesuffix(".node.json")
            for p in (root / "core/node-architect/node-catalog/scale_control").glob("*.node.json")
        }
        self.assertEqual(stems, REQUIRED_SEMANTICS)

    def test_gate_partition(self):
        root = Path(__file__).resolve().parents[1]
        nodes = [
            json.loads(p.read_text())
            for p in (root / "core/node-architect/node-catalog/scale_control").glob("*.node.json")
        ]
        self.assertEqual(sum(n["gates"] == ["G5_DEPLOY"] for n in nodes), 3)
        self.assertEqual(sum(n["gates"] == ["G3_PR"] for n in nodes), 6)

    def test_audit_projections_are_read_only(self):
        root = Path(__file__).resolve().parents[1]
        nodes = [
            json.loads(p.read_text())
            for p in (root / "core/node-architect/node-catalog/scale_control").glob("*.node.json")
        ]
        projections = [node for node in nodes if node["canonical"] == "audit_projection"]
        self.assertEqual({node["node_id"] for node in projections}, {
            "scale_control.workflow-run-observability",
            "scale_control.rollout-progress-projection",
        })
        self.assertTrue(all(node["authority_boundary"] == "read_only" for node in projections))

    def test_non_projection_authority_matches_gate(self):
        root = Path(__file__).resolve().parents[1]
        nodes = [
            json.loads(p.read_text())
            for p in (root / "core/node-architect/node-catalog/scale_control").glob("*.node.json")
        ]
        for node in nodes:
            if node["canonical"] == "audit_projection":
                continue
            expected = "g5_required" if node["gates"] == ["G5_DEPLOY"] else "g2_required"
            self.assertEqual(node["authority_boundary"], expected)

    def test_catalog_exports_eighty_one_nodes(self):
        root = Path(__file__).resolve().parents[1]
        package = yaml.safe_load((root / "projects/gwc/package.yaml").read_text())
        node_paths = [
            item["path"]
            for item in package["instructions"]
            if "/node-catalog/" in item["path"] and item["path"].endswith(".node.json")
        ]
        self.assertEqual(len(node_paths), 81)
        self.assertEqual(len(node_paths), len(set(node_paths)))

    def test_scale_permission_remains_false(self):
        root = Path(__file__).resolve().parents[1]
        matrix = json.loads((root / "core/node-architect/failure-simulation-matrix.json").read_text())
        self.assertIs(matrix["scale_81_nodes_allowed"], False)

    def test_connector_backlog_is_trace_only(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "core/node-architect/node-catalog/scale_control/README.md").read_text()
        self.assertIn("SCRUM-69", readme)
        self.assertIn("semantics only", readme)


if __name__ == "__main__":
    unittest.main()
