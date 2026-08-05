#!/usr/bin/env python3
"""Tests for package_export.smoke-verification (SCRUM-236, M5_REPLAY_SAFE)."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))  # noqa: E402

from smoke_verification import (  # noqa: E402
    SMOKE_ENVIRONMENT_UNSAFE,
    SMOKE_HASH_MISMATCH,
    SMOKE_IDEMPOTENT_REPLAY,
    SMOKE_MANIFEST_INVALID,
    SMOKE_REPLAY_CONFLICT,
    SMOKE_REQUIRED_TARGET_MISSING,
    SMOKE_RESULT_UNKNOWN,
    SMOKE_TIMEOUT,
    SMOKE_VERIFICATION_PASS,
    Outcome,
    compute_result_digest,
    verify_smoke,
)

REQUIRED_TARGETS = {
    ".governance/core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md",
    ".governance/schemas/package-export-manifest.schema.json",
    ".governance/tools/export_project_package.py",
    ".governance/tools/verify_package_export_smoke.py",
    ".governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SmokeTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-smoke-"))
        self.repo = self.tmp / "repo"
        self.pkg = self.tmp / "package"
        self.repo.mkdir()
        self.pkg.mkdir()
        # Minimal repo with the wrapped verifier present (never actually called
        # in most fixtures; we stub run_wrapped_smoke_verifier where needed).
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "verify_package_export_smoke.py").write_text(
            "import sys\nprint('{\"ok\": true}')\nsys.exit(0)\n"
        )
        # Build a valid package tree with required targets.
        for rel in REQUIRED_TARGETS:
            t = self.pkg / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(b"content:" + rel.encode())
        self.a = b"alpha\n"
        (self.repo / "core").mkdir()
        (self.pkg / "core").mkdir()
        (self.repo / "core" / "a.md").write_bytes(self.a)
        (self.pkg / "core" / "a.md").write_bytes(self.a)
        # Manifest (SCRUM-234 shape) bound to these bytes.
        self.manifest = {
            "schema_id": "gwc.package_export.export_manifest_generation",
            "schema_version": "0.1",
            "task_id": "SCRUM-236",
            "source_sha": "deadbeef",
            "project_id": "gwc",
            "package_version": "0.1.0",
            "source_ref": "main",
            "idempotency_key": "smoke-1",
            "manifest_algorithm": "sha256",
            "manifest_algorithm_version": "1",
            "plan_digest": _sha(b"plan"),
            "entry_inventory": [
                {
                    "source": "core/a.md",
                    "target": "core/a.md",
                    "entry_status": "ACCEPTED",
                    "source_digest": _sha(self.a),
                    "target_digest": _sha(self.a),
                    "byte_count": len(self.a),
                    "reason": "MANIFEST_GENERATED",
                    "detail": "ok",
                }
            ],
            "outcome": "PASS",
            "reason": "MANIFEST_GENERATED",
            "generated_at": "2026-07-22T00:00:00Z",
        }
        self.manifest_path = self.pkg / ".package-export-manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def manifest_file(self):
        return self.manifest_path

    def stub_verifier_ok(self):
        """Replace the wrapped verifier call with an in-memory ok result."""
        import smoke_verification as sv

        sv.run_wrapped_smoke_verifier = lambda **kw: {
            "ok": True,
            "project_id": "gwc",
            "package_version": "0.1.0",
            "entries": 1,
            "copied_entries": 1,
        }


class TestCleanSuccess(SmokeTestBase):
    def test_clean_success_passes(self):
        self.stub_verifier_ok()
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
            checkpoint_dir=self.tmp / "cp",
        )
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertEqual(r.reason, SMOKE_VERIFICATION_PASS)
        self.assertTrue(r.result_digest.startswith("sha256:"))

    def test_authority_never_granted(self):
        self.stub_verifier_ok()
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertFalse(r.authority_granted)


class TestRequiredTargetMissing(SmokeTestBase):
    def test_missing_required_target_fails(self):
        self.stub_verifier_ok()
        (self.pkg / ".governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md").unlink()
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_REQUIRED_TARGET_MISSING)


class TestCorruptTarget(SmokeTestBase):
    def test_corrupt_target_fails(self):
        # Tamper the target so manifest binding (SCRUM-235 primitive) detects it.
        self.stub_verifier_ok()
        (self.pkg / "core" / "a.md").write_bytes(b"CORRUPTED\n")
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_HASH_MISMATCH)


class TestMissingManifest(SmokeTestBase):
    def test_missing_manifest_fails(self):
        self.stub_verifier_ok()
        self.manifest_path.unlink()
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_MANIFEST_INVALID)


class TestMalformedManifest(SmokeTestBase):
    def test_malformed_manifest_fails(self):
        self.stub_verifier_ok()
        self.manifest_path.write_text("{not valid json")
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_MANIFEST_INVALID)


class TestCleanDirectoryViolation(SmokeTestBase):
    def test_clean_directory_violation_fails(self):
        self.stub_verifier_ok()
        (self.pkg / ".git").mkdir()  # repo-coupled marker => unsafe
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_ENVIRONMENT_UNSAFE)


class TestExtractionMaterializationFailure(SmokeTestBase):
    def test_extraction_failure_fails(self):
        import smoke_verification as sv

        def boom(**kw):
            raise RuntimeError("extraction failed")

        sv.run_wrapped_smoke_verifier = boom
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_RESULT_UNKNOWN)


class TestTimeout(SmokeTestBase):
    def test_timeout_fails(self):
        import smoke_verification as sv
        import subprocess

        def hang(**kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)

        sv.run_wrapped_smoke_verifier = hang
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_TIMEOUT)


class TestInterruptedReconciliation(SmokeTestBase):
    def test_interrupted_routes_to_checkpoint_reconciliation(self):
        # Write an interrupted checkpoint whose identity MATCHES the live
        # package; the run must reconcile (readback) rather than blindly rerun.
        self.stub_verifier_ok()
        cp_dir = self.tmp / "cp"
        import smoke_verification as sv
        from smoke_verification import (
            write_checkpoint,
            canonical_manifest_digest,
            compute_output_tree_digest,
        )

        live_identity, _ = sv._bind_package_identity(
            manifest=self.manifest, output_root=self.pkg, source_root=self.repo
        )
        write_checkpoint(
            cp_dir / "smoke-smoke-1.json",
            idempotency_key="smoke-1",
            package_identity=live_identity,
        )
        # Flip the checkpoint to interrupted to prove readback reconciliation.
        cp = cp_dir / "smoke-smoke-1.json"
        data = json.loads(cp.read_text())
        data["interrupted"] = True
        cp.write_text(json.dumps(data))
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
            checkpoint_dir=cp_dir,
        )
        self.assertEqual(r.outcome, Outcome.PASS)
        self.assertTrue(r.checkpoint.get("committed_before_execution"))


class TestIdenticalReplay(SmokeTestBase):
    def test_identical_replay_stable(self):
        self.stub_verifier_ok()
        r1 = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
            checkpoint_dir=self.tmp / "cp",
        )
        r2 = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
            checkpoint_dir=self.tmp / "cp",
            existing_result=r1.to_dict(),
        )
        self.assertEqual(r2.reason, SMOKE_IDEMPOTENT_REPLAY)
        self.assertEqual(r1.result_digest, r2.result_digest)


class TestConflictingReplay(SmokeTestBase):
    def test_conflicting_replay_fails(self):
        self.stub_verifier_ok()
        cp_dir = self.tmp / "cp"
        from smoke_verification import write_checkpoint

        write_checkpoint(
            cp_dir / "smoke-smoke-1.json",
            idempotency_key="smoke-1",
            package_identity={
                "source_sha": "OTHERSHA0000000000000000000000000000000000",
                "manifest_digest": "sha256:" + "a" * 64,
                "output_tree_digest": "sha256:" + "b" * 64,
                "project_id": "gwc",
                "package_version": "0.1.0",
                "source_ref": "main",
            },
        )
        r = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="main",
            source_base_sha="deadbeef",
            idempotency_key="smoke-1",
            task_id="SCRUM-236",
            checkpoint_dir=cp_dir,
        )
        self.assertEqual(r.outcome, Outcome.FAIL)
        self.assertEqual(r.reason, SMOKE_REPLAY_CONFLICT)


if __name__ == "__main__":
    unittest.main()
