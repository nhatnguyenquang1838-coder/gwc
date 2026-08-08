#!/usr/bin/env python3
"""Tests for serial multi-task canary runner (SCRUM-276)."""
from __future__ import annotations

import unittest

from tools.node_architect.autonomous_run_checkpoint import capture_autonomous_run
from tools.node_architect.run_autonomous_preprod_canary import run_autonomous_preprod_canary

TASK = "SCRUM-276"
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
        repository=REPO,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        run_id="g1-scrum-276-canary-20260808",
        manifest=MANIFEST,
    )
    data.update(overrides)
    return data


def all_complete(spec, checkpoint):
    return {"outcome": "COMPLETED", "reason": "TASK_DONE"}


class CanarySerialTests(unittest.TestCase):
    def test_two_tasks_complete_serially(self):
        result = run_autonomous_preprod_canary(**base_kwargs(evaluate_task=all_complete))
        self.assertEqual(result["overall_outcome"], "COMPLETED")
        self.assertEqual(result["completed_count"], 2)
        self.assertEqual(len(result["results"]), 2)

    def test_checkpoint_keys_are_replay_stable(self):
        result = run_autonomous_preprod_canary(**base_kwargs(evaluate_task=all_complete))
        for entry in result["results"]:
            self.assertEqual(
                entry["checkpoint_key"],
                capture_autonomous_run(
                    task_id=entry["task_id"],
                    run_id="g1-scrum-276-canary-20260808",
                    repository=REPO,
                    base_sha=BASE,
                    head_sha=HEAD,
                    scope_hash=SCOPE,
                    manifest=MANIFEST,
                    completed_node_ids=[],
                    next_node_id=entry["task_id"],
                ).checkpoint_key,
            )

    def test_blocked_task_stops_canary(self):
        def block_second(spec, checkpoint):
            if spec["task_id"] == "SCRUM-275":
                return {"outcome": "BLOCKED", "reason": "POLICY_BLOCKED"}
            return {"outcome": "COMPLETED", "reason": "TASK_DONE"}

        result = run_autonomous_preprod_canary(**base_kwargs(evaluate_task=block_second))
        self.assertEqual(result["overall_outcome"], "BLOCKED")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][1]["outcome"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
