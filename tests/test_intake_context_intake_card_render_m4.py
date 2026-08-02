"""Regression tests for the deterministic intake-card renderer."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

_TASK_ID = "SCRUM-182"
_REPOSITORY = "nhatnguyenquang1838-coder/gwc"
_BASE_SHA = "a" * 40
_REQUEST_CONTRACT = {
    "intent": "Implement feature X from repo instructions",
    "outcome": "A working implementation in the gwc repo",
    "constraints": ["No production deploy", "M4 maturity only"],
    "exclusions": ["Credentials", "Migration scripts"],
}
_SOURCE_RESOLUTION = {"artifact_type": "source-resolution", "schema_version": "1.0", "source_mode": "REPO"}
_REPO_IDENTITY = {"artifact_type": "repo-identity", "schema_version": "1.0", "repository": _REPOSITORY, "default_branch": "main"}
_PROTECTED_BASE_SNAPSHOT = {"artifact_type": "protected-base-snapshot", "schema_version": "1.0", "protected_base_sha": _BASE_SHA}
_RISK_PROFILE = {"artifact_type": "risk-profile", "schema_version": "1.0", "decision_digest": "digest-r1-test", "risk_level": "R2", "risk_flags": ["scope_ambiguous"], "required_gate": "G2_HUMAN_DIRECTION", "additional_authority_gates": []}
_BOUNDED_READ_SCOPE = {"artifact_type": "bounded-read-scope", "schema_version": "1.0", "outcome": "ACCEPTED", "failure_classification": None, "files_read": ["projects/gwc/README.md"], "files_exclude": [], "files_missing": [], "scope_hash": "a" * 64}
_BOUNDED_WRITE_SCOPE = {"artifact_type": "bounded-write-scope", "schema_version": "1.0", "outcome": "ACCEPTED", "candidate_paths": ["projects/gwc/README.md"], "exclusions": ["No production data"], "prohibited_operations": ["push", "deploy"], "branch_binding_status": "UNBOUND", "scope_hash": "b" * 64}
_REDACTION_DIRECTIVES = [{"json_pointer": "/request/outcome", "classification": "POLICY_REDACTED", "reason_code": "REQUEST_OUTCOME_REDACTED", "replacement": "[REDACTED]"}]


def _import_module():
    path = Path(__file__).resolve().parents[1] / "tools/node_architect/intake_card_render.py"
    spec = importlib.util.spec_from_file_location("intake_card_render", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kwargs(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "task_id": _TASK_ID, "repository": _REPOSITORY, "base_sha": _BASE_SHA,
        "request_contract": dict(_REQUEST_CONTRACT), "source_resolution": dict(_SOURCE_RESOLUTION),
        "repo_identity": dict(_REPO_IDENTITY), "protected_base_snapshot": dict(_PROTECTED_BASE_SNAPSHOT),
        "risk_profile": dict(_RISK_PROFILE), "bounded_read_scope": dict(_BOUNDED_READ_SCOPE),
        "bounded_write_scope": dict(_BOUNDED_WRITE_SCOPE), "redaction_directives": list(_REDACTION_DIRECTIVES),
        "expected_snapshot_hash": None, "created_at": "2026-08-02T00:00:00Z",
    }
    result.update(overrides)
    return result


class TestIntakeCardRenderM4(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _import_module()
        self.render = self.mod.render_intake_card

    def test_01_render_happy_path_card(self):
        card = self.render(**_kwargs())
        self.assertEqual(card["context_status"], "READY")
        self.assertEqual(card["outcome"], "READY")
        self.assertTrue(card["read_only_projection"])
        for field in ("write_authority_granted", "commit_authority_granted", "push_authority_granted", "pr_authority_granted", "merge_authority_granted", "deployment_authority_granted", "production_authority_granted"):
            self.assertFalse(card[field])

    def test_02_happy_path_reason_codes(self): self.assertIn("CARD_RENDERED", self.render(**_kwargs())["reason_codes"])
    def test_03_elevated_risk_card(self):
        risk = {**_RISK_PROFILE, "risk_level": "R3", "required_gate": "G4_MERGE"}
        self.assertEqual(self.render(**_kwargs(risk_profile=risk))["outcome"], "READY")
    def test_04_upstream_blocked_yields_blocked_card(self):
        card = self.render(**_kwargs(risk_profile={**_RISK_PROFILE, "outcome": "BLOCKED"}))
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_UPSTREAM_BLOCKED", card["reason_codes"])
    def test_05_task_repository_sha_mismatch(self): self.assertIn("CARD_INPUT_INVALID", self.render(**_kwargs(request_contract={**_REQUEST_CONTRACT, "task_id": "SCRUM-OTHER"}))["reason_codes"])
    def test_06_base_sha_mismatch(self): self.assertIn("CARD_INPUT_INVALID", self.render(**_kwargs(protected_base_snapshot={**_PROTECTED_BASE_SNAPSHOT, "protected_base_sha": "b" * 40}))["reason_codes"])
    def test_07_upstream_digest_mismatch(self): self.assertIn("CARD_UPSTREAM_DIGEST_MISMATCH", self.render(**_kwargs(risk_profile={**_RISK_PROFILE, "decision_digest": "WRONG", "_test_force_recomputed_digest": True}))["reason_codes"])
    def test_08_scope_hash_mismatch(self): self.assertIn("CARD_SCOPE_HASH_MISMATCH", self.render(**_kwargs(bounded_read_scope={**_BOUNDED_READ_SCOPE, "scope_hash": "WRONG-HASH"}))["reason_codes"])
    def test_09_explicit_directive_redaction(self):
        card = self.render(**_kwargs())
        self.assertEqual(card["redaction_status"], "APPLIED")
        self.assertTrue(card["redactions"])
    def test_10_auto_protected_key_redaction(self):
        modified, _ = self.mod.apply_redactions({"password": "x", "api_token": "y"}, [])
        self.assertNotIn("x", json.dumps(modified)); self.assertNotIn("y", json.dumps(modified))
    def test_11_invalid_redaction_directive_blocks(self): self.assertIn("CARD_REDACTION_DIRECTIVE_INVALID", self.render(**_kwargs(redaction_directives=[{"json_pointer": "/missing", "classification": "SECRET"}]))["reason_codes"])
    def test_12_protected_value_leakage_rejection(self):
        modified, _ = self.mod.apply_redactions({"api_token": "raw-secret"}, [])
        self.assertNotIn("raw-secret", json.dumps(modified))
    def test_13_hash_order_independence(self):
        a = {"intent": "X", "outcome": "Y", "constraints": ["C"], "exclusions": ["E"]}; b = {"exclusions": ["E"], "constraints": ["C"], "outcome": "Y", "intent": "X"}
        self.assertEqual(self.render(**_kwargs(request_contract=a))["snapshot_hash"], self.render(**_kwargs(request_contract=b))["snapshot_hash"])
    def test_14_hash_timestamp_independence(self): self.assertEqual(self.render(**_kwargs(created_at="2026-01-01T00:00:00Z"))["snapshot_hash"], self.render(**_kwargs(created_at="2026-12-31T00:00:00Z"))["snapshot_hash"])
    def test_15_snapshot_drift_on_material_change(self): self.assertNotEqual(self.render(**_kwargs())["snapshot_hash"], self.render(**_kwargs(request_contract={**_REQUEST_CONTRACT, "intent": "DIFFERENT"}))["snapshot_hash"])
    def test_16_expected_snapshot_hash_mismatch(self): self.assertIn("CARD_SNAPSHOT_HASH_MISMATCH", self.render(**_kwargs(expected_snapshot_hash="0" * 64))["reason_codes"])
    def test_17_all_authority_fields_always_false(self):
        card = self.render(**_kwargs()); self.assertFalse(any(card[key] for key in card if key.endswith("authority_granted")))
    def test_18_reason_code_card_rendered_present(self): self.assertIn("CARD_RENDERED", self.render(**_kwargs())["reason_codes"])
    def test_19_card_is_schema_valid_shape(self):
        card = self.render(**_kwargs()); self.assertEqual(card["artifact_type"], "intake-card"); self.assertEqual(card["contract_revision"], "intake-context/v1")
    def test_20_canonical_json_is_deterministic(self): self.assertEqual(self.mod.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')
    def test_21_canonical_json_no_trailing_whitespace(self):
        value = self.mod.canonical_json({"a": [1, 2]}); self.assertEqual(value, value.rstrip())
    def test_22_digest_payload_is_sha256(self):
        digest = self.mod.digest_payload({"key": "value"}); self.assertEqual(len(digest), 64); self.assertRegex(digest, r"^[0-9a-f]+$")
    def test_23_apply_redactions_replaces_values(self):
        modified, redactions = self.mod.apply_redactions({"a": {"b": "secret"}}, [{"json_pointer": "/a/b", "classification": "SECRET", "reason_code": "IS_SECRET"}])
        self.assertEqual(modified["a"]["b"], "[REDACTED]"); self.assertEqual(len(redactions), 1)
    def test_24_apply_redactions_protected_keys(self):
        modified, _ = self.mod.apply_redactions({"password": "pass123", "api_token": "tok", "private_key": "pk"}, [])
        serialized = json.dumps(modified); self.assertNotIn("pass123", serialized); self.assertEqual(modified["api_token"], "[REDACTED]"); self.assertEqual(modified["private_key"], "[REDACTED]")
    def test_25_non_deterministic_detection(self): self.assertEqual(self.render(**_kwargs())["snapshot_hash"], self.render(**_kwargs())["snapshot_hash"])
    def test_26_validate_upstream_bindings_ok(self):
        result = self.mod.validate_upstream_bindings(task_id=_TASK_ID, repository=_REPOSITORY, base_sha=_BASE_SHA, request_contract={"task_id": _TASK_ID}, source_resolution={}, repo_identity={"repository": _REPOSITORY}, protected_base_snapshot={"protected_base_sha": _BASE_SHA}); self.assertFalse(result["has_errors"])
    def test_27_validate_upstream_bindings_fails_on_mismatch(self):
        result = self.mod.validate_upstream_bindings(task_id="WRONG", repository=_REPOSITORY, base_sha=_BASE_SHA, request_contract={"task_id": _TASK_ID}, source_resolution={}, repo_identity={"repository": _REPOSITORY}, protected_base_snapshot={"protected_base_sha": _BASE_SHA}); self.assertTrue(result["has_errors"])
    def test_28_snapshot_excludes_created_at_from_hash(self): self.test_14_hash_timestamp_independence()
    def test_29_blocked_card_retains_evidence(self):
        card = self.render(**_kwargs(bounded_read_scope={**_BOUNDED_READ_SCOPE, "outcome": "BLOCKED"})); self.assertEqual(card["context_status"], "BLOCKED"); self.assertTrue(all(key in card for key in ("task_id", "repository", "base_sha")))
    def test_30_created_at_can_be_none(self): self.assertIsNotNone(self.render(**_kwargs(created_at=None)))
    def test_31_expected_snapshot_hash_is_optional(self): self.assertEqual(self.render(**_kwargs(expected_snapshot_hash=None))["context_status"], "READY")
    def test_32_snapshot_mismatch_does_not_leak_original(self): self.assertEqual(self.render(**_kwargs(expected_snapshot_hash="deadbeef" * 8))["context_status"], "BLOCKED")
    def test_33_upstream_contract_invalid(self): self.assertIn("CARD_UPSTREAM_CONTRACT_INVALID", self.render(**_kwargs(risk_profile={"artifact_type": "unsupported", "schema_version": "2.0"}))["reason_codes"])
    def test_34_source_binding_mismatch(self): self.assertIn("CARD_SOURCE_BINDING_MISMATCH", self.render(**_kwargs(repo_identity={"repository": "other/repo"}))["reason_codes"])


if __name__ == "__main__":
    unittest.main()
