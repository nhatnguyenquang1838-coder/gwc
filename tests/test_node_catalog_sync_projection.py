import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_sync_projection import validate_family

FAMILY_DIR = Path("core/node-architect/node-catalog/sync_projection")


class SyncProjectionNodeCatalogTest(unittest.TestCase):
    def test_family_has_exactly_nine_nodes(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), 9)

    def test_nodes_are_audit_projection_and_read_only(self):
        covered_gates: set[str] = set()
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["node_id"].startswith("sync-projection-"))
            self.assertEqual(payload["canonical"], "audit_projection")
            self.assertEqual(payload["authority_boundary"], "read_only")
            self.assertTrue(set(payload["gates"]).issubset({"G2_EXECUTION", "G3_PR"}))
            covered_gates.update(payload["gates"])
        self.assertEqual(covered_gates, {"G2_EXECUTION", "G3_PR"})

    def test_node_id_matches_file_name(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = "sync-projection-" + path.name.removesuffix(".node.json")
            self.assertEqual(payload["node_id"], expected)

    def test_required_projection_semantics_exist(self):
        stems = {path.name.removesuffix(".node.json") for path in FAMILY_DIR.glob("*.node.json")}
        required = {
            "projection-source-authority-check",
            "projection-drift-detection",
            "projection-reconcile-readback",
            "projection-failure-routing",
            "projection-evidence-linking",
            "projection-privacy-boundary-check",
        }
        self.assertTrue(required.issubset(stems))

    def test_validator_accepts_real_family(self):
        validate_family(FAMILY_DIR)

    def test_validator_rejects_canonical_authority_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "projection-source-authority-check.node.json":
                    payload["canonical"] = "canonical"
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)

    def test_validator_rejects_projection_authority_escalation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "projection-source-authority-check.node.json":
                    payload["authority_boundary"] = "g2_required"
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)

    def test_validator_rejects_production_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "projection-privacy-boundary-check.node.json":
                    payload["gates"].append("G6_PRODUCTION_DATA")
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)


if __name__ == "__main__":
    unittest.main()
