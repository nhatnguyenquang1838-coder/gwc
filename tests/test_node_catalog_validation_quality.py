import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_validation_quality import validate_family

FAMILY_DIR = Path("core/node-architect/node-catalog/validation_quality")


class ValidationQualityNodeCatalogTest(unittest.TestCase):
    def test_family_has_exactly_nine_nodes(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), 9)

    def test_nodes_are_g3_scoped(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["node_id"].startswith("validation-quality-"))
            self.assertEqual(payload["authority_boundary"], "g2_required")
            self.assertEqual(set(payload["gates"]), {"G3_PR"})

    def test_node_id_matches_file_name(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = "validation-quality-" + path.name.removesuffix(".node.json")
            self.assertEqual(payload["node_id"], expected)

    def test_validator_accepts_real_family(self):
        validate_family(FAMILY_DIR)

    def test_validator_rejects_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for path in FAMILY_DIR.glob("*.node.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if path.name == "schema-validation.node.json":
                    payload["unexpected"] = True
                (tmp_dir / path.name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(tmp_dir)


if __name__ == "__main__":
    unittest.main()
