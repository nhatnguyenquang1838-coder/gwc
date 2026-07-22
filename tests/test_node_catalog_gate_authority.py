import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_gate_authority import (
    EXPECTED_AUTHORITY,
    EXPECTED_COUNT,
    EXPECTED_FAMILY,
    validate_family,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = REPO_ROOT / "core/node-architect/node-catalog/gate_authority"


class GateAuthorityNodeCatalogTests(unittest.TestCase):
    def test_family_has_expected_count(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), EXPECTED_COUNT)

    def test_family_is_valid(self):
        self.assertEqual(validate_family(FAMILY_DIR), [])

    def test_nodes_stay_within_gate_authority_boundary(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            node = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(node["node_id"].startswith(f"{EXPECTED_FAMILY}."))
            self.assertEqual(node["authority_boundary"], EXPECTED_AUTHORITY)
            self.assertTrue(set(node["gates"]).issubset({"G1_ALIGNMENT", "G2_EXECUTION"}))
            self.assertNotIn("G4_MERGE", node["gates"])
            self.assertNotIn("G5_DEPLOY", node["gates"])
            self.assertNotIn("G6_PRODUCTION_DATA", node["gates"])

    def test_invalid_authority_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_family = Path(tmp) / EXPECTED_FAMILY
            temp_family.mkdir()
            for source in FAMILY_DIR.glob("*.node.json"):
                target = temp_family / source.name
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            first = next(temp_family.glob("*.node.json"))
            node = json.loads(first.read_text(encoding="utf-8"))
            node["authority_boundary"] = "read_only"
            first.write_text(json.dumps(node), encoding="utf-8")

            errors = validate_family(temp_family)
            self.assertTrue(any("authority_boundary" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
