from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.node_architect.unknown_write_reconciliation import decide_unknown_write_reconciliation, is_replay_equivalent

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "unknown-write-reconciliation-decision.schema.json"

BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "e" * 40
SCOPE = "sha256:af7096196898770c" + "0" * 48


def decide(**overrides):
    payload = dict(task_id="SCRUM-241", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-240-242-failure-recovery-m5-20260731", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, operation_id="op-1", provider_readback_status="VERIFIED", external_effect_status="ZERO_EFFECT", idempotency_key="idem-1", retry_count=0, max_retries=1, pending_action_recorded=True, observed_at="2026-07-31T00:00:00Z")
    payload.update(overrides)
    return decide_unknown_write_reconciliation(**payload)


class UnknownWriteReconciliationTests(unittest.TestCase):
    def test_zero_effect_with_budget_routes_bounded_retry(self):
        result = decide()
        self.assertEqual(result["outcome"], "BOUNDED_RETRY")
        self.assertFalse(result["blind_retry_allowed"])

    def test_unknown_effect_reconciles_not_retry(self):
        result = decide(external_effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertFalse(result["blind_retry_allowed"])

    def test_missing_pending_action_evidence_reconciles(self):
        result = decide(pending_action_recorded=False)
        self.assertEqual(result["outcome"], "RECONCILE")

    def test_committed_write_requires_human(self):
        result = decide(external_effect_status="COMMITTED")
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")

    def test_retry_budget_exhaustion_fails(self):
        result = decide(retry_count=1, max_retries=1)
        self.assertEqual(result["outcome"], "FAIL")

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-31T00:00:00Z")
        second = decide(observed_at="2026-07-31T00:02:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    # --- SCRUM-364 / #299: explicit reconciliation states + authoritative readback ---

    def test_committed_projects_confirmed_state(self):
        result = decide(external_effect_status="COMMITTED")
        self.assertEqual(result["reconciliation_state"], "CONFIRMED")
        self.assertFalse(result["retry_permitted"])

    def test_missing_pending_action_projects_pending_state(self):
        result = decide(pending_action_recorded=False)
        self.assertEqual(result["reconciliation_state"], "PENDING")
        self.assertFalse(result["retry_permitted"])

    def test_readback_confirmed_failure_projects_failed_state(self):
        result = decide(external_effect_status="FAILED")
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["reconciliation_state"], "FAILED")
        self.assertFalse(result["retry_permitted"])

    def test_unknown_interrupted_write_never_guessed_and_never_retried(self):
        result = decide(external_effect_status="UNKNOWN")
        self.assertEqual(result["reconciliation_state"], "UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertFalse(result["retry_permitted"])
        self.assertFalse(result["blind_retry_allowed"])
        self.assertFalse(result["pass_allowed"])
        self.assertTrue(result["checkpoint_required"])

    def test_duplicate_equivalent_effect_is_explicit_state_not_retry(self):
        result = decide(external_effect_status="DUPLICATE_EQUIVALENT")
        self.assertEqual(result["reconciliation_state"], "DUPLICATE_EQUIVALENT")
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")
        self.assertFalse(result["retry_permitted"])
        self.assertTrue(result["pass_allowed"])

    def test_partial_readback_reconciles_before_any_retry(self):
        result = decide(provider_readback_status="PARTIAL", external_effect_status="ZERO_EFFECT")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "PROVIDER_READBACK_PARTIAL")
        self.assertEqual(result["reconciliation_state"], "UNKNOWN")
        self.assertFalse(result["retry_permitted"])

    def test_partial_readback_outranks_zero_effect_retry_budget(self):
        # Retry budget remains, but readback is not authoritative -> no retry.
        result = decide(provider_readback_status="PARTIAL", retry_count=0, max_retries=5)
        self.assertFalse(result["retry_permitted"])

    def test_stale_head_readback_blocks_retry(self):
        result = decide(observed_head_sha="d" * 40)
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "STALE_HEAD_READBACK")
        self.assertEqual(result["reconciliation_state"], "UNKNOWN")
        self.assertFalse(result["retry_permitted"])

    def test_matching_observed_head_permits_bounded_retry(self):
        result = decide(observed_head_sha=HEAD)
        self.assertEqual(result["outcome"], "BOUNDED_RETRY")
        self.assertTrue(result["retry_permitted"])

    def test_no_state_ever_permits_blind_retry(self):
        for effect in ("ZERO_EFFECT", "COMMITTED", "DUPLICATE_EQUIVALENT", "UNKNOWN", "FAILED"):
            for readback in ("VERIFIED", "PARTIAL", "UNAVAILABLE", "STALE"):
                result = decide(external_effect_status=effect, provider_readback_status=readback)
                self.assertFalse(result["blind_retry_allowed"])
                self.assertIn(result["reconciliation_state"], {"CONFIRMED", "PENDING", "FAILED", "UNKNOWN", "DUPLICATE_EQUIVALENT"})
                if result["retry_permitted"]:
                    # Retry is only ever authorized by an authoritative ZERO_EFFECT readback.
                    self.assertEqual(readback, "VERIFIED")
                    self.assertEqual(effect, "ZERO_EFFECT")

    def test_replay_of_unknown_state_is_equivalent(self):
        first = decide(external_effect_status="UNKNOWN", observed_at="2026-08-15T00:00:00Z")
        second = decide(external_effect_status="UNKNOWN", observed_at="2026-08-15T09:30:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_stale_head_replay_is_not_equivalent_to_current_head(self):
        stale = decide(observed_head_sha="d" * 40)
        current = decide(observed_head_sha=HEAD)
        self.assertFalse(is_replay_equivalent(stale, current))


class UnknownWriteReconciliationSchemaTests(unittest.TestCase):
    def setUp(self):
        try:
            import jsonschema  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("jsonschema not available")
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def _assert_valid(self, payload):
        import jsonschema
        errors = sorted(jsonschema.Draft202012Validator(self.schema).iter_errors(payload), key=str)
        self.assertEqual([e.message for e in errors], [])

    def test_every_decision_shape_validates_against_closed_schema(self):
        self._assert_valid(decide())
        self._assert_valid(decide(external_effect_status="COMMITTED"))
        self._assert_valid(decide(external_effect_status="DUPLICATE_EQUIVALENT"))
        self._assert_valid(decide(external_effect_status="UNKNOWN"))
        self._assert_valid(decide(external_effect_status="FAILED"))
        self._assert_valid(decide(pending_action_recorded=False))
        self._assert_valid(decide(provider_readback_status="PARTIAL"))
        self._assert_valid(decide(observed_head_sha="d" * 40))
        self._assert_valid(decide(retry_count=1, max_retries=1))


if __name__ == "__main__":
    unittest.main()
