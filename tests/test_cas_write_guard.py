from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.cas_write_guard import evaluate_cas_write
from tools.node_architect.checkpoint_store import CheckpointConflict, CheckpointInput, load_store, persist_checkpoint, persist_to_file

BASE = "c28d0956b36f2894e369a24dfc245601bc628340"
SCOPE = "sha256:2b17eb4df4dbbc64d0eefb10d61ebe5896defd0a47d3a6704f41275fb2d30a29"
BRANCH = "codex/scrum-208-cas-write-guard-m5-20260802"
CHECKPOINT_KEY = "SCRUM-208:g2-scrum-208-r4:runtime_checkpoint.cas-write-guard"


def observation(**overrides):
    payload = {
        "task_id": "SCRUM-208", "observed_task_id": "SCRUM-208",
        "repository": "nhatnguyenquang1838-coder/gwc", "observed_repository": "nhatnguyenquang1838-coder/gwc",
        "branch": BRANCH, "observed_branch": BRANCH,
        "base_sha": BASE, "observed_base_sha": BASE,
        "scope_hash": SCOPE, "observed_scope_hash": SCOPE,
        "checkpoint_key": CHECKPOINT_KEY,
        "run_id": "g2-scrum-208-r4",
        "checkpoint_node_id": "runtime_checkpoint.cas-write-guard",
        "expected_revision": 3, "observed_revision": 3,
        "lease_owner": "ChatGPT", "observed_lease_owner": "ChatGPT",
        "lease_token": "lease-scrum-208", "observed_lease_token": "lease-scrum-208",
        "lease_expires_at": "2026-08-03T18:50:00Z", "observed_at": "2026-08-03T01:46:00Z",
        "fencing_token": 7, "observed_fencing_token": 7,
        "idempotency_key": "scrum-208-effect-001", "committed_effects": {},
        "latest_observed_state": {"revision": 3, "status": "ready"},
        "precondition_errors": [],
    }
    payload.update(overrides)
    return payload


def effect_for(payload, **binding_overrides):
    binding = {
        "task_id": payload["task_id"],
        "repository": payload["repository"],
        "branch": payload["branch"],
        "base_sha": payload["base_sha"],
        "scope_hash": payload["scope_hash"],
        "checkpoint_key": payload["checkpoint_key"],
        "run_id": payload["run_id"],
        "checkpoint_node_id": payload["checkpoint_node_id"],
        "lease_owner": payload["lease_owner"],
        "lease_token": payload["lease_token"],
        "fencing_token": payload["fencing_token"],
        "lease_expires_at": payload["lease_expires_at"],
        "idempotency_key": payload["idempotency_key"],
        "expected_revision": payload["expected_revision"],
    }
    binding.update(binding_overrides)
    return {
        "binding": binding,
        "checkpoint_key": binding["checkpoint_key"],
        "revision": payload["expected_revision"] + 1,
        "state_digest": "sha256:" + "f" * 64,
        "cas_decision_digest": "sha256:" + "e" * 64,
        "committed_at": "2026-08-03T01:46:00Z",
    }


def strict_item(*, item_overrides=None, **context_overrides):
    item_overrides = dict(item_overrides or {})
    expected_revision = item_overrides.pop("expected_revision", context_overrides.pop("expected_revision", 0))
    context = observation(expected_revision=expected_revision, observed_revision=999, **context_overrides)
    values = {
        "task_id": "SCRUM-208",
        "run_id": "g2-scrum-208-r4",
        "node_id": "runtime_checkpoint.cas-write-guard",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": "a" * 40,
        "scope_hash": SCOPE,
        "state": {"gate": "G2_EXECUTION", "status": "running"},
        "expected_revision": expected_revision,
        "lease_id": "lease-scrum-208",
        "fencing_token": 7,
        "cas_context": context,
    }
    values.update(item_overrides)
    return CheckpointInput(**values)


