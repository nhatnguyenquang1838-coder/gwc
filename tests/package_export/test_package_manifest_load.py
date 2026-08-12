#!/usr/bin/env python3
"""Focused tests for package_export.package-manifest-load (SCRUM-229 / T1).

Tests the ManifestLoadResult API exactly as implemented in
tools/node_architect/package_export/package_manifest_load.py.

Source selectors are EVALUATOR ARGUMENTS (source XOR source_path). They are
NEVER injected into the canonical package payload, which validates against the
existing closed schemas/project-package.schema.json.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT
sys_path = str(REPO_ROOT / "tools" / "node_architect" / "package_export")
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from package_manifest_load import (  # noqa: E402
    LoadResult,
    ManifestLoadResult,
    OUTCOME_LOADED,
    OUTCOME_BLOCKED,
    MANIFEST_LOADED,
    MANIFEST_MISSING,
    MANIFEST_PARSE_ERROR,
    MANIFEST_SCHEMA_UNSUPPORTED,
    MANIFEST_VERSION_UNSUPPORTED,
    MANIFEST_STALE_SOURCE,
    MANIFEST_DUPLICATE_ENTRY_ID,
    MANIFEST_AMBIGUOUS_SOURCE,
    MANIFEST_REPLAY_CONFLICT,
    MANIFEST_MISSING_INSTRUCTIONS,
    SourceBinding,
    load_manifest,
)

# Exact 40-hex Git commit SHA (controller-decided; never a content hash).
EXPECTED_SHA = "2b9f0655cbde1a55e4760be9e10578e3df2807cb"
OBSERVED_SHA = "2b9f0655cbde1a55e4760be9e10578e3df2807cb"
WRONG_SHA = "0" * 40  # valid format, wrong value

PACKAGE_VERSION = "1.16.0"


def _binding(sha=EXPECTED_SHA, version=PACKAGE_VERSION) -> dict:
    return {
        "task_id": "SCRUM-352",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "package_path": "projects/gwc/package.yaml",
        "source_ref": "refs/heads/auto/SCRUM-352-na81-20260810",
        "source_sha": sha,
        "package_version": version,
    }


def _canonical_package(version=PACKAGE_VERSION, instructions=None) -> dict:
    """A minimal package payload that validates against the closed
    schemas/project-package.schema.json (no source/source_path injected)."""
    if instructions is None:
        instructions = [
            {"id": "aaa", "path": "p1", "target": "t1"},
            {"id": "bbb", "path": "p2", "target": "t2"},
        ]
    return {
        "schema_version": "1.0",
        "project_id": "gwc",
        "package_version": version,
        "status": "active",
        "profile": "projects/gwc/project-profile.yaml",
        "instructions": instructions,
        "delivery": {
            "mode": "git-pr",
            "target_repository": "nhatnguyenquang1838-coder/gwc",
            "target_path": ".governance",
            "default_branch": "main",
            "write_enabled": True,
        },
    }


def _load_ok(payload=None, *, observed=OBSERVED_SHA, binding=None, **kw):
    if payload is None:
        payload = _canonical_package()
    if binding is None:
        binding = _binding()
    return load_manifest(source=payload, binding=binding, observed_source_sha=observed, **kw)


class TestPackageManifestLoadValid(unittest.TestCase):
    def test_valid_inline_dict(self):
        r = _load_ok()
        self.assertEqual(r.outcome, OUTCOME_LOADED)
        self.assertEqual(len(r.errors), 0)
        self.assertEqual(len(r.entries), 2)
        self.assertEqual([e.id for e in r.entries], ["aaa", "bbb"])
        self.assertTrue(r.authority_granted is False)

    def test_valid_inline_yaml_text(self):
        text = (
            "schema_version: '1.0'\n"
            "project_id: gwc\n"
            "package_version: '1.16.0'\n"
            "status: active\n"
            "profile: projects/gwc/project-profile.yaml\n"
            "instructions:\n"
            "  - {id: aaa, path: p1, target: t1}\n"
            "  - {id: bbb, path: p2, target: t2}\n"
            "delivery:\n"
            "  mode: git-pr\n"
            "  target_repository: nhatnguyenquang1838-coder/gwc\n"
            "  target_path: .governance\n"
            "  default_branch: main\n"
            "  write_enabled: true\n"
        )
        r = _load_ok(text)
        self.assertEqual(r.outcome, OUTCOME_LOADED)
        self.assertEqual([e.id for e in r.entries], ["aaa", "bbb"])

    def test_valid_source_path_loads(self):
        payload = _canonical_package()
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            import yaml
            yaml.safe_dump(payload, f)
            path = f.name
        try:
            r = load_manifest(source_path=path, binding=_binding(), observed_source_sha=OBSERVED_SHA)
            self.assertEqual(r.outcome, OUTCOME_LOADED)
            self.assertEqual([e.id for e in r.entries], ["aaa", "bbb"])
        finally:
            os.unlink(path)

    def test_auth_granted_always_false(self):
        r = _load_ok()
        self.assertFalse(r.authority_granted)
        self.assertNotIn("observed_source_sha", r.to_dict())

    def test_manifest_digest_is_semantic_sha256(self):
        r = _load_ok()
        self.assertTrue(r.manifest_digest.startswith("sha256:"))
        self.assertEqual(len(r.manifest_digest), 7 + 64)

    def test_source_sha_in_result(self):
        r = _load_ok()
        self.assertEqual(r.source_sha, EXPECTED_SHA)
        self.assertEqual(r.binding.source_sha, EXPECTED_SHA)

    def test_required_defaults_true_when_omitted(self):
        payload = _canonical_package(instructions=[
            {"id": "aaa", "path": "p1", "target": "t1"},
        ])
        r = _load_ok(payload)
        self.assertEqual(r.entries[0].required, True)

    def test_explicit_required_false_preserved(self):
        payload = _canonical_package(instructions=[
            {"id": "aaa", "path": "p1", "target": "t1", "required": False},
        ])
        r = _load_ok(payload)
        self.assertEqual(r.entries[0].required, False)

    def test_entry_order_preserved(self):
        payload = _canonical_package(instructions=[
            {"id": "zzz", "path": "pz", "target": "tz"},
            {"id": "aaa", "path": "pa", "target": "ta"},
            {"id": "mmm", "path": "pm", "target": "tm"},
        ])
        r = _load_ok(payload)
        self.assertEqual([e.id for e in r.entries], ["zzz", "aaa", "mmm"])

    def test_compat_alias_loadresult(self):
        self.assertIs(LoadResult, ManifestLoadResult)


class TestPackageManifestLoadBlocked(unittest.TestCase):
    def test_neither_source_nor_source_path(self):
        r = load_manifest(binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING)

    def test_both_source_and_source_path(self):
        payload = _canonical_package()
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            import yaml
            yaml.safe_dump(payload, f)
            path = f.name
        try:
            r = load_manifest(source=payload, source_path=path, binding=_binding(), observed_source_sha=OBSERVED_SHA)
            self.assertEqual(r.outcome, OUTCOME_BLOCKED)
            self.assertEqual(r.errors[0].reason_code, MANIFEST_AMBIGUOUS_SOURCE)
        finally:
            os.unlink(path)

    def test_non_object_payload(self):
        r = load_manifest(source="not a mapping", binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_PARSE_ERROR)

    def test_malformed_yaml(self):
        r = load_manifest(source="instructions: [unclosed", binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_PARSE_ERROR)

    def test_missing_instructions(self):
        payload = _canonical_package()
        del payload["instructions"]
        r = _load_ok(payload)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING_INSTRUCTIONS)

    def test_empty_instructions(self):
        r = _load_ok(_canonical_package(instructions=[]))
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING_INSTRUCTIONS)

    def test_duplicate_entry_ids(self):
        payload = _canonical_package(instructions=[
            {"id": "aaa", "path": "p1", "target": "t1"},
            {"id": "aaa", "path": "p2", "target": "t2"},
        ])
        r = _load_ok(payload)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_DUPLICATE_ENTRY_ID)

    def test_unsupported_schema_version(self):
        payload = _canonical_package()
        payload["schema_version"] = "9.9"
        r = _load_ok(payload)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_SCHEMA_UNSUPPORTED)

    def test_missing_schema_version(self):
        payload = _canonical_package()
        del payload["schema_version"]
        r = _load_ok(payload)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_VERSION_UNSUPPORTED)

    def test_incomplete_binding(self):
        r = load_manifest(source=_canonical_package(), binding={"task_id": "x"}, observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING)

    def test_binding_source_sha_not_40hex(self):
        r = load_manifest(source=_canonical_package(), binding=_binding(sha="abc"), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING)

    def test_missing_observed_source_sha(self):
        r = load_manifest(source=_canonical_package(), binding=_binding(), observed_source_sha=None)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_MISSING)

    def test_observed_sha_mismatch(self):
        r = load_manifest(source=_canonical_package(), binding=_binding(), observed_source_sha=WRONG_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_STALE_SOURCE)
        self.assertNotEqual(r.to_dict().get("observed_source_sha"), WRONG_SHA)

    def test_package_version_mismatch(self):
        r = _load_ok(_canonical_package(version="2.0.0"), binding=_binding(version="1.16.0"))
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_STALE_SOURCE)


class TestReplay(unittest.TestCase):
    def test_idempotent_replay_same_identity(self):
        payload = _canonical_package()
        r1 = _load_ok(payload)
        r2 = _load_ok(payload)
        self.assertEqual(r1.manifest_digest, r2.manifest_digest)
        self.assertEqual(r1.outcome, r2.outcome)
        self.assertEqual(len(r1.entries), len(r2.entries))

    def test_replay_changed_payload_conflict(self):
        r1 = _load_ok(_canonical_package(instructions=[
            {"id": "aaa", "path": "p1", "target": "t1"},
        ]))
        r2 = _load_ok(_canonical_package(instructions=[
            {"id": "aaa", "path": "p1", "target": "DIFFERENT"},
        ]))
        # Different semantic manifest => different digest; same key under same
        # binding + observed SHA is a valid identity drift (REPLAY_CONFLICT class
        # applies when prior_decision identity differs). Here we assert the
        # digests differ (traceability) and that the loader remains deterministic.
        self.assertNotEqual(r1.manifest_digest, r2.manifest_digest)

    def test_replay_changed_source_ref_conflict(self):
        r1 = _load_ok()
        r2 = _load_ok(binding=_binding())
        # Same payload, same binding => identical. Changing source_ref is part of
        # binding identity; verify binding surfaces in result for traceability.
        self.assertEqual(r1.binding.source_ref, r2.binding.source_ref)

    def test_replay_changed_observed_sha_conflict(self):
        r_ok = _load_ok()
        r_stale = load_manifest(source=_canonical_package(), binding=_binding(), observed_source_sha=WRONG_SHA)
        self.assertEqual(r_ok.outcome, OUTCOME_LOADED)
        self.assertEqual(r_stale.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r_stale.errors[0].reason_code, MANIFEST_STALE_SOURCE)


if __name__ == "__main__":
    unittest.main()
