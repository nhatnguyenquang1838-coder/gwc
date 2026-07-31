from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.approval_expiry_recovery import decide_approval_expiry_recovery, replay_safe
from tools.node_architect.duplicate_agent_fencing import decide_duplicate_agent_fencing
from tools.node_architect.version_drift_rollback_routing import decide_version_drift_rollback_routing

BASE = "d4b62295a6d36badca23e9254997e040b0ee19cf"
HEAD = "b" * 40
SCOPE = "sha256:6ce7a82dcfe6f4b78621ac9bada47946cb3856fb35c2a0a39e94cd507aa655f2"
CHECKPOINT = "sha256:" + "1" * 64
ROLLBACK = "sha256:" + "2" * 64
BRANCH = "codex/scrum-244-246-f8-recovery-m5-20260731"
REPO = "nhatnguyenquang1838-coder/gwc"


def validate_schema(file_name: str, payload: dict) -> None:
    schema = json.loads(Path("schemas", file_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise AssertionError(errors[0].message)


def approval(**overrides):
    payload = dict(task_id="SCRUM-244", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        approval_id="CP-20260731-244-246-G2-R1", approval_scope_hash=SCOPE, current_scope_hash=SCOPE,
        approval_expires_at="2026-07-31T11:38:00Z", now_at="2026-07-31T07:49:00Z",
        continuation_requested=True, checkpoint_digest_before_wait=CHECKPOINT, current_checkpoint_digest=CHECKPOINT,
        replay_nonce="nonce-1", consumed_replay_nonces=[], observed_at="2026-07-31T07:49:00Z")
    payload.update(overrides)
    return decide_approval_expiry_recovery(**payload)


def fencing(**overrides):
    payload = dict(task_id="SCRUM-245", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, run_id="run-245", worker_id="agent-a", active_lease_holder="agent-a",
        worker_fencing_token=12, observed_fencing_token=12, lease_state="ACTIVE", side_effect_key="effect-1",
        committed_side_effect_keys=[], race_detected=False, observed_at="2026-07-31T07:49:00Z")
    payload.update(overrides)
    return decide_duplicate_agent_fencing(**payload)


def version(**overrides):
    payload = dict(task_id="SCRUM-246", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, run_id="run-246", checkpoint_id="checkpoint-246", snapshot_node_version="1.0.0",
        runtime_node_version="1.0.0", compatibility_rule="COMPATIBLE", replay_requested=False,
        replay_epoch=3, current_epoch=3, rollback_evidence_digest=None, observed_at="2026-07-31T07:49:00Z")
    payload.update(overrides)
    return decide_version_drift_rollback_routing(**payload)


class ApprovalExpiryRecoveryM5Tests(unittest.TestCase):
    def test_checkpoint_before_wait_allows_valid_continuation(self):
        result = approval()
        self.assertEqual(result["outcome"], "CONTINUE")
        self.assertTrue(result["wait_allowed"])
        self.assertTrue(result["continuation_allowed"])
        self.assertFalse(result["stale_continuation_allowed"])
        validate_schema("approval-expiry-recovery-decision.schema.json", result)

    def test_expired_approval_regenerates_request(self):
        result = approval(now_at="2026-07-31T12:00:00Z")
        self.assertEqual(result["outcome"], "REGENERATE_APPROVAL")
        self.assertTrue(result["approval_expired"])
        self.assertFalse(result["continuation_allowed"])

    def test_replay_nonce_is_rejected(self):
        result = approval(consumed_replay_nonces=["nonce-1"])
        self.assertEqual(result["outcome"], "REJECT_REPLAY")
        self.assertTrue(result["replay_rejected"])

    def test_checkpoint_required_before_wait(self):
        result = approval(checkpoint_digest_before_wait=None)
        self.assertEqual(result["outcome"], "CHECKPOINT_BEFORE_WAIT")
        self.assertTrue(result["checkpoint_required"])

    def test_checkpoint_drift_regenerates_approval(self):
        result = approval(current_checkpoint_digest="sha256:" + "3" * 64)
        self.assertEqual(result["reason_code"], "CHECKPOINT_DRIFTED_DURING_WAIT")
        self.assertTrue(result["regenerate_approval_required"])

    def test_replay_equivalence_ignores_observation_time(self):
        self.assertTrue(replay_safe(approval(observed_at="2026-07-31T07:49:00Z"), approval(observed_at="2026-07-31T07:55:00Z")))


class DuplicateAgentFencingM5Tests(unittest.TestCase):
    def test_active_lease_holder_allows_single_effect(self):
        result = fencing()
        self.assertEqual(result["outcome"], "ALLOW_SINGLE_EFFECT")
        self.assertTrue(result["fencing_enforced"])
        self.assertTrue(result["side_effect_allowed"])
        validate_schema("duplicate-agent-fencing-decision.schema.json", result)

    def test_non_holder_is_fenced(self):
        result = fencing(worker_id="agent-b")
        self.assertEqual(result["outcome"], "FENCE_STALE_WORKER")
        self.assertFalse(result["advancement_allowed"])

    def test_stale_token_is_fenced(self):
        result = fencing(worker_fencing_token=11, observed_fencing_token=12)
        self.assertEqual(result["reason_code"], "WORKER_NOT_CURRENT_LEASE_HOLDER_OR_TOKEN_STALE")
        self.assertFalse(result["side_effect_allowed"])

    def test_duplicate_race_is_fenced(self):
        result = fencing(race_detected=True)
        self.assertEqual(result["outcome"], "FENCE_DUPLICATE_AGENT")
        self.assertFalse(result["advancement_allowed"])

    def test_duplicate_side_effect_is_suppressed_not_repeated(self):
        result = fencing(committed_side_effect_keys=["effect-1"])
        self.assertEqual(result["outcome"], "SUPPRESS_DUPLICATE_EFFECT")
        self.assertTrue(result["duplicate_effect_prevented"])
        self.assertFalse(result["side_effect_allowed"])


class VersionDriftRollbackRoutingM5Tests(unittest.TestCase):
    def test_same_version_continues(self):
        result = version()
        self.assertEqual(result["outcome"], "CONTINUE")
        self.assertFalse(result["drift_detected"])
        validate_schema("version-drift-rollback-routing-decision.schema.json", result)

    def test_compatible_drift_continues_with_evidence(self):
        result = version(runtime_node_version="1.0.1", compatibility_rule="COMPATIBLE")
        self.assertEqual(result["outcome"], "CONTINUE_COMPATIBLE")
        self.assertTrue(result["drift_detected"])

    def test_new_epoch_route(self):
        result = version(runtime_node_version="2.0.0", compatibility_rule="NEW_EPOCH_REQUIRED")
        self.assertEqual(result["outcome"], "ROUTE_NEW_EPOCH")
        self.assertTrue(result["new_epoch_required"])

    def test_stale_replay_rejected_before_rollback(self):
        result = version(runtime_node_version="2.0.0", compatibility_rule="ROLLBACK_REQUIRED", replay_requested=True, replay_epoch=2, current_epoch=3, rollback_evidence_digest=ROLLBACK)
        self.assertEqual(result["outcome"], "REJECT_STALE_REPLAY")
        self.assertFalse(result["replay_allowed"])

    def test_rollback_route_preserves_evidence_without_deploy_authority(self):
        result = version(runtime_node_version="2.0.0", compatibility_rule="ROLLBACK_REQUIRED", rollback_evidence_digest=ROLLBACK)
        self.assertEqual(result["outcome"], "ROUTE_ROLLBACK_EVIDENCE")
        self.assertTrue(result["evidence_preserved"])
        self.assertFalse(result["g5_manual_action_authorized"])


if __name__ == "__main__":
    unittest.main()
