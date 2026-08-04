#!/usr/bin/env python3
"""Tests for package_export.governance_tree_build (SCRUM-233, M5_REPLAY_SAFE)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from node_architect.package_export.governance_tree_build import (  # noqa: E402
    COMPLETION_MARKER,
    SCHEMA_ID,
    SCHEMA_VERSION,
    TREE_BUILD_COMPLETE,
    TREE_BUILD_STAGED,
    TREE_COPY_MISMATCH,
    TREE_IDEMPOTENT_REPLAY,
    TREE_PARTIAL_OUTPUT,
    TREE_READBACK_MISMATCH,
    TREE_REPLAY_CONFLICT,
    TREE_REQUIRED_SOURCE_MISSING,
    TREE_STALE_SOURCE,
    TREE_TARGET_COLLISION,
    Outcome,
    PlanEntry,
    authority_granted,
    build_governance_tree,
    compute_plan_digest,
)

import hashlib


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TreeBuildTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-tree-"))
        self.src = self.tmp / "src"
        self.out = self.tmp / "out" / ".governance"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def plan(self, **over):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md"),
            PlanEntry(source="core/b.md", target="core/b.md"),
        ]
        return over.get("entries", entries)

    def build(self, entries=None, key="run-1", **kw):
        return build_governance_tree(
            entries if entries is not None else self.plan(),
            self.src,
            self.out,
            idempotency_key=key,
            task_id="SCRUM-233",
            source_sha="deadbeef",
            package_version="0.1.0",
            **kw,
        )


class TestCleanBuild(TreeBuildTestBase):
    def test_clean_build_completes(self):
        r = self.build()
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        self.assertTrue(r.complete)
        self.assertEqual((self.out / "core" / "a.md").read_bytes(), b"alpha\n")
        self.assertEqual((self.out / "core" / "b.md").read_bytes(), b"beta\n")

    def test_completion_evidence_binds_identity(self):
        r = self.build()
        ev = r.completion_evidence
        self.assertEqual(ev["schema_id"], SCHEMA_ID)
        self.assertEqual(ev["schema_version"], SCHEMA_VERSION)
        self.assertEqual(ev["task_id"], "SCRUM-233")
        self.assertEqual(ev["source_sha"], "deadbeef")
        self.assertEqual(ev["package_version"], "0.1.0")
        self.assertEqual(ev["idempotency_key"], "run-1")
        self.assertEqual(ev["plan_digest"], r.plan_digest)
        self.assertEqual(ev["tree_digest"], r.tree_digest)
        self.assertEqual(len(ev["entry_inventory"]), 2)
        for item in ev["entry_inventory"]:
            self.assertIsNotNone(item["source_digest"])
            self.assertIsNotNone(item["target_digest"])
            self.assertGreater(item["byte_count"], 0)

    def test_completion_marker_written_on_disk(self):
        self.build()
        marker = json.loads((self.out / COMPLETION_MARKER).read_text())
        self.assertEqual(marker["reason"], TREE_BUILD_COMPLETE)

    def test_entry_digests_match_source_bytes(self):
        r = self.build()
        by_target = {e.target: e for e in r.entries}
        self.assertEqual(by_target["core/a.md"].source_digest, _sha(b"alpha\n"))
        self.assertEqual(by_target["core/a.md"].target_digest, _sha(b"alpha\n"))
        self.assertEqual(by_target["core/a.md"].byte_count, 6)

    def test_determinism_same_plan_same_tree_digest(self):
        r1 = self.build(key="k1")
        shutil.rmtree(self.out)
        r2 = self.build(key="k2")
        self.assertEqual(r1.tree_digest, r2.tree_digest)
        self.assertEqual(r1.plan_digest, r2.plan_digest)

    def test_plan_digest_order_independent(self):
        a = [
            PlanEntry(source="core/a.md", target="core/a.md"),
            PlanEntry(source="core/b.md", target="core/b.md"),
        ]
        self.assertEqual(compute_plan_digest(a), compute_plan_digest(list(reversed(a))))

    def test_authority_never_granted(self):
        self.assertFalse(authority_granted(self.build()))


class TestOptionalAndMissing(TreeBuildTestBase):
    def test_optional_missing_entry_is_skipped(self):
        entries = self.plan() + [
            PlanEntry(source="core/missing.md", target="core/missing.md", required=False)
        ]
        r = self.build(entries)
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        self.assertFalse((self.out / "core" / "missing.md").exists())
        self.assertEqual(len(r.entries), 2)

    def test_required_missing_aborts_build(self):
        entries = self.plan() + [
            PlanEntry(source="core/gone.md", target="core/gone.md", required=True)
        ]
        r = self.build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_REQUIRED_SOURCE_MISSING)
        self.assertFalse(r.complete)

    def test_required_source_disappears_after_planning(self):
        entries = self.plan()
        (self.src / "core" / "b.md").unlink()
        r = self.build(entries)
        self.assertEqual(r.reason, TREE_REQUIRED_SOURCE_MISSING)
        self.assertFalse(self.out.exists())


class TestFailureIsolation(TreeBuildTestBase):
    def test_target_collision_fails(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/x.md"),
            PlanEntry(source="core/b.md", target="core/x.md"),
        ]
        r = self.build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_TARGET_COLLISION)
        self.assertFalse(self.out.exists())

    def test_stale_source_digest_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", source_digest=_sha(b"OLD")),
        ]
        r = self.build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_STALE_SOURCE)
        self.assertFalse(self.out.exists())

    def test_matching_source_digest_passes(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", source_digest=_sha(b"alpha\n")),
        ]
        self.assertEqual(self.build(entries).reason, TREE_BUILD_COMPLETE)

    def test_failed_build_leaves_no_staging_tree(self):
        entries = self.plan() + [PlanEntry(source="nope.md", target="nope.md")]
        self.build(entries)
        leftovers = [p for p in (self.tmp / "out").glob("*") if ".staging" in p.name]
        self.assertEqual(leftovers, [])

    def test_crash_after_partial_staging_is_not_promoted(self):
        # Simulate crash: stage only (no promotion), then verify no final tree.
        r = self.build(promote=False, staging_root=self.tmp / "stage-crash")
        self.assertEqual(r.reason, TREE_BUILD_STAGED)
        self.assertFalse(r.complete)
        self.assertFalse(self.out.exists())

    def test_crash_before_completion_marker_is_incomplete(self):
        self.build()
        (self.out / COMPLETION_MARKER).unlink()
        # Without the marker, a rerun is not a replay — it rebuilds cleanly.
        r = self.build(key="run-1")
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)

    def test_leftover_partial_staging_is_rebuilt(self):
        stage = self.tmp / "stage-leftover"
        (stage / "core").mkdir(parents=True)
        (stage / "core" / "garbage.md").write_bytes(b"junk")
        r = self.build(staging_root=stage)
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        self.assertFalse((self.out / "core" / "garbage.md").exists())

    def test_copy_mismatch_reason_code_available(self):
        # Reason code is part of the closed taxonomy and reachable by contract.
        from node_architect.package_export import governance_tree_build as m

        self.assertIn(TREE_COPY_MISMATCH, m.REASON_CODES)
        self.assertIn(TREE_READBACK_MISMATCH, m.REASON_CODES)
        self.assertIn(TREE_PARTIAL_OUTPUT, m.REASON_CODES)


class TestReplay(TreeBuildTestBase):
    def test_identical_replay_returns_existing_tree(self):
        first = self.build(key="run-A")
        again = self.build(key="run-A")
        self.assertEqual(again.outcome, Outcome.PASS)
        self.assertEqual(again.reason, TREE_IDEMPOTENT_REPLAY)
        self.assertEqual(again.tree_digest, first.tree_digest)
        self.assertTrue(again.complete)

    def test_conflicting_replay_fails(self):
        self.build(key="run-A")
        conflicting = [PlanEntry(source="core/a.md", target="core/a.md")]
        r = self.build(conflicting, key="run-A")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_REPLAY_CONFLICT)

    def test_different_key_rebuilds(self):
        self.build(key="run-A")
        r = self.build(key="run-B")
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)

    def test_replay_does_not_mutate_existing_tree(self):
        self.build(key="run-A")
        before = (self.out / COMPLETION_MARKER).read_bytes()
        self.build(key="run-A")
        self.assertEqual((self.out / COMPLETION_MARKER).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
