import json
import unittest
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


class BaseDriftPolicyTests(unittest.TestCase):
    def test_policy_file_parses(self):
        with (ROOT / "governance/base-drift-policy.yaml").open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["policy_id"], "base-drift-evaluation")
        self.assertIn("SAFE_CONTINUE", data["decision_rules"])

    def test_schema_parses(self):
        with (ROOT / "schemas/base-drift-evaluation.schema.json").open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["title"], "Base Drift Evaluation Result")
        self.assertIn("evaluator_decision", data["required"])

    def test_cli_test_scenarios(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/evaluate_base_drift.py"), "--test"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("BASE DRIFT EVALUATOR TESTS PASSED", result.stdout)

    def test_cli_decision_output(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/evaluate_base_drift.py"),
                "--old-base-sha",
                "132304c74873d7f64651ebd3aa9ad639cd2aff92",
                "--new-base-sha",
                "132304c74873d7f64651ebd3aa9ad639cd2aff93",
                "--changed-file",
                "core/policy.md",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["evaluator_decision"], "REAPPROVE")
        self.assertEqual(payload["risk_assessment"], "REAPPROVE")


if __name__ == "__main__":
    unittest.main()
