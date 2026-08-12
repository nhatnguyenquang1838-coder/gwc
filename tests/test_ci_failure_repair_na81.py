"""NA81 current-task proof tests for SCRUM-322 (repo_delivery.ci-failure-repair).

These tests pin the *current* SCRUM-322 NA81 execution brief against the
already-merged implementation on pre-prod. They are the current-task
requirement -> code -> test evidence map that distinguishes DELIVERY from
historical reuse (SCRUM-315 post-mortem: existing code/tests present is NOT
proof the current task is delivered).

Import path note (SCRUM-323 lesson): CI runs plain
`python -m unittest discover` from the repo root under Py3.12 namespace
packages, where only the `tools` package is importable directly. We insert the
absolute `tools/` directory into sys.path[0] and import via
`tools.node_architect...` so the test imports cleanly under CI.
"""
from __future__ import annotations

import os
import sys
import unittest

# Ensure the repo `tools` package is importable under CI namespace resolution.
_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from tools.node_architect.ci_failure_repair import (  # noqa: E402
    _classify_failure,
    classify_ci_failure,
)


def _base(**overrides):
    base = dict(
        task_id="SCRUM-322",
        repository="nhatnguyenquang1838-coder/gwc",
        pr_number=99,
        head_sha="f" * 40,
        run_id="run-na81-1",
        workflow_name="validate",
        failure_text="ModuleNotFoundError: No module named 'tools.node_architect.package_export'",
        approved_file_scope=["tools/node_architect/package_export/__init__.py"],
        event_id_or_idempotency_key="na81-evt-1",
    )
    base.update(overrides)
    return base


class TestNa81TypedBlockers(unittest.TestCase):
    """Current brief: external/unknown/out-of-scope/authority-lacking failures
    MUST stop with a typed blocker (fail closed)."""

    def test_external_failure_blocked_typed(self):
        # Out-of-scope / authority-lacking external failure -> EXTERNAL_BLOCKED.
        d = classify_ci_failure(
            **_base(failure_text="Connection timed out fetching upstream registry")
        )
        self.assertEqual(d["decision"], "EXTERNAL_BLOCKED")
        self.assertEqual(d["reason_code"], "CI_EXTERNAL_FAILURE")
        self.assertFalse(d["is_repo_fixable"])
        self.assertIsNone(d["remediation_scope"])
        # A blocked failure must NOT authorize any repair (no new head).
        self.assertFalse(d["invalidate_prior_head_evidence"])

    def test_unknown_failure_fails_closed(self):
        # Unknown / unclear failure mode -> fail closed, never auto-repair.
        d = classify_ci_failure(**_base(failure_text="the_great_unknown_failure_mode"))
        self.assertEqual(d["decision"], "EVIDENCE_INVALID")
        self.assertEqual(d["reason_code"], "CI_EVIDENCE_INVALID")
        self.assertFalse(d["is_repo_fixable"])

    def test_missing_approved_scope_blocked(self):
        # Authority-lacking: no approved scope => cannot authorize repair.
        d = classify_ci_failure(
            **_base(failure_text="ModuleNotFoundError: x", approved_file_scope=None)
        )
        self.assertEqual(d["decision"], "EVIDENCE_INVALID")
        self.assertEqual(d["reason_code"], "CI_REPAIR_SCOPE_MISSING")
        self.assertFalse(d["is_repo_fixable"])
        self.assertIsNone(d["remediation_scope"])


class TestNa81BoundedRepair(unittest.TestCase):
    """Current brief: permit only the smallest repository-fixable repair inside
    the approved scope; every repair creates a new head and invalidates prior
    CI/review evidence."""

    def test_repo_fixable_inside_scope(self):
        d = classify_ci_failure(**_base())
        self.assertEqual(d["decision"], "REPAIR_REPOSITORY")
        self.assertEqual(d["reason_code"], "CI_REPO_FIXABLE")
        self.assertTrue(d["is_repo_fixable"])
        self.assertEqual(
            d["remediation_scope"],
            "bounded-pr:99:tools/node_architect/package_export/__init__.py",
        )

    def test_new_head_invalidates_prior_evidence(self):
        # Every repair decision creates a new head; prior evidence is stale.
        d = classify_ci_failure(**_base())
        self.assertTrue(d["invalidate_prior_head_evidence"])
        # execution_performed stays False: this node decides, it does not merge
        # or mutate the repository (bounded-repair authority only).
        self.assertFalse(d["execution_performed"])

    def test_classification_performs_no_execution(self):
        # Historical SCRUM-199 is evidence only: the classifier never performs
        # a repair / merge. It classifies and returns a decision artifact.
        before = _classify_failure("ModuleNotFoundError: x")
        d = classify_ci_failure(**_base())
        self.assertEqual(before, "REPAIR_REPOSITORY")
        self.assertFalse(d["execution_performed"])
        self.assertNotIn("merge", (d["remediation_scope"] or "").lower())

    def test_no_merge_authority_ever(self):
        for ft in (
            "ModuleNotFoundError: x",
            "Connection timed out",
            "the_great_unknown_failure_mode",
        ):
            with self.subTest(ft=ft):
                d = classify_ci_failure(**_base(failure_text=ft))
                self.assertNotEqual(d["decision"], "MERGE")
                self.assertNotIn("merge", (d["remediation_scope"] or "").lower())


class TestNa81Replay(unittest.TestCase):
    """Replay/idempotency conflict detection on the same idempotency key."""

    def test_replay_conflict_detected(self):
        prior = {"event_id_or_idempotency_key": "na81-evt-1"}
        d = classify_ci_failure(**_base(prior_escalation=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")

    def test_replay_idempotent_for_new_key(self):
        d = classify_ci_failure(**_base(event_id_or_idempotency_key="na81-evt-fresh"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")


if __name__ == "__main__":
    unittest.main()
