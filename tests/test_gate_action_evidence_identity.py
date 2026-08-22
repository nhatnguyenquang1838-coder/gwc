from __future__ import annotations

import unittest

from tools.gate_effect_authority import validate_evidence_identity

REPO = "nhatnguyenquang1838-coder/gwc"


def _identity(**overrides):
    value = {
        "repository": REPO,
        "event_id_or_idempotency_key": "evt-554",
        "action": "merge_approved_pr",
        "branch": "chatgpt/scrum-554",
        "pr_number": 468,
        "sha": "a" * 40,
        "sha_kind": "merge_commit",
        "workflow_run_id": "32090055388",
        "gate": "G4_MERGE",
        "node": "G4/merge",
    }
    value.update(overrides)
    return value


class EvidenceIdentityTests(unittest.TestCase):
    def test_exact_identity_passes(self):
        expected = _identity()
        self.assertEqual(validate_evidence_identity(expected, dict(expected)), [])

    def test_pr_head_evidence_cannot_satisfy_merge_sha(self):
        expected = _identity()
        observed = _identity(sha="b" * 40, sha_kind="pr_head")
        errors = validate_evidence_identity(expected, observed)
        self.assertIn("EVIDENCE_SHA_MISMATCH", errors)
        self.assertIn("EVIDENCE_SHA_KIND_MISMATCH", errors)

    def test_historical_success_different_sha_event_gate_is_rejected(self):
        expected = _identity()
        observed = _identity(
            sha="c" * 40,
            event_id_or_idempotency_key="evt-old",
            gate="G3_PR",
            node="G3/review",
        )
        errors = validate_evidence_identity(expected, observed)
        self.assertIn("EVIDENCE_SHA_MISMATCH", errors)
        self.assertIn("EVIDENCE_EVENT_MISMATCH", errors)
        self.assertIn("EVIDENCE_GATE_MISMATCH", errors)
        self.assertIn("EVIDENCE_NODE_MISMATCH", errors)

    def test_workflow_run_identity_is_exact(self):
        errors = validate_evidence_identity(_identity(), _identity(workflow_run_id="999"))
        self.assertEqual(errors, ["EVIDENCE_WORKFLOW_RUN_MISMATCH"])


if __name__ == "__main__":
    unittest.main()
