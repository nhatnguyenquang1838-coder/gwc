#!/usr/bin/env python3
"""NA81 current-task evidence tests for failure_recovery.version-drift-rollback-routing (SCRUM-369).

Per SCRUM-323 import-path lesson: insert the absolute tools/ dir into sys.path[0]
so `import node_architect...` resolves under CI `python -m unittest discover`.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))

import node_architect.version_drift_rollback_routing as vdrr  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "d4b62295a6d36badca23e9254997e040b0ee19cf"
HEAD = "b" * 40
SCOPE = "sha256:6ce7a82dcfe6f4b78621ac9bada47946cb3856fb35c2a0a39e94cd507aa655f2"
BRANCH = "auto/SCRUM-369-na81-20260810"
ROLLBACK = "sha256:" + "2" * 64
NOW = "2026-08-11T18:00:00Z"


def _validate_schema(payload):
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "version-drift-rollback-routing-decision.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda e: list(e.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


def _base(**overrides):
    payload = dict(
        task_id="SCRUM-369", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, run_id="run-369", checkpoint_id="checkpoint-369",
        snapshot_node_version="1.0.0", runtime_node_version="1.0.0",
        compatibility_rule="COMPATIBLE", replay_requested=False, replay_epoch=3, current_epoch=3,
        rollback_evidence_digest=None, observed_at=NOW,
    )
    payload.update(overrides)
    return vdrr.decide_version_drift_rollback_routing(**payload)


class VersionDriftRollbackRoutingNA81Tests(unittest.TestCase):
    def test_version_evidence_unavailable_blocks(self):
        """Brief: unavailable version evidence must BLOCK, not silently continue."""
        result = _base(snapshot_node_version="", runtime_node_version="1.0.0")
        self.assertEqual(result["reason_code"], "VERSION_EVIDENCE_UNAVAILABLE")
        self.assertEqual(result["outcome"], "BLOCK_UNSUPPORTED_DRIFT")
        self.assertFalse(result["replay_allowed"])
        self.assertTrue(result["governed_repair_required"])
        self.assertTrue(result["version_evidence_unavailable"])
        _validate_schema(result)

    def test_version_evidence_unavailable_both_missing(self):
        result = _base(snapshot_node_version="", runtime_node_version="")
        self.assertEqual(result["reason_code"], "VERSION_EVIDENCE_UNAVAILABLE")
        self.assertEqual(result["outcome"], "BLOCK_UNSUPPORTED_DRIFT")

    def test_rollback_route_has_no_destructive_effect(self):
        """Brief: rollback is decision-only; destructive guesswork is forbidden."""
        result = _base(runtime_node_version="2.0.0", compatibility_rule="ROLLBACK_REQUIRED",
                        rollback_evidence_digest=ROLLBACK)
        self.assertEqual(result["outcome"], "ROUTE_ROLLBACK_EVIDENCE")
        self.assertEqual(result["reason_code"], "DRIFT_REQUIRES_ROLLBACK_EVIDENCE_ROUTE")
        self.assertFalse(result["g5_manual_action_authorized"])
        self.assertNotIn("destructive_action_authorized", result)
        _validate_schema(result)

    def test_compatible_drift_continues(self):
        result = _base(runtime_node_version="1.0.1", compatibility_rule="COMPATIBLE")
        self.assertEqual(result["outcome"], "CONTINUE_COMPATIBLE")
        self.assertTrue(result["drift_detected"])

    def test_replan_route_new_epoch(self):
        result = _base(runtime_node_version="2.0.0", compatibility_rule="NEW_EPOCH_REQUIRED")
        self.assertEqual(result["outcome"], "ROUTE_NEW_EPOCH")
        self.assertTrue(result["new_epoch_required"])

    def test_governed_repair_route(self):
        result = _base(runtime_node_version="2.0.0", compatibility_rule="GOVERNED_REPAIR_REQUIRED")
        self.assertEqual(result["outcome"], "ROUTE_GOVERNED_REPAIR")
        self.assertTrue(result["governed_repair_required"])
        self.assertFalse(result["g5_manual_action_authorized"])

    def test_blocked_human_required_route(self):
        result = _base(runtime_node_version="2.0.0", compatibility_rule="UNKNOWN")
        self.assertEqual(result["outcome"], "BLOCK_UNSUPPORTED_DRIFT")
        self.assertEqual(result["reason_code"], "NO_COMPATIBILITY_RULE_FOR_DRIFT")

    def test_deterministic_replay_same_digest(self):
        a = _base(observed_at=NOW)
        b = _base(observed_at=NOW)
        self.assertEqual(a["decision_digest"], b["decision_digest"])


if __name__ == "__main__":
    unittest.main()
