from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_g01_runtime.py"
FIXTURE = ROOT / "tests" / "fixtures" / "g01-runtime-valid.yaml"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_g01_runtime", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G01RuntimeGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_generator()
        cls.valid_input = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))

    def test_valid_r1_input_generates_pass(self) -> None:
        artifacts, outcome = self.module.generate_artifacts(copy.deepcopy(self.valid_input))
        self.assertEqual("PASS", outcome)
        self.assertEqual("READY", artifacts["g0"]["status"])
        self.assertEqual("READY", artifacts["intake"]["status"])
        self.assertEqual("PASS", artifacts["preflight"]["outcome"])
        self.assertEqual("G2_AUTOMATIC_BOUNDED", artifacts["preflight"]["required_gate"])
        self.assertEqual([], artifacts["preflight"]["blockers"])
        check_ids = {item["id"] for item in artifacts["preflight"]["checks"]}
        self.assertIn("EXECUTION_MODE_COMPATIBILITY", check_ids)
        self.assertIn("BOOTSTRAP_BEHAVIOR_CONTRACTS", check_ids)
        self.assertIn("DELIVERY_LIFECYCLE_SCOPE", check_ids)
        self.assertEqual(
            "chat_connector_only",
            artifacts["preflight"]["runtime_context"]["execution_mode"],
        )
        self.assertIn(
            "mark_pr_ready_for_review_after_g3_pass",
            artifacts["intake"]["delivery_lifecycle"]["authorized_actions"],
        )
        self.assertIn(
            "merge",
            artifacts["intake"]["delivery_lifecycle"]["downstream_non_goals"],
        )

    def test_unclaimed_task_fails_closed(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["task"]["claimed"] = False
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "DS_ADMIN_TASK_NOT_CLAIMED",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_missing_required_source_fails_closed(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["sources"][0]["status"] = "MISSING"
        payload["sources"][0]["source_sha"] = None
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertEqual("BLOCKED", artifacts["g0"]["status"])
        self.assertIn(
            "REQUIRED_SOURCE_UNAVAILABLE",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_r2_without_human_direction_needs_input(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["risk"]["class"] = "R2"
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("NEEDS_INPUT", outcome)
        self.assertEqual("G2_HUMAN_DIRECTION", artifacts["preflight"]["required_gate"])
        self.assertIn(
            "HUMAN_DIRECTION_REQUIRED",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_unsupported_execution_mode_fails_closed(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["selected_profile"]["supported_execution_modes"] = ["local_agent"]
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "EXECUTION_MODE_UNSUPPORTED",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_missing_behavior_contract_fails_closed(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["required_behavior_contracts"][0]["status"] = "MISSING"
        payload["runtime"]["required_behavior_contracts"][0]["source_sha"] = None
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "BEHAVIOR_CONTRACT_UNAVAILABLE",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_cli_generates_schema_valid_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
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
            self.assertTrue(summary["written"])
            for relative_path in summary["artifacts"]:
                self.assertTrue((workspace / relative_path).is_file(), relative_path)

            preflight = yaml.safe_load(
                (workspace / "g1/preflight/g1-preflight-report.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual("PASS", preflight["outcome"])
            self.assertEqual("G2_AUTOMATIC_BOUNDED", preflight["required_gate"])


    def test_local_agent_requires_source_baseline_evidence(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["execution_mode"] = "local_agent"
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "SOURCE_BASELINE_EVIDENCE_REQUIRED",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_local_agent_clean_matching_source_is_eligible(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["execution_mode"] = "local_agent"
        payload["repository"]["source_baseline"] = {
            "authority": "REMOTE_PROTECTED_BASE",
            "provider": "GitHub",
            "observed_ref": payload["repository"]["base_ref"],
            "observed_sha": payload["repository"]["base_sha"],
            "observed_at_utc": "2026-08-08T14:00:00Z",
            "local_state": {
                "ref": payload["repository"]["base_ref"],
                "head_sha": payload["repository"]["base_sha"],
                "dirty": False,
                "equivalence": "MATCH",
                "analysis_eligible": True,
            },
        }
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("PASS", outcome)
        source_check = next(item for item in artifacts["preflight"]["checks"] if item["id"] == "SOURCE_BASELINE")
        self.assertEqual("SOURCE_BASELINE_VERIFIED", source_check["code"])

    def test_stale_local_state_isolated_while_remote_baseline_remains_valid(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["execution_mode"] = "local_agent"
        payload["repository"]["source_baseline"] = {
            "authority": "REMOTE_PROTECTED_BASE",
            "provider": "GitHub",
            "observed_ref": payload["repository"]["base_ref"],
            "observed_sha": payload["repository"]["base_sha"],
            "observed_at_utc": "2026-08-08T14:00:00Z",
            "local_state": {
                "ref": "main",
                "head_sha": "1111111111111111111111111111111111111111",
                "dirty": False,
                "equivalence": "MISMATCH",
                "analysis_eligible": False,
            },
        }
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("PASS", outcome)
        source_check = next(item for item in artifacts["preflight"]["checks"] if item["id"] == "SOURCE_BASELINE")
        self.assertEqual("LOCAL_ANALYSIS_SOURCE_ISOLATED", source_check["code"])

    def test_dirty_local_state_cannot_be_marked_analysis_eligible(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["execution_mode"] = "local_agent"
        payload["repository"]["source_baseline"] = {
            "authority": "REMOTE_PROTECTED_BASE",
            "provider": "GitHub",
            "observed_ref": payload["repository"]["base_ref"],
            "observed_sha": payload["repository"]["base_sha"],
            "observed_at_utc": "2026-08-08T14:00:00Z",
            "local_state": {
                "ref": payload["repository"]["base_ref"],
                "head_sha": payload["repository"]["base_sha"],
                "dirty": True,
                "equivalence": "MATCH",
                "analysis_eligible": True,
            },
        }
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "LOCAL_ANALYSIS_SOURCE_INELIGIBLE",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_source_baseline_sha_must_match_repository_base(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["runtime"]["execution_mode"] = "local_agent"
        payload["repository"]["source_baseline"] = {
            "authority": "EXPLICIT_TASK_REF",
            "provider": "GitHub",
            "observed_ref": "refs/heads/example",
            "observed_sha": "2222222222222222222222222222222222222222",
            "observed_at_utc": "2026-08-08T14:00:00Z",
            "local_state": {
                "ref": None, "head_sha": None, "dirty": None,
                "equivalence": "NOT_APPLICABLE", "analysis_eligible": False,
            },
        }
        artifacts, outcome = self.module.generate_artifacts(payload)
        self.assertEqual("BLOCKED", outcome)
        self.assertIn(
            "SOURCE_BASELINE_SHA_MISMATCH",
            {item["code"] for item in artifacts["preflight"]["blockers"]},
        )

    def test_invalid_input_exits_two_without_partial_artifacts(self) -> None:
        payload = copy.deepcopy(self.valid_input)
        payload["repository"]["base_sha"] = "not-a-sha"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            input_path = temp / "invalid.yaml"
            workspace = temp / "workspace"
            input_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--root",
                    str(ROOT),
                    "--input",
                    str(input_path),
                    "--workspace",
                    str(workspace),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual("ERROR", summary["outcome"])
            self.assertFalse(summary["written"])
            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
