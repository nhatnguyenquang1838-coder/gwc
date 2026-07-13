from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "capture_g01_decision.py"
FIXTURE = ROOT / "tests" / "fixtures" / "g01-decision-valid.yaml"
VALID_WORKSPACE = ROOT / "tests" / "fixtures" / "g01-valid"
INTAKE = VALID_WORKSPACE / "g1" / "intake" / "g1-intake-brief.yaml"
PREFLIGHT = VALID_WORKSPACE / "g1" / "preflight" / "g1-preflight-report.yaml"

spec = importlib.util.spec_from_file_location("capture_g01_decision", TOOL)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DecisionCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
        cls.intake = yaml.safe_load(INTAKE.read_text(encoding="utf-8"))
        cls.preflight = yaml.safe_load(PREFLIGHT.read_text(encoding="utf-8"))

    def test_accepted_explicit_decision_passes(self) -> None:
        options, decision, outcome, issues = module.generate_artifacts(
            copy.deepcopy(self.input), self.intake, self.preflight
        )
        self.assertEqual("PASS", outcome)
        self.assertEqual("READY", options["status"])
        self.assertEqual("ACCEPTED", decision["status"])
        self.assertEqual([], decision["authority_boundaries"]["grants"])
        self.assertEqual(
            {"G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"},
            set(decision["authority_boundaries"]["excluded"]),
        )
        self.assertTrue(decision["scope_hash"].startswith("sha256:"))
        self.assertEqual([], issues)

    def test_missing_selected_option_blocks(self) -> None:
        payload = copy.deepcopy(self.input)
        payload["decision"]["selected_option_id"] = "OPT-99"
        _, decision, outcome, issues = module.generate_artifacts(
            payload, self.intake, self.preflight
        )
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("PENDING", decision["status"])
        self.assertIn("G1_SELECTED_OPTION_NOT_FOUND", issues)

    def test_non_explicit_acceptance_blocks(self) -> None:
        payload = copy.deepcopy(self.input)
        payload["decision"]["explicit"] = False
        _, decision, outcome, issues = module.generate_artifacts(
            payload, self.intake, self.preflight
        )
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("PENDING", decision["status"])
        self.assertIn("G1_EXPLICIT_DECISION_REQUIRED", issues)

    def test_rejected_decision_is_not_pass(self) -> None:
        payload = copy.deepcopy(self.input)
        payload["decision"]["status"] = "REJECTED"
        _, decision, outcome, _ = module.generate_artifacts(
            payload, self.intake, self.preflight
        )
        self.assertEqual("REJECTED", outcome)
        self.assertEqual("REJECTED", decision["status"])

    def test_duplicate_option_ids_block(self) -> None:
        payload = copy.deepcopy(self.input)
        payload["options"][1]["id"] = "OPT-1"
        _, decision, outcome, issues = module.generate_artifacts(
            payload, self.intake, self.preflight
        )
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("PENDING", decision["status"])
        self.assertIn("G1_DUPLICATE_OPTION_ID", issues)

    def test_cli_writes_decision_and_full_workspace_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            shutil.copytree(VALID_WORKSPACE, workspace)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(ROOT),
                    "--input",
                    str(FIXTURE),
                    "--workspace",
                    str(workspace),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual("PASS", summary["outcome"])
            self.assertEqual([], summary["authority_grants"])
            self.assertTrue((workspace / "g1/brainstorming/g1-options.yaml").is_file())
            self.assertTrue((workspace / "g1/decision/g1-decision-record.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
