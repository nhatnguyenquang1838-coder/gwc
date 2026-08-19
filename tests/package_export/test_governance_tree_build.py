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
    TREE_DUPLICATE_ENTRY,
    TREE_MISSING_PARENT,
    TREE_CYCLE_DETECTED,
    TREE_AMBIGUOUS_ORDER,
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


class TestTopologyValid(TreeBuildTestBase):
    """SCRUM-356: deterministic instruction-tree topology from validated entries."""

    def _tree_plan(self):
        # root -> child -> grandchild, plus a second root
        return [
            PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0),
            PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md", order=0),
            PlanEntry(source="core/a.md", target="core/x.md", parent="core/b.md", order=0),
            PlanEntry(source="core/b.md", target="core/c.md", parent=None, order=1),
        ]

    def test_valid_tree_completes(self):
        r = self.build(self._tree_plan())
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        self.assertTrue(r.complete)

    def test_canonical_order_parents_before_children(self):
        r = self.build(self._tree_plan())
        targets = [e.target for e in r.entries]
        self.assertLess(targets.index("core/a.md"), targets.index("core/b.md"))
        self.assertLess(targets.index("core/b.md"), targets.index("core/x.md"))

    def test_sibling_order_respected(self):
        r = self.build(self._tree_plan())
        targets = [e.target for e in r.entries]
        # Both roots; order(0)=a.md before order(1)=c.md
        self.assertLess(targets.index("core/a.md"), targets.index("core/c.md"))

    def test_provenance_fields_recorded(self):
        r = self.build(self._tree_plan())
        by_target = {e.target: e for e in r.entries}
        a = by_target["core/a.md"]
        self.assertIsNone(a.parent)
        self.assertEqual(a.depth, 0)
        self.assertEqual(a.tree_path, "core/a.md")
        b = by_target["core/b.md"]
        self.assertEqual(b.parent, "core/a.md")
        self.assertEqual(b.depth, 1)
        self.assertEqual(b.tree_path, "core/a.md/core/b.md")
        x = by_target["core/x.md"]
        self.assertEqual(x.parent, "core/b.md")
        self.assertEqual(x.depth, 2)
        self.assertEqual(x.tree_path, "core/a.md/core/b.md/core/x.md")
        # index is the canonical position
        self.assertEqual([e.index for e in r.entries], list(range(len(r.entries))))

    def test_completion_evidence_carries_topology(self):
        r = self.build(self._tree_plan())
        inv = {i["target"]: i for i in r.completion_evidence["entry_inventory"]}
        self.assertEqual(inv["core/x.md"]["tree_path"], "core/a.md/core/b.md/core/x.md")
        self.assertEqual(inv["core/b.md"]["depth"], 1)
        self.assertEqual(inv["core/c.md"]["order"], 1)

    def test_legacy_flat_plan_no_parent_unchanged(self):
        # A legacy plan (no parent/order) still builds and falls back to
        # target/source ordering with depth 0 and tree_path == target.
        r = self.build(self.plan())
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        by_target = {e.target: e for e in r.entries}
        self.assertEqual(by_target["core/a.md"].depth, 0)
        self.assertEqual(by_target["core/a.md"].tree_path, "core/a.md")


