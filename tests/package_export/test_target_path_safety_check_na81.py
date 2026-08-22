#!/usr/bin/env python3
"""NA81 recert tests for package_export.target_path_safety_check (SCRUM-355, F7-N04).

Bound to the exact executable module
`tools/node_architect/package_export/target_path_safety_check.py`. These tests
prove the gate evaluator's fail-closed safety contract for the NA81 autonomous
lane recert: safe vs unsafe target paths, traversal/escape rejection,
normalization, dedupe/collision, overwrite/idempotency, and that the evaluator
grants no authority and performs no filesystem side effects.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from node_architect.package_export.target_path_safety_check import (  # noqa: E402
    DEFAULT_APPROVED_PREFIX,
    OVERWRITE_POLICY_BLOCK,
    OVERWRITE_POLICY_IDEMPOTENT,
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
    authority_granted,
    evaluate_target,
    evaluate_targets,
)

ROOT = ".governance"


class TestTargetPathSafetyCheckNA81(unittest.TestCase):
    # --- safe paths -------------------------------------------------------
    def test_nested_governance_target_is_safe(self):
        d = evaluate_target(".governance/runtime/checks/check.json", ROOT)
        self.assertEqual(d.outcome, Outcome.PASS)
        self.assertEqual(d.reason, TARGET_PATH_SAFE)
        self.assertEqual(d.normalized, ".governance/runtime/checks/check.json")
        self.assertIsNotNone(d.semantic_digest)

    def test_dot_normalized_away_is_safe(self):
        d = evaluate_target(".governance/./nested/./a.json", ROOT)
        self.assertEqual(d.outcome, Outcome.PASS)
        self.assertEqual(d.normalized, ".governance/nested/a.json")

    # --- absolute paths ---------------------------------------------------
    def test_posix_absolute_rejected(self):
        d = evaluate_target("/etc/passwd", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_ABSOLUTE)

    def test_windows_absolute_rejected(self):
        d = evaluate_target("C:\\windows\\evil.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_ABSOLUTE)

    # --- traversal / escape ----------------------------------------------
    def test_traversal_rejected(self):
        d = evaluate_target(".governance/../escape.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_TRAVERSAL)

    def test_backslash_only_rejected(self):
        d = evaluate_target(".governance\\evil.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_BACKSLASH)

    def test_root_escape_rejected(self):
        d = evaluate_target("../../.governance/x.json", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertIn(d.reason, (TARGET_PATH_TRAVERSAL, TARGET_PATH_ESCAPES_ROOT))

    def test_prefix_forbidden_when_outside_approved(self):
        d = evaluate_target("src/leak.py", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PREFIX_FORBIDDEN)

    def test_empty_target_rejected(self):
        d = evaluate_target("", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_EMPTY)

    def test_whitespace_only_target_rejected(self):
        d = evaluate_target("   ", ROOT)
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_PATH_EMPTY)

    # --- duplicate / collision --------------------------------------------
    def test_duplicate_normalized_target_detected(self):
        plan = evaluate_targets([".governance/a.json", ".governance/./a.json"], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertIn(TARGET_DUPLICATE, reasons)

    def test_case_collision_detected(self):
        plan = evaluate_targets([".governance/A.json", ".governance/a.json"], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertIn(TARGET_CASE_COLLISION, reasons)

    def test_self_copy_conflict_detected(self):
        plan = evaluate_targets([ROOT, ROOT], ROOT)
        reasons = [d.reason for d in plan.decisions]
        self.assertIn(TARGET_SYMLINK_ESCAPE, reasons)

    # --- overwrite / idempotency ------------------------------------------
    def test_existing_divergent_blocks_overwrite(self):
        state = {".governance/x.json": "differentdigest"}
        d = evaluate_target(
            ".governance/x.json",
            ROOT,
            overwrite_policy=OVERWRITE_POLICY_BLOCK,
            existing_state=state,
        )
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_OVERWRITE_FORBIDDEN)

    def test_existing_unknown_readback_blocks(self):
        state = {".governance/x.json": None}
        d = evaluate_target(
            ".governance/x.json",
            ROOT,
            overwrite_policy=OVERWRITE_POLICY_IDEMPOTENT,
            existing_state=state,
        )
        self.assertEqual(d.outcome, Outcome.FAIL)
        self.assertEqual(d.reason, TARGET_OVERWRITE_FORBIDDEN)

    def test_idempotent_identical_passes(self):
        state = {".governance/x.json": "run123"}
        d = evaluate_target(
            ".governance/x.json",
            ROOT,
            overwrite_policy=OVERWRITE_POLICY_IDEMPOTENT,
            run_identity="run123",
            existing_state=state,
        )
        self.assertEqual(d.outcome, Outcome.PASS)
        self.assertEqual(d.overwrite_decision, "idempotent_identical")

    # --- determinism / contract ------------------------------------------
    def test_deterministic_digest_same_input(self):
        a = evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        c = evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        self.assertEqual(a.semantic_digest, c.semantic_digest)

    def test_no_filesystem_side_effect(self):
        before = set(os.listdir("."))
        evaluate_targets([".governance/a.json", ".governance/b.json"], ROOT)
        after = set(os.listdir("."))
        self.assertEqual(before, after)

    def test_authority_never_granted(self):
        plan = evaluate_targets([".governance/a.json"], ROOT)
        self.assertFalse(authority_granted(plan))

    def test_approved_prefix_default(self):
        self.assertEqual(DEFAULT_APPROVED_PREFIX, ".governance/")


if __name__ == "__main__":
    unittest.main()
