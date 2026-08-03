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


def observation(**overrides):
    payload = {
        "task_id": "SCRUM-208", "observed_task_id": "SCRUM-208",
        "repository": "nhatnguyenquang1838-coder/gwc", "observed_repository": "nhatnguyenquang1838-coder/gwc",
        "branch": BRANCH, "observed_branch": BRANCH,
        "base_sha": BASE, "observed_base_sha": BASE,
        "scope_hash": SCOPE, "observed_scope_hash": SCOPE,
        "expected_revision": 3, "observed_revision": 3,
        "lease_owner": "ChatGPT", "observed_lease_owner": "ChatGPT",
        "lease_token": "lease-scrum-208", "observed_lease_token": "lease-scrum-208",
        "lease_expires_at": "2026-08-03T18:50:00Z", "observed_at": "2026-08-03T01:46:00Z",
        "fencing_token": 7, "observed_fencing_token": 7,
        "idempotency_key": "scrum-208-effect-001", "committed_effects": {},
        "latest_observed_state": {"revision": 3, "status": "ready"},
    }
    payload.update(overrides)
    return payload


def strict_item(**context_overrides):
    expected_revision = context_overrides.pop("expected_revision", 0)
    context = observation(expected_revision=expected_revision, observed_revision=999, **context_overrides)
    return CheckpointInput(
        task_id="SCRUM-208", run_id="g2-scrum-208-r4", node_id="runtime_checkpoint.cas-write-guard",
        repository="nhatnguyenquang1838-coder/gwc", branch=BRANCH, base_sha=BASE,
        head_sha="a" * 40, scope_hash=SCOPE,
        state={"gate": "G2_EXECUTION", "status": "running"}, expected_revision=expected_revision,
        lease_id="lease-scrum-208", fencing_token=7, cas_context=context,
    )


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

    def test_duplicate_effect_returns_committed_readback_without_write(self):
        effect = {"revision": 4, "state_digest": "sha256:" + "f" * 64}
        result = evaluate_cas_write(observation(committed_effects={"scrum-208-effect-001": effect}))
        self.assertEqual(result["outcome"], "DUPLICATE_EFFECT_REPLAYED")
        self.assertEqual(result["committed_effect"], effect)
        self.assertEqual(result["reconciliation_route"], "RESUME")

    def test_checkpoint_integration_is_idempotent_after_commit_before_response(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        item = strict_item()
        first = persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z")
        first_rendered = json.dumps(first, sort_keys=True)
        replayed = persist_checkpoint(first, item, committed_at="2026-08-03T01:47:00Z")
        self.assertEqual(json.dumps(replayed, sort_keys=True), first_rendered)
        self.assertEqual(len(replayed["events"]), 1)

    def test_checkpoint_mismatch_never_mutates_store(self):
        store = load_store(Path("/tmp/nonexistent-scrum208-store.json"))
        item = strict_item(expected_revision=2)
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict) as caught:
            persist_checkpoint(store, item, committed_at="2026-08-03T01:46:00Z")
        self.assertEqual(caught.exception.decision["outcome"], "CAS_MISMATCH")
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_file_restart_replay_does_not_duplicate_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            item = strict_item()
            persist_to_file(path, item)
            before = path.read_text(encoding="utf-8")
            persist_to_file(path, item)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_invalid_input_fails_closed(self):
        result = evaluate_cas_write({"task_id": "SCRUM-208"})
        self.assertEqual(result["outcome"], "INVALID_INPUT")
        self.assertEqual(result["reconciliation_route"], "STOP_BLOCKED")

    def test_result_schema_accepts_all_outcomes(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas" / "cas-write-guard-result.schema.json").read_text())
        validator = Draft202012Validator(schema)
        for result in (evaluate_cas_write(observation()), evaluate_cas_write(observation(expected_revision=1)), evaluate_cas_write(observation(fencing_token=1))):
            self.assertEqual(list(validator.iter_errors(result)), [])


if __name__ == "__main__":
    unittest.main()
