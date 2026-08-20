#!/usr/bin/env python3
"""Focused SCRUM-334 tests for validation_quality.schema-validation (#269).

Covers valid artifact, missing/malformed/ambiguous/unsupported/incompatible
schema binding, malformed + version-drifting artifacts, invalid structure,
deterministic error ordering, replay determinism, drift invalidation and the
explicit authority-negative contract.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple

from tools.node_architect.schema_validation import (
    ARTIFACT_INVALID,
    ARTIFACT_MALFORMED,
    ARTIFACT_VERSION_DRIFT,
    FAIL,
    PASS,
    SCHEMA_AMBIGUOUS,
    SCHEMA_INVALID,
    SCHEMA_MALFORMED,
    SCHEMA_MISSING,
    SCHEMA_UNSUPPORTED,
    SCHEMA_VALID,
    SCHEMA_VALIDATION_STALE,
    SCHEMA_VERSION_INCOMPATIBLE,
    RUNTIME_NODE_SCHEMA_ID,
    validate_schema,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "auto/SCRUM-334-na81-recert-20260814-r10"

DECLARED_ID = RUNTIME_NODE_SCHEMA_ID
DECLARED_VERSION = "1.0.0"


def valid_artifact() -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_type": "runtime-node",
        "id": "demo-node",
        "identity": {
            "stable_id": "demo-node",
            "family": "validation_quality",
            "capability": "schema-validation",
            "runtime_slot": 34,
            "artifact_version": "1.0.0",
        },
        "authority": {
            "required_gate": "G3_PR",
            "required_evidence": ["exact-head-ci"],
            "may_mutate": [],
            "projection_only": True,
        },
        "effects": {
            "classification": "read_only",
            "side_effects": [],
            "reversibility": "reversible",
            "idempotency": "idempotent",
        },
        "execution": {
            "determinism": "deterministic",
            "suspendable": False,
            "resume_metadata": [],
        },
        "interfaces": {
            "inputs": [],
            "outputs": [],
            "preconditions": [],
            "postconditions": [],
        },
        "audit": {
            "history_refs": [],
            "decision_refs": [],
        },
    }


def result(**overrides: Any) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = dict(
        artifact=valid_artifact(),
        declared_schema_id=DECLARED_ID,
        declared_schema_version=DECLARED_VERSION,
        head_sha=HEAD,
        idempotency_key="scrub-334-1",
        task_id="SCRUM-334",
    )
    kwargs.update(overrides)
    return validate_schema(**kwargs)


class SchemaValidationM5Tests(unittest.TestCase):
    # --- PASS path ---------------------------------------------------------

    def test_accepts_valid_runtime_node(self):
        r = result()
        self.assertEqual(r["status"], PASS)
        self.assertEqual(r["reason_codes"], [SCHEMA_VALID])
        self.assertEqual(r["resolved_schema_id"], DECLARED_ID)
        self.assertIsNotNone(r["artifact_sha"])
        self.assertFalse(r["authority_granted"])

    # --- binding: missing -------------------------------------------------

    def test_rejects_missing_schema_id(self):
        r = result(declared_schema_id="")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(SCHEMA_MISSING, r["reason_codes"])

    def test_rejects_missing_schema_version(self):
        r = result(declared_schema_version="")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(SCHEMA_MISSING, r["reason_codes"])

    # --- binding: malformed / unsupported / incompatible ------------------

    def test_rejects_malformed_schema_version(self):
        r = result(declared_schema_version="not-a-version")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(SCHEMA_MALFORMED, r["reason_codes"])

    def test_rejects_unsupported_schema_id(self):
        r = result(declared_schema_id="https://example.com/unknown.json")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(SCHEMA_UNSUPPORTED, r["reason_codes"])

    def test_rejects_incompatible_schema_version(self):
        r = result(declared_schema_version="9.9.9")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(SCHEMA_VERSION_INCOMPATIBLE, r["reason_codes"])

    # --- artifact: malformed / drift / invalid ----------------------------

    def test_rejects_non_mapping_artifact(self):
        r = result(artifact="not-a-dict")
        self.assertEqual(r["status"], FAIL)
        self.assertIn(ARTIFACT_MALFORMED, r["reason_codes"])

    def test_rejects_version_drift(self):
        art = valid_artifact()
        art["schema_version"] = "2.0.0"
        r = result(artifact=art)
        self.assertEqual(r["status"], FAIL)
        self.assertIn(ARTIFACT_VERSION_DRIFT, r["reason_codes"])

    def test_rejects_invalid_structure(self):
        art = valid_artifact()
        del art["audit"]  # required property
        r = result(artifact=art)
        self.assertEqual(r["status"], FAIL)
        self.assertIn(ARTIFACT_INVALID, r["reason_codes"])
        self.assertTrue(r["errors"])
        self.assertTrue(
            any("audit" in (e["json_path"] + e["message"]) for e in r["errors"]),
            msg=f"expected an error referencing 'audit', got {r['errors']}",
        )

    # --- ambiguity (multi-def resolution) ---------------------------------

    def test_rejects_ambiguous_schema_resolution(self):
        import tools.node_architect.schema_validation as sv

        original = sv._SUPPORTED_SCHEMAS.get(DECLARED_ID)
        try:
            sv._SUPPORTED_SCHEMAS[DECLARED_ID] = (sv._SUPPORTED_SCHEMAS[DECLARED_ID][0], sv._SUPPORTED_SCHEMAS[DECLARED_ID][0])
            r = result()
            self.assertEqual(r["status"], FAIL)
            self.assertIn(SCHEMA_AMBIGUOUS, r["reason_codes"])
        finally:
            if original is None:
                sv._SUPPORTED_SCHEMAS.pop(DECLARED_ID, None)
            else:
                sv._SUPPORTED_SCHEMAS[DECLARED_ID] = original

    # --- determinism + replay + drift -------------------------------------

    def test_deterministic_error_ordering(self):
        art = valid_artifact()
        del art["interfaces"]  # required property
        first = result(artifact=art, idempotency_key="order-1")
        second = result(artifact=art, idempotency_key="order-2")
        self.assertEqual(first["reason_codes"], second["reason_codes"])
        self.assertEqual(first["result_digest"], second["result_digest"])

    def test_replay_is_deterministic(self):
        cache: Dict[str, Any] = {}
        first = result(replay_cache=cache)
        second = result(replay_cache=cache)
        self.assertEqual(first["result_digest"], second["result_digest"])
        self.assertTrue(second["replayed"])

    def test_replay_invalidates_on_drift(self):
        cache: Dict[str, Any] = {}
        ok = result(head_sha=HEAD, replay_cache=cache)
        self.assertEqual(ok["status"], PASS)
        drifted = result(head_sha="b" * 40, replay_cache=cache)
        self.assertEqual(drifted["status"], FAIL)
        self.assertIn(SCHEMA_VALIDATION_STALE, drifted["reason_codes"])

    # --- authority-negative contract --------------------------------------

    def test_authority_negative_even_on_pass(self):
        r = result()
        self.assertEqual(r["status"], PASS)
        for field in (
            "authority_granted",
            "g2_authority_granted",
            "g3_authority_granted",
            "g4_authority_granted",
            "g5_authority_granted",
            "g6_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(r[field], f"{field} must be False")

    # --- canonical schema self-validation (G3 review fix) -----------------

    def _save_schema_state(self) -> Tuple[Any, ...]:
        import tools.node_architect.schema_validation as sv

        return (
            sv._SCHEMA_PATH,
            sv._SCHEMA,
            sv._SCHEMA_VALIDATOR,
            sv._SCHEMA_INVALID_REASON,
            dict(sv._SUPPORTED_SCHEMAS),
        )

    def _restore_schema_state(self, saved: Tuple[Any, ...]) -> None:
        import tools.node_architect.schema_validation as sv

        sv._SCHEMA_PATH = saved[0]
        sv._SCHEMA = saved[1]
        sv._SCHEMA_VALIDATOR = saved[2]
        sv._SCHEMA_INVALID_REASON = saved[3]
        sv._SUPPORTED_SCHEMAS.clear()
        sv._SUPPORTED_SCHEMAS.update(saved[4])

    def _write_temp_schema(self, content: Dict[str, Any]) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(content, fh)
        return path

    def test_load_and_register_rejects_invalid_schema(self):
        """An invalid-but-parseable canonical schema fails closed (check_schema)."""
        import tools.node_architect.schema_validation as sv

        path = self._write_temp_schema(
            {"type": 123, "properties": {"x": {"type": "string"}}}
        )
        saved = self._save_schema_state()
        try:
            sv._SCHEMA_PATH = Path(path)
            sv._SCHEMA = None
            sv._SCHEMA_VALIDATOR = None
            sv._SCHEMA_INVALID_REASON = None
            sv._SUPPORTED_SCHEMAS.clear()
            sv._load_and_register()
            self.assertEqual(sv._SCHEMA_INVALID_REASON, SCHEMA_INVALID)
            self.assertIsNone(sv._SCHEMA_VALIDATOR)
            self.assertNotIn(RUNTIME_NODE_SCHEMA_ID, sv._SUPPORTED_SCHEMAS)
        finally:
            self._restore_schema_state(saved)
            os.unlink(path)

    def test_load_and_register_rejects_id_mismatch(self):
        """A valid schema with the wrong $id fails closed (identity binding)."""
        import tools.node_architect.schema_validation as sv

        path = self._write_temp_schema(
            {
                "$id": "https://wrong.example/x.json",
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
                "additionalProperties": False,
            }
        )
        saved = self._save_schema_state()
        try:
            sv._SCHEMA_PATH = Path(path)
            sv._SCHEMA = None
            sv._SCHEMA_VALIDATOR = None
            sv._SCHEMA_INVALID_REASON = None
            sv._SUPPORTED_SCHEMAS.clear()
            sv._load_and_register()
            self.assertEqual(sv._SCHEMA_INVALID_REASON, SCHEMA_INVALID)
            self.assertIsNone(sv._SCHEMA_VALIDATOR)
        finally:
            self._restore_schema_state(saved)
            os.unlink(path)

    def test_load_and_register_accepts_valid_schema(self):
        """The real canonical schema passes check_schema + $id and registers."""
        import tools.node_architect.schema_validation as sv

        saved = self._save_schema_state()
        try:
            sv._SCHEMA = None
            sv._SCHEMA_VALIDATOR = None
            sv._SCHEMA_INVALID_REASON = None
            sv._SUPPORTED_SCHEMAS.clear()
            sv._load_and_register()
            self.assertIsNone(sv._SCHEMA_INVALID_REASON)
            self.assertIsNotNone(sv._SCHEMA_VALIDATOR)
            self.assertIn(RUNTIME_NODE_SCHEMA_ID, sv._SUPPORTED_SCHEMAS)
            self.assertEqual(
                sv._SUPPORTED_SCHEMAS[RUNTIME_NODE_SCHEMA_ID][0].get("$id"),
                RUNTIME_NODE_SCHEMA_ID,
            )
        finally:
            self._restore_schema_state(saved)

    def test_fails_closed_end_to_end_on_invalid_schema(self):
        """When the canonical schema is invalid, validate_schema fails closed."""
        import tools.node_architect.schema_validation as sv

        saved = self._save_schema_state()
        try:
            sv._SCHEMA_INVALID_REASON = SCHEMA_INVALID
            sv._SCHEMA_VALIDATOR = None
            r = result(artifact=valid_artifact())
            self.assertEqual(r["status"], FAIL)
            self.assertIn(SCHEMA_INVALID, r["reason_codes"])
        finally:
            self._restore_schema_state(saved)


if __name__ == "__main__":
    unittest.main()
