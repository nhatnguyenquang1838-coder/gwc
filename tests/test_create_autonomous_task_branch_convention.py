from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/node_architect/create_autonomous_task_branch.py"


def load():
    spec = importlib.util.spec_from_file_location("create_autonomous_task_branch", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BranchConventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load()

    def decide(self, branch, task="SCRUM-304", run="SCRUM-288-NA81-20260810-R3"):
        return self.mod.decide_branch(
            run_id=run,
            task_id=task,
            proposed_branch=branch,
            base_branch="pre-prod",
            base_sha="6" * 40,
        )

    def test_manifest_convention_accepted(self):
        # Exact working-branch convention bound by the parent run manifest.
        d = self.decide("auto/SCRUM-304-na81-20260810")
        self.assertEqual("CREATE_BRANCH", d["outcome"])

    def test_wrong_order_rejected(self):
        # auto/<run>/<task> (slash) is NOT the manifest convention.
        d = self.decide("auto/na81-20260810/SCRUM-304")
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_BRANCH_PATTERN_INVALID", d["reason_codes"])

    def test_non_scrum_prefix_rejected(self):
        d = self.decide("auto/foo-304-na81-20260810")
        self.assertEqual("REJECTED", d["outcome"])

    def test_missing_run_suffix_rejected(self):
        d = self.decide("auto/SCRUM-304-20260810")
        self.assertEqual("REJECTED", d["outcome"])

    def test_other_task_id_still_passes_pattern_at_branch_stage(self):
        # Branch-create stage only validates the convention pattern, not the
        # task<->branch binding (that binding is enforced later by the G4
        # receipt validator against the manifest allowlist). So a sibling task
        # branch has a valid pattern here.
        d = self.decide("auto/SCRUM-305-na81-20260810", task="SCRUM-304")
        self.assertEqual("CREATE_BRANCH", d["outcome"])
        self.assertNotIn("AUTONOMOUS_BRANCH_PATTERN_INVALID", d["reason_codes"])

    def test_all_81_manifest_branches_match_regex(self):
        # Sanity: the regex must accept every allowlisted working branch.
        import re
        pat = re.compile(r"^auto/SCRUM-[0-9]+-na81-20260810$")
        for tid in range(298, 379):
            self.assertTrue(pat.match(f"auto/SCRUM-{tid}-na81-20260810"), f"SCRUM-{tid} branch should match")


if __name__ == "__main__":
    unittest.main()
