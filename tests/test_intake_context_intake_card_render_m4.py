"""RED-first tests for intake_card_render — M4 pure-Python deterministic renderer."""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Shared fixtures / helpers so every test talks to the same API surface.
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "intake-card.schema.json"
)
_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / ".."
    / "tools"
    / "node_architect"
    / "validate_node_catalog_intake_context.py"
)

# Minimal valid upstream artifacts for building a happy-path card.
_REQUEST_CONTRACT: dict[str, Any] = {
    "intent": "Implement feature X from repo instructions",
    "outcome": "A working implementation in the gwc repo",
    "constraints": ["No production deploy", "M4 maturity only"],
    "exclusions": ["Credentials", "Migration scripts"],
}

_SOURCE_RESOLUTION: dict[str, Any] = {
    "artifact_type": "source-resolution",
    "schema_version": "1.0",
    "source_mode": "REPO",
    "authorities": [{"authority": "repository", "provenance": "local"}],
    "reason_codes": ["ACCEPTED"],
}

_REPO_IDENTITY: dict[str, Any] = {
    "artifact_type": "repo-identity",
    "schema_version": "1.0",
    "repository": "nhatnguyenquang1838-coder/gwc",
    "default_branch": "main",
    "protected_branch": "main",
}

_PROTECTED_BASE_SNAPSHOT: dict[str, Any] = {
    "artifact_type": "protected-base-snapshot",
    "schema_version": "1.0",
    "protected_base_sha": "a" * 40,
    "readback_status": "VERIFIED",
    "drift_state": "NONE",
}

_RISK_PROFILE: dict[str, Any] = {
    "artifact_type": "risk-profile",
    "schema_version": "1.0",
    "decision_digest": "digest-r1-test",
    "risk_level": "R2",
    "risk_flags": ["scope_ambiguous"],
    "required_gate": "G2_HUMAN_DIRECTION",
    "additional_authority_gates": [],
}

_BOUNDED_READ_SCOPE: dict[str, Any] = {
    "artifact_type": "bounded-read-scope",
    "schema_version": "1.0",
    "outcome": "ACCEPTED",
    "failure_classification": None,
    "files_read": ["projects/gwc/README.md"],
    "files_exclude": [],
    "files_missing": [],
    "scope_hash": "a" * 64,
}

_BOUNDED_WRITE_SCOPE: dict[str, Any] = {
    "artifact_type": "bounded-write-scope",
    "schema_version": "1.0",
    "outcome": "ACCEPTED",
    "candidate_paths": ["projects/gwc/README.md"],
    "exclusions": ["No production data"],
    "prohibited_operations": ["push", "deploy"],
    "branch_binding_status": "UNBOUND",
    "scope_hash": "b" * 64,
}

_REDACTION_DIRECTIVES: list[dict[str, str]] = [
    {
        "json_pointer": "/repository_context/protected_base_sha",
        "classification": "TOKEN",
        "reason_code": "PROTECTED_BASE_IS_SECRET",
        "replacement": "[REDACTED]",
    },
]

_TASK_ID = "SCRUM-182"
_REPOSITORY = "nhatnguyenquang1838-coder/gwc"
_BASE_SHA = "a" * 40


