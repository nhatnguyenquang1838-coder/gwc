"""SCRUM-373 NA81 maturity tests for the catalog-cardinality-readiness node.

Current-task requirement -> code -> test evidence map (exact SHA delivery).

Older M4 tests remain compatibility coverage. These tests bind the current
SCRUM-373 AC: exact 81-node inventory from canonical repository/catalog
evidence, deterministic digest, and DETECTION of wrong family membership
(a node placed under the wrong family blocks), duplicate / missing / extra
IDs, version/cardinality drift, and replay/digest stability (No auto-close
rule: Jira count alone is never readiness proof).
"""
from __future__ import annotations

import unittest

from tools.node_architect.catalog_cardinality_readiness import (
    decide_catalog_cardinality_readiness,
)


TASK = "SCRUM-373"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-373-na81-20260810"
BASE = "a" * 40
HEAD = "b" * 40
CATALOG_REV = "sha256:" + "a" * 64
EXPECTED_REV = "sha256:" + "a" * 64

FAMILIES = ["intake_context", "gate_authority", "repo_delivery", "runtime_checkpoint",
            "validation_quality", "sync_projection", "package_export",
            "failure_recovery", "scale_control"]

EXPECTED_FAMILY_NODE_IDS = {
    fam: [f"{fam}.node-{i}" for i in range(1, 10)] for fam in FAMILIES
}
EXPECTED_NODE_IDS = [nid for nids in EXPECTED_FAMILY_NODE_IDS.values() for nid in nids]


def base_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        repository=REPO,
        branch=BRANCH,
        base_sha=BASE,
        head_sha=HEAD,
        catalog_revision=CATALOG_REV,
        expected_revision=EXPECTED_REV,
        family_node_ids={fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()},
        expected_node_ids=list(EXPECTED_NODE_IDS),
        expected_family_node_ids={fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()},
    )
    data.update(overrides)
    return data


class ExactInventoryReadinessTests(unittest.TestCase):
    def test_exact_81_node_inventory_ready(self):
        d = decide_catalog_cardinality_readiness(**base_kwargs())
        self.assertTrue(d["readiness_passed"])
        self.assertEqual(d["outcome"], "READY")
        self.assertEqual(d["observed_unique_node_count"], 81)
        self.assertEqual(d["reason_code"], "EXACT_CATALOG_CARDINALITY_CONFIRMED")
        # Readiness never grants scale/audit authority.
        self.assertFalse(d["scale_authority_granted"])
        self.assertFalse(d["audit_authority_granted"])

    def test_digest_is_stable_replay(self):
        d1 = decide_catalog_cardinality_readiness(**base_kwargs())
        d2 = decide_catalog_cardinality_readiness(**base_kwargs())
        self.assertEqual(d1["decision_digest"], d2["decision_digest"])


class WrongFamilyMembershipTests(unittest.TestCase):
    def test_node_under_wrong_family_blocks(self):
        # Swap two nodes between families: both families keep size 9, so the
        # only violation is membership (a node under the wrong family).
        bad = {fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()}
        sc_node = bad["scale_control"].pop()
        ic_node = bad["intake_context"].pop()
        bad["scale_control"].append(ic_node)
        bad["intake_context"].append(sc_node)
        d = decide_catalog_cardinality_readiness(**base_kwargs(family_node_ids=bad))
        self.assertFalse(d["readiness_passed"])
        self.assertEqual(d["reason_code"], "FAMILY_MEMBERSHIP_MISMATCH")
        self.assertTrue(d["family_membership_violations"])

    def test_no_membership_check_when_expected_map_absent_backward_compatible(self):
        # Older callers omit expected_family_node_ids; readiness still computes.
        d = decide_catalog_cardinality_readiness(
            **base_kwargs(expected_family_node_ids=None)
        )
        self.assertTrue(d["readiness_passed"])


class MissingDuplicateExtraTests(unittest.TestCase):
    def test_missing_node_blocks(self):
        # Drop one observed node from its family; total observed count drops to 80.
        fams = {fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()}
        fams["intake_context"].pop()
        d = decide_catalog_cardinality_readiness(**base_kwargs(family_node_ids=fams))
        self.assertFalse(d["readiness_passed"])
        self.assertIn("MISMATCH", d["reason_code"])

    def test_duplicate_node_blocks(self):
        # Replace one observed node with a duplicate of another: family stays
        # size 9, but one node id now appears twice -> duplicate.
        fams = {fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()}
        fams["intake_context"].pop()  # size -> 8
        fams["intake_context"].append(EXPECTED_NODE_IDS[0])  # duplicate of existing
        d = decide_catalog_cardinality_readiness(**base_kwargs(family_node_ids=fams))
        self.assertFalse(d["readiness_passed"])
        self.assertEqual(d["reason_code"], "DUPLICATE_NODE_ID")

    def test_extra_node_blocks(self):
        # Replace one observed node with a brand-new node not in the expected
        # catalog: the extra id is surfaced and readiness is blocked.
        fams = {fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()}
        fams["intake_context"].pop()  # size -> 8
        fams["intake_context"].append("intake_context.node-99")  # extra
        d = decide_catalog_cardinality_readiness(**base_kwargs(family_node_ids=fams))
        self.assertFalse(d["readiness_passed"])
        self.assertIn("intake_context.node-99", d["unexpected_node_ids"])


class CardinalityDriftTests(unittest.TestCase):
    def test_catalog_revision_mismatch_blocks(self):
        d = decide_catalog_cardinality_readiness(
            **base_kwargs(catalog_revision="sha256:" + "b" * 64)
        )
        self.assertFalse(d["readiness_passed"])
        self.assertEqual(d["reason_code"], "CATALOG_REVISION_MISMATCH")

    def test_family_count_drift_blocks(self):
        fams = {fam: list(nids) for fam, nids in EXPECTED_FAMILY_NODE_IDS.items()}
        fams["ghost_family"] = [f"ghost_family.node-{i}" for i in range(1, 10)]
        d = decide_catalog_cardinality_readiness(**base_kwargs(family_node_ids=fams))
        self.assertFalse(d["readiness_passed"])
        self.assertEqual(d["reason_code"], "FAMILY_COUNT_MISMATCH")


if __name__ == "__main__":
    unittest.main()
