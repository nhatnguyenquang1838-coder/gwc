import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "tools" / "node_architect" / "validate_ds_admin_tc_sync.py"
RENDERER = REPO_ROOT / "tools" / "node_architect" / "render_ds_admin_tc_projection.py"


def base_packet():
    return {
        "schema_version": "0.1",
        "protocol_id": "DS_ADMIN_TC_SYNC_PROTOCOL",
        "task_id": "REVAMP-GWC-004",
        "checkpoint_id": "chk_revamp_004",
        "source_of_truth": "canonical_checkpoint",
        "repository": {
            "full_name": "nhatnguyenquang1838-coder/gwc",
            "base_branch": "main",
            "base_sha": "64ac09400b88af8ec68c3e10a695dabae5dc11ba",
        },
        "gate": {
            "current": "G3_PR",
            "status": "PASS",
            "blocking_sync_declared": False,
        },
        "git_delivery": {
            "branch": "codex/revamp-ds-admin-tc-sync-20260722",
            "pr_number": 56,
            "head_sha": "abc123",
            "ci_status": "success",
        },
        "authority": {
            "external_system_authority": False,
            "requires_g4_for_merge": True,
        },
        "targets": [
            {"target_type": "ds_admin", "enabled": True, "blocking": False, "status": "SYNC_PENDING"},
            {"target_type": "tc", "enabled": True, "blocking": False, "status": "SYNC_PENDING"},
        ],
    }


def run_validator(packet):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), str(path)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed, json.loads(completed.stdout)


class DsAdminTcSyncProtocolTest(unittest.TestCase):
    def test_valid_packet_passes(self):
        completed, result = run_validator(base_packet())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])

    def test_external_projection_cannot_be_source_of_truth(self):
        packet = base_packet()
        packet["source_of_truth"] = "external_projection"
        completed, result = run_validator(packet)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(result["ok"])
        self.assertIn("source_of_truth must be canonical_checkpoint", result["errors"])

    def test_ds_admin_cannot_have_gate_authority(self):
        packet = base_packet()
        packet["authority"]["external_system_authority"] = True
        completed, result = run_validator(packet)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("authority.external_system_authority must be false", result["errors"])

    def test_blocking_target_requires_gate_declaration(self):
        packet = base_packet()
        packet["targets"][0]["blocking"] = True
        completed, result = run_validator(packet)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("targets[0].blocking requires gate.blocking_sync_declared=true", result["errors"])

    def test_blocking_target_allowed_when_declared(self):
        packet = base_packet()
        packet["gate"]["blocking_sync_declared"] = True
        packet["targets"][0]["blocking"] = True
        completed, result = run_validator(packet)
        self.assertEqual(completed.returncode, 0, result)
        self.assertTrue(result["ok"])

    def test_renderer_outputs_deterministic_authority_boundary(self):
        checkpoint = {
            "checkpoint_id": "chk_render",
            "task": {"id": "REVAMP-GWC-004"},
            "repository": {
                "full_name": "nhatnguyenquang1838-coder/gwc",
                "base_branch": "main",
                "base_sha": "64ac09400b88af8ec68c3e10a695dabae5dc11ba",
            },
            "gate": {"current": "G3_PR", "status": "PASS"},
            "git_delivery": {"head_sha": "abc123", "ci_status": "success"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_path = Path(tmp) / "checkpoint.json"
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(RENDERER), str(checkpoint_path)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        packet = json.loads(completed.stdout)
        self.assertEqual(packet["source_of_truth"], "canonical_checkpoint")
        self.assertFalse(packet["authority"]["external_system_authority"])
        self.assertEqual([target["target_type"] for target in packet["targets"]], ["ds_admin", "tc"])

    def test_rendered_packet_validates(self):
        checkpoint = {
            "checkpoint_id": "chk_render_validates",
            "task_id": "REVAMP-GWC-004",
            "repository": {
                "full_name": "nhatnguyenquang1838-coder/gwc",
                "base_branch": "main",
                "base_sha": "64ac09400b88af8ec68c3e10a695dabae5dc11ba",
            },
            "gate": {"current": "G3_PR", "status": "PASS"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_path = Path(tmp) / "checkpoint.json"
            packet_path = Path(tmp) / "packet.json"
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
            rendered = subprocess.run(
                [sys.executable, str(RENDERER), str(checkpoint_path), "--output", str(packet_path)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            validated = subprocess.run(
                [sys.executable, str(VALIDATOR), str(packet_path)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        self.assertTrue(json.loads(validated.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
