#!/usr/bin/env python3
"""Tests for schema_compatibility_resolver (SCRUM-396).

Covers: envelope build + digest, trust-manifest resolution (EXACT /
VERIFY_ONLY / UNSUPPORTED / REJECTED), journal transition fail-closed.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from tools.node_architect.schema_compatibility_resolver import (
    CompatibilityResult,
    SchemaCompatibilityError,
    build_envelope,
    journal_transition,
    load_trust_manifest,
    resolve_compatibility,
    resolve_profile,
)

MANIFEST = {
    "schema_version": "1.0",
    "artifact_type": "schema-trust-manifest",
    "manifest_id": "mt-001",
    "issuer": "dwc-connector",
    "issued_at": "2026-08-24T01:00:00Z",
    "validity": {"not_before": "2026-08-24T00:00:00Z", "not_after": "2026-09-01T00:00:00Z"},
    "entries": [
        {
            "writer_schema_id": "gwc.checkpoint.v1",
            "writer_schema_version": "1.0",
            "profile_id": "gwc-jcs-v1",
            "profile_version": "1.0",
            "hash_algorithm": "sha256",
            "lifecycle": "NEW_WRITE_ALLOWED",
        },
        {
            "writer_schema_id": "gwc.checkpoint.v1",
            "writer_schema_version": "0.9",
            "profile_id": "legacy-python-json-v1",
            "profile_version": "1.0",
            "hash_algorithm": "sha256",
            "lifecycle": "VERIFY_ONLY",
        },
        {
            "writer_schema_id": "gwc.checkpoint.v1",
            "writer_schema_version": "0.8",
            "profile_id": "legacy-python-json-v1",
            "profile_version": "1.0",
            "hash_algorithm": "sha256",
            "lifecycle": "REJECTED",
        },
    ],
}


class EnvelopeTests(unittest.TestCase):
    def test_build_envelope_deterministic(self) -> None:
        e1 = build_envelope(
            artifact_kind="checkpoint",
            writer_schema_id="gwc.checkpoint.v1",
            writer_schema_version="1.0",
            schema_digest="sha256:" + "a" * 64,
            payload={"revision": 1, "events": []},
            profile_id="gwc-jcs-v1",
            profile_version="1.0",
        )
        e2 = build_envelope(
            artifact_kind="checkpoint",
            writer_schema_id="gwc.checkpoint.v1",
            writer_schema_version="1.0",
            schema_digest="sha256:" + "a" * 64,
            payload={"events": [], "revision": 1},
            profile_id="gwc-jcs-v1",
            profile_version="1.0",
        )
        self.assertEqual(e1["payload_digest"], e2["payload_digest"])
        self.assertEqual(e1["artifact_type"], "durable-artifact-envelope")
        self.assertEqual(e1["hash_algorithm"], "sha256")


class ManifestTests(unittest.TestCase):
    def test_resolve_profile_exact(self) -> None:
        entry = resolve_profile(MANIFEST, "gwc.checkpoint.v1", "1.0")
        self.assertEqual(entry["profile_id"], "gwc-jcs-v1")
        self.assertEqual(entry["lifecycle"], "NEW_WRITE_ALLOWED")

    def test_resolve_verify_only(self) -> None:
        entry = resolve_profile(MANIFEST, "gwc.checkpoint.v1", "0.9")
        self.assertEqual(entry["lifecycle"], "VERIFY_ONLY")

    def test_resolve_rejected(self) -> None:
        with self.assertRaises(SchemaCompatibilityError) as ctx:
            resolve_profile(MANIFEST, "gwc.checkpoint.v1", "0.8")
        self.assertIn("SCHEMA_VERSION_REJECTED", str(ctx.exception))

    def test_resolve_unknown(self) -> None:
        with self.assertRaises(SchemaCompatibilityError) as ctx:
            resolve_profile(MANIFEST, "gwc.checkpoint.v1", "99.0")
        self.assertIn("SCHEMA_VERSION_UNSUPPORTED", str(ctx.exception))

    def test_load_manifest_version_guard(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"schema_version": "9.9", "artifact_type": "schema-trust-manifest"}, fh)
            path = fh.name
        try:
            with self.assertRaises(SchemaCompatibilityError):
                load_trust_manifest(path)
        finally:
            os.unlink(path)


class ResolverTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        r = resolve_compatibility(
            writer_schema_id="gwc.checkpoint.v1",
            writer_schema_version="1.0",
            manifest=MANIFEST,
        )
        self.assertIsInstance(r, CompatibilityResult)
        self.assertEqual(r.state, "EXACT")
        self.assertEqual(r.reason_code, "SCHEMA_EXACT_MATCH")

    def test_verify_only_migration_required(self) -> None:
        r = resolve_compatibility(
            writer_schema_id="gwc.checkpoint.v1",
            writer_schema_version="0.9",
            manifest=MANIFEST,
            supported_migrations={("gwc.checkpoint.v1", "0.9"): ("1.0",)},
        )
        self.assertEqual(r.state, "MIGRATION_REQUIRED")
        self.assertEqual(r.migration_chain, ("1.0",))

    def test_unsupported_fail_closed(self) -> None:
        r = resolve_compatibility(
            writer_schema_id="gwc.checkpoint.v1",
            writer_schema_version="99.0",
            manifest=MANIFEST,
        )
        self.assertEqual(r.state, "UNSUPPORTED")
        self.assertEqual(r.reason_code, "SCHEMA_VERSION_UNSUPPORTED")


class JournalTests(unittest.TestCase):
    def test_happy_path(self) -> None:
        rec = {"state": "DISCOVERED", "updated_at": "2026-08-24T00:00:00Z"}
        rec = journal_transition(rec, "TRUST_RESOLVED")
        rec = journal_transition(rec, "COMPATIBILITY_CLASSIFIED")
        rec = journal_transition(rec, "MIGRATION_PREPARED")
        rec = journal_transition(rec, "OUTPUT_WRITTEN")
        rec = journal_transition(rec, "OUTPUT_READBACK_VERIFIED")
        rec = journal_transition(rec, "REPLAY_ELIGIBLE")
        self.assertEqual(rec["state"], "REPLAY_ELIGIBLE")

    def test_invalid_transition_fail_closed(self) -> None:
        rec = {"state": "DISCOVERED", "updated_at": "2026-08-24T00:00:00Z"}
        with self.assertRaises(SchemaCompatibilityError):
            journal_transition(rec, "REPLAY_ELIGIBLE")  # skips states -> invalid

    def test_outcome_unknown_reconciliation(self) -> None:
        rec = {"state": "OUTPUT_WRITTEN", "updated_at": "2026-08-24T00:00:00Z"}
        rec = journal_transition(rec, "OUTCOME_UNKNOWN")
        self.assertEqual(rec["state"], "OUTCOME_UNKNOWN")
        rec = journal_transition(rec, "DISCOVERED")  # reconcile before retry
        self.assertEqual(rec["state"], "DISCOVERED")

    def test_poison_quarantine(self) -> None:
        rec = {"state": "COMPATIBILITY_CLASSIFIED", "updated_at": "2026-08-24T00:00:00Z"}
        rec = journal_transition(rec, "QUARANTINED")
        self.assertEqual(rec["state"], "QUARANTINED")


if __name__ == "__main__":
    unittest.main()
