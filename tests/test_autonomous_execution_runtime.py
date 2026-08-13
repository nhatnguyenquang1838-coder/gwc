import unittest

from tools.node_architect.autonomous_execution_runtime import (
    AUTONOMOUS_ROUTE_ID,
    child_delivery_decision, claim_task, drive_closed_loop, resolve_authorized_ready_nodes,
    resolve_ready_nodes, validate_task_scope,
)

SHA = "a" * 40
AUDIT_DIGEST = "sha256:" + "b" * 64


class AutonomousExecutionRuntimeTests(unittest.TestCase):
    def test_dag_only_returns_nodes_with_complete_dependencies(self):
        tasks = [
            {"task_id": "A", "status": "COMPLETED", "dependencies": []},
            {"task_id": "B", "status": "TO_DO", "dependencies": ["A"]},
            {"task_id": "C", "status": "TO_DO", "dependencies": ["B"]},
        ]
        result = resolve_ready_nodes(tasks)
        self.assertEqual(result["ready_task_ids"], ["B"])
        self.assertEqual(result["blocked_dependencies"]["C"], ["B"])

    def test_preprod_merged_predecessor_unlocks_consumer_without_g5(self):
        tasks = [
            {"task_id": "A", "status": "PREPROD_MERGED", "dependencies": []},
            {"task_id": "B", "status": "TO_DO", "dependencies": ["A"]},
        ]
        self.assertEqual(resolve_ready_nodes(tasks)["ready_task_ids"], ["B"])

    def test_scrum_301_cannot_dispatch_while_scrum_300_incomplete(self):
        tasks = [
            {"task_id": "SCRUM-300", "status": "IN_PROGRESS", "dependencies": []},
            {"task_id": "SCRUM-301", "status": "TO_DO", "dependencies": ["SCRUM-300"]},
        ]
        result = resolve_ready_nodes(tasks)
        self.assertNotIn("SCRUM-301", result["ready_task_ids"])
        self.assertEqual(result["blocked_dependencies"]["SCRUM-301"], ["SCRUM-300"])

    def test_ready_task_requires_authority_before_claim(self):
        dag = resolve_ready_nodes([{"task_id": "SCRUM-300", "status": "TO_DO", "dependencies": []}])
        result = resolve_authorized_ready_nodes(dag=dag, manifest=None, authority_valid=False)
        self.assertEqual(result["state"], "READY_FOR_AUTHORITY")

    def test_allowlisted_ready_task_becomes_authorized_ready(self):
        dag = resolve_ready_nodes([{"task_id": "SCRUM-300", "status": "TO_DO", "dependencies": []}])
        result = resolve_authorized_ready_nodes(dag=dag, manifest={"allowed_tasks": [{"task_id": "SCRUM-300"}]}, authority_valid=True)
        self.assertEqual(result["state"], "AUTHORIZED_READY")

    def test_duplicate_claim_is_replay_safe(self):
        first = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-1", lease_id="lease-1")
        replay = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-1", lease_id="lease-1", existing_claim=first)
        conflict = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-2", lease_id="lease-2", existing_claim=first)
        self.assertEqual(replay["reason_code"], "AUTONOMOUS_CLAIM_REPLAY")
        self.assertEqual(conflict["reason_code"], "AUTONOMOUS_CLAIM_CONFLICT")

    def test_node_architect_implementation_allowed_when_not_active_authority(self):
        task = {"task_id": "SCRUM-300", "risk": "R2"}
        manifest = {"task_id": "SCRUM-300", "risk": "R2", "allowed_paths": ["core/node-architect/node-catalog/intake_context/repo-identity-check.node.json"]}
        result = validate_task_scope(task=task, manifest_task=manifest, requested_paths=manifest["allowed_paths"], immutable_authority_paths=["core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md"])
        self.assertEqual(result["outcome"], "ALLOW")

    def test_active_authority_self_modification_is_blocked(self):
        path = "tools/node_architect/validate_autonomous_preprod_policy.py"
        result = validate_task_scope(task={"task_id": "X", "risk": "R1"}, manifest_task={"task_id": "X", "risk": "R1", "allowed_paths": [path]}, requested_paths=[path], immutable_authority_paths=[path])
        self.assertEqual(result["reason_code"], "AUTONOMOUS_ACTIVE_AUTHORITY_SELF_MODIFICATION_FORBIDDEN")

    def _child(self, **overrides):
        kwargs = dict(
            task_id="X", target_branch="pre-prod", head_sha=SHA,
            ci_conclusion="success", review_conclusion="pass", standing_g4_valid=True,
            managed_evidence_current=True, required_checks_terminal_success=True,
            audit_conclusion="pass", audit_head_sha=SHA, audit_independent=True,
            audit_receipt_valid=True, audit_receipt_digest=AUDIT_DIGEST,
        )
        kwargs.update(overrides)
        return child_delivery_decision(**kwargs)

    def test_child_main_target_forbidden(self):
        self.assertEqual(self._child(target_branch="main")["reason_code"], "AUTONOMOUS_CHILD_MAIN_TARGET_FORBIDDEN")

    def test_preprod_exact_head_can_merge_only_after_audit(self):
        result = self._child()
        self.assertTrue(result["merge_allowed"])
        self.assertFalse(result["main_merge_allowed"])
        self.assertFalse(result["audit_merge_authority"])
        self.assertEqual(AUTONOMOUS_ROUTE_ID, result["route_id"])

    def test_preprod_merge_blocks_without_terminal_required_checks(self):
        self.assertEqual(self._child(required_checks_terminal_success=False)["reason_code"], "AUTONOMOUS_REQUIRED_CHECKS_NOT_TERMINAL_SUCCESS")

    def test_preprod_merge_blocks_without_current_managed_evidence(self):
        self.assertEqual(self._child(managed_evidence_current=False)["reason_code"], "AUTONOMOUS_PR_MANAGED_EVIDENCE_NOT_CURRENT")

    def test_preprod_merge_blocks_without_independent_audit(self):
        result = self._child(audit_independent=False)
        self.assertEqual(result["reason_code"], "AUTONOMOUS_G4_PREPROD_AUDIT_NOT_INDEPENDENT")

    def test_preprod_merge_blocks_stale_audit(self):
        result = self._child(audit_head_sha="c" * 40)
        self.assertEqual(result["reason_code"], "AUTONOMOUS_G4_PREPROD_AUDIT_STALE")

    def test_discover_resolves_authority_before_claim(self):
        result = drive_closed_loop({"phase": "DISCOVER", "tasks": [{"task_id": "SCRUM-300", "status": "TO_DO", "dependencies": []}], "authority_valid": False})
        self.assertEqual(result["adapter_action"], "RESOLVE_RUN_AUTHORITY")

    def test_discover_claims_only_authorized_ready_task(self):
        result = drive_closed_loop({"phase": "DISCOVER", "tasks": [{"task_id": "SCRUM-300", "status": "TO_DO", "dependencies": []}], "authority_valid": True, "manifest": {"allowed_tasks": [{"task_id": "SCRUM-300"}]}})
        self.assertEqual(result["adapter_action"], "JIRA_GITHUB_CAS_CLAIM")
        self.assertEqual(result["controller_role"], "TaskController")

    def test_claimed_routes_to_task_controller_slack_not_generic_e2e(self):
        result = drive_closed_loop({"phase": "CLAIMED", "task_id": "SCRUM-300"})
        self.assertEqual(result["adapter_action"], "TASK_CONTROLLER_DISPATCH_EXECUTOR_SLACK")
        self.assertEqual(result["controller_role"], "TaskController")
        self.assertFalse(result["slack_is_authority"])

    def test_executor_wait_routes_back_to_controller(self):
        result = drive_closed_loop({"phase": "EXECUTOR_WAIT_CONTROLLER", "task_id": "X"})
        self.assertEqual(result["adapter_action"], "TASK_CONTROLLER_REVIEW_EXECUTOR_REPORT")

    def test_implemented_phase_forces_pr_contract_builder(self):
        result = drive_closed_loop({"phase": "IMPLEMENTED", "task_id": "X"})
        self.assertEqual(result["adapter_action"], "ASSEMBLE_AND_CREATE_OR_UPDATE_PREPROD_PR")
        self.assertTrue(result["managed_evidence_required"])

    def _g3_observation(self, **overrides):
        value = {
            "phase": "G3_READY", "task_id": "X", "target_branch": "pre-prod", "head_sha": SHA,
            "ci_conclusion": "success", "review_conclusion": "pass", "standing_g4_valid": True,
            "managed_evidence_current": True, "required_checks_terminal_success": True,
        }
        value.update(overrides)
        return value

    def test_g3_ready_triggers_independent_g4_audit_before_merge(self):
        result = drive_closed_loop(self._g3_observation())
        self.assertEqual(result["adapter_action"], "INVOKE_INDEPENDENT_G4_AUDIT")
        self.assertEqual(result["audit_agent"], "agent-audit")
        self.assertFalse(result["audit_merge_authority"])

    def test_g3_ready_merges_only_with_valid_exact_head_audit(self):
        result = drive_closed_loop(self._g3_observation(
            audit_conclusion="pass", audit_head_sha=SHA, audit_independent=True,
            audit_receipt_valid=True, audit_receipt_digest=AUDIT_DIGEST,
        ))
        self.assertEqual(result["outcome"], "ALLOW")
        self.assertEqual(result["adapter_action"], "MERGE_PREPROD_EXACT_HEAD")

    def test_g3_ready_does_not_merge_on_audit_block(self):
        result = drive_closed_loop(self._g3_observation(
            audit_conclusion="block", audit_head_sha=SHA, audit_independent=True,
            audit_receipt_valid=True, audit_receipt_digest=AUDIT_DIGEST,
        ))
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIsNone(result["adapter_action"])

    def test_preprod_merged_completes_without_post_merge_g5(self):
        result = drive_closed_loop({"phase": "PREPROD_MERGED", "task_id": "X", "merge_sha": SHA})
        self.assertEqual(result["state"], "COMPLETED")
        self.assertFalse(result["post_merge_g5_required"])

    def test_closed_loop_never_routes_child_to_main(self):
        result = drive_closed_loop(self._g3_observation(
            target_branch="main", audit_conclusion="pass", audit_head_sha=SHA,
            audit_independent=True, audit_receipt_valid=True, audit_receipt_digest=AUDIT_DIGEST,
        ))
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIsNone(result["adapter_action"])


if __name__ == "__main__":
    unittest.main()
