from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/g4-g5-evidence.yml").read_text(encoding="utf-8")


class G4GateWorkflowSemanticsTests(unittest.TestCase):
    def test_unrelated_pr_comments_do_not_run_g4_authority(self):
        self.assertIn("startsWith(github.event.comment.body, 'APPROVE G4 ')", WORKFLOW)
        self.assertIn("startsWith(github.event.comment.body, 'APPROVE G4_MERGE ')", WORKFLOW)
        self.assertNotIn("Fail loudly when a PR comment is not a valid G4 approval", WORKFLOW)

    def test_post_merge_missing_receipt_is_not_retroactive_failure(self):
        self.assertIn("Post-merge evidence is observational", WORKFLOW)
        self.assertIn("core.setOutput('available', 'false')", WORKFLOW)
        self.assertIn("Post-merge evidence is not an enforcement gate", WORKFLOW)
        self.assertNotIn("core.setFailed('Merged PR has no trusted G4 authority receipt.')", WORKFLOW)

    def test_proof_artifact_only_emits_when_authority_evidence_exists(self):
        self.assertGreaterEqual(WORKFLOW.count("if: steps.proof.outputs.available == 'true'"), 2)
        self.assertIn("core.setOutput('available', 'true')", WORKFLOW)

    def test_invalid_existing_receipt_still_fails_closed(self):
        self.assertIn("G4 authority receipt marker is malformed", WORKFLOW)
        self.assertIn("Original G4 authority comment does not match the sanitized receipt", WORKFLOW)
        self.assertIn("Approved head ${parsed[2]} does not match merged head ${pr.head.sha}", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
