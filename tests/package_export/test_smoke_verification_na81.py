#!/usr/bin/env python3
"""NA81 tests for package_export.smoke-verification (SCRUM-359).

Verify the missing consumer-load failure path and replay/runtime bindings
required by the current NA81 brief but not asserted by the existing
SCRUM-236 test suite.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))  # noqa: E402

from smoke_verification import (  # noqa: E402
    SMOKE_IDEMPOTENT_REPLAY,
    SMOKE_LOAD_FAILED,
    SMOKE_REPLAY_CONFLICT,
    SMOKE_VERIFICATION_PASS,
    Outcome,
    compute_result_digest,
    verify_smoke,
    write_checkpoint,
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


class NA81SmokeTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gwc-smoke-na81-"))
        self.repo = self.tmp / "repo"
        self.pkg = self.tmp / "package"
        self.repo.mkdir()
        self.pkg.mkdir()
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "verify_package_export_smoke.py").write_text(
            "import sys\nprint('{\"ok\": true}')\nsys.exit(0)\n"
        )
        for rel in REQUIRED_TARGETS:
            t = self.pkg / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(b"content:" + rel.encode())
        self.a = b"alpha\n"
        (self.repo / "core").mkdir()
        (self.pkg / "core").mkdir()
        (self.repo / "core" / "a.md").write_bytes(self.a)
        (self.pkg / "core" / "a.md").write_bytes(self.a)
        self.manifest = {
            "schema_id": "gwc.package_export.export_manifest_generation",
            "schema_version": "0.1",
            "task_id": "SCRUM-359",
            "source_sha": "deadbeef",
            "project_id": "gwc",
            "package_version": "0.1.0",
            "source_ref": "pre-prod",
            "idempotency_key": "smoke-na81-base",
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
        import smoke_verification as sv
        sv.run_wrapped_smoke_verifier = lambda **kw: {
            "ok": True,
            "project_id": "gwc",
            "package_version": "0.1.0",
            "entries": 1,
            "copied_entries": 1,
        }

    def stub_verifier_fail(self):
        import smoke_verification as sv
        sv.run_wrapped_smoke_verifier = lambda **kw: {
            "ok": False,
            "error": "consumer import failed: malformed package structure",
        }


class TestNA81ConsumerLoad(NA81SmokeTestBase):
    def test_consumer_load_failure_returns_smoke_load_failed(self):
        self.stub_verifier_fail()
        result = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="pre-prod",
            source_base_sha="deadbeef",
            idempotency_key="smoke-na81-load-fail",
            task_id="SCRUM-359",
        )
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.reason, SMOKE_LOAD_FAILED)
        actions = {a.name: a.status for a in result.smoke_actions}
        self.assertEqual(actions.get("files_loadable"), "failed")
        d = result.to_dict()
        self.assertFalse(d["authority_granted"])
        self.assertEqual(d["task_id"], "SCRUM-359")

    def test_replay_conflict_under_same_idempotency_key(self):
        self.stub_verifier_ok()
        cp_dir = self.tmp / "cp"
        write_checkpoint(
            cp_dir / "smoke-smoke-359.json",
            idempotency_key="smoke-359",
            package_identity={
                "source_sha": "OTHERSHA0000000000000000000000000000000000",
                "manifest_digest": "sha256:" + "a" * 64,
                "output_tree_digest": "sha256:" + "b" * 64,
                "project_id": "gwc",
                "package_version": "0.1.0",
                "source_ref": "pre-prod",
            },
        )
        # Change package identity under same key => conflict
        (self.pkg / "core" / "a.md").write_bytes(b"changed\n")
        self.manifest["entry_inventory"][0]["target_digest"] = _sha(b"changed\n")
        self.manifest["entry_inventory"][0]["byte_count"] = len(b"changed\n")
        self.manifest_path.write_text(json.dumps(self.manifest))
        result = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="pre-prod",
            source_base_sha="deadbeef",
            idempotency_key="smoke-359",
            task_id="SCRUM-359",
            checkpoint_dir=cp_dir,
        )
        self.assertEqual(result.outcome, Outcome.FAIL)
        self.assertEqual(result.reason, SMOKE_REPLAY_CONFLICT)
        d = result.to_dict()
        self.assertFalse(d["authority_granted"])

    def test_result_digest_stable_excluding_observations(self):
        self.stub_verifier_ok()
        r1 = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="pre-prod",
            source_base_sha="deadbeef",
            idempotency_key="smoke-na81-digest",
            task_id="SCRUM-359",
            checkpoint_dir=self.tmp / "cp1",
        )
        r2 = verify_smoke(
            repo_root=self.repo,
            package_path=self.pkg,
            manifest_path=self.manifest_file(),
            source_ref="pre-prod",
            source_base_sha="deadbeef",
            idempotency_key="smoke-na81-digest",
            task_id="SCRUM-359",
            checkpoint_dir=self.tmp / "cp2",
        )
        # Identical inputs produce identical canonical digest even if
        # observational fields (run timestamps) differ.
        self.assertEqual(compute_result_digest(r1), compute_result_digest(r2))
        self.assertEqual(r1.outcome, Outcome.PASS)
        self.assertTrue(r1.result_digest)


if __name__ == "__main__":
    unittest.main()
