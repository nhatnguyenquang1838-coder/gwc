#!/usr/bin/env python3
"""Branch / negative / drift / replay tests for package_export.package-manifest-load."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "node_architect" / "package_export"))

from package_manifest_load import (  # noqa: E402
    LoadResult,
    authority_granted,
    load_manifest,
    OUTCOME_BLOCKED,
    OUTCOME_LOADED,
    REASON_MANIFEST_LOAD_INVALID,
    REASON_READ_FAILED,
    REASON_REPLAY_CONFLICT,
)


class TestPackageManifestLoad(unittest.TestCase):
    # ------------------------------------------------------------------
    # Happy path / branch
    # ------------------------------------------------------------------
    def test_load_from_dict(self):
        manifest = {
            "schema_id": "gwc.package_export.smoke",
            "entries": [{"source": "a", "target": "b"}],
        }
        decision = load_manifest(source=manifest, idempotency_key="k1")
        self.assertEqual(decision.outcome, OUTCOME_LOADED)
        self.assertEqual(decision.entry_count, 1)
        self.assertTrue(decision.entry_order_preserved)
        self.assertIn("sha256:", decision.manifest_digest)
        self.assertIn("sha256:", decision.decision_digest)
        self.assertFalse(authority_granted(decision))

    def test_load_from_file(self):
        manifest = {
            "schema_id": "gwc.package_export.smoke",
            "entries": [{"source": "a", "target": "b"}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(manifest, fh)
            path = fh.name
        try:
            decision = load_manifest(source_path=path, idempotency_key="k-file")
            self.assertEqual(decision.outcome, OUTCOME_LOADED)
            self.assertEqual(decision.entry_count, 1)
        finally:
            os.unlink(path)

    def test_load_preserves_entry_order(self):
        entries = [
            {"source": "z", "target": "1"},
            {"source": "a", "target": "2"},
            {"source": "m", "target": "3"},
        ]
        manifest = {"schema_id": "gwc.test", "entries": entries}
        decision = load_manifest(source=manifest, idempotency_key="k-order")
        self.assertEqual(decision.outcome, OUTCOME_LOADED)
        self.assertEqual(decision.manifest["entries"], entries)

    # ------------------------------------------------------------------
    # Negative cases
    # ------------------------------------------------------------------
    def test_negative_source_is_string_not_path(self):
        decision = load_manifest(source="not-json", idempotency_key="k-bad")
        self.assertEqual(decision.outcome, OUTCOME_BLOCKED)
        self.assertEqual(decision.reason_code, REASON_MANIFEST_LOAD_INVALID)

    def test_negative_missing_entries(self):
        decision = load_manifest(source={"schema_id": "x"}, idempotency_key="k-no-entries")
        self.assertEqual(decision.outcome, OUTCOME_BLOCKED)
        self.assertEqual(decision.reason_code, REASON_MANIFEST_LOAD_INVALID)

    def test_negative_root_not_dict(self):
        decision = load_manifest(source="[]", idempotency_key="k-array")
        # string not a path/file -> treated as invalid source type
        self.assertEqual(decision.outcome, OUTCOME_BLOCKED)
        self.assertEqual(decision.reason_code, REASON_MANIFEST_LOAD_INVALID)

    def test_negative_no_source(self):
        decision = load_manifest(idempotency_key="k-none")
        self.assertEqual(decision.outcome, OUTCOME_BLOCKED)
        self.assertEqual(decision.reason_code, REASON_MANIFEST_LOAD_INVALID)

    # ------------------------------------------------------------------
    # Drift
    # ------------------------------------------------------------------
    def test_drift_changes_manifest_digest(self):
        m1 = {"schema_id": "gwc.test", "entries": [{"a": 1}]}
        m2 = {"schema_id": "gwc.test", "entries": [{"a": 2}]}
        d1 = load_manifest(source=m1, idempotency_key="k-drift")
        d2 = load_manifest(source=m2, idempotency_key="k-drift")
        self.assertEqual(d1.outcome, OUTCOME_LOADED)
        self.assertEqual(d2.outcome, OUTCOME_LOADED)
        self.assertNotEqual(d1.manifest_digest, d2.manifest_digest)
        self.assertNotEqual(d1.decision_digest, d2.decision_digest)

    def test_deterministic_same_input_same_digest(self):
        m = {"schema_id": "gwc.test", "entries": [{"a": 1}]}
        d1 = load_manifest(source=m, idempotency_key="k-det")
        d2 = load_manifest(source=m, idempotency_key="k-det")
        self.assertEqual(d1.manifest_digest, d2.manifest_digest)
        self.assertEqual(d1.decision_digest, d2.decision_digest)

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------
    def test_replay_idempotent_same_input(self):
        m = {"schema_id": "gwc.test", "entries": [{"a": 1}]}
        prior = load_manifest(source=m, idempotency_key="k-replay")
        again = load_manifest(source=m, idempotency_key="k-replay", prior_decision=prior.to_dict())
        self.assertEqual(again.outcome, OUTCOME_LOADED)
        self.assertEqual(again.replay_status, "IDEMPOTENT")
        self.assertEqual(again.manifest_digest, prior.manifest_digest)

    def test_replay_conflict_changed_input_under_same_key(self):
        m1 = {"schema_id": "gwc.test", "entries": [{"a": 1}]}
        m2 = {"schema_id": "gwc.test", "entries": [{"a": 2}]}
        prior = load_manifest(source=m1, idempotency_key="k-conflict")
        again = load_manifest(source=m2, idempotency_key="k-conflict", prior_decision=prior.to_dict())
        self.assertEqual(again.outcome, OUTCOME_BLOCKED)
        self.assertEqual(again.reason_code, REASON_REPLAY_CONFLICT)
        self.assertEqual(again.replay_status, "CONFLICT")

    # ------------------------------------------------------------------
    # Authority boundary
    # ------------------------------------------------------------------
    def test_authority_granted_always_false(self):
        m = {"schema_id": "gwc.test", "entries": []}
        d = load_manifest(source=m, idempotency_key="k-auth")
        self.assertFalse(authority_granted(d))

    def test_to_dict_contains_all_required_keys(self):
        m = {"schema_id": "gwc.test", "entries": [{"a": 1}]}
        d = load_manifest(source=m, idempotency_key="k-dict")
        payload = d.to_dict()
        for key in (
            "schema_id", "schema_version", "loader_version", "outcome", "reason_code",
            "decision_digest", "manifest", "manifest_digest", "entry_count",
            "entry_order_preserved", "idempotency_key", "decided_at",
            "replay_status", "authority_authorized",
        ):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
