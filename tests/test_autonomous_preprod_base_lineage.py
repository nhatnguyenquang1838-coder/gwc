import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.node_architect.materialize_autonomous_preprod_base_lineage import (
    canonical_digest,
    validate_base_lineage,
)


ROOT = Path(__file__).resolve().parents[1]


class AutonomousPreprodBaseLineageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((ROOT / "schemas/autonomous-preprod-base-lineage-proof.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        cls.schema_validator = Draft202012Validator(schema)

    def setUp(self):
        self.anchor = "a" * 40
        self.current = "d" * 40
        self.policy_digest = "sha256:" + "1" * 64
        self.readback = {
            "source": "github_compare",
            "comparison_status": "ahead",
            "merge_base_sha": self.anchor,
            "authority_policy_anchor_digest": self.policy_digest,
            "authority_policy_current_digest": self.policy_digest,
            "trusted_repository_readback": True,
        }
        self.step = {
            "run_id": "na81-run",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "task_id": "SCRUM-302",
            "previous_base_sha": "b" * 40,
            "merged_head_sha": "2" * 40,
            "merge_commit_sha": "c" * 40,
            "g5_classification": "not_required",
            "trusted_merge_proof": True,
            "trusted_g5_evidence": False,
        }

    def check(self, *, current=None, readback="DEFAULT", steps=None):
        actual_readback = self.readback if readback == "DEFAULT" else readback
        return validate_base_lineage(
            run_id="na81-run",
            repository="nhatnguyenquang1838-coder/gwc",
            anchor_base_sha=self.anchor,
            current_base_sha=current or self.current,
            allowed_task_ids=["SCRUM-302", "SCRUM-303", "SCRUM-304"],
            repository_readback=actual_readback,
            steps=[] if steps is None else steps,
        )

    def assert_schema(self, result):
        errors = list(self.schema_validator.iter_errors(result["proof"]))
        self.assertEqual([], [error.message for error in errors])

    def test_trusted_descendant_compare_passes_without_enumerating_every_commit(self):
        result = self.check()
        self.assertEqual("PASS", result["outcome"])
        self.assertEqual("BASE_LINEAGE_TRUSTED", result["state"])
        self.assert_schema(result)

    def test_optional_task_merge_audit_step_does_not_need_to_cover_every_descendant_commit(self):
        result = self.check(steps=[self.step])
        self.assertEqual("PASS", result["outcome"])
        self.assertEqual(["SCRUM-302"], [row["task_id"] for row in result["proof"]["steps"]])
        self.assert_schema(result)

    def test_anchor_itself_passes_without_repository_readback(self):
        result = self.check(current=self.anchor, readback=None)
        self.assertEqual("PASS", result["outcome"])
        self.assertIsNone(result["proof"]["repository_readback"])
        self.assert_schema(result)

    def test_non_descendant_compare_fails_closed(self):
        result = self.check(readback=dict(self.readback, comparison_status="diverged"))
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_INVALID", result["reason_codes"])

    def test_wrong_merge_base_fails_closed(self):
        result = self.check(readback=dict(self.readback, merge_base_sha="e" * 40))
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_INVALID", result["reason_codes"])

    def test_untrusted_repository_readback_fails_closed(self):
        result = self.check(readback=dict(self.readback, trusted_repository_readback=False))
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED", result["reason_codes"])

    def test_machine_authority_policy_drift_requires_reauthorization(self):
        result = self.check(readback=dict(
            self.readback,
            authority_policy_current_digest="sha256:" + "2" * 64,
        ))
        self.assertIn("AUTONOMOUS_AUTHORITY_POLICY_DRIFT", result["reason_codes"])

    def test_foreign_run_audit_step_fails_closed(self):
        result = self.check(steps=[dict(self.step, run_id="other-run")])
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_FOREIGN_RUN", result["reason_codes"])

    def test_missing_task_merge_proof_fails_closed_when_step_is_supplied(self):
        result = self.check(steps=[dict(self.step, trusted_merge_proof=False)])
        self.assertIn("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED", result["reason_codes"])

    def test_g5_metadata_does_not_control_lineage_authority(self):
        result = self.check(steps=[dict(
            self.step,
            g5_classification="CI_PENDING",
            trusted_g5_evidence=False,
        )])
        self.assertEqual("PASS", result["outcome"])

    def test_proof_digest_replays_deterministically(self):
        first = self.check()["proof"]
        second = self.check()["proof"]
        self.assertEqual(first["lineage_digest"], second["lineage_digest"])
        unsigned = dict(first)
        unsigned.pop("lineage_digest")
        self.assertEqual(canonical_digest(unsigned), first["lineage_digest"])


if __name__ == "__main__":
    unittest.main()
