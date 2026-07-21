import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_module = load_module("tools/node_architect/validate_checkpoint_resume.py")
cleanup_module = load_module("tools/node_architect/cleanup_stale_sessions.py")


def utc(hours_from_now: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours_from_now)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def valid_checkpoint():
    return {
        "schema_version": "0.1",
        "checkpoint_id": "chk_revamp_003",
        "created_at_utc": utc(-1),
        "task": {"id": "REVAMP-GWC-003", "title": "checkpoint resume", "risk_class": "R2"},
        "repository": {
            "full_name": "nhatnguyenquang1838-coder/gwc",
            "base_branch": "main",
            "base_sha": "a" * 40,
            "working_branch": "codex/revamp-checkpoint-resume-20260722",
        },
        "gate": {"current": "G2_EXECUTION", "status": "READY", "source": "gwc_gate_evidence"},
        "execution_mode": "chat_connector_only",
        "scope": {
            "files_read": ["AGENTS.md"],
            "files_write": ["schemas/node-architect/checkpoint.schema.json"],
            "authorized_actions": ["create_guarded_branch", "modify_scoped_files"],
            "excluded_actions": ["merge", "deploy", "production_data"],
        },
        "git_delivery": {"branch": None, "pr_number": None, "head_sha": None, "ci_status": "not_started"},
        "validation": {"performed": ["schema parse"], "skipped": [], "evidence": ["local"]},
        "next_action": {"gate": "G2_EXECUTION", "action": "create branch", "requires_human_approval": True, "approval_command": None},
        "audit_projection": {"source_of_truth": False, "links": []},
    }


def valid_resume_token():
    return {
        "schema_version": "0.1",
        "resume_token_id": "resume_revamp_003",
        "checkpoint_id": "chk_revamp_003",
        "issued_at_utc": utc(-1),
        "expires_at_utc": utc(24),
        "next_gate": "G2_EXECUTION",
        "next_action": "create branch",
        "requires_human_approval": True,
        "approval_command": "APPROVE G2 FL-G2-REVAMP-20260722-003 53be1dd0b3acc395 2026-07-23T00:00:00Z",
        "audit_projection": {"source_of_truth": False, "links": []},
    }


class CheckpointResumeTests(unittest.TestCase):
    def test_valid_checkpoint_and_resume_token_pass(self):
        checkpoint = valid_checkpoint()
        resume = valid_resume_token()
        self.assertEqual([], validate_module.validate_checkpoint(checkpoint))
        self.assertEqual([], validate_module.validate_resume_token(resume, checkpoint))

    def test_resume_token_requires_matching_checkpoint(self):
        checkpoint = valid_checkpoint()
        resume = valid_resume_token()
        resume["checkpoint_id"] = "other"
        errors = validate_module.validate_resume_token(resume, checkpoint)
        self.assertTrue(any("does not match checkpoint" in error for error in errors))

    def test_external_projection_cannot_be_source_of_truth(self):
        checkpoint = valid_checkpoint()
        checkpoint["audit_projection"]["source_of_truth"] = True
        errors = validate_module.validate_checkpoint(checkpoint)
        self.assertTrue(any("source_of_truth" in error for error in errors))

    def test_cli_outputs_fail_for_bad_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            checkpoint_path = tmp_path / "checkpoint.json"
            resume_path = tmp_path / "resume-token.json"
            checkpoint_path.write_text(json.dumps(valid_checkpoint()), encoding="utf-8")
            resume = valid_resume_token()
            resume["approval_command"] = "approve"
            resume_path.write_text(json.dumps(resume), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/node_architect/validate_checkpoint_resume.py"), "--checkpoint", str(checkpoint_path), "--resume-token", str(resume_path)],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn('"status":"FAIL"', result.stdout)


class StaleSessionCleanupTests(unittest.TestCase):
    def test_cleanup_dry_run_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "stale-session"
            stale.mkdir()
            (stale / ".gwc-session.json").write_text(
                json.dumps({
                    "session_id": "old",
                    "last_used_at_utc": utc(-72),
                    "preserve": False,
                    "referenced_by_checkpoint": False,
                    "status": "completed",
                }),
                encoding="utf-8",
            )
            candidates = cleanup_module.scan(root, stale_after_hours=24, now=datetime.now(timezone.utc))
            self.assertEqual(1, len(candidates))
            self.assertTrue(stale.exists())

    def test_cleanup_execute_deletes_only_unprotected_stale_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "stale-session"
            stale.mkdir()
            (stale / ".gwc-session.json").write_text(
                json.dumps({
                    "session_id": "old",
                    "last_used_at_utc": utc(-72),
                    "preserve": False,
                    "referenced_by_checkpoint": False,
                    "status": "completed",
                }),
                encoding="utf-8",
            )
            protected = root / "blocked-session"
            protected.mkdir()
            (protected / "checkpoint.json").write_text("{}", encoding="utf-8")

            candidates = cleanup_module.scan(root, stale_after_hours=24, now=datetime.now(timezone.utc))
            removed = cleanup_module.remove_candidates(candidates)

            self.assertEqual([str(stale)], removed)
            self.assertFalse(stale.exists())
            self.assertTrue(protected.exists())


if __name__ == "__main__":
    unittest.main()
