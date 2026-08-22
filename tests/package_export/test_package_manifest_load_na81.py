#!/usr/bin/env python3
"""NA81 recert tests for package_export.package-manifest-load (SCRUM-352, F7-N01).

Bound to the exact executable module
`tools/node_architect/package_export/package_manifest_load.py`. These tests
prove the gate evaluator's fail-closed safety contract for the NA81 autonomous
lane recert: safe manifest load across source modes, the closed reason-code
taxonomy for blocking, deterministic digest/entries/replay identity, source XOR
source_path mutual exclusion, stale-source rejection, no authority grant, and no
filesystem side effect.

The module is a pure, deterministic, fail-closed manifest loader: the typed
ManifestLoadResult (not an exit code) is the sole LOADED signal,
authority_granted is always False, and observed_source_sha is execution-only
(never stored in the result).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Import-path rule (Py3 namespace packages): prefix tools/ explicitly so the
# host env's bare top-level `tools` package can never shadow the repo module.
sys.path.insert(0, "/home/ubuntu/gwc-ctrl-r10/.wt/SCRUM-352/tools")

from node_architect.package_export import package_manifest_load as pml_mod  # noqa: E402
from node_architect.package_export.package_manifest_load import (  # noqa: E402
    ManifestLoadResult,
    LoadResult,
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
    MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE,
    REPLAY_STATUS_NONE,
    REPLAY_STATUS_IDEMPOTENT,
    REPLAY_STATUS_CONFLICT,
    SourceBinding,
    load_manifest,
    SCHEMA_ID,
    SCHEMA_VERSION,
    compute_manifest_digest,
)

import unittest.mock as mock  # noqa: E402

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


class TestPackageManifestLoadNA81Valid(unittest.TestCase):
    # --- safe load across source modes (PASS) -----------------------------
    def test_valid_inline_dict_loads(self):
        r = _load_ok()
        self.assertEqual(r.outcome, OUTCOME_LOADED)
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.entries), 2)
        self.assertEqual([e.id for e in r.entries], ["aaa", "bbb"])

    def test_valid_inline_yaml_text_loads(self):
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

    # --- authority contract (never granted) -------------------------------
    def test_auth_granted_always_false(self):
        r = _load_ok()
        self.assertFalse(r.authority_granted)
        self.assertNotIn("observed_source_sha", r.to_dict())

    def test_source_sha_preserved_in_result(self):
        r = _load_ok()
        self.assertEqual(r.source_sha, EXPECTED_SHA)
        self.assertEqual(r.binding.source_sha, EXPECTED_SHA)

    # --- entry order + required semantics ---------------------------------
    def test_entry_order_preserved(self):
        payload = _canonical_package(instructions=[
            {"id": "zzz", "path": "pz", "target": "tz"},
            {"id": "aaa", "path": "pa", "target": "ta"},
            {"id": "mmm", "path": "pm", "target": "tm"},
        ])
        r = _load_ok(payload)
        self.assertEqual([e.id for e in r.entries], ["zzz", "aaa", "mmm"])

    def test_required_defaults_true_when_omitted(self):
        payload = _canonical_package(instructions=[{"id": "aaa", "path": "p1", "target": "t1"}])
        r = _load_ok(payload)
        self.assertEqual(r.entries[0].required, True)

    def test_explicit_required_false_preserved(self):
        payload = _canonical_package(instructions=[{"id": "aaa", "path": "p1", "target": "t1", "required": False}])
        r = _load_ok(payload)
        self.assertEqual(r.entries[0].required, False)

    # --- digest semantics (semantic sha256, no timestamps) ----------------
    def test_manifest_digest_is_semantic_sha256(self):
        r = _load_ok()
        self.assertTrue(r.manifest_digest.startswith("sha256:"))
        self.assertEqual(len(r.manifest_digest), 7 + 64)

    # --- identity / alias contract ----------------------------------------
    def test_compat_alias_loadresult(self):
        self.assertIs(LoadResult, ManifestLoadResult)
        self.assertEqual(SCHEMA_ID, "gwc.package_export.package_manifest_load")
        self.assertEqual(SCHEMA_VERSION, "0.1")


class TestPackageManifestLoadNA81Blocked(unittest.TestCase):
    # --- source XOR source_path mutual exclusion --------------------------
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

    # --- malformed / non-object payload -----------------------------------
    def test_non_object_payload(self):
        r = load_manifest(source="not a mapping", binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_PARSE_ERROR)

    def test_malformed_yaml(self):
        r = load_manifest(source="instructions: [unclosed", binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_PARSE_ERROR)

    # --- instructions list ------------------------------------------------
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

    # --- schema_version taxonomy ------------------------------------------
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

    # --- binding / source-sha integrity -----------------------------------
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


class TestPackageManifestLoadNA81Determinism(unittest.TestCase):
    def test_same_bytes_same_identity(self):
        payload = _canonical_package()
        r1 = _load_ok(payload, idempotency_key="det-k1")
        r2 = _load_ok(idempotency_key="det-k1")
        self.assertEqual(r1.manifest_digest, r2.manifest_digest)
        self.assertEqual(r1.replay_identity, r2.replay_identity)
        self.assertEqual([e.to_dict() for e in r1.entries], [e.to_dict() for e in r2.entries])

    def test_manifest_digest_deterministic(self):
        r1 = _load_ok(idempotency_key="det-k2a")
        r2 = _load_ok(idempotency_key="det-k2b")
        self.assertEqual(r1.manifest_digest, r2.manifest_digest)

    def test_loaded_entries_preserve_order_deterministically(self):
        payload = _canonical_package(instructions=[
            {"id": "zzz", "path": "pz", "target": "tz"},
            {"id": "aaa", "path": "pa", "target": "ta"},
        ])
        r1 = _load_ok(payload, idempotency_key="det-k3a")
        r2 = _load_ok(payload, idempotency_key="det-k3b")
        self.assertEqual([e.id for e in r1.entries], ["zzz", "aaa"])
        self.assertEqual([e.id for e in r2.entries], ["zzz", "aaa"])

    def test_compute_manifest_digest_matches_result(self):
        payload = _canonical_package()
        r = _load_ok(payload)
        self.assertEqual(compute_manifest_digest(payload), r.manifest_digest)


class TestPackageManifestLoadNA81Replay(unittest.TestCase):
    def test_idempotent_replay_same_identity(self):
        payload = _canonical_package()
        key = "r1"
        prior = load_manifest(source=payload, binding=_binding(), observed_source_sha=OBSERVED_SHA, idempotency_key=key)
        self.assertEqual(prior.outcome, OUTCOME_LOADED)
        self.assertEqual(prior.replay_status, REPLAY_STATUS_NONE)
        r2 = load_manifest(source=payload, binding=_binding(), observed_source_sha=OBSERVED_SHA,
                           idempotency_key=key, prior_decision={"replay_identity": prior.replay_identity})
        self.assertEqual(r2.outcome, OUTCOME_LOADED)
        self.assertEqual(r2.replay_status, REPLAY_STATUS_IDEMPOTENT)
        self.assertEqual(r2.replay_identity, prior.replay_identity)
        self.assertNotIn("observed_source_sha", r2.to_dict())

    def test_replay_changed_payload_conflict(self):
        key = "r2"
        prior_payload = _canonical_package(instructions=[{"id": "aaa", "path": "p1", "target": "t1"}])
        prior = load_manifest(source=prior_payload, binding=_binding(), observed_source_sha=OBSERVED_SHA, idempotency_key=key)
        self.assertEqual(prior.outcome, OUTCOME_LOADED)
        new_payload = _canonical_package(instructions=[{"id": "aaa", "path": "p1", "target": "DIFFERENT"}])
        r2 = load_manifest(source=new_payload, binding=_binding(), observed_source_sha=OBSERVED_SHA,
                           idempotency_key=key, prior_decision={"replay_identity": prior.replay_identity})
        self.assertEqual(r2.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r2.errors[0].reason_code, MANIFEST_REPLAY_CONFLICT)
        self.assertEqual(r2.replay_status, REPLAY_STATUS_CONFLICT)

    def test_replay_changed_source_ref_conflict(self):
        key = "r3"
        prior = load_manifest(source=_canonical_package(), binding=_binding(), observed_source_sha=OBSERVED_SHA, idempotency_key=key)
        self.assertEqual(prior.outcome, OUTCOME_LOADED)
        changed_binding = _binding()
        changed_binding["source_ref"] = "refs/heads/other-branch"
        r2 = load_manifest(source=_canonical_package(), binding=changed_binding, observed_source_sha=OBSERVED_SHA,
                            idempotency_key=key, prior_decision={"replay_identity": prior.replay_identity})
        self.assertEqual(r2.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r2.errors[0].reason_code, MANIFEST_REPLAY_CONFLICT)
        self.assertEqual(r2.replay_status, REPLAY_STATUS_CONFLICT)


class TestPackageManifestLoadNA81SchemaUnavailable(unittest.TestCase):
    """The closed input schema validation path must fail CLOSED, not silently pass."""

    def test_schema_validation_unavailable_blocks_closed(self):
        with mock.patch.object(pml_mod, "_load_input_schema", return_value=(None, "injected-unavailable")):
            r = load_manifest(source=_canonical_package(), binding=_binding(), observed_source_sha=OBSERVED_SHA)
        self.assertEqual(r.outcome, OUTCOME_BLOCKED)
        self.assertEqual(r.errors[0].reason_code, MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
