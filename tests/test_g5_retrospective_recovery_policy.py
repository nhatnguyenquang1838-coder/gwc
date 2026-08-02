from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "validate_g5_retrospective_recovery.py"
SPEC = importlib.util.spec_from_file_location("validate_g5_retrospective_recovery", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


VALID_COMMENT = """RETROSPECTIVE G5 RECOVERY EVIDENCE

This is a retrospective evidence-recovery comment for PR #175.

Original human G4 approval was provided in ChatGPT before merge:

APPROVE G4 APPROVE_G4_FL-MAT-F3-B3_20260802 45f3ac5a89a6a12c 2026-08-02T11:00:00Z

Bound PR: #175
Approved head: 45f3ac5a89a6a12cd4b0916cfaa3b5e3b972238c
Merge commit: 84de624b223d093de446b9d88bcfdf35efd89e03
Failed post-merge run: 30740337540

This comment is not backdated G4 authority. It does not authorize another merge, manual G5 action, deployment, release, production data/config change, migration, or G6 action.
"""


def candidate(**overrides):
    base = {
        "repository": "nhatnguyenquang1838-coder/gwc",
        "comment_body": VALID_COMMENT,
        "comment_id": 5156788304,
        "comment_url": "https://github.com/nhatnguyenquang1838-coder/gwc/pull/175#issuecomment-5156788304",
        "comment_author": "nhatnguyenquang1838-coder",
        "comment_author_permission": "write",
        "pr_number": 175,
        "pr_merged": True,
        "pr_head_sha": "45f3ac5a89a6a12cd4b0916cfaa3b5e3b972238c",
        "merge_commit_sha": "84de624b223d093de446b9d88bcfdf35efd89e03",
        "merged_at": "2026-08-02T08:43:37Z",
        "new_merge_authority_inferred": False,
        "manual_g5_action_authorized": False,
        "g6_authorized": False,
    }
    base.update(overrides)
    return base


class RetrospectiveG5RecoveryPolicyTest(unittest.TestCase):
    def test_accepts_bounded_recovery_comment(self):
        artifact = validator.validate(candidate())
        self.assertTrue(artifact["recovery_valid"])
        self.assertEqual(artifact["recovery_mode"], "retrospective")
        self.assertEqual(artifact["gate"], "G5_STATUS_VERIFY")
        self.assertFalse(artifact["normal_g4_authority_minted"])
        self.assertFalse(artifact["manual_g5_action_authorized"])
        self.assertFalse(artifact["g6_authorized"])

    def test_rejects_unmerged_pr(self):
        with self.assertRaisesRegex(ValueError, "already be merged"):
            validator.validate(candidate(pr_merged=False))

    def test_rejects_head_mismatch(self):
        with self.assertRaisesRegex(ValueError, "Approved head"):
            validator.validate(candidate(pr_head_sha="0" * 40))

    def test_rejects_new_authority(self):
        with self.assertRaisesRegex(ValueError, "new merge authority"):
            validator.validate(candidate(new_merge_authority_inferred=True))

    def test_rejects_expired_before_merge(self):
        bad = VALID_COMMENT.replace("2026-08-02T11:00:00Z", "2026-08-02T08:00:00Z")
        with self.assertRaisesRegex(ValueError, "expired before the merge"):
            validator.validate(candidate(comment_body=bad))


if __name__ == "__main__":
    unittest.main()
