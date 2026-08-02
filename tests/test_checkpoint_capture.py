from __future__ import annotations

import unittest

from tools.node_architect.checkpoint_capture import (
    CheckpointCapture,
    CheckpointCaptureError,
    PendingAction,
    capture_checkpoint,
    reconstruct_next_action,
)


TASK = "SCRUM-202"
RUN = "g1-scrum-202-fastlane-r1"
NODE = "runtime_checkpoint.checkpoint-capture"
GATE = "G2_EXECUTION"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "aad17d28be539c88ecef4b9fbaf3eaa08f59461b"
HEAD = "a" * 40
SCOPE = "sha256:8ab19301ea8de65c0d1d911708e14dd13d1f5d11d49f4b89c1071cbd2d57c332"
GRAPH = "scrum-104-20260726"


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


class DeterministicDigestTests(unittest.TestCase):
    def test_same_input_same_digest(self):
        a = capture_checkpoint(**base_kwargs())
        b = capture_checkpoint(**base_kwargs())
        self.assertEqual(a.state_digest, b.state_digest)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_identical_state_dict_order_independent(self):
        x = capture_checkpoint(**base_kwargs(state={"b": 2, "a": 1}))
        y = capture_checkpoint(**base_kwargs(state={"a": 1, "b": 2}))
        self.assertEqual(x.state_digest, y.state_digest)

    def test_different_state_different_digest(self):
        x = capture_checkpoint(**base_kwargs(state={"status": "running"}))
        y = capture_checkpoint(**base_kwargs(state={"status": "suspended"}))
        self.assertNotEqual(x.state_digest, y.state_digest)


class MissingBindingRejectionTests(unittest.TestCase):
    def test_missing_task_id_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(task_id=""))

    def test_missing_repository_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(repository="  "))

    def test_missing_scope_hash_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(scope_hash=""))

    def test_ambiguous_gate_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(gate="not-a-gate"))

    def test_malformed_base_sha_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(base_sha="xyz"))

    def test_none_state_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(**base_kwargs(state=None))


class PendingActionCaptureTests(unittest.TestCase):
    def test_pending_action_included_with_exact_identity(self):
        pa = PendingAction(
            action_id="write_file",
            target="tools/node_architect/checkpoint_capture.py",
            authority_gate="G2_EXECUTION",
            idempotency_key=f"{TASK}:{HEAD}:write-file",
        )
        cap = capture_checkpoint(**base_kwargs(pending_actions=[pa]))
        self.assertEqual(len(cap.pending_actions), 1)
        self.assertEqual(cap.pending_actions[0].to_dict(), pa.to_dict())

    def test_pending_action_missing_identity_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(
                    pending_actions=[PendingAction("", "t", "G2_EXECUTION", "k")]
                )
            )

    def test_pending_action_ambiguous_gate_rejected(self):
        with self.assertRaises(CheckpointCaptureError):
            capture_checkpoint(
                **base_kwargs(
                    pending_actions=[PendingAction("a", "t", "weird", "k")]
                )
            )


class CrashBeforePersistTests(unittest.TestCase):
    def test_capture_is_pure_no_persistence_side_effect(self):
        # capture_checkpoint does not write to any store; a crash before
        # persist leaves only the in-memory object, which is replayable.
        cap = capture_checkpoint(**base_kwargs(next_action="persist_checkpoint"))
        self.assertIsInstance(cap, CheckpointCapture)
        # Reconstructing from the object works without any external state.
        self.assertEqual(reconstruct_next_action(cap), "persist_checkpoint")


class ReplayReadCompatibilityTests(unittest.TestCase):
    def test_resume_reconstructs_exact_next_action(self):
        cap = capture_checkpoint(
            **base_kwargs(
                state={"status": "suspended", "gate": GATE},
                pending_actions=[
                    PendingAction("resume", "node_x", "G2_EXECUTION", f"{TASK}:{HEAD}:resume")
                ],
                next_action="runtime_checkpoint.checkpoint-persist",
            )
        )
        self.assertEqual(reconstruct_next_action(cap), "runtime_checkpoint.checkpoint-persist")

    def test_reconstruct_revalidates_binding(self):
        cap = capture_checkpoint(**base_kwargs())
        # Corrupt binding integrity on the captured object must fail closed.
        broken = CheckpointCapture(
            task_id=cap.task_id,
            run_id=cap.run_id,
            node_id=cap.node_id,
            gate=cap.gate,
            base_sha=cap.base_sha,
            head_sha=cap.head_sha,
            scope_hash="",  # tampered binding
            graph_revision=cap.graph_revision,
            repository=cap.repository,
            state_digest=cap.state_digest,
            pending_actions=cap.pending_actions,
            next_action=cap.next_action,
            captured_at=cap.captured_at,
        )
        with self.assertRaises(CheckpointCaptureError):
            reconstruct_next_action(broken)

    def test_plain_mapping_state_replay_safe(self):
        # A JSON-serializable plain mapping produces a stable digest.
        cap = capture_checkpoint(**base_kwargs(state={"k": "v", "n": 1}))
        cap2 = capture_checkpoint(**base_kwargs(state={"n": 1, "k": "v"}))
        self.assertEqual(cap.state_digest, cap2.state_digest)


if __name__ == "__main__":
    unittest.main()
