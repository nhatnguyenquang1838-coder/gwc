from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "validate_g3_delivery.py"
SCHEMA = ROOT / "schemas" / "g3-delivery-record.schema.json"
TEMPLATE = ROOT / "templates" / "gates" / "g3-delivery-record.template.yaml"

SPEC = importlib.util.spec_from_file_location("validate_g3_delivery", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class G3DeliveryRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.valid = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))

    def issues(self, record: dict) -> list[str]:
        return MODULE.validate_record(record, self.schema)

    def runtime_issues(
        self,
        record: dict,
        *,
        current_pr_head: str | None,
        implementation_ancestor_verified: bool,
        evidence_delta_paths: list[str],
        ci_checks: dict[str, str],
    ) -> list[str]:
        validator = getattr(MODULE, "validate_runtime_context", None)
        if validator is None:
            return ["validate_runtime_context missing"]
        return validator(
            record,
            current_pr_head=current_pr_head,
            implementation_ancestor_verified=implementation_ancestor_verified,
            evidence_delta_paths=evidence_delta_paths,
            ci_checks=ci_checks,
        )

    def test_template_is_v11_implementation_subject_contract(self) -> None:
        self.assertEqual("1.1", self.valid["schema_version"])
        self.assertIn("implementation_head_sha", self.valid)
        self.assertNotIn("head_sha", self.valid)
        self.assertIn("implementation_head_sha", self.valid["validation"])
        self.assertNotIn("head_sha", self.valid["validation"])
        self.assertIn("reviewed_implementation_head_sha", self.valid["review"])
        self.assertNotIn("reviewed_head_sha", self.valid["review"])
        self.assertNotIn("head_sha", self.valid["ci"])

    def test_valid_template_passes_subject_validation(self) -> None:
        self.assertEqual([], self.issues(copy.deepcopy(self.valid)))

    def test_review_implementation_head_mismatch_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["reviewed_implementation_head_sha"] = "d" * 40
        self.assertTrue(
            any("reviewed_implementation_head_sha" in issue for issue in self.issues(record))
        )

    def test_stale_review_fails_pass_outcome(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["stale"] = True
        self.assertTrue(any("stale=false" in issue for issue in self.issues(record)))

    def test_independent_reviewer_must_differ_from_implementer(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["reviewer_id"] = record["review"]["implementer_id"]
        self.assertTrue(any("must differ" in issue for issue in self.issues(record)))

    def test_open_blocker_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["findings"] = [{
            "id": "REV-1",
            "severity": "BLOCKER",
            "category": "code",
            "status": "open",
            "evidence": "broken invariant",
            "recommendation": "return to G2",
        }]
        self.assertTrue(any("BLOCKER" in issue for issue in self.issues(record)))

    def test_open_blocker_is_valid_for_changes_required(self) -> None:
        record = copy.deepcopy(self.valid)
        record["outcome"] = "fail"
        record["review"]["decision"] = "changes_required"
        record["review"]["findings"] = [{
            "id": "REV-1",
            "severity": "BLOCKER",
            "category": "code",
            "status": "open",
            "evidence": "broken invariant",
            "recommendation": "return to G2",
        }]
        self.assertEqual([], self.issues(record))

    def test_major_without_acceptance_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["findings"] = [{
            "id": "REV-2",
            "severity": "MAJOR",
            "category": "design",
            "status": "deferred",
            "evidence": "material risk",
            "recommendation": "resolve or accept",
        }]
        self.assertTrue(any("MAJOR" in issue for issue in self.issues(record)))

    def test_major_with_exact_implementation_head_acceptance_passes(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["findings"] = [{
            "id": "REV-3",
            "severity": "MAJOR",
            "category": "design",
            "status": "accepted_risk",
            "evidence": "known bounded risk",
            "recommendation": "record risk",
            "risk_acceptance": {
                "actor": "human-owner",
                "source": "task-comment",
                "accepted_at": "2026-07-15T04:35:00Z",
                "rationale": "accepted for this exact implementation subject",
                "implementation_head_sha": record["implementation_head_sha"],
            },
        }]
        self.assertEqual([], self.issues(record))

    def test_duplicate_lane_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["lanes"][-1]["name"] = "code"
        issues = self.issues(record)
        self.assertTrue(any("duplicate" in issue for issue in issues))
        self.assertTrue(any("missing required lanes" in issue for issue in issues))

    def test_unverified_acceptance_criterion_fails_pass_outcome(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["acceptance_criteria"][0]["result"] = "not_verified"
        self.assertTrue(any("AC-1" in issue for issue in self.issues(record)))

    def test_multiple_schema_errors_with_mixed_paths_are_reported(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["lanes"][0]["applicable"] = "yes"
        record["task_id"] = 7
        issues = self.issues(record)
        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(any("review.lanes.0.applicable" in issue for issue in issues))
        self.assertTrue(any("task_id" in issue for issue in issues))

    def test_pass_requires_external_current_pr_head(self) -> None:
        issues = self.runtime_issues(
            copy.deepcopy(self.valid),
            current_pr_head=None,
            implementation_ancestor_verified=True,
            evidence_delta_paths=[],
            ci_checks={"validate-instructions": "pass"},
        )
        self.assertTrue(any("current PR head" in issue for issue in issues))

    def test_evidence_only_tip_can_differ_from_implementation_subject(self) -> None:
        record = copy.deepcopy(self.valid)
        record["task_id"] = "SCRUM-397"
        record["implementation_head_sha"] = "4e0989cf0770637eabc90c20fa6757fb4f1f4089"
        record["validation"]["implementation_head_sha"] = record["implementation_head_sha"]
        record["review"]["reviewed_implementation_head_sha"] = record["implementation_head_sha"]
        issues = self.runtime_issues(
            record,
            current_pr_head="5437b7f20edfcb7b717e1b7b78d9514985927d7b",
            implementation_ancestor_verified=True,
            evidence_delta_paths=[".gwc/tasks/SCRUM-397/g3/delivery-record.yaml"],
            ci_checks={"validate-instructions": "pass"},
        )
        self.assertEqual([], issues)

    def test_non_evidence_tip_delta_fails_closed(self) -> None:
        record = copy.deepcopy(self.valid)
        record["task_id"] = "SCRUM-615"
        issues = self.runtime_issues(
            record,
            current_pr_head="c" * 40,
            implementation_ancestor_verified=True,
            evidence_delta_paths=["src/example.py"],
            ci_checks={"validate-instructions": "pass"},
        )
        self.assertTrue(any("evidence-only" in issue for issue in issues))

    def test_unverified_ancestry_fails_closed(self) -> None:
        issues = self.runtime_issues(
            copy.deepcopy(self.valid),
            current_pr_head="c" * 40,
            implementation_ancestor_verified=False,
            evidence_delta_paths=[
                f".gwc/tasks/{self.valid['task_id']}/g3/delivery-record.yaml"
            ],
            ci_checks={"validate-instructions": "pass"},
        )
        self.assertTrue(any("ancestor" in issue for issue in issues))

    def test_required_current_tip_ci_must_pass(self) -> None:
        issues = self.runtime_issues(
            copy.deepcopy(self.valid),
            current_pr_head="c" * 40,
            implementation_ancestor_verified=True,
            evidence_delta_paths=[
                f".gwc/tasks/{self.valid['task_id']}/g3/delivery-record.yaml"
            ],
            ci_checks={"validate-instructions": "fail"},
        )
        self.assertTrue(any("required CI check validate-instructions" in issue for issue in issues))

    def test_legacy_v10_active_closure_requires_explicit_migration(self) -> None:
        record = copy.deepcopy(self.valid)
        record["schema_version"] = "1.0"
        issues = self.issues(record)
        self.assertTrue(any("legacy v1.0" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
