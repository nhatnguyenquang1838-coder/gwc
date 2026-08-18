#!/usr/bin/env python3
"""NA81 tests for package_export.export-manifest-generation (SCRUM-357 / F7).

Maps the current NA81 brief requirements to code + tests (current-task proof
pattern): deterministic generation, missing source/provenance blocking,
ordering, duplicate/extra entry blocking, source-drift detection and
replay/digest stability. The prior SCRUM-234 generator declared
``MANIFEST_ENTRY_INVALID`` and provenance in its schema but never emitted
either; these tests pin the NA81-F7 delta that closes that gap.

Import rule (SCRUM-323): insert the absolute ``tools/`` dir into sys.path[0]
and import via the ``node_architect...`` namespace so CI
``python -m unittest discover`` from repo root works under Py3.12 namespace
packages.
"""

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # noqa: E402

from node_architect.package_export.export_manifest_generation import (  # noqa: E402
    ENTRY_STATUS_ACCEPTED,
    ENTRY_STATUS_REJECTED,
    MANIFEST_DIGEST_MISMATCH,
    MANIFEST_ENTRY_INVALID,
    MANIFEST_GENERATED,
    MANIFEST_IDEMPOTENT_REPLAY,
    MANIFEST_SOURCE_MISSING,
    Outcome,
    ManifestPlanEntry,
    authority_granted,
    compute_manifest_digest,
    generate_export_manifest,
)

SOURCE_SHA = "a15bdf8deadbeef0000000000000000000000000"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NA81ExportManifestTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-manifest-na81-"))
        self.src = self.tmp / "src"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        (self.src / "core" / "extra.md").write_bytes(b"gamma\n")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.prov = {
            "source_repository": "nhatnguyenquang1838-coder/gwc",
            "source_ref": "pre-prod",
            "source_base_sha": SOURCE_SHA,
            "project_id": "gwc",
            "target_root": ".governance",
        }
        self.idem = "na81-run-1"

    def plan(self):
        return [
            ManifestPlanEntry(source="core/a.md", target="core/a.md"),
            ManifestPlanEntry(source="core/b.md", target="core/b.md"),
        ]

    def gen(self, entries=None, **kw):
        return generate_export_manifest(
            entries if entries is not None else self.plan(),
            self.src,
            idempotency_key=self.idem,
            task_id="SCRUM-357",
            source_sha=SOURCE_SHA,
            package_version="0.1.0",
            **kw,
        )


class TestNA81Provenance(NA81ExportManifestTestBase):
    def test_provenance_emitted_when_provided(self):
        r = self.gen(provenance=self.prov)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)
        for key, value in self.prov.items():
            self.assertEqual(r.manifest[key], value)

    def test_provenance_omitted_when_absent(self):
        r = self.gen()
        self.assertEqual(r.outcome, Outcome.PASS)
        # Prior (pre-NA81) manifest shape unchanged: no provenance keys.
        for key in self.prov:
            self.assertNotIn(key, r.manifest)

    def test_missing_provenance_blocks_when_required(self):
        r = self.gen(require_provenance=True)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_ENTRY_INVALID)
        self.assertIn("missing required provenance", r.detail)

    def test_empty_provenance_blocks_when_required(self):
        r = self.gen(require_provenance=True, provenance={k: "" for k in self.prov})
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_ENTRY_INVALID)

    def test_provenance_present_satisfies_requirement(self):
        r = self.gen(provenance=self.prov, require_provenance=True)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)


class TestNA81EntryValidity(NA81ExportManifestTestBase):
    def test_duplicate_target_blocked(self):
        plan = [
            ManifestPlanEntry(source="core/a.md", target="core/a.md"),
            ManifestPlanEntry(source="core/b.md", target="core/a.md"),
        ]
        r = self.gen(entries=plan)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_ENTRY_INVALID)
        self.assertEqual(r.entries[0].entry_status, ENTRY_STATUS_REJECTED)
        self.assertIn("duplicate target", r.detail)

    def test_extra_entry_blocked_when_validated(self):
        upstream = {
            "entry_inventory": [
                {"target": "core/a.md", "source": "core/a.md"},
                {"target": "core/b.md", "source": "core/b.md"},
            ]
        }
        plan = self.plan() + [
            ManifestPlanEntry(source="core/extra.md", target="core/extra.md")
        ]
        r = self.gen(entries=plan, tree_build_evidence=upstream, require_validated=True)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_ENTRY_INVALID)
        self.assertIn("validated upstream inventory", r.detail)

    def test_extra_entry_allowed_without_require_validated(self):
        upstream = {"entry_inventory": [{"target": "core/a.md"}]}
        plan = self.plan() + [
            ManifestPlanEntry(source="core/extra.md", target="core/extra.md")
        ]
        # Without require_validated the extra entry is merely un-cross-checked.
        r = self.gen(entries=plan, tree_build_evidence=upstream)
        self.assertEqual(r.outcome, Outcome.PASS)


class TestNA81SourceDrift(NA81ExportManifestTestBase):
    def test_source_drift_via_expected_digest(self):
        plan = [
            ManifestPlanEntry(
                source="core/a.md",
                target="core/a.md",
                expected_source_digest="0" * 64,
            )
        ]
        r = self.gen(entries=plan)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_DIGEST_MISMATCH)
        self.assertEqual(r.entries[0].entry_status, ENTRY_STATUS_REJECTED)
        self.assertIn("drifted", r.detail)

    def test_matching_expected_digest_passes(self):
        plan = [
            ManifestPlanEntry(
                source="core/a.md",
                target="core/a.md",
                expected_source_digest=_sha(b"alpha\n"),
            )
        ]
        r = self.gen(entries=plan)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)


class TestNA81DeterminismAndReplay(NA81ExportManifestTestBase):
    def test_generated_manifest_stable_with_provenance(self):
        m1 = self.gen(provenance=self.prov).manifest
        m2 = self.gen(provenance=self.prov).manifest
        self.assertEqual(m1, m2)
        stripped = {k: v for k, v in m1.items() if k != "manifest_digest"}
        self.assertEqual(
            m1["manifest_digest"], "sha256:" + compute_manifest_digest(stripped)
        )

    def test_replay_returns_existing_with_provenance(self):
        first = self.gen(provenance=self.prov)
        second = self.gen(existing_manifest=first.manifest, provenance=self.prov)
        self.assertEqual(second.outcome, Outcome.PASS)
        self.assertEqual(second.reason, MANIFEST_IDEMPOTENT_REPLAY)
        self.assertEqual(second.manifest, first.manifest)

    def test_authority_never_granted_with_provenance(self):
        r = self.gen(provenance=self.prov)
        self.assertFalse(authority_granted(r))

    def test_missing_source_still_blocks(self):
        bad = [ManifestPlanEntry(source="core/missing.md", target="core/missing.md")]
        r = self.gen(entries=bad, provenance=self.prov)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_SOURCE_MISSING)


if __name__ == "__main__":
    unittest.main()
