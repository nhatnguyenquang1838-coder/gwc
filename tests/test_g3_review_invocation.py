from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "validate_g3_review_invocation.py"
SCHEMA = ROOT / "schemas" / "g3-code-review-invocation.schema.json"
TEMPLATE = ROOT / "templates" / "gates" / "g3-code-review-invocation.template.json"

SPEC = importlib.util.spec_from_file_location("validate_g3_review_invocation", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class G3ReviewInvocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.valid = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def issues(self, record: dict) -> list[str]:
        return MODULE.validate_record(record, self.schema)

    def test_valid_template_passes(self) -> None:
        self.assertEqual([], self.issues(copy.deepcopy(self.valid)))

    def test_reviewer_role_must_be_code_reviewer(self) -> None:
        record = copy.deepcopy(self.valid)
        record["reviewer"]["role"] = "developer"
        self.assertTrue(any("reviewer.role" in issue for issue in self.issues(record)))

    def test_independent_reviewer_must_differ_from_implementer(self) -> None:
        record = copy.deepcopy(self.valid)
        record["reviewer"]["agent_id"] = record["implementer_id"]
        self.assertTrue(any("must differ" in issue for issue in self.issues(record)))

    def test_requested_head_mismatch_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["invocation"]["requested_head_sha"] = "d" * 40
        self.assertTrue(any("requested_head_sha" in issue for issue in self.issues(record)))

    def test_completed_head_mismatch_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["invocation"]["completed_head_sha"] = "e" * 40
        self.assertTrue(any("completed_head_sha" in issue for issue in self.issues(record)))

    def test_write_action_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["write_actions"] = ["update_file"]
        self.assertTrue(self.issues(record))

    def test_stale_pass_fails(self) -> None:
        record = copy.deepcopy(self.valid)
        record["stale"] = True
        self.assertTrue(any("stale=false" in issue for issue in self.issues(record)))

    def test_open_blocker_fails_pass(self) -> None:
        record = copy.deepcopy(self.valid)
        record["findings"] = [{
            "id": "REV-1",
            "severity": "BLOCKER",
            "status": "open",
            "summary": "unsafe behavior",
        }]
        self.assertTrue(any("BLOCKER" in issue for issue in self.issues(record)))

    def test_changes_required_may_retain_open_blocker(self) -> None:
        record = copy.deepcopy(self.valid)
        record["result"] = "changes_required"
        record["findings"] = [{
            "id": "REV-1",
            "severity": "BLOCKER",
            "status": "open",
            "summary": "return to G2",
        }]
        self.assertEqual([], self.issues(record))


if __name__ == "__main__":
    unittest.main()
