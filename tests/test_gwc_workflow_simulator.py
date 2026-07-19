import unittest

from tools.gwc_workflow_simulator import (
    Gate,
    GateError,
    GwcWorkflowSimulator,
    MockApprovalSource,
    MockContextSource,
    MockG1Validator,
)


class GwcWorkflowSimulatorTests(unittest.TestCase):
    def test_happy_path_stops_at_g4_until_human_approval(self):
        simulator = GwcWorkflowSimulator(
            MockContextSource(), MockG1Validator(), MockApprovalSource()
        )

        result = simulator.run()

        self.assertEqual(result.gate, Gate.G4_MERGE)
        self.assertEqual(result.events[-1], "G4_MERGE awaiting human approval")
        self.assertNotIn("G4_MERGE approved", result.events)

    def test_g4_can_be_approved_by_the_stub(self):
        simulator = GwcWorkflowSimulator(
            MockContextSource(), MockG1Validator(), MockApprovalSource([Gate.G4_MERGE])
        )

        result = simulator.run()

        self.assertEqual(result.gate, Gate.G4_MERGE)
        self.assertEqual(result.events[-1], "G4_MERGE approved")

    def test_g1_failure_blocks_later_gates(self):
        simulator = GwcWorkflowSimulator(
            MockContextSource(), MockG1Validator(passed=False), MockApprovalSource()
        )

        with self.assertRaisesRegex(GateError, "G1_ALIGNMENT blocked"):
            simulator.run()
        self.assertNotIn("G2_EXECUTION entered", simulator.events)

    def test_g0_failure_blocks_g1(self):
        simulator = GwcWorkflowSimulator(
            MockContextSource(ready=False), MockG1Validator(), MockApprovalSource()
        )

        with self.assertRaisesRegex(GateError, "G0_CONTEXT blocked"):
            simulator.run()
        self.assertNotIn("G1_ALIGNMENT entered", simulator.events)


if __name__ == "__main__":
    unittest.main()
