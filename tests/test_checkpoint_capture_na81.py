"""SCRUM-325 NA81 maturity tests for the checkpoint-capture node.

Current-task requirement -> code -> test evidence map (exact SHA delivery).

The older SCRUM-202 tests remain compatibility coverage. These tests bind the
current SCRUM-325 AC: minimal replay state bound to exact task/run/node/head/scope,
deterministic digest, and FAIL-CLOSED exclusion of secrets / overbroad /
unbounded state (current brief EARS #3 / #5, "No auto-close" rule).
"""
from __future__ import annotations

import unittest

from tools.node_architect.checkpoint_capture import (
    CheckpointCapture,
    CheckpointCaptureError,
    PendingAction,
    capture_checkpoint,
    reconstruct_next_action,
)


TASK = "SCRUM-325"
RUN = "g1-scrum-325-na81-r1"
NODE = "runtime_checkpoint.checkpoint-capture"
GATE = "G2_EXECUTION"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "a" * 40
HEAD = "b" * 40
SCOPE = "sha256:" + "c" * 64
GRAPH = "scrum-325-na81-v0.1"


def base_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        run_id=RUN,
        node_id=NODE,
        gate=GATE,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        graph_revision=GRAPH,
        repository=REPO,
        state={"status": "running", "gate": GATE},
    )
    data.update(overrides)
    return data


class DeterministicMinimalCaptureTests(unittest.TestCase):
    def test_same_minimal_input_same_digest(self):
        a = capture_checkpoint(**base_kwargs())
        b = capture_checkpoint(**base_kwargs())
        self.assertEqual(a.state_digest, b.state_digest)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_capture_is_minimal_state_only_no_authority_grant(self):
        cap = capture_checkpoint(**base_kwargs())
        self.assertIsInstance(cap, CheckpointCapture)
        self.assertEqual(cap.to_dict()["artifact_type"], "runtime-checkpoint-capture")
        # Rendering a checkpoint captures state; it grants no later-gate authority.
        self.assertTrue(cap.to_dict()["state_digest"])


class SecretExclusionTests(unittest.TestCase):
    def test_secret_key_in_state_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"status": "running", "auth_token": "xyz"})
            )

    def test_nested_secret_key_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"status": "running", "inner": {"api_key": "k"}})
            )

    def test_password_like_key_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"password": "hunter2", "status": "ok"})
            )


class OverbroadStateExclusionTests(unittest.TestCase):
    def test_working_memory_key_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"status": "running", "working_memory": {"x": 1}})
            )

    def test_full_context_key_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"status": "running", "full_context": "huge"})
            )

    def test_unbounded_cache_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(state={"status": "running", "cache": {"k": "v"}})
            )


class StateBoundTests(unittest.TestCase):
    def test_state_exceeds_key_bound_rejected(self):
        fat = {f"k{i}": i for i in range(100)}
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(state=fat))

    def test_state_exceeds_byte_bound_rejected(self):
        fat = {"payload": "x" * (80 * 1024)}
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(state=fat))


class StaleAmbiguousBindingTests(unittest.TestCase):
    def test_empty_scope_hash_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(scope_hash=""))

    def test_malformed_base_sha_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(base_sha="not-a-sha"))


class ReplayReadCompatibilityTests(unittest.TestCase):
    def test_reconstruct_exact_next_action(self):
        cap = capture_checkpoint(
            **base_kwargs(
                state={"status": "suspended", "gate": GATE},
                pending_actions=[
                    PendingAction("resume", "node_x", "G2_EXECUTION", f"{TASK}:{HEAD}:resume")
                ],
                next_action="runtime_checkpoint.checkpoint-persist",
            )
        )
        self.assertEqual(
            reconstruct_next_action(cap), "runtime_checkpoint.checkpoint-persist"
        )

    def test_plain_mapping_replay_safe(self):
        cap = capture_checkpoint(**base_kwargs(state={"k": "v", "n": 1}))
        cap2 = capture_checkpoint(**base_kwargs(state={"n": 1, "k": "v"}))
        self.assertEqual(cap.state_digest, cap2.state_digest)


if __name__ == "__main__":
    unittest.main()
