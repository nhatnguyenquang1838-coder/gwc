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
