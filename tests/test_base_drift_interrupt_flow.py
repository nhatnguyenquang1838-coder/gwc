import json
import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BaseDriftInterruptFlowTests(unittest.TestCase):
    def run_cmd(self, *args: str) -> str:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        return completed.stdout

    def test_base_drift_evaluator_samples_pass(self):
        output = self.run_cmd("tools/evaluate_base_drift.py", "--test")
        self.assertIn("BASE DRIFT EVALUATOR TESTS PASSED", output)

    def test_interrupt_flow_samples_pass(self):
        output = self.run_cmd("tools/validate_interrupt_flow.py", "--test")
        self.assertIn("INTERRUPT FLOW VALIDATION PASSED", output)

    def test_revalidate_preserves_g2_pending_checks(self):
        output = self.run_cmd(
            "tools/evaluate_base_drift.py",
            "--old-base-sha",
            "132304c74873d7f64651ebd3aa9ad639cd2aff92",
            "--new-base-sha",
            "132304c74873d7f64651ebd3aa9ad639cd2aff93",
            "--changed-file",
            "schemas/base-drift-evaluation.schema.json",
        )
        payload = json.loads(output)
        self.assertEqual(payload["evaluator_decision"], "REVALIDATE")
        self.assertEqual(payload["authority_effect"]["g2"], "PRESERVED_PENDING_REVALIDATION")
        self.assertFalse(payload["continuation"]["requires_human_approval"])

    def test_governance_change_requires_reapproval(self):
        output = self.run_cmd(
            "tools/evaluate_base_drift.py",
            "--old-base-sha",
            "132304c74873d7f64651ebd3aa9ad639cd2aff92",
            "--new-base-sha",
            "132304c74873d7f64651ebd3aa9ad639cd2aff93",
            "--changed-file",
            "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
        )
        payload = json.loads(output)
        self.assertEqual(payload["evaluator_decision"], "REAPPROVE")
        self.assertTrue(payload["continuation"]["requires_human_approval"])


if __name__ == "__main__":
    unittest.main()
