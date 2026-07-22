import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_repo_delivery import validate_family


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "core" / "node-architect" / "node-catalog" / "repo_delivery"


class RepoDeliveryNodeCatalogTests(unittest.TestCase):
    def test_repo_delivery_family_valid(self):
        self.assertEqual(validate_family(FAMILY_DIR), [])

    def test_rejects_wrong_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for source in FAMILY_DIR.glob("*.node.json"):
                target.joinpath(source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            first = next(target.glob("*.node.json"))
            node = json.loads(first.read_text(encoding="utf-8"))
            node["authority_boundary"] = "g4_required"
            first.write_text(json.dumps(node), encoding="utf-8")
            self.assertTrue(any("authority_boundary" in error for error in validate_family(target)))

    def test_rejects_g4_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for source in FAMILY_DIR.glob("*.node.json"):
                target.joinpath(source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            first = next(target.glob("*.node.json"))
            node = json.loads(first.read_text(encoding="utf-8"))
            node["gates"] = ["G2_EXECUTION", "G4_MERGE"]
            first.write_text(json.dumps(node), encoding="utf-8")
            self.assertTrue(any("outside repo-delivery boundary" in error for error in validate_family(target)))

    def test_rejects_extra_property(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for source in FAMILY_DIR.glob("*.node.json"):
                target.joinpath(source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            first = next(target.glob("*.node.json"))
            node = json.loads(first.read_text(encoding="utf-8"))
            node["unsafe"] = True
            first.write_text(json.dumps(node), encoding="utf-8")
            self.assertTrue(any("unexpected keys" in error for error in validate_family(target)))


if __name__ == "__main__":
    unittest.main()
