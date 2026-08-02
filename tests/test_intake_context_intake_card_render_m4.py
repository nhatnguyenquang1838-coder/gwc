"""Focused regression tests for the SCRUM-182 intake-card renderer."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TASK = "SCRUM-182"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "a" * 40


def load_module():
    path = ROOT / "tools/node_architect/intake_card_render.py"
    spec = importlib.util.spec_from_file_location("intake_card_render", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures(mod: Any) -> dict[str, Any]:
    binding = [{"source_type": "repository", "ref": "main", "revision": BASE, "status": "VERIFIED"}]
    request = {
        "artifact_type": "request-contract", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "revision": "request/v1",
        "intent": "Repair intake card", "outcome": "Validated card",
        "constraints": ["M4 only", "No deploy"], "exclusions": ["Production"],
    }
    source = {
        "artifact_type": "source-resolution", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "revision": "source/v1",
        "source_mode": "REPO", "source_bindings": binding,
    }
    repo = {
        "artifact_type": "repo-identity", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "revision": "repo/v1",
        "default_branch": "main", "protected_branch": "main",
    }
    protected = {
        "artifact_type": "protected-base-snapshot", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "revision": "base/v1", "protected_base_sha": BASE,
    }
    risk = {
        "artifact_type": "risk-profile", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "source_bindings": binding,
        "outcome": "READY", "risk_level": "R2", "risk_flags": ["scope_ambiguous"],
        "required_gate": "G2_EXECUTION", "additional_authority_gates": [],
        "reason_code": "RISK_CLASSIFIED_R2", "reason_codes": ["RISK_CLASSIFIED_R2"],
        "classified_at": "2026-08-02T00:00:00Z",
    }
    risk["decision_digest"] = mod.compute_risk_decision_digest(risk)
    read_scope = {
        "artifact_type": "bounded-read-scope", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "source_bindings": binding,
        "outcome": "READY", "failure_classification": None,
        "files_read": ["projects/gwc/README.md"], "files_exclude": [], "files_missing": [],
        "observed_at": "2026-08-02T00:00:00Z",
    }
    read_scope["scope_hash"] = mod.compute_scope_digest(read_scope)
    write_scope = {
        "artifact_type": "bounded-write-scope", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "source_bindings": binding,
        "outcome": "READY", "candidate_paths": ["schemas/intake-card.schema.json"],
        "exclusions": ["Production"], "prohibited_operations": ["FORCE_PUSH"],
        "branch_binding_status": "REQUIRED_AT_G2", "required_authority_gates": ["G2_EXECUTION"],
        "evaluated_at": "2026-08-02T00:00:00Z",
    }
    write_scope["scope_hash"] = mod.compute_scope_digest(write_scope)
    return {
        "task_id": TASK, "repository": REPO, "base_sha": BASE,
        "request_contract": request, "source_resolution": source, "repo_identity": repo,
        "protected_base_snapshot": protected, "risk_profile": risk,
        "bounded_read_scope": read_scope, "bounded_write_scope": write_scope,
        "redaction_directives": [], "expected_snapshot_hash": None,
        "created_at": "2026-08-02T00:00:00Z",
    }


class IntakeCardRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()
        cls.schema = json.loads((ROOT / "schemas/intake-card.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def setUp(self) -> None:
        self.kwargs = fixtures(self.mod)

    def render(self, **changes: Any) -> dict[str, Any]:
        args = copy.deepcopy(self.kwargs)
        args.update(changes)
        return self.mod.render_intake_card(**args)

    def assert_schema(self, card: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(card), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors])

    def test_ready_card_is_schema_valid(self):
        card = self.render()
        self.assertEqual(("READY", "CARD_RENDERED"), (card["outcome"], card["reason_code"]))
        self.assert_schema(card)

    def test_all_authority_fields_are_false(self):
        card = self.render()
        self.assertFalse(any(value for key, value in card.items() if key.endswith("authority_granted")))

    def test_actual_source_ref_is_projected(self):
        card = self.render()
        row = next(item for item in card["source_bindings"] if item["source"] == "repository")
        self.assertEqual(("main", BASE, "VERIFIED", "REPO"), (row["binding"], row["revision"], row["status"], row["mode"]))

    def test_blocked_upstream_yields_blocked_card(self):
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        risk["outcome"] = "BLOCKED"
        risk["decision_digest"] = self.mod.compute_risk_decision_digest(risk)
        card = self.render(risk_profile=risk)
        self.assertEqual(("BLOCKED", "CARD_UPSTREAM_BLOCKED"), (card["outcome"], card["reason_code"]))
        self.assert_schema(card)

    def test_invalid_top_level_input_blocks(self):
        self.assertEqual("CARD_INPUT_INVALID", self.render(repository="bad")["reason_code"])

    def test_missing_required_identity_blocks(self):
        request = copy.deepcopy(self.kwargs["request_contract"])
        request.pop("task_id")
        self.assertEqual("CARD_REQUIRED_FIELD_MISSING", self.render(request_contract=request)["reason_code"])

    def test_unsupported_artifact_type_blocks(self):
        source = copy.deepcopy(self.kwargs["source_resolution"])
        source["artifact_type"] = "wrong"
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render(source_resolution=source)["reason_code"])

    def test_binding_mismatch_blocks(self):
        repo = copy.deepcopy(self.kwargs["repo_identity"])
        repo["base_sha"] = "b" * 40
        self.assertEqual("CARD_SOURCE_BINDING_MISMATCH", self.render(repo_identity=repo)["reason_code"])

    def test_invalid_risk_semantics_block(self):
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        risk["risk_level"] = "R9"
        risk["decision_digest"] = self.mod.compute_risk_decision_digest(risk)
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render(risk_profile=risk)["reason_code"])

    def test_invalid_outcome_semantics_block(self):
        scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        scope["outcome"] = "UNKNOWN"
        scope["scope_hash"] = self.mod.compute_scope_digest(scope)
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render(bounded_read_scope=scope)["reason_code"])

    def test_invalid_source_status_blocks(self):
        source = copy.deepcopy(self.kwargs["source_resolution"])
        source["source_bindings"][0]["status"] = "UNKNOWN"
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render(source_resolution=source)["reason_code"])

    def test_invalid_branch_status_blocks(self):
        scope = copy.deepcopy(self.kwargs["bounded_write_scope"])
        scope["branch_binding_status"] = "UNKNOWN"
        scope["scope_hash"] = self.mod.compute_scope_digest(scope)
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render(bounded_write_scope=scope)["reason_code"])

    def test_risk_digest_mismatch_blocks(self):
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        risk["decision_digest"] = "sha256:" + "0" * 64
        self.assertEqual("CARD_UPSTREAM_DIGEST_MISMATCH", self.render(risk_profile=risk)["reason_code"])

    def test_scope_hash_mismatch_blocks(self):
        scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        scope["scope_hash"] = "sha256:" + "0" * 64
        card = self.render(bounded_read_scope=scope)
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])

    def test_explicit_redaction_is_recorded(self):
        directive = {"json_pointer": "/request/outcome", "classification": "POLICY_REDACTED", "reason_code": "POLICY", "replacement": "[REDACTED]"}
        card = self.render(redaction_directives=[directive])
        self.assertEqual("[REDACTED]", card["request"]["outcome"])
        self.assertEqual("APPLIED", card["redaction_status"])
        self.assertNotIn("Validated card", json.dumps(card))

    def test_invalid_redaction_directive_blocks(self):
        directive = {"json_pointer": "/missing", "classification": "SECRET", "reason_code": "X", "replacement": "[REDACTED]"}
        self.assertEqual("CARD_REDACTION_DIRECTIVE_INVALID", self.render(redaction_directives=[directive])["reason_code"])

    def test_automatic_protected_key_redaction(self):
        request = copy.deepcopy(self.kwargs["request_contract"])
        request["intent"] = {"client_secret": {"raw": "leak"}}
        card = self.render(request_contract=request)
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", card["reason_code"])

    def test_hashes_ignore_created_at(self):
        first = self.render(created_at="2026-08-02T00:00:00Z")
        second = self.render(created_at="2099-01-01T00:00:00Z")
        self.assertEqual((first["scope_hash"], first["snapshot_hash"]), (second["scope_hash"], second["snapshot_hash"]))

    def test_hashes_ignore_semantic_array_order(self):
        request = copy.deepcopy(self.kwargs["request_contract"])
        request["constraints"].reverse()
        card = self.render(request_contract=request)
        original = self.render()
        self.assertEqual((original["scope_hash"], original["snapshot_hash"]), (card["scope_hash"], card["snapshot_hash"]))

    def test_material_request_drift_changes_snapshot(self):
        request = copy.deepcopy(self.kwargs["request_contract"])
        request["intent"] = "Different intent"
        self.assertNotEqual(self.render()["snapshot_hash"], self.render(request_contract=request)["snapshot_hash"])

    def test_source_revision_drift_changes_hashes(self):
        source = copy.deepcopy(self.kwargs["source_resolution"])
        source["revision"] = "source/v2"
        source["source_bindings"][0]["revision"] = "b" * 40
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        read_scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        write_scope = copy.deepcopy(self.kwargs["bounded_write_scope"])
        for artifact in (risk, read_scope, write_scope):
            artifact["source_bindings"] = copy.deepcopy(source["source_bindings"])
        risk["decision_digest"] = self.mod.compute_risk_decision_digest(risk)
        read_scope["scope_hash"] = self.mod.compute_scope_digest(read_scope)
        write_scope["scope_hash"] = self.mod.compute_scope_digest(write_scope)
        changed = self.render(source_resolution=source, risk_profile=risk, bounded_read_scope=read_scope, bounded_write_scope=write_scope)
        original = self.render()
        self.assertNotEqual((original["scope_hash"], original["snapshot_hash"]), (changed["scope_hash"], changed["snapshot_hash"]))

    def test_expected_snapshot_mismatch_blocks(self):
        card = self.render(expected_snapshot_hash="0" * 64)
        self.assertEqual("CARD_SNAPSHOT_HASH_MISMATCH", card["reason_code"])

    def test_validate_upstream_bindings_reports_error(self):
        args = copy.deepcopy(self.kwargs)
        args["bounded_write_scope"]["base_sha"] = "b" * 40
        result = self.mod.validate_upstream_bindings(**{key: args[key] for key in (
            "task_id", "repository", "base_sha", "request_contract", "source_resolution", "repo_identity",
            "protected_base_snapshot", "risk_profile", "bounded_read_scope", "bounded_write_scope")})
        self.assertTrue(result["has_errors"])


if __name__ == "__main__":
    unittest.main()
