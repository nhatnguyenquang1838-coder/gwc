#!/usr/bin/env python3
"""Fail-closed validation for a task-scoped gate action packet.

The validator is deliberately local and data-only. It does not grant authority
and it does not call Jira, GitHub, or a deployment system. A packet is valid
only when its scope hash, expiry, actor, repository identity, and readback all
agree with the requested action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


GATE_MINIMUM_ACTIONS = {
    "G0_CONTEXT": {"read_repository", "inspect_connector", "inspect_task"},
    "G1_ALIGNMENT": {"materialize_g1_artifacts", "run_read_only_validation"},
    "G2_EXECUTION": {
        "create_guarded_branch_or_worktree",
        "modify_approved_files",
        "run_sandboxed_validation",
        "stage",
        "create_commit",
        "push_working_branch",
    },
    "G3_PR": {"open_or_update_draft_pr", "mark_pr_ready_for_review", "run_independent_review"},
    "G4_MERGE": {"merge_approved_pr"},
    "G5_DEPLOY": {"verify_post_merge_ci", "deploy_approved_release", "reload_approved_runtime"},
    "G6_PRODUCTION_DATA": {
        "production_data_read",
        "production_data_write",
        "production_config_change",
        "credential_rotation",
        "migration",
    },
}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle) if path.suffix.lower() == ".json" else yaml.safe_load(handle)


def parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def canonical_scope_hash(packet: dict[str, Any]) -> str:
    normalized = dict(packet)
    normalized.pop("scope_hash", None)
    readback = normalized.get("evidence_readback")
    if isinstance(readback, dict):
        readback = dict(readback)
        readback.pop("scope_hash", None)
        normalized["evidence_readback"] = readback
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_errors(packet: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(packet), key=lambda item: list(item.path))
    ]


def semantic_errors(
    packet: dict[str, Any],
    *,
    now: datetime | None = None,
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    expected_scope_hash: str | None = None,
) -> list[str]:
    errors: list[str] = []
    now = now or datetime.now(timezone.utc)
    try:
        issued = parse_utc(packet["issued_at"], "issued_at")
        expires = parse_utc(packet["expires_at"], "expires_at")
        observed = parse_utc(packet["evidence_readback"]["observed_at"], "evidence_readback.observed_at")
        if expires <= issued:
            errors.append("expires_at must be later than issued_at")
        if expires <= now:
            errors.append("approval/action packet is expired")
        if observed < issued:
            errors.append("evidence_readback.observed_at cannot precede issued_at")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))

    if packet.get("scope_hash") != canonical_scope_hash(packet):
        errors.append("scope_hash does not match the canonical packet")
    if expected_scope_hash and packet.get("scope_hash") != expected_scope_hash:
        errors.append("scope_hash does not match expected scope hash")
    if expected_base_sha and packet.get("base_sha") != expected_base_sha:
        errors.append("base_sha does not match expected base SHA")
    if expected_head_sha and packet.get("head_sha") != expected_head_sha:
        errors.append("head_sha does not match expected head SHA")

    scope = packet.get("scope", {})
    action = packet.get("action")
    gate = packet.get("gate")
    authorized = scope.get("authorized_actions", [])
    excluded = scope.get("excluded_actions", [])
    if action not in authorized:
        errors.append("action is not present in scope.authorized_actions")
    if action in excluded:
        errors.append("action is present in scope.excluded_actions")
    if gate in GATE_MINIMUM_ACTIONS and action not in GATE_MINIMUM_ACTIONS[gate]:
        errors.append(f"action {action!r} is not valid for {gate}")

    readback = packet.get("evidence_readback", {})
    comparisons = {
        "task_id": "task_id",
        "repository": "repository",
        "base_sha": "base_sha",
        "head_sha": "head_sha",
        "gate": "gate",
        "action": "action",
        "scope_hash": "scope_hash",
    }
    for field, readback_field in comparisons.items():
        if readback.get(readback_field) != packet.get(field):
            errors.append(f"evidence_readback.{readback_field} does not match packet.{field}")
    if not readback.get("event_id_or_idempotency_key"):
        errors.append("evidence_readback.event_id_or_idempotency_key is required")
    return errors


def validate(
    packet: dict[str, Any],
    *,
    schema_path: Path,
    now: datetime | None = None,
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    expected_scope_hash: str | None = None,
) -> list[str]:
    errors = schema_errors(packet, schema_path)
    if not errors:
        errors.extend(
            semantic_errors(
                packet,
                now=now,
                expected_base_sha=expected_base_sha,
                expected_head_sha=expected_head_sha,
                expected_scope_hash=expected_scope_hash,
            )
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--now", help="Override current UTC time for deterministic validation")
    parser.add_argument("--expected-base-sha")
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--expected-scope-hash")
    args = parser.parse_args(argv)
    try:
        packet = load(args.packet)
        if not isinstance(packet, dict):
            raise ValueError("packet must be an object")
        now = parse_utc(args.now, "now") if args.now else None
        errors = validate(
            packet,
            schema_path=args.root / "schemas/gate-action-authority.schema.json",
            now=now,
            expected_base_sha=args.expected_base_sha,
            expected_head_sha=args.expected_head_sha,
            expected_scope_hash=args.expected_scope_hash,
        )
    except (OSError, ValueError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        print("GATE ACTION AUTHORITY VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("GATE ACTION AUTHORITY VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
