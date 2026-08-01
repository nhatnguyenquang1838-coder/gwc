from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class G3ReadyTransitionHotfixTests(unittest.TestCase):
    def test_only_ready_promotion_enters_merge_pending(self) -> None:
        payload = yaml.safe_load(
            (ROOT / "core" / "task-lifecycle" / "gate-transition-map.yaml").read_text(encoding="utf-8")
        )
        rules = payload["rules"]
        by_outcome = {rule["outcome"]: rule for rule in rules}

        self.assertNotIn("G3_REVIEW_PASSED", by_outcome)
        ready = by_outcome["PR_READY_FOR_REVIEW"]
        self.assertEqual("review_pending", ready["from_state"])
        self.assertEqual("MARK_READY_FOR_REVIEW", ready["transition"])
        self.assertEqual("merge_pending", ready["expected_state"])

        merge_pending_rules = [rule for rule in rules if rule["expected_state"] == "merge_pending"]
        self.assertEqual(["PR_READY_FOR_REVIEW"], [rule["outcome"] for rule in merge_pending_rules])

    def test_g3_skill_requires_code_reviewer_and_readback(self) -> None:
        skill = (ROOT / "skills" / "gwc-g3" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("code-review-invocation.json", skill)
        self.assertIn("role is exactly `code_reviewer`", skill)
        self.assertIn("mark_pull_request_ready_for_review", skill)
        self.assertIn("observed draft == false", skill)
        self.assertIn("Review PASS alone does not transition", skill)

    def test_g3_nodes_express_ordering_guards(self) -> None:
        paths = {
            "draft": ROOT / "core" / "node-architect" / "node-catalog" / "repo_delivery" / "draft-pr-creation.node.json",
            "promotion": ROOT / "core" / "node-architect" / "node-catalog" / "repo_delivery" / "ready-for-review-promotion.node.json",
            "blocker": ROOT / "core" / "node-architect" / "node-catalog" / "repo_delivery" / "pr-blocker-check.node.json",
            "decision": ROOT / "core" / "node-architect" / "node-catalog" / "validation_quality" / "g3-pass-decision.node.json",
            "evidence": ROOT / "core" / "node-architect" / "node-catalog" / "validation_quality" / "evidence-quality-check.node.json",
        }
        descriptions = {name: json.loads(path.read_text(encoding="utf-8"))["description"] for name, path in paths.items()}

        self.assertIn("code_reviewer", descriptions["draft"])
        self.assertIn("draft=false", descriptions["promotion"])
        self.assertIn("reviewed head SHA", descriptions["promotion"])
        self.assertIn("stale code-review-agent evidence", descriptions["blocker"])
        self.assertIn("merge_pending", descriptions["decision"])
        self.assertIn("empty write-actions evidence", descriptions["evidence"])


if __name__ == "__main__":
    unittest.main()
