"""M5 tests for deterministic CI failure classification (SCRUM-322)."""
from __future__ import annotations

import datetime
import unittest

from tools.node_architect.ci_failure_repair import (
    _classify_failure,
    classify_ci_failure,
)


def _base(**overrides):
    base = dict(
        task_id="SCRUM-322",
        repository="nhatnguyenquang1838-coder/gwc",
        pr_number=42,
        head_sha="a" * 40,
        run_id="run-1",
        workflow_name="validate",
        failure_text="ModuleNotFoundError: No module named 'tools.node_architect.package_export'",
        failure_type="import_error",
        job_name="validate",
        step_name="python -m pytest",
        approved_file_scope=["tools/node_architect/package_export/__init__.py"],
        event_id_or_idempotency_key="evt-1",
    )
    base.update(overrides)
    return base


class TestClassifyFailure(unittest.TestCase):
    def test_repo_fixable_import(self):
        self.assertEqual(
            _classify_failure("ModuleNotFoundError: No module named xyz"),
            "REPAIR_REPOSITORY",
        )

    def test_repo_fixable_test_failure(self):
        self.assertEqual(
            _classify_failure("FAILED tests/test_x.py::test_y"),
            "REPAIR_REPOSITORY",
        )

    def test_external_timeout(self):
        self.assertEqual(
            _classify_failure("Connection timed out while fetching upstream"),
            "EXTERNAL_BLOCKED",
        )

    def test_external_502(self):
        self.assertEqual(
            _classify_failure("HTTP 502 Bad Gateway from upstream API"),
            "EXTERNAL_BLOCKED",
        )

    def test_unknown_fails_closed(self):
        self.assertEqual(
            _classify_failure("the_great_unknown_failure_mode"),
            "EVIDENCE_INVALID",
        )

    def test_repo_fixable_wins_over_external_when_both_match(self):
        # repo-fixable pattern takes precedence when present (implements
        # deterministic conservative ordering).
        text = (
            "Error during connection: ModuleNotFoundError while running ruff "
            "502 Bad Gateway NameError"
        )
        # Both patterns match; implementation prioritizes REPAIR_REPOSITORY
        # when at least one repo-fixable pattern matches.
        self.assertEqual(_classify_failure(text), "REPAIR_REPOSITORY")


class TestClassifyCiFailure(unittest.TestCase):
    def test_repair_repository_decision(self):
        d = classify_ci_failure(**_base())
        self.assertEqual(d["decision"], "REPAIR_REPOSITORY")
        self.assertTrue(d["is_repo_fixable"])
        self.assertEqual(
            d["remediation_scope"],
            "bounded-pr:42:tools/node_architect/package_export/__init__.py",
        )
        self.assertTrue(d["invalidate_prior_head_evidence"])

    def test_external_blocked_decision(self):
        d = classify_ci_failure(
            **_base(failure_text="Connection timed out fetching dependency")
        )
        self.assertEqual(d["decision"], "EXTERNAL_BLOCKED")
        self.assertFalse(d["is_repo_fixable"])
        self.assertIsNone(d["remediation_scope"])
        self.assertFalse(d["invalidate_prior_head_evidence"])

    def test_evidence_invalid_when_scope_missing(self):
        d = classify_ci_failure(
            **_base(
                failure_text="ModuleNotFoundError: x",
                approved_file_scope=None,
            )
        )
        self.assertEqual(d["decision"], "EVIDENCE_INVALID")
        self.assertEqual(d["reason_code"], "CI_REPAIR_SCOPE_MISSING")

    def test_execution_performed_is_always_false(self):
        for decision in ("REPAIR_REPOSITORY", "EXTERNAL_BLOCKED", "EVIDENCE_INVALID"):
            with self.subTest(decision=decision):
                d = classify_ci_failure(
                    **_base(failure_text="ModuleNotFoundError: x" if decision == "REPAIR_REPOSITORY" else "timeout")
                )
                self.assertFalse(d["execution_performed"])

    def test_deterministic_digest(self):
        a = classify_ci_failure(**_base())
        b = classify_ci_failure(**_base())
        self.assertEqual(a["escalation_digest"], b["escalation_digest"])

    def test_replay_idempotent(self):
        d = classify_ci_failure(**_base(event_id_or_idempotency_key="evt-2"))
        self.assertEqual(d["replay_status"], "IDEMPOTENT")

    def test_replay_conflict(self):
        prior = {"event_id_or_idempotency_key": "evt-1"}
        d = classify_ci_failure(**_base(prior_escalation=prior))
        self.assertEqual(d["replay_status"], "CONFLICT")

    def test_invalid_task_id_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(task_id="BAD"))

    def test_invalid_repository_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(repository="not-a-repo"))

    def test_invalid_head_sha_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(head_sha="xyz"))

    def test_missing_run_id_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(run_id=""))

    def test_missing_workflow_name_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(workflow_name=""))

    def test_missing_failure_text_rejected(self):
        with self.assertRaises(ValueError):
            classify_ci_failure(**_base(failure_text=""))

    def test_digest_format(self):
        d = classify_ci_failure(**_base())
        self.assertRegex(d["escalation_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_schema_version_and_artifact_type(self):
        d = classify_ci_failure(**_base())
        self.assertEqual(d["schema_version"], "1.0")
        self.assertEqual(d["artifact_type"], "ci-failure-repair")

    def test_decided_at_defaults_to_none(self):
        d = classify_ci_failure(**_base())
        self.assertIsNone(d["decided_at"])

    def test_decided_at_set(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        d = classify_ci_failure(**_base(decided_at=now))
        self.assertEqual(d["decided_at"], now)

    def test_pip_install_failure_is_repair(self):
        self.assertEqual(
            _classify_failure("pip install -r requirements.txt failed"),
            "REPAIR_REPOSITORY",
        )

    def test_runner_offline_is_external(self):
        self.assertEqual(
            _classify_failure("self-hosted runner offline, cannot schedule"),
            "EXTERNAL_BLOCKED",
        )

    def test_failure_text_is_normalized_to_str(self):
        d = classify_ci_failure(**_base(failure_text=123))
        self.assertIsInstance(d["failure_text"], str)
        self.assertEqual(d["failure_text"], "123")

    def test_decision_never_grants_merge_authority(self):
        d = classify_ci_failure(**_base())
        self.assertNotEqual(d["decision"], "MERGE")
        self.assertNotIn("merge", d["remediation_scope"] or "")


if __name__ == "__main__":
    unittest.main()
