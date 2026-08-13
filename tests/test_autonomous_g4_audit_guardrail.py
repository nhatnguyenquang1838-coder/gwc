import unittest

from tools.node_architect.audit_guardrail import evaluate_g4_preprod_audit, validate_audit_receipt

SHA = "a" * 40
BASE = "b" * 40


class AutonomousG4AuditGuardrailTests(unittest.TestCase):
    def evidence(self, **overrides):
        data = {
            "task_id": "SCRUM-300",
            "repository": "owner/gwc",
            "pr_number": 42,
            "target_branch": "pre-prod",
            "base_sha": BASE,
            "head_sha": SHA,
            "g3_head_sha": SHA,
            "dag_authority_valid": True,
            "parent_authority_valid": True,
            "g0_ready": True,
            "g1_pass": True,
            "derived_g2_valid": True,
            "managed_evidence_current": True,
            "exact_head_ci_success": True,
            "required_checks_terminal_success": True,
            "g3_independent": True,
            "g3_conclusion": "pass",
            "scope_valid": True,
            "risk_valid": True,
            "actions_valid": True,
            "standing_g4_applicable": True,
            "auditor_id": "agent-audit-1",
            "implementer_id": "executor-1",
            "auditor_context_id": "audit-context-1",
            "implementer_context_id": "executor-context-1",
            "audit_write_actions": [],
            "dag_digest": "sha256:" + "1" * 64,
            "parent_authority_ref": "AR-1",
            "g0_ref": "G0",
            "g1_ref": "G1",
            "g2_ref": "G2",
            "g3_ref": "G3",
            "ci_ref": "CI",
            "managed_evidence_digest": "sha256:" + "2" * 64,
            "standing_g4_ref": "G4-STANDING",
        }
        data.update(overrides)
        return data

    def test_pass_is_deterministic_and_has_no_merge_authority(self):
        one = evaluate_g4_preprod_audit(self.evidence())
        two = evaluate_g4_preprod_audit(self.evidence())
        self.assertEqual(one["audit_outcome"], "PASS")
        self.assertEqual(one["receipt_digest"], two["receipt_digest"])
        self.assertFalse(one["merge_authority"])
        self.assertEqual(one["write_actions"], [])

    def test_same_implementer_is_blocked(self):
        result = evaluate_g4_preprod_audit(self.evidence(auditor_id="executor-1"))
        self.assertEqual(result["audit_outcome"], "BLOCK")
        self.assertIn("AUDIT_NOT_INDEPENDENT", result["blockers"])

    def test_same_context_is_blocked(self):
        result = evaluate_g4_preprod_audit(self.evidence(auditor_context_id="executor-context-1"))
        self.assertEqual(result["audit_outcome"], "BLOCK")
        self.assertIn("AUDIT_CONTEXT_NOT_INDEPENDENT", result["blockers"])

    def test_g3_head_drift_is_blocked(self):
        result = evaluate_g4_preprod_audit(self.evidence(g3_head_sha="c" * 40))
        self.assertEqual(result["audit_outcome"], "BLOCK")
        self.assertIn("AUDIT_G3_HEAD_STALE", result["blockers"])

    def test_auditor_write_action_is_blocked(self):
        result = evaluate_g4_preprod_audit(self.evidence(audit_write_actions=["comment_pr"]))
        self.assertEqual(result["audit_outcome"], "BLOCK")
        self.assertIn("AUDIT_WRITE_ACTION_FORBIDDEN", result["blockers"])

    def test_receipt_stales_on_head_change(self):
        receipt = evaluate_g4_preprod_audit(self.evidence())
        result = validate_audit_receipt(receipt, expected_head_sha="d" * 40)
        self.assertEqual(result["outcome"], "BLOCK")
        self.assertEqual(result["reason_code"], "AUDIT_RECEIPT_STALE_HEAD")


if __name__ == "__main__":
    unittest.main()
