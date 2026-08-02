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

    def test_07_unsupported_source_contract_blocks(self):
        source = _clone_kwargs(self.kwargs)["source_resolution"]
        source["artifact_type"] = "unsupported"
        card = self.render_with(source_resolution=source)
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", card["reason_code"])

    def test_08_binding_mismatch_across_any_upstream_blocks(self):
        read_scope = _clone_kwargs(self.kwargs)["bounded_read_scope"]
        read_scope["task_id"] = "SCRUM-OTHER"
        read_scope = self.recompute_scope(read_scope)
        card = self.render_with(bounded_read_scope=read_scope)
        self.assertEqual("CARD_SOURCE_BINDING_MISMATCH", card["reason_code"])

    def test_09_risk_digest_is_recomputed(self):
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        risk["risk_level"] = "R3"
        card = self.render_with(risk_profile=risk)
        self.assertEqual("CARD_UPSTREAM_DIGEST_MISMATCH", card["reason_code"])

    def test_10_read_scope_hash_is_recomputed(self):
        read_scope = _clone_kwargs(self.kwargs)["bounded_read_scope"]
        read_scope["files_read"].append("AGENTS.md")
        card = self.render_with(bounded_read_scope=read_scope)
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])

    def test_11_write_scope_hash_is_recomputed(self):
        write_scope = _clone_kwargs(self.kwargs)["bounded_write_scope"]
        write_scope["candidate_paths"].append("AGENTS.md")
        card = self.render_with(bounded_write_scope=write_scope)
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])

    def test_12_explicit_directive_redaction(self):
        directives = [{"json_pointer": "/request/outcome", "classification": "POLICY_REDACTED", "reason_code": "REQUEST_OUTCOME_REDACTED", "replacement": "[REDACTED]"}]
        card = self.render_with(redaction_directives=directives)
        self.assertEqual("[REDACTED]", card["request"]["outcome"])
        self.assertEqual("APPLIED", card["redaction_status"])
        self.assertEqual("CARD_RENDERED_REDACTED", card["reason_code"])

    def test_13_invalid_directive_classification_blocks(self):
        directives = [{"json_pointer": "/request/outcome", "classification": "UNKNOWN", "reason_code": "X", "replacement": "[REDACTED]"}]
        card = self.render_with(redaction_directives=directives)
        self.assertEqual("CARD_REDACTION_DIRECTIVE_INVALID", card["reason_code"])
        self.assertEqual("BLOCKED", card["redaction_status"])

    def test_14_invalid_directive_replacement_blocks(self):
        directives = [{"json_pointer": "/request/outcome", "classification": "SECRET", "reason_code": "X", "replacement": "MASKED"}]
        self.assertEqual("CARD_REDACTION_DIRECTIVE_INVALID", self.render_with(redaction_directives=directives)["reason_code"])

    def test_15_missing_directive_target_blocks(self):
        directives = [{"json_pointer": "/missing", "classification": "SECRET", "reason_code": "X", "replacement": "[REDACTED]"}]
        self.assertEqual("CARD_REDACTION_DIRECTIVE_INVALID", self.render_with(redaction_directives=directives)["reason_code"])

    def test_16_automatic_redaction_handles_nested_non_string_values(self):
        modified, redactions = self.mod.apply_redactions({"auth": {"api_token": {"raw": ["secret"]}}}, [])
        self.assertEqual("[REDACTED]", modified["auth"]["api_token"])
        self.assertNotIn("secret", json.dumps(modified))
        self.assertTrue(redactions)

    def test_17_redaction_metadata_never_contains_original(self):
        modified, redactions = self.mod.apply_redactions({"password": "raw-secret"}, [])
        self.assertNotIn("raw-secret", json.dumps({"payload": modified, "redactions": redactions}))

    def test_18_hash_order_independence(self):
        first = self.render_with()
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request["constraints"] = list(reversed(request["constraints"]))
        request["exclusions"] = list(reversed(request["exclusions"]))
        second = self.render_with(request_contract=request)
        self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])

    def test_19_hash_timestamp_independence(self):
        first = self.render_with(created_at="2026-01-01T00:00:00Z")
        second = self.render_with(created_at="2026-12-31T00:00:00Z")
        self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])

    def test_20_scope_hash_changes_on_source_mode_drift(self):
        source = _clone_kwargs(self.kwargs)["source_resolution"]
        source["source_mode"] = "MIXED"
        card = self.render_with(source_resolution=source)
        self.assertNotEqual(self.render_with()["scope_hash"], card["scope_hash"])

    def test_21_scope_hash_changes_on_source_revision_drift(self):
        source = _clone_kwargs(self.kwargs)["source_resolution"]
        source["revision"] = "source/v2"
        self.assertNotEqual(self.render_with()["scope_hash"], self.render_with(source_resolution=source)["scope_hash"])

    def test_22_snapshot_changes_on_status_and_reason_drift(self):
        ready = self.render_with()
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        risk.update({"outcome": "BLOCKED", "reason_code": "RISK_SOURCE_STALE", "reason_codes": ["RISK_SOURCE_STALE"]})
        risk = self.recompute_risk(risk)
        blocked = self.render_with(risk_profile=risk)
        self.assertNotEqual(ready["snapshot_hash"], blocked["snapshot_hash"])

    def test_23_snapshot_changes_on_material_request_drift(self):
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request["intent"] = "Different intent"
        self.assertNotEqual(self.render_with()["snapshot_hash"], self.render_with(request_contract=request)["snapshot_hash"])

    def test_24_expected_snapshot_match_passes(self):
        baseline = self.render_with()
        card = self.render_with(expected_snapshot_hash=baseline["snapshot_hash"])
        self.assertEqual("READY", card["outcome"])

    def test_25_expected_snapshot_mismatch_blocks(self):
        card = self.render_with(expected_snapshot_hash="0" * 64)
        self.assertEqual("CARD_SNAPSHOT_HASH_MISMATCH", card["reason_code"])

    def test_26_blocked_cards_remain_schema_shaped(self):
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request.pop("intent")
        card = self.render_with(request_contract=request)
        required = {"request", "source_bindings", "repository_context", "risk_projection", "read_scope_projection", "write_scope_projection", "upstream_artifacts", "scope_hash", "snapshot_hash"}
        self.assertTrue(required.issubset(card))

    def test_27_upstream_summary_contains_all_seven_artifacts(self):
        card = self.render_with()
        self.assertEqual(7, len(card["upstream_artifacts"]))

    def test_28_source_binding_projection_contains_mode_and_revisions(self):
        card = self.render_with()
        source = next(item for item in card["source_bindings"] if item["source"].endswith("source-resolution"))
        self.assertEqual("REPO", source["mode"])
        self.assertEqual("source/v1", source["revision"])

    def test_29_scope_projections_keep_canonical_hashes(self):
        card = self.render_with()
        self.assertRegex(card["read_scope_projection"]["read_scope_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(card["write_scope_projection"]["write_scope_hash"], r"^[0-9a-f]{64}$")

    def test_30_reason_codes_are_sorted_unique(self):
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        risk.update({"outcome": "BLOCKED", "reason_code": "RISK_SOURCE_STALE", "reason_codes": ["RISK_SOURCE_STALE"]})
        risk = self.recompute_risk(risk)
        card = self.render_with(risk_profile=risk, redaction_directives=[{"json_pointer": "/request/outcome", "classification": "POLICY_REDACTED", "reason_code": "X", "replacement": "[REDACTED]"}])
        self.assertEqual(sorted(set(card["reason_codes"])), card["reason_codes"])

    def test_31_canonical_json_is_deterministic(self):
        self.assertEqual('{"a":2,"b":1}', self.mod.canonical_json({"b": 1, "a": 2}))

    def test_32_digest_payload_is_sha256(self):
        self.assertRegex(self.mod.digest_payload({"key": "value"}), r"^[0-9a-f]{64}$")

    def test_33_risk_digest_ignores_classified_at(self):
        risk = _clone_kwargs(self.kwargs)["risk_profile"]
        first = self.mod.compute_risk_decision_digest(risk)
        risk["classified_at"] = "2099-01-01T00:00:00Z"
        self.assertEqual(first, self.mod.compute_risk_decision_digest(risk))

    def test_34_scope_digest_ignores_evidence_timestamp(self):
        read_scope = _clone_kwargs(self.kwargs)["bounded_read_scope"]
        first = self.mod.compute_scope_digest(read_scope)
        read_scope["observed_at"] = "2099-01-01T00:00:00Z"
        self.assertEqual(first, self.mod.compute_scope_digest(read_scope))

    def test_35_validate_upstream_bindings_checks_all_artifacts(self):
        args = _clone_kwargs(self.kwargs)
        args["bounded_write_scope"]["base_sha"] = "b" * 40
        result = self.mod.validate_upstream_bindings(
            task_id=args["task_id"], repository=args["repository"], base_sha=args["base_sha"],
            request_contract=args["request_contract"], source_resolution=args["source_resolution"],
            repo_identity=args["repo_identity"], protected_base_snapshot=args["protected_base_snapshot"],
            risk_profile=args["risk_profile"], bounded_read_scope=args["bounded_read_scope"],
            bounded_write_scope=args["bounded_write_scope"],
        )
        self.assertTrue(result["has_errors"])

    def test_36_non_mapping_upstream_returns_blocked_card(self):
        card = self.render_with(request_contract=[])
        self.assertEqual("CARD_INPUT_INVALID", card["reason_code"])

    def test_37_malformed_request_lists_reject_contract(self):
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request["constraints"] = "not-a-list"
        self.assertEqual("CARD_UPSTREAM_CONTRACT_INVALID", self.render_with(request_contract=request)["reason_code"])

    def test_38_invalid_scope_hash_format_is_digest_mismatch(self):
        read_scope = _clone_kwargs(self.kwargs)["bounded_read_scope"]
        read_scope["scope_hash"] = "bad"
        card = self.render_with(bounded_read_scope=read_scope)
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])

    def test_39_card_snapshot_hash_includes_reason_codes(self):
        card = self.render_with()
        copy = json.loads(json.dumps(card))
        copy["reason_codes"] = ["DIFFERENT"]
        copy["snapshot_hash"] = "pending"
        self.assertNotEqual(card["snapshot_hash"], self.mod.digest_payload({k: v for k, v in copy.items() if k not in {"created_at", "snapshot_hash"}}))

    def test_40_no_arbitrary_upstream_dictionary_copy(self):
        request = _clone_kwargs(self.kwargs)["request_contract"]
        request["arbitrary_internal"] = {"do_not_copy": True}
        card = self.render_with(request_contract=request)
        self.assertNotIn("arbitrary_internal", json.dumps(card))

    def test_41_redaction_directive_cannot_change_scope_hash(self):
        directives = [{"json_pointer": "/scope_hash", "classification": "SECRET", "reason_code": "X", "replacement": "[REDACTED]"}]
        self.assertEqual("CARD_REDACTION_DIRECTIVE_INVALID", self.render_with(redaction_directives=directives)["reason_code"])

    def test_42_created_at_can_be_none(self):
        self.assertEqual("", self.render_with(created_at=None)["created_at"])

    def test_43_snapshot_hash_is_lowercase_hex(self):
        self.assertRegex(self.render_with()["snapshot_hash"], r"^[0-9a-f]{64}$")

    def test_44_scope_hash_is_lowercase_hex(self):
        self.assertRegex(self.render_with()["scope_hash"], r"^[0-9a-f]{64}$")

    def test_45_default_happy_path_is_not_redacted(self):
        card = self.render_with()
        self.assertEqual("NONE", card["redaction_status"])
        self.assertEqual([], card["redactions"])


if __name__ == "__main__":
    unittest.main()
