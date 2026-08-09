import unittest

from tools.node_architect.autonomous_execution_runtime import (
    child_delivery_decision, claim_task, drive_closed_loop, resolve_ready_nodes, validate_task_scope,
)

SHA = "a" * 40


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

    def test_duplicate_claim_is_replay_safe(self):
        first = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-1", lease_id="lease-1")
        replay = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-1", lease_id="lease-1", existing_claim=first)
        self.assertEqual(replay["reason_code"], "AUTONOMOUS_CLAIM_REPLAY")
        conflict = claim_task(task_id="B", ready_task_ids=["B"], claimant="agent-2", lease_id="lease-2", existing_claim=first)
        self.assertEqual(conflict["reason_code"], "AUTONOMOUS_CLAIM_CONFLICT")

    def test_node_architect_implementation_allowed_when_not_active_authority(self):
        task = {"task_id": "SCRUM-298", "risk": "R2"}
        manifest = {"task_id": "SCRUM-298", "risk": "R2", "allowed_paths": ["core/node-architect/node-catalog/intake_context/request-intake.node.json"]}
        result = validate_task_scope(task=task, manifest_task=manifest,
            requested_paths=manifest["allowed_paths"],
            immutable_authority_paths=["core/node-architect/AUTONOMOUS_PREPROD_RUNTIME_CONTRACT_v0.1.md", "tools/node_architect/validate_autonomous_preprod_policy.py"])
        self.assertEqual(result["outcome"], "ALLOW")

    def test_active_authority_self_modification_is_blocked(self):
        task = {"task_id": "X", "risk": "R1"}
        path = "tools/node_architect/validate_autonomous_preprod_policy.py"
        result = validate_task_scope(task=task, manifest_task={"task_id": "X", "risk": "R1", "allowed_paths": [path]},
            requested_paths=[path], immutable_authority_paths=[path])
        self.assertEqual(result["reason_code"], "AUTONOMOUS_ACTIVE_AUTHORITY_SELF_MODIFICATION_FORBIDDEN")

    def test_child_main_target_forbidden(self):
        result = child_delivery_decision(task_id="X", target_branch="main", head_sha=SHA,
                                         ci_conclusion="success", review_conclusion="pass", standing_g4_valid=True)
        self.assertEqual(result["reason_code"], "AUTONOMOUS_CHILD_MAIN_TARGET_FORBIDDEN")

    def test_preprod_exact_head_can_merge(self):
        result = child_delivery_decision(task_id="X", target_branch="pre-prod", head_sha=SHA,
                                         ci_conclusion="success", review_conclusion="pass", standing_g4_valid=True)
        self.assertTrue(result["merge_allowed"])
        self.assertFalse(result["main_merge_allowed"])

    def test_closed_loop_wires_g5_back_to_dag_refresh(self):
        result = drive_closed_loop({"phase": "G5_VERIFIED", "task_id": "X"})
        self.assertEqual(result["adapter_action"], "MARK_COMPLETE_REQUERY_DAG_AND_PROMOTIONS")

    def test_closed_loop_never_routes_child_to_main(self):
        result = drive_closed_loop({
            "phase": "G3_READY", "task_id": "X", "target_branch": "main", "head_sha": SHA,
            "ci_conclusion": "success", "review_conclusion": "pass", "standing_g4_valid": True,
        })
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIsNone(result["adapter_action"])


if __name__ == "__main__":
    unittest.main()
