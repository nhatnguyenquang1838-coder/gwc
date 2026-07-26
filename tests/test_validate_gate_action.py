from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.validate_gate_action import canonical_scope_hash, validate


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def packet() -> dict:
    value = {
        "schema_version": "1.0",
        "artifact_type": "gate-action-authority",
        "task_id": "SCRUM-103",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "working_branch": "codex/scrum-103-lifecycle-authority",
        "gate": "G2_EXECUTION",
        "action": "modify_approved_files",
        "scope": {
            "authorized_paths": ["tools/validate_gate_action.py"],
            "authorized_actions": ["modify_approved_files", "run_sandboxed_validation"],
            "excluded_actions": ["merge", "deploy"],
            "risk_class": "R2",
        },
        "issued_at": "2026-07-26T05:56:22Z",
        "expires_at": "2026-07-27T05:56:22Z",
        "actor": {"kind": "local_agent", "id": "codex"},
    }
    value["evidence_readback"] = {
        "status": "confirmed",
        "observed_at": "2026-07-26T06:00:00Z",
        "task_id": value["task_id"],
        "repository": value["repository"],
        "base_sha": value["base_sha"],
        "head_sha": value["head_sha"],
        "gate": value["gate"],
        "action": value["action"],
        "scope_hash": "sha256:" + "0" * 64,
        "event_id_or_idempotency_key": "evt-scrum-103-1",
    }
    value["scope_hash"] = canonical_scope_hash(value)
    value["evidence_readback"]["scope_hash"] = value["scope_hash"]
    return value


class GateActionAuthorityTests(unittest.TestCase):
    def test_valid_packet_passes(self):
        errors = validate(
            packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc),
            expected_base_sha=BASE_SHA,
            expected_head_sha=HEAD_SHA,
        )
        self.assertEqual([], errors)

    def test_scope_tampering_fails_closed(self):
        value = packet()
        value["scope"]["authorized_paths"].append("core/unsafe.md")
        errors = validate(value, schema_path=ROOT / "schemas/gate-action-authority.schema.json")
        self.assertTrue(any("scope_hash" in error for error in errors))

    def test_expiry_fails_closed(self):
        errors = validate(
            packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 7, 28, tzinfo=timezone.utc),
        )
        self.assertTrue(any("expired" in error for error in errors))

    def test_readback_identity_mismatch_fails_closed(self):
        value = copy.deepcopy(packet())
        value["evidence_readback"]["head_sha"] = BASE_SHA
        errors = validate(value, schema_path=ROOT / "schemas/gate-action-authority.schema.json")
        self.assertTrue(any("head_sha" in error for error in errors))

    def test_gate_action_mapping_rejects_merge_at_g2(self):
        value = packet()
        value["action"] = "merge_approved_pr"
        value["scope"]["authorized_actions"].append("merge_approved_pr")
        value["scope_hash"] = canonical_scope_hash(value)
        value["evidence_readback"]["action"] = value["action"]
        value["evidence_readback"]["scope_hash"] = value["scope_hash"]
        errors = validate(value, schema_path=ROOT / "schemas/gate-action-authority.schema.json")
        self.assertTrue(any("not valid for G2_EXECUTION" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
