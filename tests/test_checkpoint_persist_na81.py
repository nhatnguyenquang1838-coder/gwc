"""SCRUM-326 NA81 maturity tests for the checkpoint-persist node.

Current-task requirement -> code -> test evidence map (exact SHA delivery).

The older SCRUM-203 tests remain compatibility coverage. These tests bind the
current SCRUM-326 AC: durable/idempotent atomic persist with canonical
key/version semantics, authoritative write readback, interrupted/unknown outcome
reconciliation, forbidden duplicate effects, CAS version conflict rejection,
and crash/replay safety. No auto-close rule: historical green tests are not
current delivery proof.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
import tempfile

# SCRUM-323 lesson: insert absolute tools/ dir so node_architect imports resolve
# under CI `python -m unittest discover` from repo root (Python 3.12 namespace pkgs).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from tools.node_architect.checkpoint_store import (
    CheckpointConflict,
    CheckpointInput,
    ReadbackMismatch,
    checkpoint_key,
    digest_payload,
    load_store,
    persist_checkpoint,
    persist_to_file,
    reconcile_unknown_outcome,
    replay_checkpoint,
    validate_readback,
)

TASK = "SCRUM-326"
RUN = "g1-scrum-326-na81-r1"
NODE = "runtime_checkpoint.checkpoint-persist"
GATE = "G2_EXECUTION"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "a" * 40
HEAD = "b" * 40
SCOPE = "sha256:" + "c" * 64
GRAPH = "scrum-326-na81-v0.1"


def base_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        run_id=RUN,
        node_id=NODE,
        branch="auto/SCRUM-326-na81-20260810",
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        graph_revision=GRAPH,
        repository=REPO,
        state={"status": "running", "gate": GATE},
    )
    data.update(overrides)
    return data


def fresh_item(expected_revision=None, **overrides):
    return CheckpointInput(
        **base_kwargs(
            expected_revision=expected_revision,
            **overrides,
        )
    )


def _persist_with_cas(store, expected_revision=0):
    return persist_checkpoint(
        store,
        fresh_item(
            expected_revision=expected_revision,
            lease_id="lease-1",
            fencing_token=1,
            cas_context={
                "lease_owner": "worker-1",
                "lease_expires_at": "2099-01-01T00:00:00Z",
            },
        ),
        committed_at="2026-08-12T00:00:00Z",
    )


class FirstPersistTests(unittest.TestCase):
    def test_first_persist_creates_event_and_checkpoint(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-1.json")),
            fresh_item(),
            committed_at="2026-08-12T00:00:00Z",
        )
        self.assertEqual(store["revision"], 1)
        self.assertEqual(len(store["events"]), 1)
        key = checkpoint_key(TASK, RUN, NODE)
        self.assertIn(key, store["checkpoints"])
        record = store["checkpoints"][key]
        self.assertEqual(record["state_digest"], digest_payload(base_kwargs()["state"]))

    def test_persist_binds_canonical_key_version(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-2.json")),
            fresh_item(expected_revision=0),
            committed_at="2026-08-12T00:00:00Z",
        )
        key = checkpoint_key(TASK, RUN, NODE)
        record = store["checkpoints"][key]
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["previous_revision"], 0)


class IdempotentDuplicateTests(unittest.TestCase):
    def test_duplicate_effect_replay_returns_store_unchanged(self):
        store = load_store(Path("/tmp/nonexistent-gwc-store-scrum326-dup.json"))
        first = _persist_with_cas(store, expected_revision=0)
        self.assertEqual(first["revision"], 1)
        before_events = list(first["events"])
        before_effects = dict(first.get("effects", {}))
        # Second call with same identity must replay the committed effect.
        # Replay uses the original expected_revision because it is part of the
        # committed effect binding.
        second = _persist_with_cas(first, expected_revision=0)
        self.assertEqual(second["revision"], 1)
        self.assertEqual(second["events"], before_events)
        self.assertEqual(second.get("effects", {}), before_effects)

    def test_duplicate_attempt_does_not_create_second_event(self):
        store = _persist_with_cas(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-dup2.json")),
            expected_revision=0,
        )
        event_count = len(store["events"])
        second = _persist_with_cas(store, expected_revision=0)
        self.assertEqual(len(second["events"]), event_count)


class CasVersionConflictTests(unittest.TestCase):
    def test_cas_version_conflict_raises_checkpoint_conflict(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-cas.json")),
            fresh_item(expected_revision=0),
            committed_at="2026-08-12T00:00:00Z",
        )
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict):
            persist_checkpoint(store, fresh_item(expected_revision=0))
        self.assertEqual(json.dumps(store, sort_keys=True), before)


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_persist_replaces_target_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            original = {"schema_version": "1.0", "revision": 0, "events": []}
            # Write a pre-existing file that must be replaced atomically.
            path.write_text(json.dumps(original, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            new_payload = {
                "schema_version": "1.0",
                "revision": 1,
                "events": [{"event_type": "x", "revision": 1}],
            }
            from tools.node_architect.checkpoint_store import write_store
            write_store(path, new_payload)
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["revision"], 1)

    def test_crash_replay_safety_with_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            persist_to_file(path, fresh_item(expected_revision=0))
            loaded = load_store(path)
            before_events = list(loaded["events"])
            replayed = replay_checkpoint(loaded, TASK, RUN, NODE)
            self.assertIsNotNone(replayed)
            self.assertEqual(loaded["events"], before_events)


class ReconcileUnknownOutcomeTests(unittest.TestCase):
    def test_missing_checkpoint_record_is_unknown(self):
        store = {
            "schema_version": "1.0",
            "revision": 1,
            "events": [],
            "checkpoints": {},
            "effects": {},
        }
        result = reconcile_unknown_outcome(store, fresh_item())
        self.assertEqual(result["outcome"], "UNKNOWN_OUTCOME")
        self.assertIn("MISSING_CHECKPOINT_RECORD", result["reasons"])

    def test_invalid_checkpoints_field_is_unknown(self):
        store = {
            "schema_version": "1.0",
            "revision": 1,
            "events": [],
            "checkpoints": "not-a-mapping",
            "effects": {},
        }
        result = reconcile_unknown_outcome(store, fresh_item())
        self.assertEqual(result["outcome"], "UNKNOWN_OUTCOME")
        self.assertIn("INVALID_CHECKPOINTS", result["reasons"])

    def test_store_digest_mismatch_is_unknown(self):
        store = {
            "schema_version": "1.0",
            "revision": 1,
            "events": [],
            "checkpoints": {},
            "effects": {},
            "store_digest": "sha256:" + "0" * 64,
        }
        result = reconcile_unknown_outcome(store, fresh_item())
        self.assertEqual(result["outcome"], "UNKNOWN_OUTCOME")
        self.assertIn("STORE_DIGEST_MISMATCH", result["reasons"])

    def test_known_state_passes(self):
        key = checkpoint_key(TASK, RUN, NODE)
        record = {
            "revision": 1,
            "state_digest": digest_payload(base_kwargs()["state"]),
        }
        inner = {
            "revision": 1,
            "events": [{"schema_version": "1.0", "artifact_type": "runtime-event", "event_type": "x", "revision": 1}],
            "checkpoints": {key: record},
            "effects": {},
            "binding": {"task_id": TASK, "repository": REPO, "branch": "main", "base_sha": BASE, "scope_hash": SCOPE},
            "lease_binding": {
                "lease_owner": "worker-1",
                "lease_token": "lease-1",
                "fencing_token": 1,
                "lease_expires_at": "2099-01-01T00:00:00Z",
            },
        }
        inner["store_digest"] = digest_payload(
            {
                "revision": inner["revision"],
                "binding": inner.get("binding"),
                "lease_binding": inner.get("lease_binding"),
                "events": inner["events"],
                "checkpoints": inner["checkpoints"],
                "effects": inner.get("effects", {}),
            }
        )
        store = {"schema_version": "1.0", "revision": 1, **inner}
        result = reconcile_unknown_outcome(store, fresh_item())
        self.assertEqual(result["outcome"], "KNOWN_STATE")
        self.assertEqual(result["reconciliation_route"], None)


class ReadbackMismatchTests(unittest.TestCase):
    def test_readback_confirms_persisted_state(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-rb1.json")),
            fresh_item(),
            committed_at="2026-08-12T00:00:00Z",
        )
        result = validate_readback(store, fresh_item())
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["revision"], 1)

    def test_readback_detects_missing_checkpoint(self):
        store = {"schema_version": "1.0", "revision": 1, "events": [], "checkpoints": {}, "effects": {}}
        with self.assertRaises(ReadbackMismatch):
            validate_readback(store, fresh_item())

    def test_readback_detects_state_digest_mismatch(self):
        store = persist_checkpoint(
            load_store(Path("/tmp/nonexistent-gwc-store-scrum326-rb3.json")),
            fresh_item(),
            committed_at="2026-08-12T00:00:00Z",
        )
        key = checkpoint_key(TASK, RUN, NODE)
        store["checkpoints"][key]["state_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ReadbackMismatch):
            validate_readback(store, fresh_item())


if __name__ == "__main__":
    unittest.main()
