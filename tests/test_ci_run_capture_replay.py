from __future__ import annotations

import unittest

from tools.node_architect.ci_run_capture import capture_ci_observation, is_replay_equivalent

BASE = "3b0938065e71e699d327d041f5b6023ed30a29dc"
HEAD = "b" * 40
SCOPE = "sha256:234b96f0de6a07fb7ab8c2d444ea6feeb4274230a6be3e0d530331648fd2d0f6"


def observe(payload, when="2026-07-30T14:00:00Z"):
    return capture_ci_observation(task_id="SCRUM-198", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-198-ci-run-capture-m5-fastlane-r3-20260730", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, provider_payload=payload, observed_at=when)


class CiRunCaptureReplayTests(unittest.TestCase):
    def test_missing_provider_data_is_unavailable_not_pass(self):
        obs = observe({"workflow_runs": [], "statuses": []})
        self.assertEqual(obs["classification"], "UNAVAILABLE")
        self.assertFalse(obs["checkpoint_required"])

    def test_exact_success_is_passed(self):
        obs = observe({"workflow_runs": [{"id": 1, "name": "validate", "head_sha": HEAD, "status": "completed", "conclusion": "success"}]})
        self.assertEqual(obs["classification"], "PASSED")
        self.assertEqual(obs["selected_runs"][0]["head_sha"], HEAD)

    def test_pending_requires_checkpoint(self):
        obs = observe({"workflow_runs": [{"id": 2, "name": "validate", "head_sha": HEAD, "status": "in_progress", "conclusion": None}]})
        self.assertEqual(obs["classification"], "PENDING")
        self.assertTrue(obs["checkpoint_required"])

    def test_head_drift_invalidates_observation(self):
        obs = observe({"workflow_runs": [{"id": 3, "name": "validate", "head_sha": "c" * 40, "status": "completed", "conclusion": "success"}]})
        self.assertEqual(obs["classification"], "SHA_MISMATCH")
        self.assertEqual(obs["rejected_candidates"][0]["reason"], "sha_mismatch")

    def test_replay_equivalent_ignores_observation_time(self):
        payload = {"workflow_runs": [{"id": 4, "name": "validate", "head_sha": HEAD, "status": "completed", "conclusion": "success"}]}
        first = observe(payload, "2026-07-30T14:00:00Z")
        second = observe(payload, "2026-07-30T14:01:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
