import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_package_export import validate_family

FAMILY_DIR = Path("core/node-architect/node-catalog/package_export")


class PackageExportNodeCatalogTest(unittest.TestCase):
    def test_family_has_exactly_nine_nodes(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), 9)

    def test_nodes_are_delivery_evidence_and_g2_bounded(self):
        covered_gates: set[str] = set()
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["node_id"].startswith("package-export-"))
            self.assertEqual(payload["canonical"], "delivery_evidence")
            self.assertEqual(payload["authority_boundary"], "g2_required")
            self.assertTrue(set(payload["gates"]).issubset({"G2_EXECUTION", "G3_PR"}))
            covered_gates.update(payload["gates"])
        self.assertEqual(covered_gates, {"G2_EXECUTION", "G3_PR"})

    def test_node_id_matches_file_name(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = "package-export-" + path.name.removesuffix(".node.json")
            self.assertEqual(payload["node_id"], expected)

    def test_required_export_semantics_exist(self):
        stems = {path.name.removesuffix(".node.json") for path in FAMILY_DIR.glob("*.node.json")}
        required = {
            "package-manifest-load", "entry-schema-validation", "source-path-safety-check",
            "target-path-safety-check", "governance-tree-build", "export-manifest-generation",
            "deterministic-hash-verification", "smoke-verification", "export-failure-routing",
        }
        self.assertEqual(stems, required)

    def test_validator_accepts_real_family(self):
        validate_family(FAMILY_DIR)

    def test_validator_rejects_canonical_authority_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "export-manifest-generation.node.json":
                    payload["canonical"] = "canonical"
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)

    def test_validator_rejects_deploy_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "smoke-verification.node.json":
                    payload["gates"].append("G5_DEPLOY")
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)

    def test_validator_rejects_extra_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "package-manifest-load.node.json":
                    payload["publish"] = True
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)


if __name__ == "__main__":
    unittest.main()
