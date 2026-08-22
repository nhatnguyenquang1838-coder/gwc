"""SCRUM-319 (diff-readback) DELTA_REQUIRED focused tests.

Maps the live SCRUM-319 Jira AC matrix to deterministic assertions against
``decide_diff_readback``:
  complete diff, incomplete visibility, foreign/out-of-scope, prohibited
  path/change, stale SHA, same-SHA replay/digest stability, no authority grant.

These run alongside (not instead of) the legacy
``test_repo_delivery_m5_batch_b2.py`` suite; they extend coverage for the
CORRECTION seq=3 gaps without altering existing verdicts.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.diff_readback import decide_diff_readback

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "3acf169b91fa2d4c4c32f573fa3318d00dad9088"
HEAD = "a" * 40
BRANCH = "auto/SCRUM-319-na81-recert-20260814-r10"
APPROVED = [
    "tools/node_architect/diff_readback.py",
    "tests/test_repo_delivery_scrum319_diff_readback_delta.py",
    "releases/changelog.d/",
]
# Immutable authority/control-plane paths that must never be touched (prohibited).
PROHIBITED = [
    "AGENTS.md",
    "core/Coding_Project_Governance_v1.0.md",
    "config.yaml",
    ".github/**",
]


def _schema() -> dict:
    return json.loads(Path("schemas/diff-readback-decision.schema.json").read_text())


def load_schema(name: str) -> dict:
    return json.loads(Path("schemas", name).read_text())


def _valid(evidence: dict) -> dict:
    """A minimal complete-visibility, in-scope, non-prohibited, current-SHA call."""
    evidence.setdefault("repository", REPO)
    evidence.setdefault("base_sha", BASE)
    evidence.setdefault("head_sha", HEAD)
    evidence.setdefault("branch", BRANCH)
    evidence.setdefault("connector_status", "available")
    evidence.setdefault("compare_status", "ahead")
    evidence.setdefault("ahead_by", 1)
    evidence.setdefault("behind_by", 0)
    evidence.setdefault("readback_coverage", "complete")
    evidence.setdefault("approved_paths", APPROVED)
    evidence.setdefault("changed_files", [
        {"filename": "tools/node_architect/diff_readback.py", "status": "modified",
         "additions": 10, "deletions": 2},
    ])
    return decide_diff_readback(evidence)


class DiffReadbackScrum319DeltaTests(unittest.TestCase):
    # --- schema validity preserved ---
    def test_schema_still_valid(self) -> None:
        Draft202012Validator.check_schema(load_schema("diff-readback-decision.schema.json"))

    # 1) complete diff -> PASS + valid against closed schema
    def test_complete_diff_passes(self) -> None:
        decision = _valid({})
        self.assertEqual(decision["outcome"], "PASS")
        self.assertNotIn("INCOMPLETE_VISIBILITY", decision["reason_codes"])
        self.assertNotIn("PROHIBITED_CHANGE_DETECTED", decision["reason_codes"])
        self.assertNotIn("STALE_BASE_SHA", decision["reason_codes"])
        Draft202012Validator(load_schema("diff-readback-decision.schema.json")).validate(decision)

    # 2) incomplete visibility must fail closed
    def test_incomplete_visibility_blocks(self) -> None:
        decision = _valid({"readback_coverage": "partial"})
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("INCOMPLETE_VISIBILITY", decision["reason_codes"])

    def test_unknown_visibility_blocks(self) -> None:
        decision = _valid({"readback_coverage": "unknown"})
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("READBACK_VISIBILITY_UNKNOWN", decision["reason_codes"])

    # 3) foreign / out-of-scope path -> BLOCKED (distinct reason)
    def test_foreign_out_of_scope_blocks(self) -> None:
        decision = _valid({"changed_files": [
            {"filename": "scripts/unapproved.py", "status": "added", "additions": 1, "deletions": 0},
        ]})
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("OUT_OF_SCOPE_PATH", decision["reason_codes"])
        self.assertNotIn("PROHIBITED_CHANGE_DETECTED", decision["reason_codes"])

    # 4) prohibited path/change -> explicit PROHIBITED_CHANGE_DETECTED (fail closed)
    def test_prohibited_change_detected(self) -> None:
        for path in ["AGENTS.md", "core/Coding_Project_Governance_v1.0.md", ".github/workflows/ci.yml"]:
            decision = _valid({
                "prohibited_paths": PROHIBITED,
                "changed_files": [
                    {"filename": path, "status": "modified", "additions": 1, "deletions": 0},
                ],
            })
            self.assertEqual(decision["outcome"], "BLOCKED", path)
            self.assertIn("PROHIBITED_CHANGE_DETECTED", decision["reason_codes"], path)

    def test_prohibited_distinct_from_out_of_scope(self) -> None:
        # A prohibited hit is reported even when the same path is also approved.
        decision = _valid({
            "approved_paths": APPROVED + ["AGENTS.md"],
            "prohibited_paths": PROHIBITED,
            "changed_files": [{"filename": "AGENTS.md", "status": "modified", "additions": 1, "deletions": 0}],
        })
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("PROHIBITED_CHANGE_DETECTED", decision["reason_codes"])

    # 5) stale base/head SHA must fail closed
    def test_stale_base_sha_blocks(self) -> None:
        decision = _valid({"expected_base_sha": BASE, "base_sha": "f" * 40})
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("STALE_BASE_SHA", decision["reason_codes"])

    def test_stale_head_sha_blocks(self) -> None:
        decision = _valid({"expected_head_sha": HEAD, "head_sha": "e" * 40})
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("STALE_HEAD_SHA", decision["reason_codes"])

    # 6) same-input replay / digest stability
    def test_replay_digest_stable(self) -> None:
        a = _valid({"changed_files": [
            {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 4, "deletions": 1},
        ]})
        b = _valid({"changed_files": [
            {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 4, "deletions": 1},
        ]})
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertTrue(a["decision_digest"].startswith("sha256:"))

    def test_digest_differs_on_content_change(self) -> None:
        a = _valid({"changed_files": [
            {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 4, "deletions": 1},
        ]})
        b = _valid({"changed_files": [
            {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 9, "deletions": 0},
        ]})
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    # 7) no authority grant (never grants review/merge/deploy)
    def test_no_authority_grant(self) -> None:
        decision = _valid({})
        self.assertFalse(decision["merge_authority_granted"])
        self.assertFalse(decision["deployment_authority_granted"])
        self.assertFalse(decision["production_authority_granted"])

    # INTERCEPT (seq=4): absence of completeness proof MUST fail closed,
    # never silently become "complete".
    def test_absent_coverage_fails_closed(self) -> None:
        evidence = {
            "repository": REPO, "base_sha": BASE, "head_sha": HEAD, "branch": BRANCH,
            "connector_status": "available", "compare_status": "ahead",
            "ahead_by": 1, "behind_by": 0, "approved_paths": APPROVED,
            "changed_files": [
                {"filename": "tools/node_architect/diff_readback.py", "status": "added", "additions": 1, "deletions": 0},
            ],
        }
        # No readback_coverage key at all.
        decision = decide_diff_readback(evidence)
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("READBACK_VISIBILITY_UNKNOWN", decision["reason_codes"])
        self.assertNotIn("DIFF_READBACK_OK", decision["reason_codes"])

    # INTERCEPT (seq=4): digest must be content-provenance sensitive AND
    # replay-stable. Changing a prohibited hit changes the digest; identical
    # evidence keeps it stable.
    def test_digest_sensitive_to_prohibited_hit(self) -> None:
        clean = _valid({"changed_files": [
            {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 3, "deletions": 1},
        ]})
        prohibited = _valid({
            "prohibited_paths": PROHIBITED,
            "changed_files": [
                {"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 3, "deletions": 1},
                {"filename": "AGENTS.md", "status": "modified", "additions": 0, "deletions": 0},
            ],
        })
        self.assertNotEqual(clean["decision_digest"], prohibited["decision_digest"])

    def test_digest_replay_stable_across_calls(self) -> None:
        kwargs = dict(
            repository=REPO, base_sha=BASE, head_sha=HEAD, branch=BRANCH,
            connector_status="available", compare_status="ahead",
            ahead_by=1, behind_by=0, readback_coverage="complete",
            approved_paths=APPROVED,
            changed_files=[{"filename": "tools/node_architect/diff_readback.py", "status": "modified", "additions": 3, "deletions": 1}],
        )
        a = decide_diff_readback(kwargs)
        b = decide_diff_readback(kwargs)
        self.assertEqual(a["decision_digest"], b["decision_digest"])


if __name__ == "__main__":
    unittest.main()
