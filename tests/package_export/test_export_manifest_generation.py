#!/usr/bin/env python3
"""Tests for package_export.export-manifest-generation (SCRUM-234, M5_EVIDENCE)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Import as a direct module (no package __init__ needed) to stay within the
# G2-approved authorized_paths for this task.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))  # noqa: E402

from export_manifest_generation import (  # noqa: E402
    ENTRY_STATUS_ACCEPTED,
    ENTRY_STATUS_MISSING,
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
    import hashlib

    return hashlib.sha256(data).hexdigest()


class ManifestTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-manifest-"))
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

    def gen(self, entries=None, key="run-1", cross_check=False, **kw):
        return generate_export_manifest(
            entries if entries is not None else self.plan(),
            self.src,
            idempotency_key=key,
            task_id="SCRUM-234",
            source_sha="deadbeef",
            package_version="0.1.0",
            cross_check=cross_check,
            **kw,
        )


class TestCleanGeneration(ManifestTestBase):
    def test_generates_with_acceptance(self):
        r = self.gen()
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, MANIFEST_GENERATED)
        self.assertTrue(r.generated)
        self.assertEqual(len(r.entries), 2)
        for e in r.entries:
            self.assertEqual(e.entry_status, ENTRY_STATUS_ACCEPTED)
            self.assertIsNotNone(e.source_digest)
            self.assertEqual(e.byte_count, len(b"alpha\n") if e.source.endswith("a.md") else len(b"beta\n"))
        self.assertTrue(r.manifest["manifest_digest"].startswith("sha256:"))

    def test_authority_never_granted(self):
        r = self.gen()
        self.assertFalse(authority_granted(r))

    def test_manifest_is_deterministic(self):
        m1 = self.gen().manifest
        m2 = self.gen().manifest
        self.assertEqual(m1, m2)

    def test_manifest_digest_is_self_consistent(self):
        r = self.gen()
        stripped = {k: v for k, v in r.manifest.items() if k != "manifest_digest"}
        self.assertEqual(
            r.manifest["manifest_digest"],
            "sha256:" + compute_manifest_digest(stripped),
        )

    def test_plan_digest_order_independent(self):
        a = compute_plan_digest(self.plan())
        b = compute_plan_digest(list(reversed(self.plan())))
        self.assertEqual(a, b)


class TestMissingSources(ManifestTestBase):
    def test_required_missing_fails(self):
        bad = [ManifestPlanEntry(source="core/missing.md", target="core/missing.md")]
        r = self.gen(entries=bad)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, MANIFEST_SOURCE_MISSING)
        self.assertEqual(r.entries[0].entry_status, ENTRY_STATUS_MISSING)

    def test_optional_missing_recorded_not_fatal(self):
        plan = [
            ManifestPlanEntry(source="core/a.md", target="core/a.md", required=True),
            ManifestPlanEntry(source="core/opt.md", target="core/opt.md", required=False),
        ]
        r = self.gen(entries=plan)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.entries[1].entry_status, ENTRY_STATUS_MISSING)


class TestCrossCheck(ManifestTestBase):
    def test_cross_check_digest_match_passes(self):
        upstream = {
            "entry_inventory": [
                {"target": "core/a.md", "source": "core/a.md",
                 "source_digest": _sha(b"alpha\n"), "target_digest": _sha(b"alpha\n")},
                {"target": "core/b.md", "source": "core/b.md",
                 "source_digest": _sha(b"beta\n"), "target_digest": _sha(b"beta\n")},
            ]
        }
        r = self.gen(tree_build_evidence=upstream, cross_check=True)
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.entries[0].target_digest, _sha(b"alpha\n"))

    def test_cross_check_digest_mismatch_fails(self):
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


class TestReplay(ManifestTestBase):
    def test_idempotent_replay(self):
        first = self.gen()
        second = self.gen(existing_manifest=first.manifest)
        self.assertEqual(second.outcome, Outcome.PASS)
        self.assertEqual(second.reason, MANIFEST_IDEMPOTENT_REPLAY)
        self.assertEqual(second.manifest, first.manifest)

    def test_replay_conflict_on_plan_change(self):
        first = self.gen()
        other_plan = [ManifestPlanEntry(source="core/a.md", target="core/a.md")]
        other = self.gen(entries=other_plan)
        conflict = self.gen(existing_manifest=other.manifest, key="run-1")
        self.assertEqual(conflict.outcome, Outcome.FAIL)
        self.assertEqual(conflict.reason, MANIFEST_DIGEST_MISMATCH)


if __name__ == "__main__":
    unittest.main()
