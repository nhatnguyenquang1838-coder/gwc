import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "node_architect" / "validate_kiro_local_agent_package.py"
RENDERER = REPO_ROOT / "tools" / "node_architect" / "render_kiro_local_agent_package.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validator = load_module(VALIDATOR, "validate_kiro_local_agent_package")
renderer = load_module(RENDERER, "render_kiro_local_agent_package")


class KiroLocalAgentPackageTests(unittest.TestCase):
    def plan(self):
        return {
            "task_id": "REVAMP-GWC-005",
            "checkpoint_id": "chk_revamp_gwc_005_g2",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "base_branch": "main",
            "base_sha": "9ac1d11430a1d6992c394f090158385e6b0fe583",
            "working_branch": "codex/revamp-kiro-local-agent-package-20260722",
            "approval_request_id": "FL-G2-REVAMP-20260722-005",
            "scope_hash_16": "0841550e28da185b",
            "issued_at_utc": "2026-07-21T17:45:00Z",
            "expires_at_utc": "2026-07-23T00:00:00Z",
            "files_read": [
                "core/node-architect/KIRO_STRICT_CODING_STATE_RULE_v0.1.md",
                "core/node-architect/CHECKPOINT_RESUME_RULE_v0.1.md",
            ],
            "files_write": [
                "core/node-architect/KIRO_LOCAL_AGENT_EXECUTION_PACKAGE_v0.1.md",
                "schemas/node-architect/kiro-local-agent-package.schema.json",
                "schemas/node-architect/local-agent-command.schema.json",
                "schemas/node-architect/local-agent-validation-report.schema.json",
                "tools/node_architect/validate_kiro_local_agent_package.py",
                "tools/node_architect/render_kiro_local_agent_package.py",
                "tests/test_kiro_local_agent_package.py",
            ],
            "validation_required": ["python -m unittest discover -s tests -p test_kiro_local_agent_package.py"],
        }

    def package(self):
        return renderer.render_package(self.plan())

    def test_valid_rendered_package(self):
        package = self.package()
        self.assertEqual(["package_valid"], validator.validate_package(package))
        self.assertEqual(package["package_type"], "kiro_local_agent_execution_package")
        self.assertEqual(package["authority"]["gate"], "G2")

    def test_rejects_write_scope_widening(self):
        package = self.package()
        for command in package["commands"]:
            if command["category"] == "modify_scoped_files":
                command["touches"].append("README.md")
        with self.assertRaisesRegex(validator.ValidationError, "outside scope.files_write"):
            validator.validate_package(package)

    def test_rejects_forbidden_command(self):
        package = self.package()
        package["commands"].append(
            {
                "id": "merge-now",
                "category": "merge",
                "description": "Forbidden merge action",
                "touches": [],
            }
        )
        with self.assertRaisesRegex(validator.ValidationError, "not allowed"):
            validator.validate_package(package)

    def test_rejects_missing_g2_authority(self):
        package = self.package()
        package["authority"]["gate"] = "G3"
        with self.assertRaisesRegex(validator.ValidationError, "must be G2"):
            validator.validate_package(package)

    def test_rejects_missing_report_fields(self):
        package = self.package()
        report = {
            "package_id": package["package_id"],
            "task_id": package["task"]["id"],
        }
        with self.assertRaisesRegex(validator.ValidationError, "report missing fields"):
            validator.validate_report(package, report)

    def test_report_detects_changed_files_outside_scope(self):
        package = self.package()
        report = {field: [] for field in renderer.REPORT_FIELDS}
        report.update(
            {
                "package_id": package["package_id"],
                "task_id": package["task"]["id"],
                "checkpoint_id": package["checkpoint"]["checkpoint_id"],
                "repository": package["repository"]["full_name"],
                "base_sha": package["repository"]["base_sha"],
                "branch": package["repository"]["working_branch"],
                "changed_files": ["README.md"],
                "scope_drift": "NONE",
                "prohibited_action_detected": False,
                "next_gate": "G3_PR",
            }
        )
        with self.assertRaisesRegex(validator.ValidationError, "outside package scope"):
            validator.validate_report(package, report)

    def test_cli_renderer_and_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path = tmp_path / "plan.json"
            package_path = tmp_path / "package.json"
            plan_path.write_text(json.dumps(self.plan()), encoding="utf-8")

            render_result = subprocess.run(
                [sys.executable, str(RENDERER), str(plan_path), "--output", str(package_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(render_result.returncode, 0, render_result.stderr + render_result.stdout)

            validate_result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(package_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(validate_result.returncode, 0, validate_result.stderr + validate_result.stdout)
            self.assertIn('"status":"PASS"', validate_result.stdout)


if __name__ == "__main__":
    unittest.main()
