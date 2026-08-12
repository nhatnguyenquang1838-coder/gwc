#!/usr/bin/env python3
"""NA81 tests for scale_control.exact-head-readiness-check (SCRUM-376, F9-N07)."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.exact_head_readiness import (
    MIXED_HEAD_EVIDENCE_BLOCKED,
    BLOCKER_FINDINGS_PRESENT,
    SCOPE_DRIFT_DETECTED,
    decide_exact_head_readiness,
)

BASE = "4c3ca535a3e9d9c71fb4bd0ca7e0f0264e664f3a"
HEAD = "c" * 40
OLD = "d" * 40
BRANCH = "auto/SCRUM-376-na81-20260810"
REPO = "nhatnguyenquang1838-coder/gwc"
NOW = "2026-08-12T14:20:00Z"
REV = "sha256:" + "a" * 64


def validate_schema(file_name: str, payload: dict) -> None:
    schema = json.loads(Path("schemas", file_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


def check(name, *, head=HEAD, status="completed", conclusion="success"):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "head_sha": head,
    }


def artifact(name, *, head=HEAD, digest=REV):
    return {"name": name, "head_sha": head, "digest": digest}


def exact_head(**overrides):
    payload = dict(
        task_id="SCRUM-376",
        repository=REPO,
        branch=BRANCH,
        base_sha=BASE,
        current_head_sha=HEAD,
        expected_head_sha=HEAD,
        required_check_names=["validate-instructions", "build-project-package"],
        observed_checks=[check("validate-instructions"), check("build-project-package")],
        required_artifact_names=["instruction-package-gwc"],
        observed_artifacts=[artifact("instruction-package-gwc")],
        connector_status="CONFIRMED",
        exact_head_filter_applied=True,
        blocker_findings=None,
        scope_drift_detected=False,
        observed_at=NOW,
    )
    payload.update(overrides)
    return decide_exact_head_readiness(**payload)


class ExactHeadReadinessNA81Tests(unittest.TestCase):
    def test_exact_clean_readiness_passes(self):
        result = exact_head()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EXACT_HEAD_READY")
        self.assertFalse(result["scale_authority_granted"])
        self.assertEqual(result["blocker_findings"], [])
        self.assertFalse(result["scope_drift_detected"])
        validate_schema("exact-head-readiness-decision.schema.json", result)

    def test_stale_expected_head_is_rejected(self):
        self.assertEqual(
            exact_head(expected_head_sha=OLD)["reason_code"], "STALE_HEAD_REJECTED"
        )

    def test_missing_required_check_blocks(self):
        result = exact_head(observed_checks=[check("validate-instructions")])
        self.assertEqual(result["reason_code"], "REQUIRED_CHECK_MISSING")
        self.assertEqual(result["missing_check_names"], ["build-project-package"])

    def test_failed_or_pending_required_check_blocks(self):
        self.assertEqual(
            exact_head(observed_checks=[
                check("validate-instructions", conclusion="failure"),
                check("build-project-package"),
            ])["reason_code"],
            "REQUIRED_CHECK_FAILED",
        )
        self.assertEqual(
            exact_head(observed_checks=[
                check("validate-instructions", status="in_progress", conclusion=None),
                check("build-project-package"),
            ])["reason_code"],
            "REQUIRED_CHECK_NON_TERMINAL",
        )

    def test_wrong_head_required_check_is_missing(self):
        result = exact_head(
            observed_checks=[
                check("validate-instructions", head=OLD),
                check("build-project-package", head=OLD),
            ]
        )
        self.assertEqual(result["reason_code"], "REQUIRED_CHECK_MISSING")

    def test_missing_artifact_blocks(self):
        self.assertEqual(
            exact_head(observed_artifacts=[])["reason_code"], "REQUIRED_ARTIFACT_MISSING"
        )

    def test_connector_visibility_gap_is_fail_closed(self):
        self.assertEqual(
            exact_head(connector_status="UNSUPPORTED", exact_head_filter_applied=False)["reason_code"],
            "CONNECTOR_OBSERVABILITY_INCOMPLETE",
        )
        self.assertEqual(
            exact_head(connector_status="EMPTY", exact_head_filter_applied=False)["reason_code"],
            "EMPTY_UNFILTERED_CONNECTOR_RESULT",
        )

    def test_mixed_head_evidence_blocks(self):
        """A stale (wrong-head) required check alongside an exact check must BLOCK."""
        # Exact check comes AFTER stale duplicate so check_by_name captures the exact one.
        result = exact_head(
            observed_checks=[
                check("validate-instructions", head=HEAD),
                check("build-project-package", head=OLD),
                check("build-project-package", head=HEAD),
            ]
        )
        self.assertEqual(result["reason_code"], MIXED_HEAD_EVIDENCE_BLOCKED)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertFalse(result["readiness_passed"])

    def test_mixed_head_artifact_evidence_blocks(self):
        # Required artifact exact + extra stale duplicate for same name.
        result = exact_head(
            observed_artifacts=[
                artifact("instruction-package-gwc", head=HEAD),
                artifact("instruction-package-gwc", head=OLD),
            ]
        )
        self.assertEqual(result["reason_code"], MIXED_HEAD_EVIDENCE_BLOCKED)
        self.assertEqual(result["outcome"], "BLOCKED")

    def test_blocker_findings_present_blocks(self):
        # All required checks exact and successful; blocker_findings should block.
        result = exact_head(
            observed_checks=[
                check("validate-instructions", head=HEAD),
                check("build-project-package", head=HEAD),
            ],
            blocker_findings=["MAJOR: unreviewed G3 finding", "UNRESOLVED: scope boundary leak"],
        )
        self.assertEqual(result["reason_code"], BLOCKER_FINDINGS_PRESENT)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertFalse(result["readiness_passed"])

    def test_scope_drift_detected_blocks(self):
        result = exact_head(scope_drift_detected=True)
        self.assertEqual(result["reason_code"], SCOPE_DRIFT_DETECTED)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertTrue(result["scope_drift_detected"])
        self.assertFalse(result["readiness_passed"])

    def test_invalid_blocker_findings_are_rejected(self):
        result = exact_head(blocker_findings=["ok", 123])
        self.assertEqual(result["reason_code"], "INVALID_BLOCKER_FINDINGS")

    def test_replay_same_inputs_produce_same_result(self):
        result_a = exact_head(observed_at="2026-08-12T10:00:00Z")
        result_b = exact_head(observed_at="2026-08-12T10:00:00Z")
        self.assertEqual(result_a["outcome"], result_b["outcome"])
        self.assertEqual(result_a["reason_code"], result_b["reason_code"])
        self.assertEqual(result_a["decision_digest"], result_b["decision_digest"])
        # Different observed_at should still yield same decision
        result_c = exact_head(observed_at="2099-01-01T00:00:00Z")
        self.assertEqual(result_c["outcome"], result_a["outcome"])
        self.assertEqual(result_c["reason_code"], result_a["reason_code"])


if __name__ == "__main__":
    unittest.main()
