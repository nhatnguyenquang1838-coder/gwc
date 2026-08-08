import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone

from tools.node_architect.materialize_research_execution import (
    approval_scope_hash,
    compile_execution_task_spec,
    materialize_research_execution,
    validate_research_approval,
)

NOW = datetime(2026, 8, 8, 14, 0, tzinfo=timezone.utc)


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def research_and_approval(*, g3=True):
    scope = {
        "scope_id": "round-1",
        "objective": "Implement bounded trace contract",
        "implementation_guidance": ["add schema", "add validator"],
        "acceptance_criteria": ["tests pass", "no authority elevation"],
        "dependencies": ["SCRUM-274"],
        "risk_class": "R2",
        "authorized_paths": ["schemas/node-architect/**", "tools/node_architect/**", "tests/**"],
        "excluded_actions": ["merge", "deploy", "production_data_write"],
    }
    scope["scope_digest"] = digest(scope)
    research = {
        "research_ref": "SCRUM-279",
        "research_digest": digest({"research": "trace"}),
        "repository": "nhatnguyenquang1838-coder/gwc",
        "lane": "node-architect-research",
        "status": "In Review",
        "priority": "High",
        "dependencies": ["SCRUM-274"],
        "scopes": {"round-1": dict(scope)},
    }
    approval = {
        "schema_version": "1.0",
        "artifact_type": "research-execution-approval",
        "approval_id": "RESEARCH-APPROVAL-279-R1",
        "issued_at": "2026-08-08T13:00:00Z",
        "expires_at": "2026-08-09T13:00:00Z",
        "authority_revision": "1",
        "research_ref": research["research_ref"],
        "research_digest": research["research_digest"],
        "repository": research["repository"],
        "base_ref": "main",
        "base_sha": "2e20badf04b4d84bf8a2e88d6e1e88d540745d35",
        "active_lane": research["lane"],
        "risk_ceiling": "R2",
        "approved_scope": dict(scope),
        "delegated_g2_actions": [
            "create_guarded_branch_or_worktree",
            "modify_approved_files",
            "run_sandboxed_validation",
            "create_commit",
            "push_working_branch",
        ],
        "delegated_g3_actions": [
            "open_or_update_draft_pr",
            "monitor_exact_head_ci",
            "repair_within_approved_scope",
            "run_independent_read_only_review",
            "mark_pr_ready_for_review",
        ] if g3 else [],
        "human_approval": {
            "source": "human_exact_command",
            "exact_command_digest": digest("APPROVE RESEARCH"),
            "trusted_readback": True,
        },
        "g4_g5_g6_authority_granted": False,
    }
    approval["scope_hash"] = approval_scope_hash(approval)
    return research, approval


def dep_ok():
    return {
        "jira_status": "Done",
        "semantic_state": "deliverable",
        "repository_implementation": True,
        "exact_sha_verified": True,
        "evidence_refs": ["main@2e20badf"],
    }


class MaterializationTests(unittest.TestCase):
    def test_deterministic_spec_and_no_g4(self):
        r, a = research_and_approval()
        s1 = compile_execution_task_spec(r, a, now=NOW)
        s2 = compile_execution_task_spec(r, a, now=NOW)
        self.assertEqual(s1["materialization_key"], s2["materialization_key"])
        self.assertFalse(s1["g4_g5_g6_authority_granted"])
        self.assertTrue(s1["child_authority"]["g2"]["authority_granted"])
        self.assertTrue(s1["child_authority"]["g3"]["authority_granted"])
        self.assertEqual(s1["child_authority"]["g2"]["risk_ceiling"], "R2")

    def test_g3_omitted_stays_none(self):
        r, a = research_and_approval(g3=False)
        s = compile_execution_task_spec(r, a, now=NOW)
        self.assertIsNone(s["child_authority"]["g3"])

    def test_scope_drift_blocks(self):
        r, a = research_and_approval()
        r = copy.deepcopy(r)
        r["scopes"]["round-1"]["objective"] = "drift"
        ok, reason = validate_research_approval(r, a, now=NOW)
        self.assertFalse(ok)
        self.assertEqual(reason, "RESEARCH_SCOPE_DRIFT")

    def test_parent_scope_hash_drift_blocks(self):
        r, a = research_and_approval()
        a = copy.deepcopy(a)
        a["delegated_g2_actions"].remove("run_sandboxed_validation")
        ok, reason = validate_research_approval(r, a, now=NOW)
        self.assertFalse(ok)
        self.assertEqual(reason, "RESEARCH_APPROVAL_SCOPE_HASH_MISMATCH")

    def test_risk_ceiling_blocks_broader_child_risk(self):
        r, a = research_and_approval()
        a = copy.deepcopy(a)
        a["risk_ceiling"] = "R1"
        a["scope_hash"] = approval_scope_hash(a)
        ok, reason = validate_research_approval(r, a, now=NOW)
        self.assertFalse(ok)
        self.assertEqual(reason, "CHILD_G2_RISK_EXCEEDS_PARENT_CEILING")

    def test_authority_escalation_blocks(self):
        r, a = research_and_approval()
        a = copy.deepcopy(a)
        a["delegated_g3_actions"].append("merge")
        ok, reason = validate_research_approval(r, a, now=NOW)
        self.assertFalse(ok)
        self.assertEqual(reason, "RESEARCH_APPROVAL_AUTHORITY_ESCALATION")

    def test_reconcile_both_missing_one_and_conflict(self):
        r, a = research_and_approval()
        first = materialize_research_execution(r, a, {}, now=NOW)
        self.assertEqual(first["outcome"], "ACTION_REQUIRED")
        self.assertEqual({x["provider"] for x in first["projection_intents"]}, {"github", "jira"})
        key = first["materialization_key"]
        gh = {"id": "324", "materialization_key": key, "origin_research_ref": "SCRUM-279"}
        one = materialize_research_execution(r, a, {"github": [gh], "jira": []}, now=NOW)
        self.assertEqual([x["provider"] for x in one["projection_intents"]], ["jira"])
        jr = {"id": "SCRUM-285", "materialization_key": key, "origin_research_ref": "SCRUM-279"}
        ready = materialize_research_execution(r, a, {"github": [gh], "jira": [jr]}, now=NOW)
        self.assertEqual(ready["outcome"], "READY")
        self.assertIsNotNone(ready["claim_intent"])
        conflict = materialize_research_execution(
            r,
            a,
            {"github": [gh, {**gh, "id": "325"}], "jira": [jr]},
            now=NOW,
        )
        self.assertEqual(conflict["outcome"], "CONFLICT")

    def test_partial_effect_requires_reconciliation(self):
        r, a = research_and_approval()
        x = materialize_research_execution(
            r,
            a,
            {"github": [], "jira": []},
            effects_started=["github"],
            now=NOW,
        )
        self.assertEqual(x["outcome"], "RECONCILIATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
