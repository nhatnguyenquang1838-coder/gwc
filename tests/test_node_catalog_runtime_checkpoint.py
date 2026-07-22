import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_runtime_checkpoint import validate_family


REPO_ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = REPO_ROOT / "core" / "node-architect" / "node-catalog" / "runtime_checkpoint"


class RuntimeCheckpointNodeCatalogTests(unittest.TestCase):
    def copy_family(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        target = temp / "runtime_checkpoint"
        target.mkdir()
        for path in FAMILY_DIR.iterdir():
            if path.is_file():
                (target / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def test_runtime_checkpoint_family_is_valid(self):
        validate_family(FAMILY_DIR)

    def test_rejects_wrong_authority_boundary(self):
        family = self.copy_family()
        node_path = family / "checkpoint-capture.node.json"
        node = json.loads(node_path.read_text(encoding="utf-8"))
        node["authority_boundary"] = "g4_required"
        node_path.write_text(json.dumps(node, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(AssertionError):
            validate_family(family)

    def test_rejects_wrong_gate(self):
        family = self.copy_family()
        node_path = family / "resume-token-validation.node.json"
        node = json.loads(node_path.read_text(encoding="utf-8"))
        node["gates"] = ["G2_EXECUTION", "G4_MERGE"]
        node_path.write_text(json.dumps(node, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(AssertionError):
            validate_family(family)

    def test_rejects_extra_property(self):
        family = self.copy_family()
        node_path = family / "cas-write-guard.node.json"
        node = json.loads(node_path.read_text(encoding="utf-8"))
        node["runtime_engine"] = "not allowed"
        node_path.write_text(json.dumps(node, indent=2) + "\n", encoding="utf-8")

        with self.assertRaises(AssertionError):
            validate_family(family)

    def test_rejects_missing_node(self):
        family = self.copy_family()
        (family / "checkpoint-expiry-cleanup.node.json").unlink()

        with self.assertRaises(AssertionError):
            validate_family(family)


if __name__ == "__main__":
    unittest.main()