class TestTopologyNegative(unittest.TestCase):
    """SCRUM-356: cycles, duplicate entries, missing parents and ambiguous
    ordering must block the build fail-closed — before any write."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-tree-neg-"))
        self.src = self.tmp / "src"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        self.out = self.tmp / "out" / ".governance"
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _build(self, entries, key="neg"):
        return build_governance_tree(
            entries, self.src, self.out, idempotency_key=key,
            task_id="SCRUM-356", source_sha="deadbeef", package_version="0.1.0",
        )

    def test_cycle_detected_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", parent="core/b.md"),
            PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md"),
        ]
        r = self._build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_CYCLE_DETECTED)
        self.assertFalse(r.complete)
        self.assertFalse(self.out.exists())

    def test_self_cycle_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", parent="core/a.md"),
        ]
        r = self._build(entries)
        self.assertEqual(r.reason, TREE_CYCLE_DETECTED)
        self.assertFalse(self.out.exists())

    def test_missing_parent_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", parent="core/ghost.md"),
        ]
        r = self._build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_MISSING_PARENT)
        self.assertFalse(self.out.exists())

    def test_duplicate_entry_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md"),
            PlanEntry(source="core/a.md", target="core/a.md"),
        ]
        r = self._build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_DUPLICATE_ENTRY)
        self.assertFalse(self.out.exists())

    def test_ambiguous_order_blocks_build(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0),
            PlanEntry(source="core/b.md", target="core/b.md", parent=None, order=0),
        ]
        r = self._build(entries)
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, TREE_AMBIGUOUS_ORDER)
        self.assertFalse(self.out.exists())

    def test_topology_failure_does_not_write_output(self):
        entries = [
            PlanEntry(source="core/a.md", target="core/a.md", parent="core/missing.md"),
        ]
        self._build(entries)
        # No output tree and no leftover staging must remain.
        self.assertFalse(self.out.exists())
        leftovers = [p for p in (self.tmp / "out").glob("*") if ".staging" in p.name]
        self.assertEqual(leftovers, [])

    def test_topology_reason_codes_in_closed_taxonomy(self):
        from node_architect.package_export import governance_tree_build as m

        for code in (TREE_DUPLICATE_ENTRY, TREE_MISSING_PARENT,
                     TREE_CYCLE_DETECTED, TREE_AMBIGUOUS_ORDER):
            self.assertIn(code, m.REASON_CODES)


class TestTopologyReplayAndDrift(unittest.TestCase):
    """SCRUM-356: source drift and same-input same-digest replay for trees."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-tree-rep-"))
        self.src = self.tmp / "src"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        (self.src / "core" / "c.md").write_bytes(b"gamma\n")
        self.out = self.tmp / "out" / ".governance"
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _plan(self, key):
        return [
            PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0),
            PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md", order=0),
            PlanEntry(source="core/c.md", target="core/c.md", parent=None, order=1),
        ]

    def _build(self, entries=None, key="rep", **kw):
        return build_governance_tree(
            entries if entries is not None else self._plan(key),
            self.src, self.out, idempotency_key=key,
            task_id="SCRUM-356", source_sha="deadbeef", package_version="0.1.0", **kw,
        )

    def test_same_input_same_digest_replay(self):
        first = self._build(key="k")
        again = self._build(key="k")
        self.assertEqual(again.reason, TREE_IDEMPOTENT_REPLAY)
        self.assertEqual(again.tree_digest, first.tree_digest)

    def test_plan_digest_is_topology_aware(self):
        a = [
            PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0),
            PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md", order=0),
        ]
        b = [
            PlanEntry(source="core/b.md", target="core/b.md", parent=None, order=0),
            PlanEntry(source="core/a.md", target="core/a.md", parent="core/b.md", order=0),
        ]
        # Same files, different parent wiring -> different plan digest.
        self.assertNotEqual(compute_plan_digest(a), compute_plan_digest(b))

    def test_source_drift_blocks_rebuild(self):
        # Plan carries a recorded source digest (planning-time evidence).
        plan = [
            PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0,
                      source_digest=_sha(b"alpha\n")),
            PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md", order=0,
                      source_digest=_sha(b"beta\n")),
            PlanEntry(source="core/c.md", target="core/c.md", parent=None, order=1),
        ]
        r = self._build(plan, key="k")
        self.assertEqual(r.reason, TREE_BUILD_COMPLETE)
        # Source drifts after planning -> stale-source block.
        (self.src / "core" / "b.md").write_bytes(b"TAMPERED\n")
        again = self._build(plan, key="k2")
        self.assertEqual(again.reason, TREE_STALE_SOURCE)
        self.assertFalse(again.complete)


class TestSchemaValidity(unittest.TestCase):
    """The completion evidence emitted for a topology-aware tree validates."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-tree-schema-"))
        self.src = self.tmp / "src"
        (self.src / "core").mkdir(parents=True)
        (self.src / "core" / "a.md").write_bytes(b"alpha\n")
        (self.src / "core" / "b.md").write_bytes(b"beta\n")
        self.out = self.tmp / "out" / ".governance"
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_topology_evidence_validates_against_schema(self):
        import jsonschema

        r = build_governance_tree(
            [
                PlanEntry(source="core/a.md", target="core/a.md", parent=None, order=0),
                PlanEntry(source="core/b.md", target="core/b.md", parent="core/a.md", order=0),
            ],
            self.src, self.out, idempotency_key="k",
            task_id="SCRUM-356", source_sha="deadbeef", package_version="0.1.0",
        )
        schema = json.loads(
            (Path(__file__).resolve().parents[2]
             / "schemas/node-architect/package-export/governance-tree-build.schema.json")
            .read_text(encoding="utf-8")
        )
        jsonschema.validate(r.completion_evidence, schema)


if __name__ == "__main__":
    unittest.main()
