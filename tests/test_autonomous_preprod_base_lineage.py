import unittest

from tools.node_architect.materialize_autonomous_preprod_base_lineage import validate_base_lineage


class AutonomousPreprodBaseLineageTests(unittest.TestCase):
    def setUp(self):
        self.anchor = "a" * 40
        self.merge1 = "b" * 40
        self.merge2 = "c" * 40
        self.step1 = {
            "run_id": "na81-run",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "task_id": "SCRUM-302",
            "previous_base_sha": self.anchor,
            "merged_head_sha": "1" * 40,
            "merge_commit_sha": self.merge1,
            "g5_classification": "success",
            "trusted_merge_proof": True,
            "trusted_g5_evidence": True,
        }
        self.step2 = {
            "run_id": "na81-run",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "task_id": "SCRUM-303",
            "previous_base_sha": self.merge1,
            "merged_head_sha": "2" * 40,
            "merge_commit_sha": self.merge2,
            "g5_classification": "not_required",
            "trusted_merge_proof": True,
            "trusted_g5_evidence": False,
        }

    def check(self, current=None, steps=None):
        return validate_base_lineage(
            run_id="na81-run",
            repository="nhatnguyenquang1838-coder/gwc",
            anchor_base_sha=self.anchor,
            current_base_sha=current or self.merge2,
            allowed_task_ids=["SCRUM-302", "SCRUM-303", "SCRUM-304"],
            steps=steps if steps is not None else [self.step1, self.step2],
        )

    def test_exact_trusted_descendant_chain_passes(self):
        result = self.check()
        self.assertEqual("PASS", result["outcome"])
        self.assertEqual("BASE_LINEAGE_TRUSTED", result["state"])

    def test_anchor_itself_passes_with_empty_chain(self):
        self.assertEqual("PASS", self.check(current=self.anchor, steps=[])["outcome"])

    def test_arbitrary_preprod_drift_fails_closed(self):
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED", self.check(current="d" * 40, steps=[self.step1])["reason_codes"])

    def test_g5_pending_does_not_block_trusted_merge_lineage(self):
        step1 = dict(self.step1, g5_classification="CI_PENDING", trusted_g5_evidence=False)
        self.assertEqual("PASS", self.check(steps=[step1, self.step2])["outcome"])

    def test_missing_merge_proof_still_fails_closed(self):
        step1 = dict(self.step1, trusted_merge_proof=False)
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED", self.check(steps=[step1, self.step2])["reason_codes"])

    def test_foreign_run_fails_closed(self):
        step1 = dict(self.step1, run_id="other-run")
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_FOREIGN_RUN", self.check(steps=[step1, self.step2])["reason_codes"])


if __name__ == "__main__":
    unittest.main()
