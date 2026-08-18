#!/usr/bin/env python3
"""Validate task-scoped gate action authority packets.

This is a data-only, fail-closed validator. It does not call Jira, GitHub, or a
deployment system and never grants authority.

Every G4 merge requires a trusted PR-native ``gwc:g4-authority-receipt``.
Autonomous pre-prod merges additionally require a trusted
``gwc:g4-pr-evidence-receipt`` binding the current PR body, run graph, G0→G6
story, and managed-evidence digest to the current PR head. Legacy/normal G4
packets remain compatible unless autonomous evidence is explicitly expected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from tools.gate_effect_authority import evaluate_transitive_authority, validate_evidence_identity

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
G4_PR_EVIDENCE_MARKER = "gwc:g4-pr-evidence-receipt"
GITHUB_ACTIONS_BOT = "github-actions[bot]"
GITHUB_ACTIONS_BOT_COMMENT = "github_actions_bot_comment"
G4_RECEIPT_FAILURE = "G4_AUTHORITY_RECEIPT_MISSING_OR_STALE"
G4_PR_EVIDENCE_FAILURE = "G4_PR_EVIDENCE_RECEIPT_MISSING_OR_STALE"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


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


def _trusted_receipt_common_errors(
    receipt: dict[str, Any],
    *,
    marker: str,
    failure_code: str,
    packet: dict[str, Any],
    now: datetime,
    expected_head_sha: str | None,
    expected_g4_approval_id: str | None,
    expected_g4_scope_prefix: str | None,
) -> list[str]:
    errors: list[str] = []
    if receipt.get("status") != "present":
        errors.append(f"{failure_code}: receipt status must be 'present'")
    if receipt.get("source") != GITHUB_ACTIONS_BOT_COMMENT:
        errors.append(f"{failure_code}: receipt must come from a GitHub Actions bot comment")
    if receipt.get("bot_login") != GITHUB_ACTIONS_BOT:
        errors.append(f"{failure_code}: receipt must be authored by github-actions[bot]")
    if receipt.get("marker") != marker:
        errors.append(f"{failure_code}: trusted marker is missing or mismatched")
    approved_head = receipt.get("approved_head_sha")
    if approved_head != packet.get("head_sha"):
        errors.append(f"{failure_code}: receipt head does not match packet head SHA")
    if expected_head_sha and approved_head != expected_head_sha:
        errors.append(f"{failure_code}: receipt head does not match current PR head SHA")
    if expected_g4_approval_id and receipt.get("approval_id") != expected_g4_approval_id:
        errors.append(f"{failure_code}: approval_id does not match expected G4 approval ID")
    if expected_g4_scope_prefix and receipt.get("scope_hash_prefix") != expected_g4_scope_prefix:
        errors.append(f"{failure_code}: scope hash prefix does not match expected scope prefix")
    try:
        if parse_utc(receipt["expires_at"], f"{marker}.expires_at") <= now:
            errors.append(f"{failure_code}: receipt is expired")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    for field in ("pr_number", "receipt_comment_id", "source_comment_id"):
        value = receipt.get(field)
        if not isinstance(value, int) or value < 1:
            errors.append(f"{failure_code}: {field} must be a positive integer")
    return errors


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
    return _trusted_receipt_common_errors(
        receipt,
        marker=G4_RECEIPT_MARKER,
        failure_code=G4_RECEIPT_FAILURE,
        packet=packet,
        now=now,
        expected_head_sha=expected_head_sha,
        expected_g4_approval_id=expected_g4_approval_id,
        expected_g4_scope_prefix=expected_g4_scope_prefix,
    )


def _g4_pr_evidence_errors(
    packet: dict[str, Any],
    *,
    now: datetime,
    expected_head_sha: str | None,
    expected_g4_approval_id: str | None,
    expected_g4_scope_prefix: str | None,
    expected_pr_body_digest: str | None,
    expected_managed_block_digest: str | None,
    expected_run_graph_digest: str | None,
    expected_gate_story_digest: str | None,
    expected_evidence_digest: str | None,
) -> list[str]:
    receipt = packet.get("evidence_readback", {}).get("g4_pr_evidence_receipt")
    if not isinstance(receipt, dict):
        return [f"{G4_PR_EVIDENCE_FAILURE}: G4 merge requires trusted current PR evidence receipt"]
    errors = _trusted_receipt_common_errors(
        receipt,
        marker=G4_PR_EVIDENCE_MARKER,
        failure_code=G4_PR_EVIDENCE_FAILURE,
        packet=packet,
        now=now,
        expected_head_sha=expected_head_sha,
        expected_g4_approval_id=expected_g4_approval_id,
        expected_g4_scope_prefix=expected_g4_scope_prefix,
    )
    digest_expectations = {
        "pr_body_digest": expected_pr_body_digest,
        "managed_block_digest": expected_managed_block_digest,
        "run_graph_digest": expected_run_graph_digest,
        "gate_story_digest": expected_gate_story_digest,
        "evidence_digest": expected_evidence_digest,
    }
    for field, expected in digest_expectations.items():
        value = receipt.get(field)
        if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
            errors.append(f"{G4_PR_EVIDENCE_FAILURE}: {field} must be a sha256 digest")
        elif expected and value != expected:
            errors.append(f"{G4_PR_EVIDENCE_FAILURE}: {field} does not match current PR evidence")
    for field in ("run_id", "task_id"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{G4_PR_EVIDENCE_FAILURE}: {field} must be present")
    if receipt.get("task_id") != packet.get("task_id"):
        errors.append(f"{G4_PR_EVIDENCE_FAILURE}: task_id does not match packet task")
    return errors


def _requires_g4_pr_evidence(
    packet: dict[str, Any],
    *,
    expected_pr_body_digest: str | None,
    expected_managed_block_digest: str | None,
    expected_run_graph_digest: str | None,
    expected_gate_story_digest: str | None,
    expected_evidence_digest: str | None,
) -> bool:
    receipt = packet.get("evidence_readback", {}).get("g4_pr_evidence_receipt")
    expected = (
        expected_pr_body_digest,
        expected_managed_block_digest,
        expected_run_graph_digest,
        expected_gate_story_digest,
        expected_evidence_digest,
    )
    return (
        str(packet.get("working_branch", "")).startswith("auto/")
        or isinstance(receipt, dict)
        or any(value is not None for value in expected)
    )


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
    expected_pr_body_digest: str | None = None,
    expected_managed_block_digest: str | None = None,
    expected_run_graph_digest: str | None = None,
    expected_gate_story_digest: str | None = None,
    expected_evidence_digest: str | None = None,
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

    transitive = evaluate_transitive_authority(
        packet,
        effect_graph=packet.get("effect_graph") if isinstance(packet.get("effect_graph"), dict) else None,
        trusted_profile=(
            packet.get("trusted_effect_profile")
            if isinstance(packet.get("trusted_effect_profile"), dict)
            else None
        ),
    )
    if not transitive["allowed"]:
        errors.extend(transitive["reason_codes"])

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
        if _requires_g4_pr_evidence(
            packet,
            expected_pr_body_digest=expected_pr_body_digest,
            expected_managed_block_digest=expected_managed_block_digest,
            expected_run_graph_digest=expected_run_graph_digest,
            expected_gate_story_digest=expected_gate_story_digest,
            expected_evidence_digest=expected_evidence_digest,
        ):
            errors.extend(
                _g4_pr_evidence_errors(
                    packet,
                    now=now,
                    expected_head_sha=expected_head_sha,
                    expected_g4_approval_id=expected_g4_approval_id,
                    expected_g4_scope_prefix=expected_g4_scope_prefix,
                    expected_pr_body_digest=expected_pr_body_digest,
                    expected_managed_block_digest=expected_managed_block_digest,
                    expected_run_graph_digest=expected_run_graph_digest,
                    expected_gate_story_digest=expected_gate_story_digest,
                    expected_evidence_digest=expected_evidence_digest,
                )
            )

    readback = packet.get("evidence_readback", {})
    for field in ("task_id", "repository", "base_sha", "head_sha", "gate", "action", "scope_hash"):
        if readback.get(field) != packet.get(field):
            errors.append(f"evidence_readback.{field} does not match packet.{field}")
    if not readback.get("event_id_or_idempotency_key"):
        errors.append("evidence_readback.event_id_or_idempotency_key is required")

    expected_identity = packet.get("expected_evidence_identity")
    observed_identity = readback.get("execution_identity")
    if expected_identity is not None or observed_identity is not None:
        if not isinstance(expected_identity, dict) or not isinstance(observed_identity, dict):
            errors.append("EVIDENCE_IDENTITY_REQUIRED")
        else:
            errors.extend(validate_evidence_identity(expected_identity, observed_identity))
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
    expected_pr_body_digest: str | None = None,
    expected_managed_block_digest: str | None = None,
    expected_run_graph_digest: str | None = None,
    expected_gate_story_digest: str | None = None,
    expected_evidence_digest: str | None = None,
) -> list[str]:
    errors = schema_errors(packet, schema_path)
    if not errors:
        focused_policies = (
            ("effect_graph", "gate-action-effect-graph.schema.json"),
            ("trusted_effect_profile", "gate-action-effect-profile.schema.json"),
        )
        for field, schema_name in focused_policies:
            policy = packet.get(field)
            if isinstance(policy, dict):
                errors.extend(
                    f"{field}.{error}"
                    for error in schema_errors(policy, schema_path.parent / schema_name)
                )
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
                expected_pr_body_digest=expected_pr_body_digest,
                expected_managed_block_digest=expected_managed_block_digest,
                expected_run_graph_digest=expected_run_graph_digest,
                expected_gate_story_digest=expected_gate_story_digest,
                expected_evidence_digest=expected_evidence_digest,
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
    parser.add_argument("--expected-pr-body-digest")
    parser.add_argument("--expected-managed-block-digest")
    parser.add_argument("--expected-run-graph-digest")
    parser.add_argument("--expected-gate-story-digest")
    parser.add_argument("--expected-evidence-digest")
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
            expected_pr_body_digest=args.expected_pr_body_digest,
            expected_managed_block_digest=args.expected_managed_block_digest,
            expected_run_graph_digest=args.expected_run_graph_digest,
            expected_gate_story_digest=args.expected_gate_story_digest,
            expected_evidence_digest=args.expected_evidence_digest,
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
