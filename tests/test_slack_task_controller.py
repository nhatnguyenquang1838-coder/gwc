import unittest

from tools.node_architect.slack_task_controller import compile_executor_contract, controller_next_action


class SlackTaskControllerTests(unittest.TestCase):
    def subtasks(self):
        return [
            {"id": "S1", "objective": "inspect", "allowed_work": ["read"], "expected_output": "evidence", "report_requirement": "report evidence", "after_report": "CONTINUE"},
            {"id": "S2", "objective": "implement", "allowed_work": ["write scoped files"], "expected_output": "patch", "report_requirement": "report diff/tests", "after_report": "WAIT_CONTROLLER"},
            {"id": "S3", "objective": "validate", "allowed_work": ["test"], "expected_output": "terminal evidence", "report_requirement": "report exact evidence", "after_report": "TERMINAL"},
        ]

    def kwargs(self, **overrides):
        values = dict(
            task_id="SCRUM-300", repository="owner/gwc", base_sha="a" * 40, branch="auto/run/SCRUM-300",
            selected_option={"id": "OPTION-A"}, g2_authority_ref="G2-REF", subtasks=self.subtasks(),
            controller_id="controller-1", executor_id="executor-1", slack_thread_ref="C1:123.456",
        )
        values.update(overrides)
        return values

    def test_contract_is_bounded_and_slack_is_not_authority(self):
        contract = compile_executor_contract(**self.kwargs())
        self.assertFalse(contract["slack_is_authority"])
        self.assertEqual(len(contract["subtasks"]), 3)
        self.assertNotIn("rejected_options", contract)

    def test_subtask_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "SUBTASK_COUNT"):
            compile_executor_contract(**self.kwargs(subtasks=self.subtasks()[:2]))

    def test_non_hex_base_sha_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "BINDING_INVALID"):
            compile_executor_contract(**self.kwargs(base_sha="z" * 40))

    def test_controller_cannot_be_executor(self):
        with self.assertRaisesRegex(ValueError, "ROLE_IDENTITY_INVALID"):
            compile_executor_contract(**self.kwargs(executor_id="controller-1"))

    def test_rejected_option_noise_is_not_forwarded(self):
        with self.assertRaisesRegex(ValueError, "CONTAINS_NOISE"):
            compile_executor_contract(**self.kwargs(selected_option={"id": "A", "rejected_options": ["B"]}))

    def test_duplicate_subtask_id_is_blocked(self):
        subtasks = self.subtasks()
        subtasks[1]["id"] = "S1"
        with self.assertRaisesRegex(ValueError, "ID_DUPLICATE"):
            compile_executor_contract(**self.kwargs(subtasks=subtasks))

    def test_wait_controller_is_respected(self):
        result = controller_next_action({"subtask_id": "S2", "status": "DONE", "after_report": "WAIT_CONTROLLER"}, expected_subtask_id="S2")
        self.assertEqual(result["outcome"], "WAIT_CONTROLLER")

    def test_material_drift_intercepts(self):
        result = controller_next_action({"subtask_id": "S1", "status": "RUNNING", "after_report": "CONTINUE", "scope_drift": True}, expected_subtask_id="S1")
        self.assertEqual(result["outcome"], "INTERCEPT")


if __name__ == "__main__":
    unittest.main()
