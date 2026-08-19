"""NA81 current-task proof tests for SCRUM-322 (repo_delivery.ci-failure-repair).

These tests pin the current SCRUM-322 NA81 execution brief against the
already-merged implementation on pre-prod. They are the current-task
requirement -> code -> test proof that distinguishes DELIVERY from historical
reuse. Existing code or historical SCRUM-199 is evidence only, not current-task
completion.
"""
from __future__ import annotations

import os
import sys
import unittest

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
    def test_external_failure_blocked_typed(self):
        d = classify_ci_failure(
            **_base(failure_text="Connection timed out fetching upstream registry")
        )
        self.assertEqual(d["decision"], "EXTERNAL_BLOCKED")
        self.assertEqual(d["reason_code"], "CI_EXTERNAL_FAILURE")
        self.assertFalse(d["is_repo_fixable"])
        self.assertIsNone(d["remediation_scope"])
        self.assertFalse(d["invalidate_prior_head_evidence"])

    def test_unknown_failure_fails_closed(self):
        d = classify_ci_failure(**_base(failure_text="the_great_unknown_failure_mode"))
        self.assertEqual(d["decision"], "EVIDENCE_INVALID")
        self.assertEqual(d["reason_code"], "CI_EVIDENCE_INVALID")
        self.assertFalse(d["is_repo_fixable"])

    def test_missing_approved_scope_blocked(self):
        d = classify_ci_failure(
            **_base(failure_text="ModuleNotFoundError: x", approved_file_scope=None)
        )
        self.assertEqual(d["decision"], "EVIDENCE_INVALID")
        self.assertEqual(d["reason_code"], "CI_REPAIR_SCOPE_MISSING")
        self.assertFalse(d["is_repo_fixable"])
        self.assertIsNone(d["remediation_scope"])


class TestNa81BoundedRepair(unittest.TestCase):
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
        d = classify_ci_failure(**_base())
        self.assertTrue(d["invalidate_prior_head_evidence"])
        self.assertFalse(d["execution_performed"])

    def test_classification_performs_no_execution(self):
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
    def test_replay_conflict_detected(self):
        prior = {"event_id_or_idempotency_key": "na81-evt-1"}
        d = classify_ci_failure(**_base(prior_escalation=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")

    def test_replay_idempotent_for_new_key(self):
        d = classify_ci_failure(**_base(event_id_or_idempotency_key="na81-evt-fresh"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")


if __name__ == "__main__":
    unittest.main()
