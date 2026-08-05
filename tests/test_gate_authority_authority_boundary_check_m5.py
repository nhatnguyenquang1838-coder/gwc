"""SCRUM-188 M5 tests for the replay-safe authority boundary evaluator."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.authority_boundary_check import (
    ACTION_TO_MINIMUM_GATE,
    check_authority_boundary,
)


ROOT = Path(__file__).parents[1]
TASK = "SCRUM-188"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "7" * 40
HEAD = "8" * 40
SCOPE_HASH = "sha256:" + "a" * 64


class AuthorityBoundaryDecisionTests(unittest.TestCase):
    def scope(self, action: str, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "task_id": TASK,
            "repository": REPOSITORY,
            "base_sha": BASE,
            "head_sha": HEAD,
            "scope_hash": SCOPE_HASH,
            "authorized_actions": [action],
            "excluded_actions": [],
        }
        value.update(overrides)
        return value

    def call(
        self,
        action: str,
        *,
        current_gate: str = "G2_EXECUTION",
        current_status: str = "PASS",
        scope: dict[str, object] | None = None,
        production_scope_applicable: object = False,
        manual_g5_action: object = False,
        risk_class: object = "R2",
        policy: dict[str, object] | None = None,
        prior_decision: dict[str, object] | None = None,
        evaluated_at: object = "2026-08-05T06:30:00Z",
    ) -> dict[str, object]:
        resolved_scope = scope or self.scope(action)
        state = {
            "task_id": TASK,
            "repository": REPOSITORY,
            "current_base_sha": BASE,
            "head_sha": HEAD,
            "scope_hash": SCOPE_HASH,
            "current_gate": current_gate,
            "gate_status": current_status,
        }
        return check_authority_boundary(
            task_id=TASK,
            repository=REPOSITORY,
            requested_action=action,
            gate_state_resolution=state,
            scope_identity=resolved_scope,
            gate_policy=policy or {"action_map": ACTION_TO_MINIMUM_GATE},
            risk_class=risk_class,
            production_scope_applicable=production_scope_applicable,
            manual_g5_action=manual_g5_action,
            event_id_or_idempotency_key="event-scrum-188-001",
            prior_decision=prior_decision,
            evaluated_at=evaluated_at,
        )

    def assert_safe_flags(self, decision: dict[str, object]) -> None:
        for key in (
            "authority_granted", "execution_authority_granted", "write_authority_granted",
            "pr_authority_granted", "merge_authority_granted",
            "deployment_authority_granted", "production_authority_granted",
        ):
            self.assertIs(decision[key], False)

    def test_schema_and_authority_flags(self) -> None:
        decision = self.call("file")
        schema = json.loads((ROOT / "schemas/authority-boundary-decision.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(decision)), [])
        self.assertEqual(decision["artifact_type"], "authority-boundary-decision")
        self.assert_safe_flags(decision)

    def test_schema_requires_complete_scope_identity_bindings(self) -> None:
        decision = self.call("file")
        decision["scope_identity"].pop("head_sha")
        schema = json.loads((ROOT / "schemas/authority-boundary-decision.schema.json").read_text())
        errors = list(Draft202012Validator(schema).iter_errors(decision))
        self.assertTrue(errors)

        malformed_scope = self.scope("file")
        malformed_scope.pop("base_sha")
        result = self.call("file", scope=malformed_scope)
        self.assertEqual(result["primary_reason_code"], "AUTHORITY_INPUT_INVALID")
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(result)), [])

    def test_malformed_inputs_return_schema_valid_fail_closed_decision(self) -> None:
        result = self.call(
            "file",
            risk_class="R9",
            production_scope_applicable="yes",
            manual_g5_action=1,
            evaluated_at=123,
        )
        schema = json.loads((ROOT / "schemas/authority-boundary-decision.schema.json").read_text())
        self.assertEqual(result["primary_reason_code"], "AUTHORITY_INPUT_INVALID")
        self.assertEqual(result["decision"], "BLOCK")
        self.assert_safe_flags(result)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(result)), [])

    def test_canonical_action_mapping(self) -> None:
        expected = {
            "read": "G0_CONTEXT",
            "g1_read_only_validation": "G1_ALIGNMENT",
            "file": "G2_EXECUTION",
            "draft_pr": "G3_PR",
            "merge": "G4_MERGE",
            "post_merge_status": "G5_DEPLOY",
            "deploy": "G5_DEPLOY",
            "production_data_write": "G6_PRODUCTION_DATA",
        }
        for action, gate in expected.items():
            with self.subTest(action=action):
                self.assertEqual(ACTION_TO_MINIMUM_GATE[action], gate)

    def test_read_and_g1_validation_are_preparation_only(self) -> None:
        read = self.call("read", current_gate="G0_CONTEXT")
        self.assertEqual((read["decision"], read["approval_required"]), ("ALLOW_PREPARATION", False))
        g1 = self.call("g1_read_only_validation", current_gate="G1_ALIGNMENT")
        self.assertEqual(g1["decision"], "ALLOW_PREPARATION")
        self.assert_safe_flags(g1)

    def test_execution_and_later_gates_require_separate_approval(self) -> None:
        execution = self.call("file", current_gate="G2_EXECUTION")
        self.assertEqual((execution["decision"], execution["required_approval_gate"]), ("REQUIRE_APPROVAL", "G2_EXECUTION"))
        draft = self.call("draft_pr", current_gate="G2_EXECUTION")
        self.assertEqual(draft["required_approval_gate"], "G3_PR")
        merge = self.call("merge", current_gate="G3_PR")
        self.assertEqual(merge["required_approval_gate"], "G4_MERGE")
        self.assertIn("AUTHORITY_LATER_GATE_INHERITANCE_REJECTED", merge["reason_codes"])

    def test_insufficient_gate_is_not_authority(self) -> None:
        decision = self.call("file", current_gate="G1_ALIGNMENT")
        self.assertEqual(decision["decision"], "REQUIRE_APPROVAL")
        self.assertIn("AUTHORITY_GATE_INSUFFICIENT", decision["reason_codes"])
        self.assert_safe_flags(decision)

    def test_g5_status_is_automatic_but_manual_deploy_is_not(self) -> None:
        status = self.call("post_merge_status", current_gate="G4_MERGE")
        self.assertEqual(status["decision"], "ALLOW_PREPARATION")
        self.assertFalse(status["approval_required"])
        deploy = self.call("deploy", current_gate="G4_MERGE", manual_g5_action=True)
        self.assertEqual(deploy["decision"], "REQUIRE_APPROVAL")
        self.assertEqual(deploy["required_approval_gate"], "G5_DEPLOY")
        self.assertIn("AUTHORITY_G5_MANUAL_APPROVAL_REQUIRED", deploy["reason_codes"])

    def test_g6_is_not_applicable_without_production_scope(self) -> None:
        decision = self.call("production_data_write", production_scope_applicable=False)
        self.assertEqual((decision["decision"], decision["primary_reason_code"]), ("NOT_APPLICABLE", "AUTHORITY_G6_NOT_APPLICABLE"))
        applicable = self.call("production_data_write", production_scope_applicable=True)
        self.assertEqual(applicable["required_approval_gate"], "G6_PRODUCTION_DATA")
        self.assertEqual(applicable["decision"], "REQUIRE_APPROVAL")

    def test_unknown_excluded_and_scope_mismatch_fail_closed(self) -> None:
        unknown = self.call("invented_action")
        self.assertEqual((unknown["decision"], unknown["primary_reason_code"]), ("BLOCK", "AUTHORITY_ACTION_UNKNOWN"))
        excluded = self.call("file", scope=self.scope("file", excluded_actions=["file"]))
        self.assertEqual((excluded["decision"], excluded["prohibited"]), ("BLOCK", True))
        mismatch = self.call("file", scope=self.scope("file", task_id="OTHER-1"))
        self.assertEqual(mismatch["primary_reason_code"], "AUTHORITY_SCOPE_MISMATCH")

    def test_policy_cannot_remap_canonical_minimum_gate(self) -> None:
        remapped = dict(ACTION_TO_MINIMUM_GATE)
        remapped["file"] = "G0_CONTEXT"
        decision = self.call("file", policy={"action_map": remapped})
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertEqual(decision["minimum_gate"], "G2_EXECUTION")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_POLICY_MISMATCH")

    def test_prohibited_history_actions_are_never_authorized(self) -> None:
        decision = self.call("force_push", scope=self.scope("force_push"))
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_ACTION_PROHIBITED")
        self.assertTrue(decision["prohibited"])

    def test_replay_is_deterministic_and_conflicts_fail_closed(self) -> None:
        first = self.call("file", evaluated_at="2026-08-05T00:00:00Z")
        second = self.call("file", evaluated_at="2026-08-06T00:00:00Z")
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        replay = self.call("file", prior_decision=first)
        self.assertEqual(replay["replay_status"], "IDEMPOTENT_REPLAY")
        changed = copy.deepcopy(first)
        changed["requested_action"] = "merge"
        conflict = self.call("file", prior_decision=changed)
        self.assertEqual((conflict["decision"], conflict["primary_reason_code"]), ("BLOCK", "AUTHORITY_REPLAY_CONFLICT"))

    def test_failed_gate_blocks_and_authority_flags_stay_false(self) -> None:
        decision = self.call("file", current_status="FAILED")
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertIn("AUTHORITY_GATE_INSUFFICIENT", decision["reason_codes"])
        self.assert_safe_flags(decision)


if __name__ == "__main__":
    unittest.main()
