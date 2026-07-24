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

    @staticmethod
    def implementation_plan() -> dict:
        return {
            "applicability": "required",
            "reason": "Non-trivial implementation requires a plan.",
            "source": "generated_kiro",
            "task_me_applicable": True,
            "task_me_available": False,
            "task_me_invoked": False,
            "task_me_fallback_reason": "Task Me unavailable.",
            "canonical_task_uid": "GWC-G1-PLAN-01",
            "repository": "owner/repo",
            "protected_base_sha": "a" * 40,
            "plan_root": ".kiro/specs/gwc-g1-plan-01",
            "requirements_path": ".kiro/specs/gwc-g1-plan-01/requirements.md",
            "design_path": ".kiro/specs/gwc-g1-plan-01/design.md",
            "tasks_path": ".kiro/specs/gwc-g1-plan-01/tasks.md",
            "plan_revision": "sha256:" + "b" * 64,
            "validation_status": "PASS",
            "validation_evidence": "evidence/plan-validation.json",
            "generated_by": "chatgpt-agent/kiro-fallback",
            "generated_at_utc": "2026-07-24T08:00:00Z",
        }

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
        self.assertEqual("1.0", decision["schema_version"])
        self.assertNotIn("implementation_plan_ref", decision)
        self.assertEqual([], issues)

    def test_plan_aware_decision_copies_immutable_reference(self) -> None:
        preflight = copy.deepcopy(self.preflight)
        plan = self.implementation_plan()
        preflight["schema_version"] = "1.1"
        preflight["implementation_plan"] = plan
        _, decision, outcome, issues = module.generate_artifacts(
            copy.deepcopy(self.input), self.intake, preflight
        )
        expected = {field: plan[field] for field in module.PLAN_REF_FIELDS}
        self.assertEqual("PASS", outcome)
        self.assertEqual([], issues)
        self.assertEqual("1.1", decision["schema_version"])
        self.assertEqual(expected, decision["implementation_plan_ref"])
        self.assertEqual(plan["plan_revision"], decision["implementation_plan_ref"]["plan_revision"])
        plan["plan_revision"] = "sha256:" + "c" * 64
        self.assertNotEqual(plan["plan_revision"], decision["implementation_plan_ref"]["plan_revision"])

    def test_plan_aware_preflight_without_plan_blocks(self) -> None:
        preflight = copy.deepcopy(self.preflight)
        preflight["schema_version"] = "1.1"
        _, decision, outcome, issues = module.generate_artifacts(
            copy.deepcopy(self.input), self.intake, preflight
        )
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("PENDING", decision["status"])
        self.assertEqual("1.0", decision["schema_version"])
        self.assertNotIn("implementation_plan_ref", decision)
        self.assertIn("G1_IMPLEMENTATION_PLAN_EVIDENCE_MISSING", issues)

    def test_incomplete_plan_reference_blocks(self) -> None:
        preflight = copy.deepcopy(self.preflight)
        preflight["schema_version"] = "1.1"
        preflight["implementation_plan"] = self.implementation_plan()
        del preflight["implementation_plan"]["plan_revision"]
        _, decision, outcome, issues = module.generate_artifacts(
            copy.deepcopy(self.input), self.intake, preflight
        )
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("PENDING", decision["status"])
        self.assertTrue(any(issue.startswith("G1_IMPLEMENTATION_PLAN_REFERENCE_INCOMPLETE") for issue in issues))

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
