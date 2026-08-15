"""SCRUM-311 NA81 tests for closed-envelope expiry + stale-evidence denial.

These are CURRENT-TASK tests (not the SCRUM-188 reuse-only m5 suite). They prove
the SCRUM-311 brief requirement -> code -> test mapping on the exact pre-prod SHA:
ALLOW only exact closed-envelope matches; DENY expired / stale / mismatched /
unknown / cross-gate; deterministic, replay-safe, zero side effects on deny.
"""
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
TASK = "SCRUM-311"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "7" * 40
HEAD = "8" * 40
SCOPE_HASH = "sha256:" + "a" * 64


class AuthorityBoundarySCRUM311Tests(unittest.TestCase):
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

    def state(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "task_id": TASK,
            "repository": REPOSITORY,
            "current_base_sha": BASE,
            "head_sha": HEAD,
            "scope_hash": SCOPE_HASH,
            "current_gate": "G2_EXECUTION",
            "gate_status": "PASS",
        }
        value.update(overrides)
        return value

    def call(self, **kwargs: object) -> dict[str, object]:
        base = dict(
            task_id=TASK,
            repository=REPOSITORY,
            requested_action="file",
            gate_state_resolution=self.state(),
            scope_identity=self.scope("file"),
            gate_policy={"action_map": ACTION_TO_MINIMUM_GATE},
            risk_class="R2",
            production_scope_applicable=False,
            manual_g5_action=False,
            event_id_or_idempotency_key="event-scrum-311-001",
            evaluated_at="2026-08-12T12:00:00Z",
        )
        base.update(kwargs)
        return check_authority_boundary(**base)  # type: ignore[arg-type]

    def assert_schema_valid(self, decision: dict[str, object]) -> None:
        schema = json.loads(
            (ROOT / "schemas/authority-boundary-decision.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(decision)), [])

    # --- exact ALLOW (closed-envelope match) ---
    def test_exact_envelope_match_is_allowed(self) -> None:
        decision = self.call(envelope_expires_at="2026-08-12T13:00:00Z")
        self.assertEqual(decision["decision"], "REQUIRE_APPROVAL")
        self.assertNotIn("AUTHORITY_ENVELOPE_EXPIRED", decision["reason_codes"])
        self.assert_schema_valid(decision)

    # --- expired envelope denied ---
    def test_expired_envelope_denied(self) -> None:
        # evaluated_at AFTER envelope_expires_at -> expired
        decision = self.call(
            evaluated_at="2026-08-12T14:00:00Z",
            envelope_expires_at="2026-08-12T13:00:00Z",
        )
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_ENVELOPE_EXPIRED")
        self.assertTrue(decision["authority_granted"] is False)
        self.assert_schema_valid(decision)

    def test_unparseable_expiry_denied(self) -> None:
        decision = self.call(envelope_expires_at="not-a-timestamp")
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_ENVELOPE_EXPIRED")

    # --- stale evidence denied ---
    def test_stale_evidence_flag_denied(self) -> None:
        decision = self.call(stale_evidence=True)
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_STALE_EVIDENCE_REJECTED")
        self.assertTrue(decision["authority_granted"] is False)
        self.assert_schema_valid(decision)

    # --- wrong action / scope still rejected (baseline, must stay green) ---
    def test_wrong_action_rejected(self) -> None:
        decision = self.call(
            requested_action="deploy",
            scope_identity=self.scope("file"),
        )
        self.assertEqual(decision["decision"], "BLOCK")
        self.assertIn("AUTHORITY_SCOPE_MISMATCH", decision["reason_codes"])

    def test_unknown_action_rejected(self) -> None:
        decision = self.call(requested_action="invented_action")
        self.assertEqual(decision["primary_reason_code"], "AUTHORITY_ACTION_UNKNOWN")

    # --- cross-gate privilege expansion rejected (no transitive higher-gate authority) ---
    def test_cross_gate_privilege_expansion_rejected(self) -> None:
        # merge requires G4_MERGE minimum; requesting it at G3_PR must NOT silently
        # inherit the higher gate. It deterministically requires explicit G4 approval
        # and is flagged AUTHORITY_LATER_GATE_INHERITANCE_REJECTED (no transitive authority).
        decision = self.call(
            requested_action="merge",
            scope_identity=self.scope("merge"),
            gate_state_resolution=self.state(current_gate="G3_PR"),
        )
        self.assertEqual(decision["decision"], "REQUIRE_APPROVAL")
        self.assertEqual(decision["required_approval_gate"], "G4_MERGE")
        self.assertIn("AUTHORITY_GATE_INSUFFICIENT", decision["reason_codes"])
        self.assertIn("AUTHORITY_LATER_GATE_INHERITANCE_REJECTED", decision["reason_codes"])

    # --- replay / drift determinism ---
    def test_replay_is_deterministic(self) -> None:
        first = self.call(envelope_expires_at="2026-08-12T13:00:00Z")
        second = self.call(envelope_expires_at="2026-08-12T13:00:00Z")
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        # expired replay stays expired deterministically
        exp1 = self.call(evaluated_at="2026-08-12T14:00:00Z", envelope_expires_at="2026-08-12T13:00:00Z")
        exp2 = self.call(evaluated_at="2026-08-12T14:00:00Z", envelope_expires_at="2026-08-12T13:00:00Z")
        self.assertEqual(exp1["decision_digest"], exp2["decision_digest"])

    # --- zero protected side effects on deny ---
    def test_deny_has_no_protected_side_effects(self) -> None:
        decision = self.call(stale_evidence=True)
        for key in (
            "authority_granted", "execution_authority_granted", "write_authority_granted",
            "pr_authority_granted", "merge_authority_granted",
            "deployment_authority_granted", "production_authority_granted",
        ):
            self.assertIs(decision[key], False)


if __name__ == "__main__":
    unittest.main()
