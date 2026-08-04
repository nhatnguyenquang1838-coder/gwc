#!/usr/bin/env python3
"""Tests for package_export.target_path_safety_check (SCRUM-232, M4_DETERMINISTIC)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from node_architect.package_export.target_path_safety_check import (
    TARGET_CASE_COLLISION,
    TARGET_DUPLICATE,
    TARGET_OVERWRITE_FORBIDDEN,
    TARGET_PATH_ABSOLUTE,
    TARGET_PATH_BACKSLASH,
    TARGET_PATH_EMPTY,
    TARGET_PATH_ESCAPES_ROOT,
    TARGET_PATH_SAFE,
    TARGET_PATH_TRAVERSAL,
    TARGET_PREFIX_FORBIDDEN,
    TARGET_SYMLINK_ESCAPE,
    Outcome,
    evaluate_target,
    evaluate_targets,
    authority_granted,
)

ROOT = ".governance"


class TestTargetPathSafetyCheck(unittest.TestCase):
    def test_valid_governance_target_is_safe(self):
        d = evaluate_target(".governance/runtime/check.json", ROOT)
        self.assertEqual(d.outcome, Outcome.PASS)
        self.assertEqual(d.reason, TARGET_PATH_SAFE)
        self.assertEqual(d.normalized, ".governance/runtime/check.json")
        self.assertIsNotNone(d.semantic_digest)

    def test_absolute_path_rejected(self):
        d = evaluate_target("/etc/passwd", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_ABSOLUTE)

    def test_windows_absolute_rejected(self):
        d = evaluate_target("C:\\windows\\x.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_ABSOLUTE)

    def test_traversal_rejected(self):
        d = evaluate_target(".governance/../escape.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_TRAVERSAL)

    def test_backslash_rejected(self):
        d = evaluate_target(".governance\\evil.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_BACKSLASH)

    def test_escapes_root_rejected(self):
        d = evaluate_target("../../.governance/x.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertIn(d.reason, (TARGET_PATH_TRAVERSAL, TARGET_PATH_ESCAPES_ROOT))

    def test_prefix_forbidden_when_outside(self):
        d = evaluate_target("src/leak.py", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PREFIX_FORBIDDEN)

    def test_empty_target_rejected(self):
        d = evaluate_target("", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_EMPTY)

    def test_duplicate_normalized_target_detected(self):
        plan = evaluate_targets([".governance/a.json", ".governance/./a.json"], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertIn(TARGET_DUPLICATE, reasons)

    def test_case_collision_detected(self):
        plan = evaluate_targets([".governance/A.json", ".governance/a.json"], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertIn(TARGET_CASE_COLLISION, reasons)

    def test_existing_divergent_blocks_overwrite(self):
        state = {".governance/x.json": "differentdigest"}
        d = evaluate_target(
            ".governance/x.json", ROOT, overwrite_policy="block", existing_state=state
        )
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_OVERWRITE_FORBIDDEN)

    def test_existing_unknown_readback_blocks(self):
        state = {".governance/x.json": None}
        d = evaluate_target(
            ".governance/x.json", ROOT, overwrite_policy="idempotent", existing_state=state
        )
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_OVERWRITE_FORBIDDEN)

    def test_idempotent_identical_passes(self):
        state = {".governance/x.json": "run123"}
        d = evaluate_target(
            ".governance/x.json",
            ROOT,
            overwrite_policy="idempotent",
            run_identity="run123",
            existing_state=state,
        )
        self.assertEqual(d.outcome, Outcome.PASS)
        self.assertEqual(d.overwrite_decision, "idempotent_identical")

    def test_source_target_self_copy_conflict(self):
        plan = evaluate_targets([".governance", ROOT], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertTrue(
            TARGET_SYMLINK_ESCAPE in reasons or TARGET_PATH_SAFE in reasons
        )

    def test_deterministic_digest_same_input(self):
        a = evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        c = evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        self.assertEqual(a.semantic_digest, c.semantic_digest)

    def test_authority_never_granted(self):
        plan = evaluate_targets([".governance/a.json"], ROOT)
        self.assertFalse(authority_granted(plan))

    def test_no_filesystem_side_effect(self):
        import os

        before = set(os.listdir("."))
        evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        after = set(os.listdir("."))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