class CASWriteGuardTests(unittest.TestCase):
    def test_revision_match_allows_one_monotonic_write(self):
        result = evaluate_cas_write(observation())
        self.assertEqual(result["outcome"], "ALLOW_WRITE")
        self.assertTrue(result["may_write"])
        self.assertEqual(result["next_revision"], 4)
        self.assertFalse(result["auto_retry_allowed"])

    def test_revision_mismatch_returns_latest_state_and_routes_to_repair(self):
        result = evaluate_cas_write(observation(expected_revision=2))
        self.assertEqual(result["outcome"], "CAS_MISMATCH")
        self.assertEqual(result["latest_observed_state"], {"revision": 3, "status": "ready"})
        self.assertEqual(result["reconciliation_route"], "REPAIR")
        self.assertFalse(result["auto_retry_allowed"])

    def test_stale_fencing_rejects_even_when_revision_matches(self):
        result = evaluate_cas_write(observation(fencing_token=6))
        self.assertEqual(result["outcome"], "FENCING_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "ABORT_STALE_WORKER")

    def test_duplicate_agent_owner_is_fenced(self):
        result = evaluate_cas_write(observation(lease_owner="OtherAgent"))
        self.assertEqual(result["outcome"], "LEASE_OWNER_MISMATCH")
        self.assertIn("STALE_OR_DUPLICATE_AGENT", result["reason_codes"])

    def test_stale_lease_token_rejects(self):
        result = evaluate_cas_write(observation(lease_token="old-lease"))
        self.assertEqual(result["outcome"], "LEASE_STALE")

    def test_expired_lease_routes_to_reapproval(self):
        result = evaluate_cas_write(observation(lease_expires_at="2026-08-03T01:45:00Z"))
        self.assertEqual(result["outcome"], "LEASE_EXPIRED")
        self.assertEqual(result["reconciliation_route"], "REAPPROVAL_REQUIRED")

    def test_scope_mismatch_requires_reapproval(self):
        result = evaluate_cas_write(observation(scope_hash="sha256:" + "2" * 64))
        self.assertEqual(result["outcome"], "SCOPE_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "REAPPROVAL_REQUIRED")

    def test_base_drift_routes_to_reapproval(self):
        result = evaluate_cas_write(observation(observed_base_sha="b" * 40))
        self.assertEqual(result["outcome"], "BASE_DRIFT")
        self.assertEqual(result["next_node"], "runtime_checkpoint.state-reconciliation")

    def test_bound_duplicate_effect_replays_after_revision_advance_and_later_expiry(self):
        payload = observation(
            observed_revision=4,
            lease_expires_at="2026-08-03T01:45:00Z",
            observed_at="2026-08-03T01:47:00Z",
        )
        effect = effect_for(payload)
        payload["committed_effects"] = {payload["idempotency_key"]: effect}
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "DUPLICATE_EFFECT_REPLAYED")
        self.assertEqual(result["committed_effect"], effect)
        self.assertEqual(result["reconciliation_route"], "RESUME")

    def test_duplicate_effect_does_not_bypass_current_fencing_check(self):
        payload = observation(observed_fencing_token=8)
        payload["committed_effects"] = {payload["idempotency_key"]: effect_for(payload)}
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "FENCING_MISMATCH")

    def test_duplicate_effect_collision_fails_closed(self):
        payload = observation()
        payload["committed_effects"] = {
            payload["idempotency_key"]: effect_for(payload, checkpoint_key="SCRUM-999:other:node")
        }
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "SCOPE_MISMATCH")
        self.assertIn("COMMITTED_EFFECT_BINDING_MISMATCH:checkpoint_key", result["reason_codes"])

    def test_legacy_unbound_effect_fails_closed(self):
        payload = observation()
        payload["committed_effects"] = {payload["idempotency_key"]: {"revision": 4}}
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "INVALID_INPUT")
        self.assertIn("COMMITTED_EFFECT_BINDING_MISSING", result["reason_codes"])

    def test_checkpoint_integration_is_idempotent_after_commit_before_response(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        item = strict_item()
        first = persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z", evaluation_time="2026-08-03T01:44:00Z")
        first_rendered = json.dumps(first, sort_keys=True)
        replayed = persist_checkpoint(first, item, committed_at="2026-08-03T01:47:00Z", evaluation_time="2026-08-03T01:47:00Z")
        self.assertEqual(json.dumps(replayed, sort_keys=True), first_rendered)
        self.assertEqual(len(replayed["events"]), 1)

    def test_checkpoint_replay_tolerates_later_expiry_after_exact_effect_ownership(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        item = strict_item(lease_expires_at="2026-08-03T01:45:00Z")
        first = persist_checkpoint(
            store, item, committed_at="2026-08-03T01:44:00Z",
            evaluation_time="2026-08-03T01:44:00Z",
        )
        before = json.dumps(first, sort_keys=True)
        replayed = persist_checkpoint(
            first, item, committed_at="2026-08-03T01:47:00Z",
            evaluation_time="2026-08-03T01:47:00Z",
        )
        self.assertEqual(json.dumps(replayed, sort_keys=True), before)

    def test_context_expected_identity_conflict_never_mutates_store(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        before = json.dumps(store, sort_keys=True)
        item = strict_item(task_id="SCRUM-999")
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z", evaluation_time="2026-08-03T01:44:00Z")
        self.assertEqual(caught.exception.decision["outcome"], "INVALID_INPUT")
        self.assertIn("CONTEXT_ITEM_CONFLICT:task_id", caught.exception.decision["reason_codes"])
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_context_observed_identity_conflict_never_mutates_store(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        before = json.dumps(store, sort_keys=True)
        item = strict_item(observed_repository="evil/repo")
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z", evaluation_time="2026-08-03T01:44:00Z")
        self.assertEqual(caught.exception.decision["outcome"], "INVALID_INPUT")
        self.assertIn("CONTEXT_OBSERVED_BINDING_CONFLICT:observed_repository", caught.exception.decision["reason_codes"])
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_item_lease_and_fencing_conflicts_fail_closed(self):
        for override, reason in (({"lease_token": "other-lease"}, "CONTEXT_ITEM_CONFLICT:lease_token"), ({"fencing_token": 8}, "CONTEXT_ITEM_CONFLICT:fencing_token")):
            with self.subTest(reason=reason):
                store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
                with self.assertRaises(CheckpointConflict) as caught:
                    persist_checkpoint(store, strict_item(**override), committed_at="2026-08-03T01:46:00Z", evaluation_time="2026-08-03T01:44:00Z")
                self.assertIn(reason, caught.exception.decision["reason_codes"])

    def test_same_idempotency_key_cannot_cross_checkpoint_identity(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-scrum208-store.json")),
            strict_item(),
            committed_at="2026-08-03T01:46:00Z",
            evaluation_time="2026-08-03T01:44:00Z",
        )
        other = strict_item(
            item_overrides={"run_id": "other-run"},
            run_id="other-run",
            checkpoint_key="SCRUM-208:other-run:runtime_checkpoint.cas-write-guard",
        )
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(store, other, committed_at="2026-08-03T01:47:00Z", evaluation_time="2026-08-03T01:47:00Z")
        self.assertEqual(caught.exception.decision["outcome"], "SCOPE_MISMATCH")
        self.assertIn("COMMITTED_EFFECT_BINDING_MISMATCH:checkpoint_key", caught.exception.decision["reason_codes"])
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_stale_context_cannot_replay_existing_effect(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-scrum208-store.json")),
            strict_item(),
            committed_at="2026-08-03T01:46:00Z",
            evaluation_time="2026-08-03T01:44:00Z",
        )
        stale = strict_item(
            item_overrides={"lease_id": "stale-lease"},
            lease_token="stale-lease",
            observed_lease_token="stale-lease",
        )
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(
                store, stale, committed_at="2026-08-03T01:47:00Z",
                evaluation_time="2026-08-03T01:47:00Z",
            )
        self.assertEqual(caught.exception.decision["outcome"], "LEASE_STALE")

    def test_new_idempotency_key_cannot_self_assert_stale_lease_authority(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-scrum208-store.json")),
            strict_item(idempotency_key="effect-1"),
            committed_at="2026-08-03T01:44:00Z",
            evaluation_time="2026-08-03T01:44:00Z",
        )
        stale = strict_item(
            item_overrides={"expected_revision": 1, "lease_id": "stale-lease", "fencing_token": 6},
            expected_revision=1, idempotency_key="effect-2",
            lease_owner="StaleAgent", observed_lease_owner="StaleAgent",
            lease_token="stale-lease", observed_lease_token="stale-lease",
            fencing_token=6, observed_fencing_token=6,
        )
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(
                store, stale, committed_at="2026-08-03T01:45:00Z",
                evaluation_time="2026-08-03T01:45:00Z",
            )
        self.assertEqual(caught.exception.decision["outcome"], "LEASE_OWNER_MISMATCH")
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_caller_cannot_extend_authoritative_lease_expiry(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-scrum208-store.json")),
            strict_item(idempotency_key="effect-1", lease_expires_at="2026-08-03T01:45:00Z"),
            committed_at="2026-08-03T01:44:00Z",
            evaluation_time="2026-08-03T01:44:00Z",
        )
        next_item = strict_item(
            item_overrides={"expected_revision": 1},
            expected_revision=1, idempotency_key="effect-2",
            lease_expires_at="2026-08-03T18:50:00Z",
            observed_at="2026-08-03T00:00:00Z",
        )
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(
                store, next_item, committed_at="2026-08-03T01:47:00Z",
                evaluation_time="2026-08-03T01:47:00Z",
            )
        self.assertEqual(caught.exception.decision["outcome"], "LEASE_EXPIRED")

    def test_nonempty_strict_store_without_lease_binding_fails_closed(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        store["revision"] = 1
        store["checkpoints"] = {"legacy": {"task_id": "SCRUM-208"}}
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(
                store, strict_item(item_overrides={"expected_revision": 1}, expected_revision=1),
                committed_at="2026-08-03T01:44:00Z",
                evaluation_time="2026-08-03T01:44:00Z",
            )
        self.assertEqual(caught.exception.decision["outcome"], "INVALID_INPUT")
        self.assertIn("STORE_LEASE_BINDING_MISSING", caught.exception.decision["reason_codes"])

    def test_checkpoint_mismatch_never_mutates_store(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        item = strict_item(expected_revision=2)
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z", evaluation_time="2026-08-03T01:44:00Z")
        self.assertEqual(caught.exception.decision["outcome"], "CAS_MISMATCH")
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_file_restart_replay_does_not_duplicate_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            item = strict_item()
            persist_to_file(path, item, evaluation_time="2026-08-03T01:44:00Z")
            before = path.read_text(encoding="utf-8")
            persist_to_file(path, item, evaluation_time="2026-08-03T01:47:00Z")
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_invalid_input_fails_closed(self):
        result = evaluate_cas_write({"task_id": "SCRUM-208"})
        self.assertEqual(result["outcome"], "INVALID_INPUT")
        self.assertEqual(result["reconciliation_route"], "STOP_BLOCKED")

    def test_result_schema_accepts_all_outcomes(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas" / "cas-write-guard-result.schema.json").read_text())
        validator = Draft202012Validator(schema)
        payload = observation()
        effect = effect_for(payload)
        payload["committed_effects"] = {payload["idempotency_key"]: effect}
        results = (
            evaluate_cas_write(observation()),
            evaluate_cas_write(observation(expected_revision=1)),
            evaluate_cas_write(observation(fencing_token=1)),
            evaluate_cas_write(payload),
        )
        for result in results:
            self.assertEqual(list(validator.iter_errors(result)), [])


if __name__ == "__main__":
    unittest.main()
