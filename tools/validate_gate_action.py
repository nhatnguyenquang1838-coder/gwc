#!/usr/bin/env python3
"""Validate task-scoped gate action authority packets.

This is a data-only, fail-closed validator. It does not call Jira, GitHub, or a
deployment system and never grants authority.

For G4 merge actions, the packet must include a trusted PR-native
``gwc:g4-authority-receipt`` readback from a ``github-actions[bot]`` PR comment
bound to the current PR head. Chat-only G4 approval is not merge-ready evidence
until that bot receipt exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
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

G4_MERGE_GATE = "G4_MERGE"
G4_MERGE_ACTION = "merge_approved_pr"
OPEN_PR_STATE = "open"
G4_RECEIPT_MARKER = "gwc:g4-authority-receipt"
GITHUB_ACTIONS_BOT = "github-actions[bot]"
GITHUB_ACTIONS_BOT_COMMENT = "github_actions_bot_comment"
G4_RECEIPT_FAILURE = "G4_AUTHORITY_RECEIPT_MISSING_OR_STALE"


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


def _g4_receipt_errors(
    packet: dict[str, Any],
    *,
    now: datetime,
    expected_head_sha: str | None,
    expected_g4_approval_id: str | None,
    expected_g4_scope_prefix: str | None,
) -> list[str]:
    receipt = packet.get("evidence_readback", {}).get("g4_authority_receipt")
    if not isinstance(receipt, dict):
        return [f"{G4_RECEIPT_FAILURE}: G4 merge requires trusted PR-native G4 authority receipt"]

    errors: list[str] = []
    if receipt.get("status") != "present":
        errors.append(f"{G4_RECEIPT_FAILURE}: receipt status must be 'present'")
    if receipt.get("source") != GITHUB_ACTIONS_BOT_COMMENT:
        errors.append("G4 authority receipt must come from a GitHub Actions bot comment")
    if receipt.get("bot_login") != GITHUB_ACTIONS_BOT:
        errors.append("G4 authority receipt must be authored by github-actions[bot]")
    if receipt.get("marker") != G4_RECEIPT_MARKER:
        errors.append("G4 authority receipt marker is missing or not trusted")

    approved_head = receipt.get("approved_head_sha")
    if approved_head != packet.get("head_sha"):
        errors.append(f"{G4_RECEIPT_FAILURE}: authority receipt head does not match packet head SHA")
    if expected_head_sha and approved_head != expected_head_sha:
        errors.append(f"{G4_RECEIPT_FAILURE}: authority receipt head does not match current PR head SHA")
    if expected_g4_approval_id and receipt.get("approval_id") != expected_g4_approval_id:
        errors.append("G4 authority receipt approval_id does not match expected G4 approval ID")
    if expected_g4_scope_prefix and receipt.get("scope_hash_prefix") != expected_g4_scope_prefix:
        errors.append("G4 authority receipt scope hash prefix does not match expected scope prefix")

    try:
        if parse_utc(receipt["expires_at"], "evidence_readback.g4_authority_receipt.expires_at") <= now:
            errors.append(f"{G4_RECEIPT_FAILURE}: authority receipt is expired")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))

    for field in ("pr_number", "receipt_comment_id", "source_comment_id"):
        value = receipt.get(field)
        if not isinstance(value, int) or value < 1:
            errors.append(f"G4 authority receipt {field} must be a positive integer")
    return errors


def semantic_errors(
    packet: dict[str, Any],
    *,
    now: datetime | None = None,
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    expected_scope_hash: str | None = None,
    observed_pr_state: str | None = None,
    expected_g4_approval_id: str | None = None,
    expected_g4_scope_prefix: str | None = None,
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
    if action not in scope.get("authorized_actions", []):
        errors.append("action is not present in scope.authorized_actions")
    if action in scope.get("excluded_actions", []):
        errors.append("action is present in scope.excluded_actions")
    if gate in GATE_MINIMUM_ACTIONS and action not in GATE_MINIMUM_ACTIONS[gate]:
        errors.append(f"action {action!r} is not valid for {gate}")

    if gate == G4_MERGE_GATE and action == G4_MERGE_ACTION:
        if expected_head_sha is None:
            errors.append("G4 merge requires expected current PR head SHA")
        if observed_pr_state is None:
            errors.append("G4 merge requires observed PR state before merge")
        elif observed_pr_state != OPEN_PR_STATE:
            errors.append("G4 merge requires observed PR state 'open' before merge")
        errors.extend(
            _g4_receipt_errors(
                packet,
                now=now,
                expected_head_sha=expected_head_sha,
                expected_g4_approval_id=expected_g4_approval_id,
                expected_g4_scope_prefix=expected_g4_scope_prefix,
            )
        )

    readback = packet.get("evidence_readback", {})
    for field in ("task_id", "repository", "base_sha", "head_sha", "gate", "action", "scope_hash"):
        if readback.get(field) != packet.get(field):
            errors.append(f"evidence_readback.{field} does not match packet.{field}")
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
    observed_pr_state: str | None = None,
    expected_g4_approval_id: str | None = None,
    expected_g4_scope_prefix: str | None = None,
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
                observed_pr_state=observed_pr_state,
                expected_g4_approval_id=expected_g4_approval_id,
                expected_g4_scope_prefix=expected_g4_scope_prefix,
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
    parser.add_argument("--expected-g4-approval-id")
    parser.add_argument("--expected-g4-scope-prefix")
    parser.add_argument("--observed-pr-state", choices=["open", "closed", "merged"])
    args = parser.parse_args(argv)

    try:
        packet = load(args.packet)
        if not isinstance(packet, dict):
            raise ValueError("packet must be an object")
        errors = validate(
            packet,
            schema_path=args.root / "schemas/gate-action-authority.schema.json",
            now=parse_utc(args.now, "now") if args.now else None,
            expected_base_sha=args.expected_base_sha,
            expected_head_sha=args.expected_head_sha,
            expected_scope_hash=args.expected_scope_hash,
            observed_pr_state=args.observed_pr_state,
            expected_g4_approval_id=args.expected_g4_approval_id,
            expected_g4_scope_prefix=args.expected_g4_scope_prefix,
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
