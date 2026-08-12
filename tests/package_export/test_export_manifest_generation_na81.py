#!/usr/bin/env python3
"""NA81 delivery tests for SCRUM-357 — package_export.export-manifest-generation.

Requirement → code → test evidence map for the current NA81 brief:

1. Deterministic generation
2. Missing source/provenance blocks generation
3. Ordering stability
4. Duplicate / extra entry handling
5. Source drift (cross-check mismatch)
6. Replay / digest stability
7. Authority never granted
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))  # noqa: E402

from export_manifest_generation import (
    ENTRY_STATUS_ACCEPTED,
    ENTRY_STATUS_MISSING,
    ENTRY_STATUS_REJECTED,
    MANIFEST_DIGEST_MISMATCH,
    MANIFEST_GENERATED,
    MANIFEST_IDEMPOTENT_REPLAY,
    MANIFEST_SOURCE_MISSING,
    Outcome,
    ExportManifestResult,
    ManifestPlanEntry,
    authority_granted,
    compute_manifest_digest,
    compute_plan_digest,
    generate_export_manifest,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SCRUM357EvidenceMap(unittest.TestCase):
    """Current-task requirement → existing code proof for SCRUM-357."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-manifest-357-"))
        self.src = self.tmp / "src"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def plan(self):
        return [
            ManifestPlanEntry(source="core/a.md", target="core/a.md"),
            ManifestPlanEntry(source="core/b.md", target="core/b.md"),
        ]

    def gen(self, entries=None, key="scr-357", cross_check=False, **kw):
        return generate_export_manifest(
            entries if entries is not None else self.plan(),
            self.src,
            idempotency_key=key,
            task_id="SCRUM-357",
            source_sha="e78283cc" + "0" * 32,
            package_version="0.1.0",
            cross_check=cross_check,
            **kw,
        )

    # 1. Deterministic generation -------------------------------------------
    def test_deterministic_generation(self):
        r = self.gen()
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)
        self.assertEqual(len(r.entries), 2)
        for e in r.entries:
            self.assertEqual(e.entry_status, ENTRY_STATUS_ACCEPTED)
            self.assertIsNotNone(e.source_digest)
        self.assertTrue(r.manifest["manifest_digest"].startswith("sha256:"))

    # 2. Missing source/provenance blocks generation -------------------------
    def test_required_source_missing_blocks(self):
        r = self.gen(entries=[ManifestPlanEntry(source="core/missing.md", target="core/missing.md")])
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_SOURCE_MISSING)
        self.assertEqual(r.entries[0].entry_status, ENTRY_STATUS_MISSING)

    # 3. Ordering stability -------------------------------------------------
    def test_ordering_stable(self):
        a = compute_plan_digest(self.plan())
        b = compute_plan_digest(list(reversed(self.plan())))
        self.assertEqual(a, b)

    # 4. Duplicate / extra entry ---------------------------------------------
    def test_duplicate_plan_entry_handled_deterministically(self):
        # Duplicate source/target in plan: generator records both entries
        # deterministically because the plan is sorted by (target, source).
        dup_plan = [
            ManifestPlanEntry(source="core/a.md", target="core/a.md"),
            ManifestPlanEntry(source="core/a.md", target="core/a.md"),
            ManifestPlanEntry(source="core/b.md", target="core/b.md"),
        ]
        r = self.gen(entries=dup_plan)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)
        self.assertEqual(len(r.entries), 3)
        # All entries are ACCEPTED because sources exist.
        for e in r.entries:
            self.assertEqual(e.entry_status, ENTRY_STATUS_ACCEPTED)
        # Deterministic: same plan produces same manifest.
        r2 = self.gen(entries=dup_plan)
        self.assertEqual(r.manifest, r2.manifest)

    # 5. Source drift (cross-check mismatch) ---------------------------------
    def test_source_drift_mismatch_blocks(self):
        upstream = {
            "entry_inventory": [
                {"target": "core/a.md", "source": "core/a.md",
                 "source_digest": "0" * 64, "target_digest": "0" * 64},
            ]
        }
        r = self.gen(
            entries=[ManifestPlanEntry(source="core/a.md", target="core/a.md")],
            tree_build_evidence=upstream,
            cross_check=True,
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_DIGEST_MISMATCH)
        self.assertEqual(r.entries[0].entry_status, ENTRY_STATUS_REJECTED)

    # 6. Replay / digest stability -------------------------------------------
    def test_replay_digest_stable(self):
        first = self.gen()
        second = self.gen(existing_manifest=first.manifest)
        self.assertEqual(second.outcome, Outcome.PASS)
        self.assertEqual(second.reason, MANIFEST_IDEMPOTENT_REPLAY)
        self.assertEqual(second.manifest, first.manifest)
        # Digest is self-consistent.
        stripped = {k: v for k, v in first.manifest.items() if k != "manifest_digest"}
        self.assertEqual(
            first.manifest["manifest_digest"],
            "sha256:" + compute_manifest_digest(stripped),
        )

    # 7. Authority never granted ---------------------------------------------
    def test_authority_never_granted(self):
        r = self.gen()
        self.assertFalse(authority_granted(r))


if __name__ == "__main__":
    unittest.main()
