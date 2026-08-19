from __future__ import annotations

import unittest

from tools.node_architect.blocker_severity_classification import (
    BLOCKED,
    PASS,
    UNMATCHED,
    classify_blocker_severity,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "auto/SCRUM-340-na81-recert-20260814-r10"


def evidence(findings=None, **overrides) -> dict:
    value = {
        "task_id": "SCRUM-340",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "g3-graph-20260814",
        "idempotency_key": "scrum-340-bsc-1",
        "pr_number": 275,
        "findings": findings if findings is not None else [],
    }
    value.update(overrides)
    return value


class BlockerSeverityClassificationM5Tests(unittest.TestCase):
    # --- 1. known severity classes --------------------------------------
    def test_known_low_severity_classifies_pass(self):
        # LOW / MEDIUM are advisory and below the waivable threshold -> PASS.
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_ADVISORY_STYLE"}]))
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["CLASSIFIED"])
        self.assertFalse(result["merge_authority_granted"])

    def test_known_high_severity_blocks(self):
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_SCOPE_DRIFT"}]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("BLOCKER_PRESENT", result["reason_codes"])
        self.assertEqual(result["classification"][0]["severity"], "HIGH")

    # --- 2. unmatched finding -------------------------------------------
    def test_unmatched_finding_blocks_fail_closed(self):
        # A finding with no matching stable rule ID must never be silently
        # waived: it fails closed to BLOCKED.
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_UNKNOWN_X"}]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["reason_codes"], ["UNMATCHED"])
        self.assertFalse(result["merge_authority_granted"])

    def test_malformed_finding_blocks(self):
        result = classify_blocker_severity(evidence(findings=["not-a-mapping"]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("UNMATCHED", result["reason_codes"])

    # --- 3. conflicting rules -------------------------------------------
    def test_conflicting_rules_block(self):
        # One finding matched by two rules that resolve to different
        # severities is ambiguous and must fail closed.
        result = classify_blocker_severity(
            evidence(findings=[{"rule_ids": ["LEAK_SCOPE_DRIFT", "LEAK_STALE_REVIEW"]}])
        )
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("CONFLICTING_RULES", result["reason_codes"])

    # --- 4. authority / evidence / data-integrity boundary --------------
    def test_authority_boundary_never_waived(self):
        # Authority findings are terminal regardless of declared severity and
        # must block -- never silently waived.
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_AUTHORITY_BOUNDARY"}]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("BLOCKER_PRESENT", result["reason_codes"])
        self.assertEqual(result["classification"][0]["classification"], "BLOCKING")

    def test_evidence_boundary_never_waived(self):
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_EVIDENCE_PROVENANCE"}]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("BLOCKER_PRESENT", result["reason_codes"])

    def test_data_integrity_boundary_never_waived(self):
        result = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_DATA_INTEGRITY"}]))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("BLOCKER_PRESENT", result["reason_codes"])

    def test_closed_findings_do_not_block(self):
        # Resolved / closed findings are not counted against classification.
        result = classify_blocker_severity(
            evidence(
                findings=[
                    {"rule_id": "LEAK_AUTHORITY_BOUNDARY", "status": "CLOSED"},
                    {"rule_id": "LEAK_SCOPE_DRIFT", "resolved": True},
                ]
            )
        )
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["CLASSIFIED"])

    # --- 5. policy drift ------------------------------------------------
    def test_policy_drift_blocks(self):
        # A mismatched policy_version must fail closed with POLICY_DRIFT.
        result = classify_blocker_severity(evidence(findings=[], policy_version="bogus-1"), policy_version="bogus-1")
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["reason_codes"], ["POLICY_DRIFT"])

    def test_descriptor_identity_drift_blocks(self):
        # A descriptor whose node identity / authority boundary drifted fails
        # closed (read-only guard; descriptor never mutated).
        result = classify_blocker_severity(evidence(findings=[]), descriptor={"node_id": "wrong.node", "authority_boundary": "g3_required"})
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("POLICY_DRIFT", result["reason_codes"])

    # --- 6. replay determinism ------------------------------------------
    def test_replay_is_deterministic(self):
        cache: dict = {}
        first = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_SCOPE_DRIFT"}]), replay_cache=cache)
        second = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_SCOPE_DRIFT"}]), replay_cache=cache)
        self.assertEqual(first["classification_digest"], second["classification_digest"])
        self.assertTrue(second["replayed"])
        # Determinism without cache too.
        third = classify_blocker_severity(evidence(findings=[{"rule_id": "LEAK_SCOPE_DRIFT"}]))
        self.assertEqual(first["classification_digest"], third["classification_digest"])


if __name__ == "__main__":
    unittest.main()
