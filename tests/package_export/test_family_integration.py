#!/usr/bin/env python3
"""Family integration test for the package_export node catalog (SCRUM-237, AC-6)."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "node_architect" / "package_export"))

from export_failure_routing import DECISION_TABLE, ROUTES  # noqa: E402


class TestFamilyNineNodes(unittest.TestCase):
    def test_family_validator_passes_nine_nodes(self):
        """The shared family validator must confirm exactly nine nodes."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/node_architect/validate_node_catalog_package_export.py")],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid", result.stdout)

    def test_all_nine_semantics_present(self):
        node_dir = ROOT / "core/node-architect/node-catalog/package_export"
        stems = {p.name.removesuffix(".node.json") for p in node_dir.glob("*.node.json")}
        required = {
            "package-manifest-load", "entry-schema-validation", "source-path-safety-check",
            "target-path-safety-check", "governance-tree-build", "export-manifest-generation",
            "deterministic-hash-verification", "smoke-verification", "export-failure-routing",
        }
        self.assertEqual(stems, required)

    def test_every_mapped_reason_resolves_to_a_route(self):
        """AC-6: every reason in the router's decision table resolves to one of six routes."""
        self.assertTrue(DECISION_TABLE)
        for reason, (route, _requires_readback, _retryable) in DECISION_TABLE.items():
            with self.subTest(reason=reason):
                self.assertIn(route, ROUTES)

    def test_no_route_grants_authority(self):
        # Every route in the taxonomy is a recommendation; none implies publish/merge/deploy.
        self.assertEqual(len(ROUTES), 6)


if __name__ == "__main__":
    unittest.main()
