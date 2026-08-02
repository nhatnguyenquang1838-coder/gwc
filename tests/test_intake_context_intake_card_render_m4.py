"""Regression tests for the deterministic SCRUM-182 intake-card renderer."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

_TASK_ID = "SCRUM-182"
_REPOSITORY = "nhatnguyenquang1838-coder/gwc"
_BASE_SHA = "a" * 40


def _import_module():
    path = Path(__file__).resolve().parents[1] / "tools/node_architect/intake_card_render.py"
    spec = importlib.util.spec_from_file_location("intake_card_render", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_kwargs(mod: Any) -> dict[str, Any]:
    request = {
        "artifact_type": "request-contract",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "revision": "request/v1",
        "intent": "Implement feature X from repo instructions",
        "outcome": "A working implementation in the gwc repo",
        "constraints": ["M4 maturity only", "No production deploy"],
        "exclusions": ["Migration scripts", "Credentials"],
    }
    source = {
        "artifact_type": "source-resolution",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "source_mode": "REPO",
        "revision": "source/v1",
        "source_bindings": [
            {
                "source_type": "repository",
                "ref": "main",
                "revision": _BASE_SHA,
                "status": "VERIFIED",
            }
        ],
    }
    repo = {
        "artifact_type": "repo-identity",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "default_branch": "main",
        "protected_branch": "main",
        "revision": "repo-identity/v1",
    }
    protected = {
        "artifact_type": "protected-base-snapshot",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "protected_base_sha": _BASE_SHA,
        "revision": "protected-base/v1",
    }
    risk = {
        "artifact_type": "risk-profile",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "source_bindings": source["source_bindings"],
        "outcome": "READY",
        "risk_level": "R2",
        "risk_flags": ["scope_ambiguous"],
        "required_gate": "G2_EXECUTION",
        "additional_authority_gates": [],
        "approval_requirements": ["Exact G2 authority"],
        "reason_code": "RISK_CLASSIFIED_R2",
        "reason_codes": ["RISK_CLASSIFIED_R2"],
        "classified_at": "2026-08-02T00:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    risk["decision_digest"] = mod.compute_risk_decision_digest(risk)
    read_scope = {
        "artifact_type": "bounded-read-scope",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "source_bindings": source["source_bindings"],
        "outcome": "READY",
        "failure_classification": None,
        "files_read": ["projects/gwc/README.md"],
        "files_exclude": [],
        "files_missing": [],
        "observed_at": "2026-08-02T00:00:00Z",
    }
    read_scope["scope_hash"] = mod.compute_scope_digest(read_scope)
    write_scope = {
        "artifact_type": "bounded-write-scope",
        "schema_version": "1.0",
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "source_bindings": source["source_bindings"],
        "outcome": "READY",
        "candidate_paths": ["projects/gwc/README.md"],
        "exclusions": ["No production data"],
        "prohibited_operations": ["deploy", "push-main"],
        "branch_binding_status": "UNBOUND",
        "required_authority_gates": ["G2_EXECUTION"],
        "evaluated_at": "2026-08-02T00:00:00Z",
    }
    write_scope["scope_hash"] = mod.compute_scope_digest(write_scope)
    return {
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "request_contract": request,
        "source_resolution": source,
        "repo_identity": repo,
        "protected_base_snapshot": protected,
        "risk_profile": risk,
        "bounded_read_scope": read_scope,
        "bounded_write_scope": write_scope,
        "redaction_directives": [],
        "expected_snapshot_hash": None,
        "created_at": "2026-08-02T00:00:00Z",
    }


def _clone_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(kwargs))


class TestIntakeCardRenderM4(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _import_module()
        self.render = self.mod.render_intake_card
        self.kwargs = _base_kwargs(self.mod)

    def render_with(self, **overrides: Any) -> dict[str, Any]:
        args = _clone_kwargs(self.kwargs)
        args.update(overrides)
        return self.render(**args)

    def recompute_risk(self, risk: dict[str, Any]) -> dict[str, Any]:
        risk = json.loads(json.dumps(risk))
        risk["decision_digest"] = self.mod.compute_risk_decision_digest(risk)
        return risk

    def recompute_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        scope = json.loads(json.dumps(scope))
        scope["scope_hash"] = self.mod.compute_scope_digest(scope)
        return scope

    def test_01_render_happy_path_card(self):
        card = self.render_with()
        self.assertEqual("READY", card["context_status"])
        self.assertEqual("CARD_RENDERED", card["reason_code"])
        self.assertTrue(card["read_only_projection"])

    def test_02_all_authority_fields_are_false(self):
        card = self.render_with()
        self.assertFalse(any(value for key, value in card.items() if key.endswith("authority_granted")))

    def test_03_elevated_risk_retains_later_gate(self):
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        risk.update({"risk_level": "R3", "required_gate": "G2_EXECUTION", "additional_authority_gates": ["G5_DEPLOY"]})
        risk = self.recompute_risk(risk)
        card = self.render_with(risk_profile=risk)
        self.assertEqual(["G5_DEPLOY"], card["risk_projection"]["additional_authority_gates"])

    def test_04_upstream_blocked_yields_blocked_card(self):
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        risk["outcome"] = "BLOCKED"
        risk["reason_code"] = "RISK_SOURCE_STALE"
        risk["reason_codes"] = ["RISK_SOURCE_STALE"]
        risk = self.recompute_risk(risk)
        card = self.render_with(risk_profile=risk)
        self.assertEqual("BLOCKED", card["outcome"])
        self.assertIn("CARD_UPSTREAM_BLOCKED", card["reason_codes"])

    def test_05_invalid_top_level_input_blocks(self):
        card = self.render_with(repository="not-a-repository")
        self.assertEqual("CARD_INPUT_INVALID", card["reason_code"])

    def test_06_missing_required_request_field_blocks(self):
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request.pop("intent")
        card = self.render_with(request_contract=request)
        self.assertEqual("CARD_REQUIRED_FIELD_MISSING", card["reason_code"])

    def test_07_unsupported_artifact_type_blocks(