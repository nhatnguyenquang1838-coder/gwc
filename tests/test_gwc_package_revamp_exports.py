from __future__ import annotations

from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "projects" / "gwc" / "package.yaml"


class GwcPackageRevampExportTests(unittest.TestCase):
    def load_package(self):
        with PACKAGE.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def test_package_version_bumped_for_consumer_export(self):
        package = self.load_package()
        self.assertEqual(package["package_version"], "1.17.0")

    def test_revamp_export_entries_are_declared(self):
        package = self.load_package()
        by_id = {entry["id"]: entry for entry in package["instructions"]}
        required_ids = {
            "revamp-upgrade-gwc-workflow",
            "gwc-fastlane-bootstrap-workflow",
            "consumer-package-export-rule",
            "package-export-manifest-schema",
            "consumer-package-export-tool",
            "kiro-local-agent-execution-package",
            "ds-admin-tc-sync-protocol",
        }
        self.assertTrue(required_ids.issubset(by_id.keys()))

    def test_package_has_no_duplicate_targets(self):
        package = self.load_package()
        targets = [entry["target"] for entry in package["instructions"]]
        self.assertEqual(len(targets), len(set(targets)))


if __name__ == "__main__":
    unittest.main()
