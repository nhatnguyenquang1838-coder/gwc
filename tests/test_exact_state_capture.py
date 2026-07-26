import unittest

from tools.node_architect.exact_state_capture import ExactState, capture_exact_state


SHA = "a" * 40


class ExactStateCaptureTests(unittest.TestCase):
    def test_success_is_bound_to_exact_sha(self):
        result = capture_exact_state(
            task_id="SCRUM-107",
            repository="owner/repo",
            expected_sha=SHA,
            observation={
                "head_sha": SHA,
                "status": "completed",
                "conclusion": "success",
                "workflow": "CI",
                "run_id": 7,
            },
        )
        self.assertEqual(result.state, ExactState.SUCCESS)

    def test_mismatched_sha_cannot_pass(self):
        result = capture_exact_state(
            task_id="SCRUM-107",
            repository="owner/repo",
            expected_sha=SHA,
            observation={
                "head_sha": "b" * 40,
                "status": "completed",
                "conclusion": "success",
            },
        )
        self.assertEqual(result.state, ExactState.SHA_MISMATCH)

    def test_pending_is_exact_sha_bound(self):
        result = capture_exact_state(
            task_id="SCRUM-107",
            repository="owner/repo",
            expected_sha=SHA,
            observation={"head_sha": SHA, "status": "in_progress", "conclusion": None},
        )
        self.assertEqual(result.state, ExactState.PENDING)

    def test_missing_observation_is_not_pending(self):
        result = capture_exact_state(
            task_id="SCRUM-107",
            repository="owner/repo",
            expected_sha=SHA,
            observation=None,
        )
        self.assertEqual(result.state, ExactState.OBSERVABILITY_INCOMPLETE)

    def test_terminal_failure_is_classified(self):
        result = capture_exact_state(
            task_id="SCRUM-107",
            repository="owner/repo",
            expected_sha=SHA,
            observation={"head_sha": SHA, "status": "completed", "conclusion": "failure"},
        )
        self.assertEqual(result.state, ExactState.FAILURE)


if __name__ == "__main__":
    unittest.main()
