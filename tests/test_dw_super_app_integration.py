import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.validate_dw_super_app_integration as integration_validator


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "core/integration/dw-super-app-integration-contract.json"


class DwSuperAppIntegrationContractTests(unittest.TestCase):
    def test_contract_is_valid(self):
        report = integration_validator.validate_contract(ROOT)
        self.assertTrue(report["valid"], report["issues"])

    def load_contract(self) -> dict:
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_artifact_class_ids_are_unique_and_complete(self):
        contract = self.load_contract()
        ids = [item["id"] for item in contract["artifact_classes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 12)

    def test_projection_cannot_become_authority(self):
        contract = self.load_contract()
        for item in contract["integrations"]:
            if item["id"] == "slack":
                item["authority"] = "canonical"
        path = ROOT / ".tmp-scrum-116-contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        try:
            with patch.object(integration_validator, "CONTRACT", Path(path.name)):
                report = integration_validator.validate_contract(ROOT)
            self.assertFalse(report["valid"])
            self.assertTrue(any("slack must be a projection" in issue for issue in report["issues"]))
        finally:
            path.unlink(missing_ok=True)

    def test_collision_example_is_fail_closed(self):
        contract = self.load_contract()
        rejected = [item for item in contract["provenance_examples"] if not item["resolves"]]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["failure_code"], "STALE_LEASE_OR_FENCING")

    def test_missing_compatibility_mode_fails(self):
        contract = self.load_contract()
        self.assertEqual(set(contract["compatibility_modes"]), {"submodule", "power-dist", "immutable-release", "offline-zip"})


if __name__ == "__main__":
    unittest.main()
