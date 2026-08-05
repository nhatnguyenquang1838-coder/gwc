"""Tests for the shared gate_authority node catalog owner (SCRUM-192)."""
from __future__ import annotations

import unittest

from tools.node_architect.validate_node_catalog_gate_authority import (
    validate_node_catalog_gate_authority,
)


class TestNodeCatalog(unittest.TestCase):
    def test_catalog_complete(self):
        rep = validate_node_catalog_gate_authority()
        self.assertEqual(rep["summary"], "OK")
        self.assertTrue(rep["all_present"])
        self.assertEqual(set(rep["nodes"].keys()),
                         {"SCRUM-185", "SCRUM-186", "SCRUM-190", "SCRUM-191", "SCRUM-192"})

    def test_every_node_has_required_callable(self):
        rep = validate_node_catalog_gate_authority()
        for node_id, node in rep["nodes"].items():
            self.assertTrue(node["present"], node_id)
            self.assertEqual(node["missing"], [], node_id)

    def test_pure_no_side_effect(self):
        a = validate_node_catalog_gate_authority()
        b = validate_node_catalog_gate_authority()
        self.assertEqual(a["summary"], b["summary"])


if __name__ == "__main__":
    unittest.main()
