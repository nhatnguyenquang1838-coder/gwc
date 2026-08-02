from __future__ import annotations

import unittest

from tools.node_architect.client_runtime import BLOCKED, PASS, TERMINAL_NODE, VERTICAL_SLICE_ROUTE, run_client_runtime

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "codex/scrum-256-validation-quality-closure-r3-20260802"
GRAPH = "scrum-256-route-v1"


def request() -> dict:
    task = "SCRUM-256"
    return {
        "task_id": task,
        "repository": REPO,
        "protected_base_sha": BASE,
        "scenario_id": GRAPH,
        "evidence": {
            "run_id": "scrum-256-canary-r3",
            "branch": BRANCH,
            "head_sha": HEAD,
            "scope_hash": SCOPE,
            "graph_revision": GRAPH,
            "pr_number": 178,
            "policy_digest": "sha256:" + "4" * 64,
            "ci": {"status": "success", "head_sha": HEAD, "branch": BRANCH, "scope_hash": SCOPE, "graph_revision": GRAPH},
            "review_receipt": {"schema_valid": True, "outcome": "PASS", "task_id": task, "repository": REPO, "pr_number": 178, "head_sha": HEAD, "scope_hash": SCOPE, "reviewer_identity": "independent-reviewer", "access_mode": "read_only", "write_actions": [], "open_findings": 0, "findings": [], "reviewed_at": "2026-08-02T09:00:00Z", "source": "github-review"},
            "evaluated_at": "2026-08-02T09:05:00Z",
            "evidence_sources": ["github-actions", "github-review"],
            "validations": [{"name": "exact-route-canary", "status": "PASS", "head_sha": HEAD, "scope_hash": SCOPE, "digest": "sha256:" + "5" * 64}],
            "ready_for_review": {"eligible": True, "head_sha": HEAD, "scope_drift": False, "unresolved_threads": 0},
            "findings": [],
        },
    }


class Scrum256VerticalSliceClosureTests(unittest.TestCase):
    def test_exact_route_reaches_typed_terminal(self):
        result = run_client_runtime(request())
        self.assertEqual(result.status, PASS)
        self.assertEqual(result.executed_nodes, VERTICAL_SLICE_ROUTE + (TERMINAL_NODE,))
        self.assertFalse(result.manual_fallback_used)
        self.assertEqual(result.evidence["runtime_terminal"]["event_count"], len(VERTICAL_SLICE_ROUTE))
        self.assertGreaterEqual(result.evidence["runtime_terminal"]["checkpoint_count"], 1)

    def test_quality_failure_blocks_before_g3(self):
        data = request(); data["evidence"]["review_receipt"]["head_sha"] = "9" * 40
        result = run_client_runtime(data)
        self.assertEqual(result.status, BLOCKED)
        self.assertEqual(result.blocked_node, "validation_quality.evidence-quality-check")
        self.assertNotIn("validation_quality.g3-pass-decision", result.executed_nodes)

    def test_g3_blocker_prevents_terminal_pass(self):
        data = request(); data["evidence"]["findings"] = [{"severity": "BLOCKER", "status": "OPEN"}]
        result = run_client_runtime(data)
        self.assertEqual(result.status, BLOCKED)
        self.assertEqual(result.blocked_node, "validation_quality.g3-pass-decision")
        self.assertEqual(result.terminal_code, "G3_CHANGES_REQUIRED")

    def test_route_rejects_manual_shortcut(self):
        data = request(); data["route_nodes"] = list(VERTICAL_SLICE_ROUTE[:-1])
        result = run_client_runtime(data)
        self.assertEqual(result.status, BLOCKED)
        self.assertFalse(result.manual_fallback_used)


if __name__ == "__main__":
    unittest.main()
