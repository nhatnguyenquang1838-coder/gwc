from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.validate_gate_action import canonical_scope_hash, validate

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
DRIFTED_HEAD_SHA = "c" * 40
G4_APPROVAL_ID = "G4-SCRUM-271-PR271-20260807T0300Z"
G4_SCOPE_PREFIX = "0123456789abcdef"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


def packet() -> dict:
    value = {
        "schema_version": "1.0",
        "artifact_type": "gate-action-authority",
        "task_id": "SCRUM-271",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_ref": "main",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "working_branch": "chatgpt/scrum-271-autonomous-preprod-runtime-r1-20260807",
        "gate": "G2_EXECUTION",
        "action": "modify_approved_files",
        "scope": {
            "authorized_paths": ["tools/validate_gate_action.py"],
            "authorized_actions": ["modify_approved_files", "run_sandboxed_validation"],
            "excluded_actions": ["merge", "deploy"],
            "risk_class": "R3",
        },
        "issued_at": "2026-08-06T19:44:00Z",
        "expires_at": "2026-08-07T19:44:00Z",
        "actor": {"kind": "connector", "id": "chatgpt"},
    }
    value["evidence_readback"] = {
        "status": "confirmed",
        "observed_at": "2026-08-06T20:00:00Z",
        "task_id": value["task_id"],
        "repository": value["repository"],
        "base_sha": value["base_sha"],
        "head_sha": value["head_sha"],
        "gate": value["gate"],
        "action": value["action"],
        "scope_hash": "sha256:" + "0" * 64,
        "event_id_or_idempotency_key": "evt-scrum-271-1",
    }
    value["scope_hash"] = canonical_scope_hash(value)
    value["evidence_readback"]["scope_hash"] = value["scope_hash"]
    return value


def g4_authority_receipt(*, head_sha: str = HEAD_SHA, status: str = "present", expires_at: str = "2026-08-07T19:44:00Z") -> dict:
    return {
        "status": status,
        "source": "github_actions_bot_comment",
        "bot_login": "github-actions[bot]",
        "marker": "gwc:g4-authority-receipt",
        "approval_id": G4_APPROVAL_ID,
        "pr_number": 271,
        "receipt_comment_id": 271001,
        "source_comment_id": 271000,
        "approved_head_sha": head_sha,
        "scope_hash_prefix": G4_SCOPE_PREFIX,
        "expires_at": expires_at,
    }


def g4_pr_evidence_receipt(
    *,
    head_sha: str = HEAD_SHA,
    status: str = "present",
    pr_body_digest: str = DIGEST_A,
    graph_digest: str = DIGEST_C,
    task_id: str = "SCRUM-271",
    expires_at: str = "2026-08-07T19:44:00Z",
) -> dict:
    return {
        "status": status,
        "source": "github_actions_bot_comment",
        "bot_login": "github-actions[bot]",
        "marker": "gwc:g4-pr-evidence-receipt",
        "approval_id": G4_APPROVAL_ID,
        "pr_number": 271,
        "receipt_comment_id": 271101,
        "source_comment_id": 271000,
        "approved_head_sha": head_sha,
        "scope_hash_prefix": G4_SCOPE_PREFIX,
        "expires_at": expires_at,
        "run_id": "run-scrum-271-fixture-1",
        "task_id": task_id,
        "pr_body_digest": pr_body_digest,
        "managed_block_digest": DIGEST_B,
        "run_graph_digest": graph_digest,
        "gate_story_digest": DIGEST_D,
        "evidence_digest": DIGEST_E,
    }


def g4_merge_packet(*, include_authority: bool = True, include_evidence: bool = True, evidence: dict | None = None) -> dict:
    value = packet()
    value["gate"] = "G4_MERGE"
    value["action"] = "merge_approved_pr"
    value["scope"] = {
        "authorized_paths": ["tools/validate_gate_action.py"],
        "authorized_actions": ["merge_approved_pr"],
        "excluded_actions": ["deploy", "release", "production_data_write"],
        "risk_class": "R3",
    }
    value["evidence_readback"].update(
        {
            "gate": value["gate"],
            "action": value["action"],
            "event_id_or_idempotency_key": "evt-scrum-271-g4-1",
        }
    )
    if include_authority:
        value["evidence_readback"]["g4_authority_receipt"] = g4_authority_receipt()
    if include_evidence:
        value["evidence_readback"]["g4_pr_evidence_receipt"] = evidence or g4_pr_evidence_receipt()
    value["scope_hash"] = canonical_scope_hash(value)
    value["evidence_readback"]["scope_hash"] = value["scope_hash"]
    return value


