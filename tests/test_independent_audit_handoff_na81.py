#!/usr/bin/env python3
"""NA81 current-task evidence tests for scale_control.independent-audit-handoff (SCRUM-378).

Per SCRUM-323 import-path lesson: insert the absolute tools/ dir into sys.path[0]
so `import node_architect...` resolves under CI `python -m unittest discover`
(Python 3.12 namespace packages make only `tools` importable directly).
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))

import node_architect.independent_audit_handoff as iah  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "4c3ca535a3e9d9c71fb4bd0ca7e0f0264e664f3a"
HEAD = "c" * 40
BRANCH = "auto/SCRUM-378-na81-20260810"
REV = "sha256:" + "a" * 64
NOW = "2026-08-11T18:00:00Z"


def _ci(workflow, conclusion="success", head=HEAD, run_id=1):
    return {"workflow": workflow, "run_id": run_id, "conclusion": conclusion, "head_sha": head}


def _base(**overrides):
    payload = dict(
        task_id="SCRUM-378",
        repository=REPO,
        branch=BRANCH,
        base_sha=BASE,
        head_sha=HEAD,
        package_revision=REV,
        expected_revision=REV,
        completeness_manifest={"families": 9, "nodes": 81, "artifacts": ["catalog", "schemas", "tests", "g5-evidence"]},
        ci_evidence=[_ci("Validate instructions", run_id=1), _ci("Build instruction packages", run_id=2)],
        limitation_disclosures=["no_production_scale_authority", "no_deployment_authority", "independent_audit_required"],
        reviewer="independent-auditor-x",
    )
    payload.update(overrides)
    return iah.decide_independent_audit_handoff(**payload)


def _validate_schema(payload):
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "schemas" / "independent-audit-handoff-decision.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda e: list(e.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


class IndependentAuditHandoffNA81Tests(unittest.TestCase):
    def test_current_task_ready_with_full_evidence_map(self):
        """Current SCRUM-378 brief: evidence map binds each requirement to exact source."""
        evidence_map = [
            {"requirement": "exact head/scope bound", "source": "git rev-parse pre-prod", "status": "proven"},
            {"requirement": "DAG/dependencies enumerated", "source": "Jira SCRUM-378 issuelinks", "status": "proven"},
            {"requirement": "no merge/scale/deploy authority", "source": "decision flags all False", "status": "proven"},
        ]
        result = _base(
            implementer="hermes-agent",
            evidence_map=evidence_map,
            dag_dependencies=["SCRUM-377"],
            exclusions=["no main merge", "no deploy", "no production data"],
            findings=["node descriptor minimal; brief authoritative"],
            unresolved_risks=["remaining 80 nodes still In Progress on board"],
            next_legal_action="Human G4 promotes pre-prod -> main",
        )
        self.assertEqual(result["handoff_status"], "READY_FOR_INDEPENDENT_AUDIT")
        self.assertEqual(result["reason_code"], "REVISION_BOUND_AUDIT_HANDOFF_READY")
        self.assertTrue(result["reviewer_independent"])
        self.assertEqual(result["evidence_map"], evidence_map)
        self.assertEqual(result["unverified_evidence"], [])
        self.assertEqual(result["dag_dependencies"], ["SCRUM-377"])
        self.assertEqual(result["exclusions"], ["no main merge", "no deploy", "no production data"])
        self.assertEqual(result["next_legal_action"], "Human G4 promotes pre-prod -> main")
        _validate_schema(result)

    def test_reviewer_conflict_blocks_handoff(self):
        """Brief: verify implementer/reviewer independence; reviewer conflict must BLOCK."""
        result = _base(implementer="hermes-agent", reviewer="hermes-agent")
        self.assertEqual(result["handoff_status"], "BLOCKED")
        self.assertEqual(result["reason_code"], "REVIEWER_CONFLICT")
        self.assertFalse(result["reviewer_independent"])

    def test_missing_or_stale_evidence_stays_explicit(self):
        """Brief: missing/stale evidence stays explicit (surfaced, not auto-passed)."""
        evidence_map = [
            {"requirement": "exact head/scope bound", "source": "git rev-parse pre-prod", "status": "proven"},
            {"requirement": "G5 readback for all delivered nodes", "source": "MISSING", "status": "missing"},
            {"requirement": "reviewer independence proof", "source": "stale comment 2026-08-01", "status": "stale"},
        ]
        result = _base(evidence_map=evidence_map)
        self.assertEqual(result["handoff_status"], "READY_FOR_INDEPENDENT_AUDIT")
        self.assertEqual(set(result["unverified_evidence"]), {"G5 readback for all delivered nodes", "reviewer independence proof"})
        _validate_schema(result)

    def test_invalid_evidence_map_blocks(self):
        result = _base(evidence_map=[{"requirement": "", "status": "proven"}])
        self.assertEqual(result["reason_code"], "INVALID_EVIDENCE_MAP")
        result2 = _base(evidence_map=[{"requirement": "x", "status": "bogus"}])
        self.assertEqual(result2["reason_code"], "INVALID_EVIDENCE_MAP")

    def test_explicit_no_authority_fields_remain_false(self):
        result = _base(implementer="other", evidence_map=[{"requirement": "r", "source": "s", "status": "proven"}])
        for key in ("merge_authority_granted", "deployment_authority_granted",
                    "production_authority_granted", "scale_authority_granted",
                    "audit_completion_authority_granted"):
            self.assertFalse(result[key], key)
        self.assertTrue(result["read_only_projection"])

    def test_deterministic_replay_same_digest(self):
        args = dict(
            implementer="other",
            evidence_map=[{"requirement": "r", "source": "s", "status": "proven"}],
            dag_dependencies=["SCRUM-377"],
            exclusions=["x"], findings=["f"], unresolved_risks=["u"],
            next_legal_action="Human G4",
        )
        a = _base(**args)
        b = _base(**args)
        self.assertEqual(a["decision_digest"], b["decision_digest"])

    def test_missing_exact_sha_fails_closed_regression(self):
        result = _base(base_sha="zzz")
        self.assertEqual(result["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")


if __name__ == "__main__":
    import unittest
    unittest.main()
