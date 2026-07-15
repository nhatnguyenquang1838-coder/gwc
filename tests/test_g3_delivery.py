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

    def test_valid_template_passes(self) -> None:
        self.assertEqual([], self.issues(copy.deepcopy(self.valid)))

    def test_review_head_mismatch_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["reviewed_head_sha"] = "d" * 40
        self.assertTrue(any("reviewed_head_sha" in issue for issue in self.issues(record)))

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

    def test_major_with_exact_head_acceptance_passes(self) -> None:
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
                "rationale": "accepted for this exact head",
                "head_sha": record["head_sha"],
            },
        }]
        self.assertEqual([], self.issues(record))

    def test_duplicate_lane_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["review"]["lanes"][-1]["name"] = "code"
        issues = self.issues(record)
        self.assertTrue(any("duplicate" in issue for issue in issues))
        self.assertTrue(any("missing required lanes" in issue for issue in issues))

    def test_ci_head_mismatch_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["ci"]["head_sha"] = "e" * 40
        self.assertTrue(any("ci.head_sha" in issue for issue in self.issues(record)))

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


if __name__ == "__main__":
    unittest.main()
