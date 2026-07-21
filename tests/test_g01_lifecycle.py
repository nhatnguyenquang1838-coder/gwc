from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_g01", ROOT / "tools" / "validate_g01.py"
)
assert SPEC and SPEC.loader
validate_g01 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_g01
SPEC.loader.exec_module(validate_g01)


class G01LifecycleValidationTests(unittest.TestCase):
    def test_all_g01_schemas_are_valid_draft_2020_12(self) -> None:
        for schema_name in (
            "g0-context-snapshot.schema.json",
            "g1-intake-brief.schema.json",
            "g1-preflight-report.schema.json",
            "g1-options.schema.json",
            "g1-decision-record.schema.json",
        ):
            schema = validate_g01._load_json(ROOT / "schemas" / schema_name)
            Draft202012Validator.check_schema(schema)

    def test_valid_fixture_passes(self) -> None:
        report = validate_g01.validate_workspace(
            ROOT, ROOT / "tests" / "fixtures" / "g01-valid"
        )
        self.assertTrue(report.valid, report.to_dict())
        self.assertEqual("PASS", report.outcome)
        self.assertEqual([], report.issues)

    def test_selected_option_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            shutil.copytree(ROOT / "tests" / "fixtures" / "g01-valid", workspace)
            shutil.copyfile(
                ROOT / "tests" / "fixtures" / "g01-invalid-decision.yaml",
                workspace / "g1" / "decision" / "g1-decision-record.yaml",
            )
            report = validate_g01.validate_workspace(ROOT, workspace)
        codes = {issue.code for issue in report.issues}
        self.assertFalse(report.valid)
        self.assertIn("G1_SELECTED_OPTION_NOT_FOUND", codes)

    def test_missing_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            shutil.copytree(ROOT / "tests" / "fixtures" / "g01-valid", workspace)
            (workspace / "g1" / "decision" / "g1-decision-record.yaml").unlink()
            report = validate_g01.validate_workspace(ROOT, workspace)
        codes = {issue.code for issue in report.issues}
        self.assertEqual("BLOCKED", report.outcome)
        self.assertIn("MISSING_ARTIFACT", codes)

    def test_downstream_gate_artifact_is_required_when_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            shutil.copytree(ROOT / "tests" / "fixtures" / "g01-valid", workspace)
            report = validate_g01.validate_workspace(ROOT, workspace, gate="G2_EXECUTION")
        codes = {issue.code for issue in report.issues}
        self.assertIn("GATE_ARTIFACT_MISSING", codes)

    def test_downstream_gate_artifact_must_be_non_empty_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            shutil.copytree(ROOT / "tests" / "fixtures" / "g01-valid", workspace)
            envelope = workspace / "g2" / "execution-envelope.yaml"
            envelope.parent.mkdir(parents=True)
            envelope.write_text("[]\n", encoding="utf-8")
            report = validate_g01.validate_workspace(ROOT, workspace, gate="G2_EXECUTION")
        codes = {issue.code for issue in report.issues}
        self.assertIn("GATE_ARTIFACT_INVALID", codes)


if __name__ == "__main__":
    unittest.main()
