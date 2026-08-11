"""SCRUM-305-bound regression tests for intake-card-render source-verification blocking.

DELTA_REQUIRED scope (controller decision): render_intake_card() must BLOCK any
non-VERIFIED source binding status (STALE/MISSING/AMBIGUOUS/CONFLICT) across
source_resolution / risk_profile / bounded_read_scope / bounded_write_scope, returning
CARD_SOURCE_NOT_VERIFIED plus a per-status CARD_SOURCE_<STATUS> code, never a misleading
READY card. Verified (VERIFIED) inputs keep prior READY behavior (replay stability,
schema-valid, authority fields false).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TASK = "SCRUM-305"
REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "4e3cd0cbf8b47cf8bfdb5263a41551fc1a2f2fbb"


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
        "intent": "Render accepted F1 intake artifacts into one traceable intake card",
        "outcome": "Validated card",
        "constraints": ["deterministic-order", "provenance", "stable-digest"], "exclusions": ["production"],
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
        "outcome": "READY", "risk_level": "R1", "risk_flags": [],
        "required_gate": "G2_EXECUTION", "additional_authority_gates": [],
        "reason_code": "RISK_CLASSIFIED_R1", "reason_codes": ["RISK_CLASSIFIED_R1"],
        "classified_at": "2026-08-11T00:00:00Z",
    }
    risk["decision_digest"] = mod.compute_risk_decision_digest(risk)
    read_scope = {
        "artifact_type": "bounded-read-scope", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "source_bindings": binding,
        "outcome": "READY", "failure_classification": None,
        "files_read": ["projects/gwc/README.md"], "files_exclude": [], "files_missing": [],
        "observed_at": "2026-08-11T00:00:00Z",
    }
    read_scope["scope_hash"] = mod.compute_scope_digest(read_scope)
    write_scope = {
        "artifact_type": "bounded-write-scope", "schema_version": "1.0", "task_id": TASK,
        "repository": REPO, "base_sha": BASE, "source_bindings": binding,
        "outcome": "READY", "candidate_paths": ["schemas/intake-card.schema.json"],
        "exclusions": ["production"], "prohibited_operations": ["FORCE_PUSH"],
        "branch_binding_status": "REQUIRED_AT_G2", "required_authority_gates": ["G2_EXECUTION"],
        "evaluated_at": "2026-08-11T00:00:00Z",
    }
    write_scope["scope_hash"] = mod.compute_scope_digest(write_scope)
    return {
        "task_id": TASK, "repository": REPO, "base_sha": BASE,
        "request_contract": request, "source_resolution": source, "repo_identity": repo,
        "protected_base_snapshot": protected, "risk_profile": risk,
        "bounded_read_scope": read_scope, "bounded_write_scope": write_scope,
        "redaction_directives": [], "expected_snapshot_hash": None,
        "created_at": "2026-08-11T00:00:00Z",
    }


class Scrum305IntakeCardRendererTests(unittest.TestCase):
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

    def _with_status(self, status: str) -> dict[str, Any]:
        """Return kwargs where source_resolution + all dependent bindings carry `status`."""
        source = copy.deepcopy(self.kwargs["source_resolution"])
        source["source_bindings"][0]["status"] = status
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        risk["source_bindings"] = copy.deepcopy(source["source_bindings"])
        risk["decision_digest"] = self.mod.compute_risk_decision_digest(risk)
        read_scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        read_scope["source_bindings"] = copy.deepcopy(source["source_bindings"])
        read_scope["scope_hash"] = self.mod.compute_scope_digest(read_scope)
        write_scope = copy.deepcopy(self.kwargs["bounded_write_scope"])
        write_scope["source_bindings"] = copy.deepcopy(source["source_bindings"])
        write_scope["scope_hash"] = self.mod.compute_scope_digest(write_scope)
        return dict(
            source_resolution=source, risk_profile=risk,
            bounded_read_scope=read_scope, bounded_write_scope=write_scope,
        )

    # --- accepted VERIFIED inputs still render READY (prior behavior preserved) ---
    def test_verified_inputs_render_ready(self):
        card = self.render()
        self.assertEqual(("READY", "CARD_RENDERED"), (card["outcome"], card["reason_code"]))
        self.assert_schema(card)

    def test_ready_card_is_read_only_projection(self):
        card = self.render()
        self.assertTrue(card["read_only_projection"])

    def test_all_authority_fields_false(self):
        card = self.render()
        self.assertFalse(any(value for key, value in card.items() if key.endswith("authority_granted")))

    # --- replay stability: ordering / created_at do not change scope/snapshot hashes ---
    def test_replay_ignores_created_at(self):
        first = self.render(created_at="2026-08-11T00:00:00Z")
        second = self.render(created_at="2099-01-01T00:00:00Z")
        self.assertEqual((first["scope_hash"], first["snapshot_hash"]),
                         (second["scope_hash"], second["snapshot_hash"]))

    def test_replay_ignores_input_ordering(self):
        request = copy.deepcopy(self.kwargs["request_contract"])
        request["constraints"].reverse()
        card = self.render(request_contract=request)
        original = self.render()
        self.assertEqual((original["scope_hash"], original["snapshot_hash"]),
                         (card["scope_hash"], card["snapshot_hash"]))

    # --- non-VERIFIED source status in source_resolution blocks ---
    def test_stale_source_blocks(self):
        card = self.render(**self._with_status("STALE"))
        self.assertEqual(("BLOCKED", "CARD_SOURCE_NOT_VERIFIED"), (card["outcome"], card["reason_code"]))
        self.assertIn("CARD_SOURCE_STALE", card["reason_codes"])
        self.assertNotEqual("CARD_RENDERED", card["reason_code"])
        self.assert_schema(card)

    def test_missing_source_blocks(self):
        card = self.render(**self._with_status("MISSING"))
        self.assertEqual(("BLOCKED", "CARD_SOURCE_NOT_VERIFIED"), (card["outcome"], card["reason_code"]))
        self.assertIn("CARD_SOURCE_MISSING", card["reason_codes"])
        self.assert_schema(card)

    def test_ambiguous_source_blocks(self):
        card = self.render(**self._with_status("AMBIGUOUS"))
        self.assertEqual(("BLOCKED", "CARD_SOURCE_NOT_VERIFIED"), (card["outcome"], card["reason_code"]))
        self.assertIn("CARD_SOURCE_AMBIGUOUS", card["reason_codes"])
        self.assert_schema(card)

    def test_conflict_source_blocks(self):
        card = self.render(**self._with_status("CONFLICT"))
        self.assertEqual(("BLOCKED", "CARD_SOURCE_NOT_VERIFIED"), (card["outcome"], card["reason_code"]))
        self.assertIn("CARD_SOURCE_CONFLICT", card["reason_codes"])
        self.assert_schema(card)

    # NOTE: UNKNOWN is not a member of SRC_STATUSES, so it is rejected earlier by
    # _contract (CARD_UPSTREAM_CONTRACT_INVALID) rather than the non-VERIFIED block.
    # The controller's delta scope is STALE/MISSING/AMBIGUOUS/CONFLICT only.

    # --- non-VERIFIED status only in bounded_read_scope also blocks (no misleading READY) ---
    def test_non_verified_read_scope_blocks(self):
        read_scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        read_scope["source_bindings"][0]["status"] = "STALE"
        read_scope["scope_hash"] = self.mod.compute_scope_digest(read_scope)
        card = self.render(bounded_read_scope=read_scope)
        self.assertEqual(("BLOCKED", "CARD_SOURCE_NOT_VERIFIED"), (card["outcome"], card["reason_code"]))
        self.assertIn("CARD_SOURCE_STALE", card["reason_codes"])
        self.assert_schema(card)

    # --- existing digest-mismatch behavior remains (no regression) ---
    def test_risk_digest_mismatch_blocks(self):
        risk = copy.deepcopy(self.kwargs["risk_profile"])
        risk["decision_digest"] = "sha256:" + "0" * 64
        card = self.render(risk_profile=risk)
        self.assertEqual("CARD_UPSTREAM_DIGEST_MISMATCH", card["reason_code"])

    def test_scope_hash_mismatch_blocks(self):
        scope = copy.deepcopy(self.kwargs["bounded_read_scope"])
        scope["scope_hash"] = "sha256:" + "0" * 64
        card = self.render(bounded_read_scope=scope)
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])


if __name__ == "__main__":
    unittest.main()
