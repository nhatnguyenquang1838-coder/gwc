from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ImplementationPlanHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_module("validate_g01_scrum89", "tools/validate_g01.py")
        cls.generator = load_module("generate_g01_scrum89", "tools/generate_g01_runtime.py")
        cls.preflight_schema = json.loads((ROOT / "schemas/g1-preflight-report.schema.json").read_text())
        cls.decision_schema = json.loads((ROOT / "schemas/g1-decision-record.schema.json").read_text())
        cls.runtime_schema = json.loads((ROOT / "schemas/g01-runtime-input.schema.json").read_text())
        for schema in (cls.preflight_schema, cls.decision_schema, cls.runtime_schema):
            Draft202012Validator.check_schema(schema)

    def plan(self, **overrides):
        value = {
            "applicability": "required",
            "reason": "Non-trivial implementation requires impact analysis.",
            "source": "generated_kiro",
            "task_me_applicable": True,
            "task_me_available": False,
            "task_me_invoked": False,
            "task_me_fallback_reason": "Task Me connector unavailable.",
            "canonical_task_uid": "GWC-G1-PLAN-01",
            "repository": "owner/repo",
            "protected_base_sha": "a" * 40,
            "plan_root": ".kiro/specs/gwc-g1-plan-01",
            "requirements_path": ".kiro/specs/gwc-g1-plan-01/requirements.md",
            "design_path": ".kiro/specs/gwc-g1-plan-01/design.md",
            "tasks_path": ".kiro/specs/gwc-g1-plan-01/tasks.md",
            "plan_revision": "sha256:" + "b" * 64,
            "validation_status": "PASS",
            "validation_evidence": "evidence/plan.json",
            "generated_by": "chatgpt-agent/kiro-fallback",
            "generated_at_utc": "2026-07-24T08:00:00Z",
        }
        value.update(overrides)
        return value

    def ref(self, plan):
        return {field: plan[field] for field in self.validator.PLAN_REF_FIELDS}

    def test_complete_generated_kiro_fallback_passes(self):
        plan = self.plan()
        self.assertEqual([], self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        ))

    def test_existing_plan_reuse_passes(self):
        plan = self.plan(source="existing_kiro", task_me_applicable=False, task_me_fallback_reason=None)
        self.assertEqual([], self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        ))

    def test_task_me_plan_requires_invocation(self):
        plan = self.plan(source="task_me", task_me_available=True, task_me_invoked=False, task_me_fallback_reason=None)
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        )}
        self.assertIn("G1_TASK_ME_NOT_INVOKED", codes)
        self.assertIn("G1_TASK_ME_REQUIRED", codes)

    def test_missing_required_plan_field_blocks(self):
        plan = self.plan(tasks_path=None)
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_MISSING", codes)

    def test_invalid_plan_status_blocks(self):
        plan = self.plan(validation_status="FAIL")
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_NOT_VALIDATED", codes)

    def test_not_applicable_is_explicit(self):
        plan = self.plan(
            applicability="not_applicable", source="plan_not_applicable",
            task_me_applicable=False, task_me_available=False, task_me_invoked=False,
            task_me_fallback_reason=None, plan_root=None, requirements_path=None,
            design_path=None, tasks_path=None, plan_revision=None,
            validation_status="NOT_APPLICABLE", validation_evidence=None,
        )
        self.assertEqual([], self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        ))

    def test_plan_aware_schema_version_requires_pair(self):
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"schema_version": "1.1"}, {"schema_version": "1.1"}
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_EVIDENCE_MISSING", codes)

    def test_partial_evidence_pair_blocks(self):
        plan = self.plan()
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan}, {}
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_EVIDENCE_INCOMPLETE", codes)

    def test_stale_revision_blocks(self):
        plan = self.plan()
        ref = self.ref(plan)
        ref["plan_revision"] = "sha256:" + "c" * 64
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": ref},
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_REFERENCE_MISMATCH", codes)

    def test_base_drift_blocks(self):
        plan = self.plan(protected_base_sha="c" * 40)
        codes = {issue.code for issue in self.validator._implementation_plan_issues(
            {"trace": {"repository": "owner/repo", "base_sha": "a" * 40}, "implementation_plan": plan},
            {"implementation_plan_ref": self.ref(plan)},
        )}
        self.assertIn("G1_IMPLEMENTATION_PLAN_BASE_MISMATCH", codes)

    def test_g2_requires_plan_read_receipt(self):
        plan = self.plan()
        artifacts = {"preflight": {"implementation_plan": plan}, "decision": {"implementation_plan_ref": self.ref(plan)}}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "g2").mkdir()
            envelope = {"implementation_plan": self.ref(plan)}
            issues = self.validator._g2_plan_read_issues(workspace, artifacts, envelope)
        self.assertIn("G2_PLAN_READ_RECEIPT_MISSING", {issue.code for issue in issues})

    def test_g2_verified_receipt_passes(self):
        plan = self.plan()
        artifacts = {"preflight": {"implementation_plan": plan}, "decision": {"implementation_plan_ref": self.ref(plan)}}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "g2").mkdir()
            receipt = {
                "canonical_task_uid": plan["canonical_task_uid"], "repository": plan["repository"],
                "base_sha": plan["protected_base_sha"], "plan_revision": plan["plan_revision"],
                "paths_read": [plan["requirements_path"], plan["design_path"], plan["tasks_path"]],
                "scope_consistency": "MATCH", "repository_state": "MATCH", "status": "VERIFIED",
            }
            (workspace / "g2/plan-read-receipt.yaml").write_text(yaml.safe_dump(receipt))
            issues = self.validator._g2_plan_read_issues(workspace, artifacts, {"implementation_plan": self.ref(plan)})
        self.assertEqual([], issues)

    def test_generator_emits_plan_and_route(self):
        runtime_input = {
            "schema_version": "1.0",
            "artifact_type": "g01-runtime-input",
            "generated_at": "2026-07-24T08:00:00Z",
            "project": {"id": "gwc", "name": "GWC", "profile_path": "projects/gwc/project-profile.yaml"},
            "repository": {"full_name": "owner/repo", "base_ref": "main", "base_sha": "a" * 40, "protected_branches": ["main"], "connector": "GitHub", "write_enabled": True, "verified": True},
            "runtime": {
                "agent_runtime_id": "chatgpt-agent", "execution_mode": "chat_connector_only",
                "selected_profile": {"id": "chatgpt", "path": "governance/agent-runtime-profiles/chatgpt.yaml", "status": "active", "source_sha": "a" * 40, "supported_execution_modes": ["chat_connector_only"]},
                "connector_priority": ["GitHub", "DWC", "DW1"], "selected_connector": "GitHub",
                "connector_fallback_evidence": [{"connector": "GitHub", "role": "primary", "status": "AVAILABLE", "evidence": "verified"}],
                "required_behavior_contracts": [{"path": "core/Agent_Behavior_Semantic_Contract_v1.0.md", "required": True, "status": "AVAILABLE", "source_sha": "a" * 40}],
            },
            "task": {"id": "SCRUM-89", "claimed": True},
            "request": {
                "requester": "user", "problem": {"statement": "Plan handoff missing.", "why_now": "G2 can start without plan readback."},
                "desired_outcome": "Draft PR", "affected": ["agents"], "in_scope": ["runtime"], "non_goals": ["merge"],
                "constraints": ["guarded branch"], "assumptions": ["GitHub available"],
                "risks": [{"id": "RISK-1", "description": "drift", "impact": "high", "mitigation": "bind SHA"}],
                "acceptance_criteria": [{"id": "AC-1", "statement": "G2 reads plan", "verifiable": True}], "unresolved_questions": [],
            },
            "policies": [{"id": "GWC", "path": "AGENTS.md", "ref": "main", "source_sha": "a" * 40}],
            "sources": [{"path": "AGENTS.md", "required": True, "status": "AVAILABLE", "source_sha": "a" * 40}],
            "risk": {"class": "R2", "human_direction_confirmed": True},
            "implementation_plan_observation": self.plan(),
        }
        errors = list(Draft202012Validator(self.runtime_schema, format_checker=FormatChecker()).iter_errors(runtime_input))
        self.assertEqual([], errors)
        artifacts, outcome = self.generator.generate_artifacts(runtime_input)
        self.assertEqual("PASS", outcome)
        self.assertEqual("1.1", artifacts["preflight"]["schema_version"])
        self.assertEqual(runtime_input["implementation_plan_observation"], artifacts["preflight"]["implementation_plan"])
        names = {step["name"] for step in artifacts["preflight"]["execution_feasibility"]["route_steps"]}
        self.assertIn("implementation-plan-discovery-validation-and-handoff", names)


if __name__ == "__main__":
    unittest.main()