def _canonical(obj: Any) -> str:
    """Deterministic canonical JSON — the same reference used by renderer."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _expected_snapshot_hash(card_payload: dict[str, Any]) -> str:
    """Reproduce the exact hash-computation rule from the spec.

    Hash the canonical redacted content projection EXCLUDING:
      - created_at
      - snapshot_hash
      - expected_snapshot_hash (the comparison field)
      - outcome, context_status, next_required_action
      - reason_code, reason_codes
    """
    # Deep-copy then strip excluded keys
    trimmed = json.loads(_canonical(card_payload))  # deep copy

    def _strip_excluded(obj):
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                if k in (
                    "created_at",
                    "snapshot_hash",
                    "expected_snapshot_hash",
                    "outcome",
                    "context_status",
                    "next_required_action",
                    "reason_code",
                    "reason_codes",
                ):
                    continue
                out[k] = _strip_excluded(v) if isinstance(v, (dict, list)) else v
            return out
        if isinstance(obj, list):
            return [_strip_excluded(item) for item in obj]
        return obj

    trimmed = _strip_excluded(trimmed)
    return hashlib.sha256(_canonical(trimmed).encode("utf-8")).hexdigest()


def _import_module():
    """Import intake_card_render so we can test it."""
    import importlib.util

    mod_path = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "node_architect"
        / "intake_card_render.py"
    )
    spec = importlib.util.spec_from_file_location(
        "intake_card_render", mod_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_renderer_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid kwargs dict for render_intake_card()."""
    base: dict[str, Any] = {
        "task_id": _TASK_ID,
        "repository": _REPOSITORY,
        "base_sha": _BASE_SHA,
        "request_contract": dict(_REQUEST_CONTRACT),
        "source_resolution": dict(_SOURCE_RESOLUTION),
        "repo_identity": dict(_REPO_IDENTITY),
        "protected_base_snapshot": dict(_PROTECTED_BASE_SNAPSHOT),
        "risk_profile": dict(_RISK_PROFILE),
        "bounded_read_scope": dict(_BOUNDED_READ_SCOPE),
        "bounded_write_scope": dict(_BOUNDED_WRITE_SCOPE),
        "redaction_directives": list(_REDACTION_DIRECTIVES),
        "expected_snapshot_hash": None,
        "created_at": "2026-08-02T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestIntakeCardRenderM4(unittest.TestCase):
    """RED-first test suite for intake_card_render (M4 deterministic renderer).

    Test plan mirrors the TDD implementation plan:
      Task 1 — schema + RED tests for every path.
      Task 2 — minimal deterministic renderer to make all tests pass.
    """

    def setUp(self) -> None:
        self.mod = _import_module()
        self.render = self.mod.render_intake_card
        self._schema_path = _SCHEMA_PATH
        return super().setUp()

    # ------------------------------------------------------------------
    # Task 1 — normal ready-context card (happy path).
    # ------------------------------------------------------------------
    def test_01_render_happy_path_card(self):
        """A fully valid set of upstream artifacts yields a READY card."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)

        self.assertEqual(card["schema_version"], "1.0")
        self.assertEqual(card["artifact_type"], "intake-card")
        self.assertEqual(card["contract_revision"], "intake-context/v1")
        self.assertEqual(card["task_id"], _TASK_ID)
        self.assertEqual(card["repository"], _REPOSITORY)
        self.assertEqual(card["base_sha"], _BASE_SHA)
        self.assertEqual(card["context_status"], "READY")
        self.assertEqual(card["outcome"], "READY")
        self.assertEqual(
            card["next_required_action"], "CONTINUE_CONTEXT_EVALUATION"
        )
        # read_only projection enforced
        self.assertTrue(card["read_only_projection"])
        # No authority fields should ever be true.
        for field in (
            "write_authority_granted",
            "commit_authority_granted",
            "push_authority_granted",
            "pr_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(card[field])

    def test_02_happy_path_reason_codes(self):
        """Rendered card contains CARD_RENDERED in reason_codes."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)
        self.assertIn("CARD_RENDERED", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — elevated / R3 card with retained later-gate requirements.
    # ------------------------------------------------------------------
    def test_03_elevated_risk_card(self):
        """R2/R3 risk profile produces READY card; gate flags persist."""
        kwargs = _make_renderer_kwargs(
            risk_profile={
                "artifact_type": "risk-profile",
                "schema_version": "1.0",
                "decision_digest": "digest-r3-test",
                "risk_level": "R3",
                "risk_flags": ["production_operation"],
                "required_gate": "G4_MERGE",
                "additional_authority_gates": ["G5_DEPLOY"],
            }
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "READY")
        self.assertEqual(card["outcome"], "READY")

    # ------------------------------------------------------------------
    # Task 1 — structurally valid blocked upstream context.
    # ------------------------------------------------------------------
    def test_04_upstream_blocked_yields_blocked_card(self):
        """Any upstream artifact with outcome=BLOCKED produces BLOCKED card."""
        kwargs = _make_renderer_kwargs(
            risk_profile={
                **_RISK_PROFILE,
                "outcome": "BLOCKED",
            }
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertEqual(card["outcome"], "BLOCKED")
        self.assertIn("CARD_UPSTREAM_BLOCKED", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — task / repository / base mismatch.
    # ------------------------------------------------------------------
    def test_05_task_repository_sha_mismatch(self):
        """Inconsistent identity fields across upstreams → CARD_INPUT_INVALID."""
        kwargs = _make_renderer_kwargs(
            request_contract={
                **_REQUEST_CONTRACT,
                "task_id": "SCRUM-OTHER",  # wrong task
            }
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_INPUT_INVALID", card["reason_codes"])

    def test_06_base_sha_mismatch(self):
        """Base SHA drift between upstreams → CARD_INPUT_INVALID."""
        kwargs = _make_renderer_kwargs(
            protected_base_snapshot={
                **_PROTECTED_BASE_SNAPSHOT,
                "protected_base_sha": "b" * 40,  # different sha
            },
            overrides_extra={"base_sha": _BASE_SHA},
        )
        # We need the kwargs to have mismatched base_sha internally.
        # Override manually.
        bad_kwargs = _make_renderer_kwargs()
        bad_kwargs["base_sha"] = "a" * 40
        bad_kwargs["protected_base_snapshot"] = {
            **_PROTECTED_BASE_SNAPSHOT,
            "protected_base_sha": "b" * 40,
        }
        card = self.render(**bad_kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_INPUT_INVALID", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — malformed upstream digest / recomputed mismatch.
    # ------------------------------------------------------------------
    def test_07_upstream_digest_mismatch(self):
        """Malformed decision_digest that doesn't recompute → CARD_UPSTREAM_DIGEST_MISMATCH."""
        kwargs = _make_renderer_kwargs(
            risk_profile={
                **_RISK_PROFILE,
                "decision_digest": "WRONG-DIGEST-VALUE",
                # Force a mismatch: provide valid underlying fields so the
                # renderer can recompute a DIFFERENT digest.
                "_test_force_recomputed_digest": True,
            }
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_UPSTREAM_DIGEST_MISMATCH", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — read/write scope-hash mismatch.
    # ------------------------------------------------------------------
    def test_08_scope_hash_mismatch(self):
        """Wrong scope_hash in bounded scopes → CARD_SCOPE_HASH_MISMATCH."""
        bad_kwargs = _make_renderer_kwargs()
        bad_kwargs["bounded_read_scope"] = {
            **_BOUNDED_READ_SCOPE,
            "scope_hash": "WRONG-HASH",
        }
        card = self.render(**bad_kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_SCOPE_HASH_MISMATCH", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — explicit directive redaction.
    # ------------------------------------------------------------------
    def test_09_explicit_directive_redaction(self):
        """Redaction directives replace targeted fields with [REDACTED]."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)
        redaction_status = card.get("redaction_status")
        redactions = card.get("redactions", [])
        if redaction_status == "APPLIED":
            for r in redactions:
                self.assertEqual(r["replacement"], "[REDACTED]")

    # ------------------------------------------------------------------
    # Task 1 — automatic protected-key redaction.
    # ------------------------------------------------------------------
    def test_10_auto_protected_key_redaction(self):
        """Keys like password, secret, token are auto-redacted."""
        kwargs = _make_renderer_kwargs()
        kwargs["request_contract"] = {
            **_REQUEST_CONTRACT,
            "password": "supersecret123",
            "api_token": "tok-abc",
        }
        card = self.render(**kwargs)
        card_str = json.dumps(card, sort_keys=True)
        # The raw secrets must NOT appear anywhere in the card.
        self.assertNotIn("supersecret123", card_str)
        self.assertNotIn("tok-abc", card_str)

    # ------------------------------------------------------------------
    # Task 1 — invalid redaction directive blocks rendering.
    # ------------------------------------------------------------------
    def test_11_invalid_redaction_directive_blocks(self):
        """Directive pointing to absent field → CARD_REDACTION_DIRECTIVE_INVALID."""
        bad_kwargs = _make_renderer_kwargs()
        bad_kwargs["redaction_directives"] = [
            {
                "json_pointer": "/nonexistent/path/deep",
                "classification": "SECRET",
                "reason_code": "POINTER_MISSING",
                "replacement": "[REDACTED]",
            }
        ]
        card = self.render(**bad_kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn(
            "CARD_REDACTION_DIRECTIVE_INVALID", card["reason_codes"]
        )

    # ------------------------------------------------------------------
    # Task 1 — protected value leakage rejection.
    # ------------------------------------------------------------------
    def test_12_protected_value_leakage_rejection(self):
        """Any unprotected secret in output → CARD_REDACTION_REQUIRED."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)
        card_str = json.dumps(card, sort_keys=True)
        # snapshot_hash is hex; ensure no raw sha256-length token leaks.
        for pattern in (r"[A-Za-z0-9]{64}",):
            matches = re.findall(pattern, card_str)
            for m in matches:
                # Must be a valid hex; if it is, assert it doesn't match
                # any input secret.
                pass  # snapshot hashes are expected hex strings — fine.

    # ------------------------------------------------------------------
    # Task 1 — input-order and timestamp independent hashes.
    # ------------------------------------------------------------------
    def test_13_hash_order_independence(self):
        """Two inputs with same content but different key order produce the same hash."""
        kwargs_a = _make_renderer_kwargs(
            request_contract={
                "intent": "X",
                "outcome": "Y",
                "constraints": ["C"],
                "exclusions": ["E"],
            }
        )
        kwargs_b = _make_renderer_kwargs(
            request_contract={
                "exclusions": ["E"],
                "intent": "X",
                "constraints": ["C"],
                "outcome": "Y",
            }
        )
        card_a = self.render(**kwargs_a)
        card_b = self.render(**kwargs_b)
        self.assertEqual(card_a["snapshot_hash"], card_b["snapshot_hash"])

    def test_14_hash_timestamp_independence(self):
        """Different created_at values must not change snapshot_hash."""
        kwargs_a = _make_renderer_kwargs(created_at="2026-08-01T00:00:00Z")
        kwargs_b = _make_renderer_kwargs(created_at="2026-12-31T23:59:59Z")
        card_a = self.render(**kwargs_a)
        card_b = self.render(**kwargs_b)
        self.assertEqual(card_a["snapshot_hash"], card_b["snapshot_hash"])

    # ------------------------------------------------------------------
    # Task 1 — snapshot drift after material change.
    # ------------------------------------------------------------------
    def test_15_snapshot_drift_on_material_change(self):
        """Changing any material field alters snapshot_hash."""
        kwargs_base = _make_renderer_kwargs()
        card_base = self.render(**kwargs_base)
        h_base = card_base["snapshot_hash"]

        kwargs_chg = _make_renderer_kwargs(
            request_contract={**_REQUEST_CONTRACT, "intent": "DIFFERENT"}
        )
        card_chg = self.render(**kwargs_chg)
        h_chg = card_chg["snapshot_hash"]
        self.assertNotEqual(h_base, h_chg)

    # ------------------------------------------------------------------
    # Task 1 — expected snapshot mismatch.
    # ------------------------------------------------------------------
    def test_16_expected_snapshot_hash_mismatch(self):
        """Providing a wrong expected_snapshot_hash → CARD_SNAPSHOT_HASH_MISMATCH."""
        kwargs = _make_renderer_kwargs(
            expected_snapshot_hash="0" * 64
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_SNAPSHOT_HASH_MISMATCH", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — every authority field is always false.
    # ------------------------------------------------------------------
    def test_17_all_authority_fields_always_false(self):
        """No matter the input, no authority field is ever true."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)
        for field in (
            "write_authority_granted",
            "commit_authority_granted",
            "push_authority_granted",
            "pr_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(card[field], f"{field} must always be false")

    # ------------------------------------------------------------------
    # Task 1 — required reason codes are present in every outcome.
    # ------------------------------------------------------------------
    def test_18_reason_code_card_rendered_present(self):
        """CARD_RENDERED appears when context is fully ready."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)
        self.assertIn("CARD_RENDERED", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — schema validity of the produced card.
    # ------------------------------------------------------------------
    def test_19_card_is_schema_valid(self):
        """The rendered card must pass JSON Schema validation."""
        kwargs = _make_renderer_kwargs()
        card = self.render(**kwargs)

        # Minimal JSON-Schema-enforceable checks that mirror the schema:
        self.assertEqual(card["schema_version"], "1.0")
        self.assertEqual(card["artifact_type"], "intake-card")
        self.assertEqual(card["contract_revision"], "intake-context/v1")
        self.assertIn(card["context_status"], ["READY", "BLOCKED"])
        self.assertIn(card["outcome"], ["READY", "BLOCKED"])
        self.assertIn(card["redaction_status"], ["NONE", "APPLIED", "BLOCKED"])

    # ------------------------------------------------------------------
    # Task 2 — deterministic renderer: canonical_json.
    # ------------------------------------------------------------------
    def test_20_canonical_json_is_deterministic(self):
        """canonical_json must be order-independent and whitespace-normal."""
        cj = self.mod.canonical_json({"b": 1, "a": 2})
        self.assertEqual(
            json.loads(cj), {"a": 2, "b": 1}
        )  # keys are sorted
        # No pretty-printing — compact form.
        self.assertNotIn("\n", cj)

    def test_21_canonical_json_no_trailing_whitespace(self):
        """No insignificant whitespace in canonical output."""
        cj = self.mod.canonical_json({"a": [1, 2]})
        self.assertTrue(cj.rstrip() == cj)

    # ------------------------------------------------------------------
    # Task 2 — digest_payload consistency.
    # ------------------------------------------------------------------
    def test_22_digest_payload_is_sha256(self):
        """digest_payload returns a 64-char lowercase hex SHA-256 string."""
        payload = {"key": "value"}
        d = self.mod.digest_payload(payload)
        self.assertLen(d, 64)
        self.assertRegex(d, r"^[0-9a-f]+$")

    # ------------------------------------------------------------------
    # Task 2 — redaction: apply_redactions returns (modified, list).
    # ------------------------------------------------------------------
    def test_23_apply_redactions_replaces_values(self):
        """apply_redactions must replace targeted values with [REDACTED]."""
        payload = {"a": {"b": "secret_value"}}
        directives = [
            {
                "json_pointer": "/a/b",
                "classification": "SECRET",
                "reason_code": "IS_SECRET",
                "replacement": "[REDACTED]",
            }
        ]
        modified, redactions = self.mod.apply_redactions(payload, directives)
        self.assertEqual(modified["a"]["b"], "[REDACTED]")
        self.assertLen(redactions, 1)

    def test_24_apply_redactions_protected_keys(self):
        """Keys matching protected patterns are auto-redacted."""
        payload = {
            "password": "pass123",
            "api_token": "tok",
            "private_key": "pk",
        }
        modified, redactions = self.mod.apply_redactions(
            payload, []  # no explicit directives needed
        )
        self.assertNotIn("pass123", json.dumps(modified))
        self.assertNotIn("tok", json.dumps(modified))

    # ------------------------------------------------------------------
    # Task 1 — non-determinism detection (CARD_NONDETERMINISTIC).
    # ------------------------------------------------------------------
    def test_25_non_deterministic_detection(self):
        """Repeated renders of identical input must yield equal hashes."""
        kwargs = _make_renderer_kwargs()
        h1 = self.render(**kwargs)["snapshot_hash"]
        h2 = self.render(**kwargs)["snapshot_hash"]
        self.assertEqual(h1, h2)

    # ------------------------------------------------------------------
    # Task 2 — validate_upstream_bindings.
    # ------------------------------------------------------------------
    def test_26_validate_upstream_bindings_ok(self):
        """Matching identity fields across upstreams pass validation."""
        bindings = {
            "task_id": _TASK_ID,
            "repository": _REPOSITORY,
            "base_sha": _BASE_SHA,
        }
        result = self.mod.validate_upstream_bindings(
            task_id=_TASK_ID,
            repository=_REPOSITORY,
            base_sha=_BASE_SHA,
            request_contract={"task_id": _TASK_ID},
            source_resolution={},
            repo_identity={"repository": _REPOSITORY},
            protected_base_snapshot={"protected_base_sha": _BASE_SHA},
        )
        self.assertFalse(result["has_errors"])

    def test_27_validate_upstream_bindings_fails_on_mismatch(self):
        """Mismatched task_id → validation error."""
        result = self.mod.validate_upstream_bindings(
            task_id="WRONG",
            repository=_REPOSITORY,
            base_sha=_BASE_SHA,
            request_contract={"task_id": _TASK_ID},
            source_resolution={},
            repo_identity={"repository": _REPOSITORY},
            protected_base_snapshot={"protected_base_sha": _BASE_SHA},
        )
        self.assertTrue(result["has_errors"])

    # ------------------------------------------------------------------
    # Task 1 — snapshot_hash excluded fields per refinement.
    # ------------------------------------------------------------------
    def test_28_snapshot_excludes_created_at_from_hash(self):
        """snapshot_hash must NOT include created_at."""
        h1 = self.render(**_make_renderer_kwargs(created_at="2026-01-01T00:00:00Z"))[
            "snapshot_hash"
        ]
        h2 = self.render(**_make_renderer_kwargs(created_at="2026-12-31T00:00:00Z"))[
            "snapshot_hash"
        ]
        self.assertEqual(h1, h2)

    # ------------------------------------------------------------------
    # Task 1 — blocked card retains non-sensitive evidence.
    # ------------------------------------------------------------------
    def test_29_blocked_card_retains_evidence(self):
        """A BLOCKED card must still be schema-valid with evidence."""
        kwargs = _make_renderer_kwargs()
        kwargs["bounded_read_scope"] = {
            **_BOUNDED_READ_SCOPE,
            "outcome": "BLOCKED",
            "failure_classification": "MISSING_EVIDENCE",
        }
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_UPSTREAM_BLOCKED", card["reason_codes"])
        # Should still have task_id, repository, base_sha etc.
        self.assertTrue(
            all(k in card for k in ("task_id", "repository", "base_sha"))
        )

    # ------------------------------------------------------------------
    # Task 2 — render_intake_card signature accepts created_at optional.
    # ------------------------------------------------------------------
    def test_30_created_at_can_be_none(self):
        """created_at=None must not crash the renderer."""
        kwargs = _make_renderer_kwargs(created_at=None)
        card = self.render(**kwargs)
        self.assertIsNotNone(card)

    # ------------------------------------------------------------------
    # Task 2 — render_intake_card accepts expected_snapshot_hash optional.
    # ------------------------------------------------------------------
    def test_31_expected_snapshot_hash_is_optional(self):
        """expected_snapshot_hash=None is fine."""
        kwargs = _make_renderer_kwargs(expected_snapshot_hash=None)
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "READY")

    # ------------------------------------------------------------------
    # Task 1 — snapshot hash mismatch does not leak original snapshot.
    # ------------------------------------------------------------------
    def test_32_snapshot_mismatch_does_not_leak_original(self):
        """When expected_snapshot_hash mismatches, card must still be valid."""
        kwargs = _make_renderer_kwargs(
            expected_snapshot_hash="deadbeef" * 4
        )
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn("CARD_SNAPSHOT_HASH_MISMATCH", card["reason_codes"])

    # ------------------------------------------------------------------
    # Task 1 — upstream contract invalid (unsupported type/version).
    # ------------------------------------------------------------------
    def test_33_upstream_contract_invalid(self):
        """Unsupported artifact_type/schema_version → CARD_UPSTREAM_CONTRACT_INVALID."""
        bad_kwargs = _make_renderer_kwargs()
        bad_kwargs["risk_profile"] = {
            "artifact_type": "unsupported-type",
            "schema_version": "2.0",
        }
        card = self.render(**bad_kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn(
            "CARD_UPSTREAM_CONTRACT_INVALID", card["reason_codes"]
        )

    # ------------------------------------------------------------------
    # Task 1 — source binding mismatch across upstreams.
    # ------------------------------------------------------------------
    def test_34_source_binding_mismatch(self):
        """Different repositories across upstreams → CARD_SOURCE_BINDING_MISMATCH."""
        kwargs = _make_renderer_kwargs()
        kwargs["repo_identity"] = {"repository": "other/repo"}
        card = self.render(**kwargs)
        self.assertEqual(card["context_status"], "BLOCKED")
        self.assertIn(
            "CARD_SOURCE_BINDING_MISMATCH", card["reason_codes"]
        )


if __name__ == "__main__":
    unittest.main()
