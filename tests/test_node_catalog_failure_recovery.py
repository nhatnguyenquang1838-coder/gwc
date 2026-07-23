import json
import tempfile
import unittest
from pathlib import Path

from tools.node_architect.validate_node_catalog_failure_recovery import validate_family

FAMILY_DIR = Path("core/node-architect/node-catalog/failure_recovery")
MATRIX = Path("core/node-architect/failure-simulation-matrix.json")


class FailureRecoveryNodeCatalogTest(unittest.TestCase):
    def test_family_has_exactly_nine_nodes(self):
        self.assertEqual(len(list(FAMILY_DIR.glob("*.node.json"))), 9)

    def test_required_semantics_and_matrix_pass(self):
        validate_family(FAMILY_DIR, MATRIX)

    def test_ids_match_filenames(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["node_id"], "failure_recovery." + path.name.removesuffix(".node.json"))

    def test_g5_is_descriptive_and_separately_gated(self):
        g5 = []
        for path in FAMILY_DIR.glob("*.node.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["authority_boundary"] == "g5_required":
                g5.append(payload)
        self.assertEqual(len(g5), 1)
        self.assertEqual(g5[0]["gates"], ["G5_DEPLOY"])

    def test_no_g4_or_g6_gate(self):
        for path in FAMILY_DIR.glob("*.node.json"):
            gates = set(json.loads(path.read_text(encoding="utf-8"))["gates"])
            self.assertFalse(gates & {"G4_MERGE", "G6_PRODUCTION_DATA"})

    def test_rejects_tenth_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for path in FAMILY_DIR.iterdir():
                (directory / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            (directory / "extra.node.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(directory, MATRIX)

    def test_rejects_authority_gate_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for path in FAMILY_DIR.iterdir():
                if path.is_file():
                    (directory / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            target = directory / "timeout-recovery.node.json"
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["gates"] = ["G5_DEPLOY"]
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validate_family(directory, MATRIX)


if __name__ == "__main__":
    unittest.main()