class GateActionAuthorityTests(unittest.TestCase):
    def test_valid_g2_packet_passes(self):
        errors = validate(
            packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_base_sha=BASE_SHA,
            expected_head_sha=HEAD_SHA,
        )
        self.assertEqual([], errors)

    def test_scope_tampering_fails_closed(self):
        value = packet()
        value["scope"]["authorized_paths"].append("core/unsafe.md")
        errors = validate(value, schema_path=ROOT / "schemas/gate-action-authority.schema.json")
        self.assertTrue(any("scope_hash" in error for error in errors))

    def test_gate_action_mapping_rejects_merge_at_g2(self):
        value = packet()
        value["action"] = "merge_approved_pr"
        value["scope"]["authorized_actions"].append("merge_approved_pr")
        value["scope_hash"] = canonical_scope_hash(value)
        value["evidence_readback"]["action"] = value["action"]
        value["evidence_readback"]["scope_hash"] = value["scope_hash"]
        errors = validate(value, schema_path=ROOT / "schemas/gate-action-authority.schema.json")
        self.assertTrue(any("not valid for G2_EXECUTION" in error for error in errors))

    def test_g4_merge_passes_only_with_both_current_receipts(self):
        errors = validate(
            g4_merge_packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
            expected_g4_approval_id=G4_APPROVAL_ID,
            expected_g4_scope_prefix=G4_SCOPE_PREFIX,
            expected_pr_body_digest=DIGEST_A,
            expected_managed_block_digest=DIGEST_B,
            expected_run_graph_digest=DIGEST_C,
            expected_gate_story_digest=DIGEST_D,
            expected_evidence_digest=DIGEST_E,
        )
        self.assertEqual([], errors)

    def test_g4_merge_requires_existing_authority_receipt(self):
        errors = validate(
            g4_merge_packet(include_authority=False),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
        )
        self.assertTrue(any("g4_authority_receipt" in error for error in errors))

    def test_g4_merge_requires_pr_evidence_receipt(self):
        errors = validate(
            g4_merge_packet(include_evidence=False),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
        )
        self.assertTrue(any("g4_pr_evidence_receipt" in error for error in errors))

    def test_g4_merge_rejects_stale_pr_body_digest(self):
        errors = validate(
            g4_merge_packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
            expected_pr_body_digest="sha256:" + "f" * 64,
        )
        self.assertTrue(any("pr_body_digest" in error for error in errors))

    def test_g4_merge_rejects_graph_drift(self):
        errors = validate(
            g4_merge_packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
            expected_run_graph_digest="sha256:" + "f" * 64,
        )
        self.assertTrue(any("run_graph_digest" in error for error in errors))

    def test_g4_merge_rejects_head_drift_in_evidence_receipt(self):
        errors = validate(
            g4_merge_packet(evidence=g4_pr_evidence_receipt(head_sha=DRIFTED_HEAD_SHA)),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
        )
        self.assertTrue(any("G4_PR_EVIDENCE_RECEIPT_MISSING_OR_STALE" in error for error in errors))

    def test_g4_merge_rejects_task_mismatch(self):
        errors = validate(
            g4_merge_packet(evidence=g4_pr_evidence_receipt(task_id="SCRUM-999")),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="open",
        )
        self.assertTrue(any("task_id does not match" in error for error in errors))

    def test_g4_merge_rejects_closed_pr(self):
        errors = validate(
            g4_merge_packet(),
            schema_path=ROOT / "schemas/gate-action-authority.schema.json",
            now=datetime(2026, 8, 6, 21, 0, tzinfo=timezone.utc),
            expected_head_sha=HEAD_SHA,
            observed_pr_state="closed",
        )
        self.assertTrue(any("observed PR state 'open'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
