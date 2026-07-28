from __future__ import annotations

import json
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "distribution" / "power-package.yaml"
CONFIG_PATH = ROOT / "distribution" / "config" / "gwc.defaults.yaml"
CONFIG_SCHEMA_PATH = ROOT / "distribution" / "contracts" / "gwc-config.schema.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish-power.yml"
G5_STANDING_AUTOMATION_POLICY_PATH = ROOT / "core" / "G5_STANDING_AUTOMATION_POLICY_v1.0.md"
FOUNDATION_SHA = "299cd605899467377cd31651b27d31c3f88db759"

REQUIRED_SOURCE_PATHS = (
    "AGENTS.md",
    "core/Coding_Project_Governance_v1.0.md",
    "core/GATE_LIFECYCLE_CONTRACT_v1.0.md",
    "core/G5_STANDING_AUTOMATION_POLICY_v1.0.md",
    "core/Agent_Operating_Runtime_Contract_v1.0.md",
    "core/Agent_Behavior_Semantic_Contract_v1.0.md",
    "core/Agent_Response_Presentation_Contract_v1.0.md",
    "core/E2E_DRAFT_PR_DELIVERY_RULE.md",
    "core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md",
    "core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md",
    "agents/chatgpt-agent/agent-instructions.md",
    "agents/dwc/agent-instructions.md",
    "agents/dwc/capabilities.yaml",
    "skills/gwc-g0/SKILL.md",
    "skills/gwc-g1/SKILL.md",
    "libs/g0-g1-skill-library/manifest.yaml",
    "libs/g0-g1-skill-library/skills/g0-context-loading.md",
    "libs/g0-g1-skill-library/skills/g1-intake-options-preflight.md",
    "libs/g0-g1-skill-library/skills/g1-decision-record.md",
    "libs/g0-g1-skill-library/skills/g0-g1-approval-envelope.md",
    "docs/g01-lifecycle.md",
    "projects/gwc/project-profile.yaml",
    "projects/gwc/project-instructions.md",
    "projects/gwc/project-extension.md",
    "projects/gwc/package.yaml",
    "schemas/g0-context-snapshot.schema.json",
    "schemas/g01-runtime-input.schema.json",
    "schemas/g01-decision-input.schema.json",
    "schemas/g1-intake-brief.schema.json",
    "schemas/g1-preflight-report.schema.json",
    "schemas/g1-options.schema.json",
    "schemas/g1-decision-record.schema.json",
    "schemas/approval-envelope.schema.json",
    "templates/g01/g0-context-snapshot.template.yaml",
    "templates/g01/g01-runtime-input.template.yaml",
    "templates/g01/g01-decision-input.template.yaml",
    "templates/g01/g1-intake-brief.template.yaml",
    "templates/g01/g1-preflight-report.template.yaml",
    "templates/g01/g1-options.template.yaml",
    "templates/g01/g1-decision-record.template.yaml",
    "tools/generate_g01_runtime.py",
    "tools/capture_g01_decision.py",
    "tools/validate_g01.py",
    "requirements.txt",
)

FORBIDDEN_MARKERS = (
    ".gwc/**",
    ".ua/**",
    ".task-me/**",
    ".kiro/specs/**",
    ".github/**",
    "tests/**",
    "releases/**",
    "apps/**",
    "dashboard/**",
    "frontend/**",
    "**/generated/**",
    "**/.env*",
    "**/secrets/**",
)


def _matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatchcase(path, pattern)


class GWCPowerDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.recipe = yaml.safe_load(RECIPE_PATH.read_text(encoding="utf-8"))

    def test_entrypoints_and_runtime_root(self) -> None:
        self.assertEqual("gwc", self.recipe["metadata"]["id"])
        self.assertEqual(
            ["skills/gwc-g0/SKILL.md", "skills/gwc-g1/SKILL.md"],
            self.recipe["spec"]["package"]["entrypoints"],
        )
        self.assertEqual(".gwc", self.recipe["spec"]["runtime"]["dataRoot"])
        self.assertFalse(self.recipe["spec"]["runtime"]["configRequired"])

    def test_required_dependency_inventory_exists_and_is_selected(self) -> None:
        include = self.recipe["spec"]["include"]
        for relative in REQUIRED_SOURCE_PATHS:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file(), f"missing required source: {relative}")
                self.assertTrue(any(_matches(pattern, relative) for pattern in include), f"not selected: {relative}")

    def test_recipe_has_fail_closed_boundaries(self) -> None:
        forbidden = self.recipe["spec"]["forbidden"]["paths"]
        include = self.recipe["spec"]["include"]
        for marker in FORBIDDEN_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, forbidden)
        for pattern in include:
            lowered = pattern.lower()
            self.assertFalse(lowered.startswith((".gwc", ".ua", ".task-me", ".kiro/specs")))
            self.assertNotIn("dashboard", lowered)
            self.assertNotIn("frontend", lowered)
            self.assertNotIn("generated", lowered)
        self.assertTrue(self.recipe["spec"]["forbidden"]["contentPatterns"])

    def test_neutral_config_validates_and_grants_no_external_write(self) -> None:
        schema = json.loads(CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(config), key=lambda item: list(item.path))
        self.assertEqual([], errors, [error.message for error in errors])
        spec = config["spec"]
        self.assertEqual(".gwc", spec["runtimeRoot"])
        self.assertEqual("jira-mcp", spec["taskProvider"])
        self.assertFalse(spec["externalWritesEnabled"])
        self.assertTrue(spec["approvalRequiredForRepositoryWrites"])

    def test_workflow_is_immutable_and_auto_publishes_main(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(
            f"DW-SuperApps/.github/workflows/reusable-publish-power.yml@{FOUNDATION_SHA}",
            text,
        )
        self.assertIn(f"foundation_ref: {FOUNDATION_SHA}", text)
        self.assertIn("push:", text)
        self.assertIn("      - main", text)
        self.assertGreaterEqual(text.count("default: false"), 2)
        self.assertIn(
            "package_version: ${{ github.event.inputs.package_version || format('gwc-main-{0}-{1}', github.run_number, github.sha) }}",
            text,
        )
        self.assertIn(
            "publish_release: ${{ github.event_name == 'push' || github.event.inputs.publish_release == 'true' }}",
            text,
        )
        self.assertIn(
            "publish_distribution_branch: ${{ github.event_name == 'push' || github.event.inputs.publish_distribution_branch == 'true' }}",
            text,
        )

    def test_auto_publish_has_standing_g5_policy_and_audit_boundary(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        policy = G5_STANDING_AUTOMATION_POLICY_PATH.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("standing automated g5", policy.lower())
        self.assertIn("push` to `main`", policy)
        self.assertIn("publish a GitHub Release", policy)
        self.assertIn("`power-dist` branch", policy)
        self.assertIn("workflow run ID", policy)
        self.assertIn("power-dist` branch SHA", policy)
        self.assertIn("does not grant merge authority", policy)

    def test_package_does_not_embed_task_evidence(self) -> None:
        include = "\n".join(self.recipe["spec"]["include"])
        self.assertNotIn(".gwc/", include)
        self.assertNotIn("execution-envelope", include)
        self.assertNotIn("approval", include.lower().replace("approval-envelope.schema.json", ""))


if __name__ == "__main__":
    unittest.main()
