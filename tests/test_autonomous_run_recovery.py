#!/usr/bin/env python3
"""Tests for replay-safe autonomous run checkpoint (SCRUM-276)."""
from __future__ import annotations

import unittest

from tools.node_architect.autonomous_run_checkpoint import (
    AutonomousRunCheckpointError,
    capture_autonomous_run,
    is_replay_equivalent,
    manifest_digest,
    run_key,
)

TASK = "SCRUM-276"
RUN = "g1-scrum-276-canary-20260808"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "773baa601492dabf6ad8e835b62e48a68b0c1b55"
HEAD = "a" * 40
SCOPE = "sha256:f944f4848794f226708eee0b002b5de314981b48a23027857ed7364d05344787"

MANIFEST = {
    "tasks": [
        {"task_id": "SCRUM-274", "action": "verify_merge_sha"},
        {"task_id": "SCRUM-275", "action": "open_draft_pr"},
    ]
}


def base_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        run_id=RUN,
        repository=REPO,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        manifest=MANIFEST,
    )
    data.update(overrides)
    return data


class DeterministicDigestTests(unittest.TestCase):
    def test_same_manifest_same_digest(self):
        a = capture_autonomous_run(**base_kwargs())
        b = capture_autonomous_run(**base_kwargs())
        self.assertEqual(a.state_digest, b.state_digest)
        self.assertEqual(a.checkpoint_key, b.checkpoint_key)
        self.assertEqual(a.checkpoint_key, b.checkpoint_key)

    def test_same_manifest_identical_checkpoint_key(self):
        a = capture_autonomous_run(**base_kwargs())
        b = capture_autonomous_run(**base_kwargs())
        self.assertEqual(run_key(TASK, RUN, manifest_digest(MANIFEST)),
                         a.checkpoint_key)
        self.assertEqual(a.checkpoint_key, b.checkpoint_key)

    def test_deterministic_run_key_stable(self):
        self.assertEqual(
            run_key(TASK, RUN, manifest_digest(MANIFEST)),
            run_key(TASK, RUN, manifest_digest(MANIFEST)),
        )

    def test_replay_equivalent_ignores_timestamp(self):
        first = capture_autonomous_run(**base_kwargs(timestamp="2026-08-08T16:00:00Z"))
        second = capture_autonomous_run(**base_kwargs(timestamp="2026-08-08T16:05:00Z"))
        self.assertTrue(is_replay_equivalent(first, second))


class MissingBindingRejectionTests(unittest.TestCase):
    def test_missing_task_id_rejected(self):
        with self.assertRaises(AutonomousRunCheckpointError):
            capture_autonomous_run(**base_kwargs(task_id=""))

    def test_missing_repository_rejected(self):
        with self.assertRaises(AutonomousRunCheckpointError):
            capture_autonomous_run(**base_kwargs(repository="  "))

    def test_missing_scope_hash_rejected(self):
        with self.assertRaises(AutonomousRunCheckpointError):
            capture_autonomous_run(**base_kwargs(scope_hash=""))

    def test_malformed_base_sha_rejected(self):
        with self.assertRaises(AutonomousRunCheckpointError):
            capture_autonomous_run(**base_kwargs(base_sha="xyz"))


class ProgressTests(unittest.TestCase):
    def test_completed_nodes_advance(self):
        a = capture_autonomous_run(**base_kwargs(completed_node_ids=["SCRUM-274"]))
        b = capture_autonomous_run(**base_kwargs(completed_node_ids=["SCRUM-274", "SCRUM-275"]))
        self.assertNotEqual(a.state_digest, b.state_digest)
        self.assertEqual(b.completed_node_ids, ("SCRUM-274", "SCRUM-275"))


if __name__ == "__main__":
    unittest.main()
