from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "runtime"


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate(name: str, payload: dict) -> list:
    return list(Draft202012Validator(load(name), format_checker=FormatChecker()).iter_errors(payload))


BASE_REPOSITORY = {
    "full_name": "nhatnguyenquang1838-coder/gwc",
    "base_branch": "main",
    "base_sha": "76644885f4b25cb49a2a34bfea0e2ede941caa01",
    "working_branch": "codex/scrum-105-durable-runtime-contracts-20260726",
    "head_sha": None,
}


class DurableRuntimeContractTests(unittest.TestCase):
    def test_run_event_and_checkpoint_positive_fixtures(self) -> None:
        run = {
            "schema_version": "0.1",
            "artifact_type": "durable-run",
            "run_id": "run_scrum105_demo",
            "task_id": "SCRUM-105",
            "repository": BASE_REPOSITORY,
            "gate": "G2_EXECUTION",
            "runtime_version": "0.1",
            "node_pack_version": "0.1",
            "status": "active",
            "current_checkpoint_id": "chk_scrum105_1",
            "created_at_utc": "2026-07-26T12:00:00Z",
            "updated_at_utc": "2026-07-26T12:01:00Z",
        }
        event = {
            "schema_version": "0.1",
            "artifact_type": "durable-event",
            "event_id": "evt_scrum105_1",
            "run_id": "run_scrum105_demo",
            "sequence": 1,
            "parent_event_id": None,
            "event_type": "node_started",
            "occurred_at_utc": "2026-07-26T12:00:01Z",
            "actor": {"kind": "chatgpt", "id": "codex-local-agent", "execution_mode": "local_agent"},
            "gate": "G2_EXECUTION",
            "node_id": "runtime.contract.validate",
            "outcome": "pending",
            "runtime_version": "0.1",
            "node_version": "0.1",
            "checkpoint_revision": 1,
            "idempotency_key": "run_scrum105_demo:1",
            "evidence_refs": [".gwc/tasks/SCRUM-105/g2/execution-envelope.yaml"],
            "payload": {"purpose": "contract validation"},
        }
        checkpoint = {
            "schema_version": "0.1",
            "artifact_type": "durable-checkpoint",
            "checkpoint_id": "chk_scrum105_1",
            "run_id": "run_scrum105_demo",
            "revision": 1,
            "cas": {"expected_revision": 0},
            "lease": {"owner": "codex-local-agent", "expires_at_utc": "2026-07-26T12:10:00Z", "fencing_token": 1},
            "current_node_id": "runtime.contract.validate",
            "current_node_version": "0.1",
            "next_node_id": "runtime.contract.report",
            "next_action": "run targeted contract tests",
            "gate": "G2_EXECUTION",
            "status": "running",
            "pending_action_ids": [],
            "suspend_reason": None,
            "scope_hash": "sha256:963ec355ad3940bb78edd9f7d08ad17a68813065b92b92babe5b1b0fce29ca38",
            "created_at_utc": "2026-07-26T12:00:00Z",
            "updated_at_utc": "2026-07-26T12:00:02Z",
        }
        self.assertEqual(validate("durable-run.schema.json", run), [])
        self.assertEqual(validate("durable-event.schema.json", event), [])
        self.assertEqual(validate("durable-checkpoint.schema.json", checkpoint), [])

    def test_pending_action_requires_readback_for_terminal_success(self) -> None:
        payload = {
            "schema_version": "0.1",
            "artifact_type": "pending-action",
            "action_id": "act_scrum105_1",
            "run_id": "run_scrum105_demo",
            "adapter_id": "jira.readback",
            "operation": "read_issue",
            "idempotency_key": "run_scrum105_demo:read_issue:1",
            "status": "succeeded",
            "attempt_count": 1,
            "readback_required": True,
            "readback_status": "confirmed",
            "external_reference": "SCRUM-105",
            "readback_evidence_refs": ["jira:SCRUM-105:comment-10197"],
            "last_error": None,
            "requested_at_utc": "2026-07-26T12:00:00Z",
            "updated_at_utc": "2026-07-26T12:01:00Z",
        }
        self.assertEqual(validate("pending-action.schema.json", payload), [])
        payload["readback_status"] = "pending"
        self.assertTrue(validate("pending-action.schema.json", payload))

    def test_side_effect_adapter_requires_readback_capability(self) -> None:
        payload = {
            "schema_version": "0.1",
            "artifact_type": "adapter-contract",
            "adapter_id": "bounded.write",
            "adapter_version": "0.1",
            "capabilities": {"side_effects": True, "idempotency": True, "readback": True},
            "request": {
                "run_id": "run_scrum105_demo",
                "checkpoint_id": "chk_scrum105_1",
                "checkpoint_revision": 1,
                "fencing_token": 1,
                "node_id": "runtime.contract.validate",
                "node_version": "0.1",
                "gate": "G2_EXECUTION",
                "idempotency_key": "run_scrum105_demo:write:1",
                "payload": {},
            },
            "result": {
                "outcome": "success",
                "adapter_version": "0.1",
                "readback_status": "confirmed",
                "evidence_refs": ["readback:bounded.write:1"],
                "error_code": None,
            },
        }
        self.assertEqual(validate("adapter-contract.schema.json", payload), [])
        payload["capabilities"]["readback"] = False
        self.assertTrue(validate("adapter-contract.schema.json", payload))

    def test_storage_migration_is_not_production_authority(self) -> None:
        payload = {
            "schema_version": "0.1",
            "artifact_type": "storage-migration",
            "contract_version": "0.1",
            "source_backend": "sqlite_pilot",
            "target_backend": "postgresql",
            "provider_neutral_operations": ["append_event", "read_checkpoint", "cas_checkpoint", "record_readback"],
            "phases": [
                {"id": "contract_freeze", "purpose": "freeze logical contract", "verification_required": True, "rollback_evidence": "versioned contract"},
                {"id": "compatibility_probe", "purpose": "compare provider constraints", "verification_required": True, "rollback_evidence": "probe report"},
                {"id": "backfill_verify", "purpose": "verify any approved backfill", "verification_required": True, "rollback_evidence": "checkpointed backfill evidence"},
                {"id": "cutover_readback", "purpose": "verify cutover readback", "verification_required": True, "rollback_evidence": "source retained during rollback window"},
            ],
            "rollback_required": True,
            "production_authorized": False,
            "cutover": {"requires_exact_readback": True, "requires_human_gate": True, "data_loss_tolerance": "zero"},
        }
        self.assertEqual(validate("storage-migration.schema.json", payload), [])
        payload["production_authorized"] = True
        self.assertTrue(validate("storage-migration.schema.json", payload))


if __name__ == "__main__":
    unittest.main()
