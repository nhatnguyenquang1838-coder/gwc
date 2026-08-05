#!/usr/bin/env python3
"""Tests for package_export.deterministic-hash-verification (SCRUM-235, M5_REPLAY_SAFE)."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))  # noqa: E402

from deterministic_hash_verification import (  # noqa: E402
    ENTRY_STATUS_ACCEPTED,
    ENTRY_STATUS_SKIPPED_OPTIONAL,
    HASH_BYTE_COUNT_MISMATCH,
    HASH_IDEMPOTENT_REPLAY,
    HASH_MANIFEST_DIGEST_MISMATCH,
    HASH_REPLAY_CONFLICT,
    HASH_SOURCE_MISMATCH,
    HASH_TARGET_MISSING,
    HASH_TARGET_MISMATCH,
    HASH_UNMANIFESTED_TARGET,
    HASH_VERIFICATION_PASS,
    Outcome,
    canonical_manifest_digest,
    verify_deterministic_hash,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VerifyTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-hash-verify-"))
        self.src = self.tmp / "src"
        self.out = self.tmp / "out"
        self.src.mkdir()
        self.out.mkdir()
        self.a = b"alpha\n"
        self.b = b"beta\n"
        (self.src / "core").mkdir()
        (self.out / "core").mkdir()
        # Default tree: only a.md present, so a single-entry manifest is complete.
        (self.src / "core" / "a.md").write_bytes(self.a)
        (self.out / "core" / "a.md").write_bytes(self.a)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def add_both(self):
        (self.src / "core" / "b.md").write_bytes(self.b)
        (self.out / "core" / "b.md").write_bytes(self.b)

    def manifest(self, *, entries, source_sha="deadbeef", idempotency_key="run-1",
                 manifest_digest=None, algorithm="sha256", version="1", reason="MANIFEST_GENERATED",
                 outcome="PASS", extra=None):
        m = {
            "schema_id": "gwc.package_export.export_manifest_generation",
            "schema_version": "0.1",
            "task_id": "SCRUM-235",
            "source_sha": source_sha,
            "package_version": "0.1.0",
            "idempotency_key": idempotency_key,
            "manifest_algorithm": algorithm,
            "manifest_algorithm_version": version,
            "plan_digest": _sha(b"plan"),
            "entry_inventory": entries,
            "outcome": outcome,
            "reason": reason,
            "generated_at": "2026-07-22T00:00:00Z",
        }
        if extra:
            m.update(extra)
        m["manifest_digest"] = manifest_digest or canonical_manifest_digest(m)
        return m

    def copied_entry(self, source, target, data):
        return {
            "source": source,
            "target": target,
            "entry_status": ENTRY_STATUS_ACCEPTED,
            "source_digest": _sha(data),
            "target_digest": _sha(data),
            "byte_count": len(data),
            "reason": "MANIFEST_GENERATED",
            "detail": "ok",
        }


class TestExactMatch(VerifyTestBase):
    def test_exact_match_passes(self):
        self.add_both()
        m = self.manifest(entries=[
            self.copied_entry("core/a.md", "core/a.md", self.a),
            self.copied_entry("core/b.md", "core/b.md", self.b),
        ])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1", task_id="SCRUM-235")
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, HASH_VERIFICATION_PASS)
        self.assertEqual(r.entries_verified, 2)
        self.assertEqual(r.entries_rejected, 0)

    def test_authority_never_granted(self):
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertFalse(r.authority_granted)
        self.assertFalse(r.to_dict()["authority_granted"])


class TestChangedSource(VerifyTestBase):
    def test_changed_source_after_export_fails(self):
        (self.src / "core" / "a.md").write_bytes(b"ALPHA-CHANGED\n")
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_SOURCE_MISMATCH)


class TestChangedTarget(VerifyTestBase):
    def test_changed_target_fails(self):
        (self.out / "core" / "a.md").write_bytes(b"ALPHA-TAMPERED\n")
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_TARGET_MISMATCH)


class TestMissingTarget(VerifyTestBase):
    def test_missing_target_fails(self):
        (self.out / "core" / "a.md").unlink()
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_TARGET_MISSING)


class TestExtraTarget(VerifyTestBase):
    def test_extra_unmanifested_target_fails(self):
        (self.out / "core" / "extra.md").write_bytes(b"rogue\n")
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_UNMANIFESTED_TARGET)


class TestWrongByteCount(VerifyTestBase):
    def test_wrong_byte_count_fails(self):
        m = self.manifest(entries=[{
            "source": "core/a.md",
            "target": "core/a.md",
            "entry_status": ENTRY_STATUS_ACCEPTED,
            "source_digest": _sha(self.a),
            "target_digest": _sha(self.a),
            "byte_count": 9999,
            "reason": "MANIFEST_GENERATED",
            "detail": "ok",
        }])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_BYTE_COUNT_MISMATCH)


class TestWrongManifestDigest(VerifyTestBase):
    def test_wrong_manifest_digest_fails(self):
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)],
                          manifest_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000")
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, HASH_MANIFEST_DIGEST_MISMATCH)
        self.assertTrue(any(d.reason == HASH_MANIFEST_DIGEST_MISMATCH for d in r.reject_detail))


class TestUnstableEntryOrder(VerifyTestBase):
    def test_unstable_entry_order_still_passes(self):
        self.add_both()
        e1 = self.copied_entry("core/a.md", "core/a.md", self.a)
        e2 = self.copied_entry("core/b.md", "core/b.md", self.b)
        m1 = self.manifest(entries=[e1, e2])
        m2 = self.manifest(entries=[e2, e1], idempotency_key="run-order-2")
        r1 = verify_deterministic_hash(manifest=m1, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-order-1")
        r2 = verify_deterministic_hash(manifest=m2, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-order-2")
        self.assertEqual(r1.outcome, Outcome.PASS)
        self.assertEqual(r2.outcome, Outcome.PASS)
        # Output-tree digest must be order-independent.
        self.assertEqual(r1.output_tree_digest, r2.output_tree_digest)


class TestChangedGenerationTime(VerifyTestBase):
    def test_changed_generation_time_does_not_change_result(self):
        base = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        later = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)],
                              extra={"generated_at": "2099-01-01T00:00:00Z"})
        r1 = verify_deterministic_hash(manifest=base, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1")
        r2 = verify_deterministic_hash(manifest=later, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1")
        self.assertEqual(r1.outcome, Outcome.PASS)
        self.assertEqual(r2.outcome, Outcome.PASS)
        self.assertEqual(r1.manifest_digest, r2.manifest_digest)


class TestSkippedOptional(VerifyTestBase):
    def test_skipped_optional_entry_requires_no_target(self):
        # b.md exists in source but intentionally not copied to output.
        (self.src / "core" / "b.md").write_bytes(self.b)
        m = self.manifest(entries=[
            self.copied_entry("core/a.md", "core/a.md", self.a),
            {
                "source": "core/b.md",
                "target": "core/b.md",
                "entry_status": ENTRY_STATUS_SKIPPED_OPTIONAL,
                "source_digest": None,
                "target_digest": None,
                "byte_count": None,
                "reason": "MANIFEST_SOURCE_MISSING",
                "detail": "optional skipped",
            },
        ])
        r = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                      idempotency_key="run-1")
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.entries_verified, 2)


class TestReplay(VerifyTestBase):
    def test_identical_replay_returns_same_result(self):
        m = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)])
        r1 = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1", task_id="SCRUM-235")
        self.assertEqual(r1.reason, HASH_VERIFICATION_PASS)
        r2 = verify_deterministic_hash(manifest=m, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1", task_id="SCRUM-235",
                                       existing_result=r1.to_dict())
        self.assertEqual(r2.outcome, Outcome.PASS)
        self.assertEqual(r2.reason, HASH_IDEMPOTENT_REPLAY)
        self.assertEqual(r1.manifest_digest, r2.manifest_digest)
        self.assertEqual(r1.output_tree_digest, r2.output_tree_digest)

    def test_conflicting_replay_fails(self):
        m1 = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)],
                           source_sha="deadbeef")
        r1 = verify_deterministic_hash(manifest=m1, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1")
        self.assertEqual(r1.reason, HASH_VERIFICATION_PASS)
        # Same idempotency key, but the manifest identity changed (different source_sha).
        m2 = self.manifest(entries=[self.copied_entry("core/a.md", "core/a.md", self.a)],
                           source_sha="feedface")
        r2 = verify_deterministic_hash(manifest=m2, source_root=self.src, output_root=self.out,
                                       idempotency_key="run-1", existing_result=r1.to_dict())
        self.assertEqual(r2.outcome, Outcome.FAIL)
        self.assertEqual(r2.reason, HASH_REPLAY_CONFLICT)


if __name__ == "__main__":
    unittest.main()
