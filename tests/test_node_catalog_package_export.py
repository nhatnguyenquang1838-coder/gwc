import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_package_export import validate_family, validate_runtime_contracts

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "core/node-architect/node-catalog/package_export"


class PackageExportNodeCatalogTest(unittest.TestCase):
    def test_family_has_exactly_nine_nodes(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), 9)

    def test_nodes_are_delivery_evidence_and_g2_bounded(self):
        covered_gates: set[str] = set()
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["node_id"].startswith("package_export."))
            self.assertEqual(payload["canonical"], "delivery_evidence")
            self.assertEqual(payload["authority_boundary"], "g2_required")
            self.assertTrue(set(payload["gates"]).issubset({"G2_EXECUTION", "G3_PR"}))
            covered_gates.update(payload["gates"])
        self.assertEqual(covered_gates, {"G2_EXECUTION", "G3_PR"})

    def test_node_id_matches_file_name(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = "package_export." + path.name.removesuffix(".node.json")
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
        self.assertEqual([], validate_family(FAMILY_DIR, root=ROOT))

    def test_runtime_contracts_validate(self):
        self.assertEqual([], validate_runtime_contracts(ROOT))

    def test_runtime_contracts_bind_entry_schema_validation(self):
        contracts = {
            "package_export.entry-schema-validation": {
                "schema": "schemas/node-architect/package-export/entry-schema-validation.schema.json",
                "evaluator": "tools/node_architect/package_export/entry_schema_validation.py",
                "test": "tests/test_package_export_entry_schema_validation.py",
            }
        }
        from tools.node_architect.validate_node_catalog_package_export import RUNTIME_CONTRACTS
        for node_id, expected in contracts.items():
            actual = RUNTIME_CONTRACTS[node_id]
            self.assertEqual(actual["schema"], expected["schema"])
            self.assertEqual(actual["evaluator"], expected["evaluator"])
            self.assertEqual(actual["test"], expected["test"])

    def test_runtime_contracts_bind_package_manifest_load(self):
        from tools.node_architect.validate_node_catalog_package_export import RUNTIME_CONTRACTS
        expected = {
            "schema": "schemas/node-architect/package-export/package-manifest-load.schema.json",
            "evaluator": "tools/node_architect/package_export/package_manifest_load.py",
            "test": "tests/package_export/test_package_manifest_load.py",
        }
        actual = RUNTIME_CONTRACTS["package_export.package-manifest-load"]
        self.assertEqual(actual["schema"], expected["schema"])
        self.assertEqual(actual["evaluator"], expected["evaluator"])
        self.assertEqual(actual["test"], expected["test"])

    def test_both_materialized_nodes_are_enriched(self):
        enriched_stems = {"entry-schema-validation", "package-manifest-load"}
        for stem in enriched_stems:
            path = FAMILY_DIR / f"{stem}.node.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            for field in ("intent", "outcome", "constraints", "exclusions", "entry_guards", "reason_codes"):
                self.assertTrue(payload.get(field), f"{stem} missing field {field}")
            self.assertIn("evaluator", payload["source_resolution"])
            self.assertIn("schema", payload["source_resolution"])

    def test_validator_rejects_canonical_authority_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "export-manifest-generation.node.json":
                    payload["canonical"] = "canonical"
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            errors = validate_family(tmp_dir, root=ROOT)
            self.assertTrue(any("delivery_evidence" in e for e in errors))

    def test_validator_rejects_deploy_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "smoke-verification.node.json":
                    payload["gates"].append("G5_DEPLOY")
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            errors = validate_family(tmp_dir, root=ROOT)
            self.assertTrue(any("subset" in e for e in errors))

    def test_validator_rejects_extra_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "package-manifest-load.node.json":
                    payload["publish"] = True
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            errors = validate_family(tmp_dir, root=ROOT)
            self.assertTrue(any("unexpected fields" in e for e in errors))

    def test_validator_rejects_node_id_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "entry-schema-validation.node.json":
                    payload["node_id"] = "package-export-entry-schema-validation"
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            errors = validate_family(tmp_dir, root=ROOT)
            self.assertTrue(any("node_id mismatch" in e for e in errors))

    def test_enriched_node_has_maturity_fields(self):
        path = FAMILY_DIR / "entry-schema-validation.node.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for field in ("intent", "outcome", "constraints", "exclusions", "entry_guards", "reason_codes"):
            self.assertTrue(payload.get(field), f"enriched node missing field {field}")
        self.assertIn("evaluator", payload["source_resolution"])
        self.assertIn("schema", payload["source_resolution"])


if __name__ == "__main__":
    unittest.main()
