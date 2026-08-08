#!/usr/bin/env python3
"""Tests for exact pre-prod merge-SHA G5 verification (SCRUM-276)."""
from __future__ import annotations

import unittest

from tools.node_architect.exact_head_readiness import decide_exact_head_readiness
from tools.node_architect.verify_preprod_merge_sha import verify_preprod_merge_sha

TASK = "SCRUM-276"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "773baa601492dabf6ad8e835b62e48a68b0c1b55"
MERGE = "b" * 40
SCOPE = "sha256:f944f4848794f226708eee0b002b5de314981b48a23027857ed7364d05344787"


def artifact(name, *, head=MERGE, digest="sha256:" + "a" * 64):
    return {"name": name, "head_sha": head, "digest": digest}


def base_kwargs(**overrides):
    payload = dict(
        task_id=TASK,
        repository=REPO,
        base_sha=BASE,
        merge_sha=MERGE,
        required_check_names=["validate-instructions", "build-project-package"],
        observed_checks=[
            {
                "name": "validate-instructions",
                "head_sha": MERGE,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "build-project-package",
                "head_sha": MERGE,
                "status": "completed",
                "conclusion": "success",
            },
        ],
        required_artifact_names=["runtime-checkpoint"],
        observed_artifacts=[artifact("runtime-checkpoint")],
        connector_status="CONFIRMED",
        exact_head_filter_applied=True,
    )
    payload.update(overrides)
    return payload


class ExactShaVerificationTests(unittest.TestCase):
    def test_exact_merge_sha_passes(self):
        result = verify_preprod_merge_sha(**base_kwargs())
        self.assertEqual(result["g5_status"], "PASS")
        self.assertTrue(result["exact_head_bound"])
        self.assertFalse(result["authority_granted"])

    def test_pending_check_is_ci_pending(self):
        result = verify_preprod_merge_sha(**base_kwargs(
            observed_checks=[
                {
                    "name": "validate-instructions",
                    "head_sha": MERGE,
                    "status": "in_progress",
                    "conclusion": None,
                },
                {
                    "name": "build-project-package",
                    "head_sha": MERGE,
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        ))
        self.assertEqual(result["g5_status"], "CI_PENDING")
        self.assertIn("validate-instructions", result["pending_checks"])

    def test_failed_check_fails(self):
        result = verify_preprod_merge_sha(**base_kwargs(
            observed_checks=[
                {
                    "name": "validate-instructions",
                    "head_sha": MERGE,
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "name": "build-project-package",
                    "head_sha": MERGE,
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        ))
        self.assertEqual(result["g5_status"], "FAIL")
        self.assertIn("validate-instructions", result["failed_checks"])

    def test_unobservable_connector_is_incomplete(self):
        result = verify_preprod_merge_sha(**base_kwargs(connector_status="ERROR"))
        self.assertEqual(result["g5_status"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertTrue(result["limitations"])

    def test_merge_sha_mismatch_is_not_exact_bound(self):
        other = "c" * 40
        result = verify_preprod_merge_sha(**base_kwargs(merge_sha=other))
        self.assertFalse(result["exact_head_bound"])
        self.assertNotEqual(result["g5_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
