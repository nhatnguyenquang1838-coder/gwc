#!/usr/bin/env python3
"""Typed, replay-safe compare-and-swap guard for GWC runtime writes.

The evaluator is pure and connector-free. Callers provide the latest observed
state plus task, repository, branch, protected-base, scope, checkpoint, lease,
fencing, revision, and idempotency evidence. A rejection never authorizes
automatic retry; it returns the latest state and an explicit SCRUM-209
reconciliation route.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CASWriteDecision:
    schema_version: str
    artifact_type: str
    node_id: str
    outcome: str
    reason_codes: list[str]
    may_write: bool
    expected_revision: int | None
    observed_revision: int | None
    next_revision: int | None
    latest_observed_state: dict[str, Any]
    latest_observed_state_digest: str
    idempotency_key: str
    committed_effect: dict[str, Any] | None
    requires_reconciliation: bool
    reconciliation_route: str | None
    next_node: str | None
    next_action: str
    auto_retry_allowed: bool
    decision_digest: str
    merge_authority_granted: bool
    deployment_authority_granted: bool
    production_authority_granted: bool


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_timestamp(value: Any) -> datetime | None:
    if not _non_empty(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _string_sequence(value: Any) -> list[str] | None:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    result: list[str] = []
    for item in value:
        if not _non_empty(item):
            return None
        result.append(str(item))
    return result


def _decision(
    *, observation: Mapping[str, Any], outcome: str, reasons: list[str],
    may_write: bool, requires_reconciliation: bool,
    reconciliation_route: str | None, next_node: str | None,
    next_action: str, committed_effect: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = observation.get("expected_revision")
    observed = observation.get("observed_revision")
    latest_state = observation.get("latest_observed_state")
    if not isinstance(latest_state, Mapping):
        latest_state = {}
    state = dict(latest_state)
    payload = {
        "schema_version": "1.0",
        "artifact_type": "cas-write-guard-result",
        "node_id": "runtime_checkpoint.cas-write-guard",
        "outcome": outcome,
        "reason_codes": reasons,
        "may_write": may_write,
        "expected_revision": expected if _non_negative_int(expected) else None,
        "observed_revision": observed if _non_negative_int(observed) else None,
        "next_revision": (observed + 1) if may_write and _non_negative_int(observed) else None,
        "latest_observed_state": state,
        "latest_observed_state_digest": digest_payload(state),
        "idempotency_key": str(observation.get("idempotency_key") or ""),
        "committed_effect": dict(committed_effect) if isinstance(committed_effect, Mapping) else None,
        "requires_reconciliation": requires_reconciliation,
        "reconciliation_route": reconciliation_route,
        "next_node": next_node,
        "next_action": next_action,
        "auto_retry_allowed": False,
    }
    return asdict(CASWriteDecision(
        **payload,
        decision_digest=digest_payload(payload),
        merge_authority_granted=False,
        deployment_authority_granted=False,
        production_authority_granted=False,
    ))


def _effect_binding_mismatch(
    observation: Mapping[str, Any], effect: Mapping[str, Any]
) -> tuple[str, list[str], str, str] | None:
    """Return outcome/reasons/route/action when a committed effect is not owned by this request."""
    binding = effect.get("binding")
    if not isinstance(binding, Mapping):
        return (
            "INVALID_INPUT",
            ["COMMITTED_EFFECT_BINDING_MISSING"],
            "STOP_BLOCKED",
            "stop_and_report_unbound_committed_effect",
        )

    groups = (
        (
            "SCOPE_MISMATCH",
            "REAPPROVAL_REQUIRED",
            "reconcile_effect_scope_and_request_reapproval",
            (
                "task_id", "repository", "branch", "scope_hash",
                "checkpoint_key", "run_id", "checkpoint_node_id",
                "idempotency_key", "expected_revision",
            ),
        ),
        (
            "BASE_DRIFT",
            "REAPPROVAL_REQUIRED",
            "refresh_base_and_request_reapproval",
            ("base_sha",),
        ),
        (
            "LEASE_OWNER_MISMATCH",
            "ABORT_STALE_WORKER",
            "abort_stale_worker_and_reconcile_owner",
            ("lease_owner",),
        ),
        (
            "LEASE_STALE",
            "ABORT_STALE_WORKER",
            "abort_stale_worker_and_reconcile_lease",
            ("lease_token", "lease_expires_at"),
        ),
        (
            "FENCING_MISMATCH",
            "ABORT_STALE_WORKER",
            "abort_stale_worker_and_reconcile_fencing",
            ("fencing_token",),
        ),
    )
    for outcome, route, action, fields in groups:
        mismatch = [f"COMMITTED_EFFECT_BINDING_MISMATCH:{field}" for field in fields if binding.get(field) != observation.get(field)]
        if mismatch:
            return outcome, mismatch, route, action
    return None


def evaluate_cas_write(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic allow/reject decision without mutating state."""
    required_strings = (
        "task_id", "observed_task_id", "repository", "observed_repository",
        "branch", "observed_branch", "base_sha", "observed_base_sha",
        "scope_hash", "observed_scope_hash", "checkpoint_key", "run_id",
        "checkpoint_node_id", "lease_owner", "observed_lease_owner",
        "lease_token", "observed_lease_token", "lease_expires_at",
        "observed_at", "idempotency_key",
    )
    reasons: list[str] = []
    for field in required_strings:
        if not _non_empty(observation.get(field)):
            reasons.append(f"MISSING_OR_INVALID:{field}")
    for field in ("expected_revision", "observed_revision", "fencing_token", "observed_fencing_token"):
        if not _non_negative_int(observation.get(field)):
            reasons.append(f"MISSING_OR_INVALID:{field}")
    if not str(observation.get("scope_hash", "")).startswith("sha256:"):
        reasons.append("INVALID_SCOPE_HASH")
    if not str(observation.get("observed_scope_hash", "")).startswith("sha256:"):
        reasons.append("INVALID_OBSERVED_SCOPE_HASH")
    if not isinstance(observation.get("latest_observed_state"), Mapping):
        reasons.append("INVALID_LATEST_OBSERVED_STATE")
    committed_effects = observation.get("committed_effects", {})
    if not isinstance(committed_effects, Mapping):
        reasons.append("INVALID_COMMITTED_EFFECTS")
        committed_effects = {}

    precondition_errors = _string_sequence(observation.get("precondition_errors"))
    if precondition_errors is None:
        reasons.append("INVALID_PRECONDITION_ERRORS")
    else:
        reasons.extend(precondition_errors)

    lease_expiry = _parse_timestamp(observation.get("lease_expires_at"))
    observed_at = _parse_timestamp(observation.get("observed_at"))
    if lease_expiry is None:
        reasons.append("INVALID_LEASE_EXPIRY")
    if observed_at is None:
        reasons.append("INVALID_OBSERVED_AT")

    if reasons:
        return _decision(
            observation=observation, outcome="INVALID_INPUT", reasons=reasons,
            may_write=False, requires_reconciliation=True,
            reconciliation_route="STOP_BLOCKED", next_node="runtime_checkpoint.state-reconciliation",
            next_action="stop_and_report_invalid_cas_input",
        )

    identity_pairs = (
        ("task_id", "observed_task_id", "TASK_MISMATCH"),
        ("repository", "observed_repository", "REPOSITORY_MISMATCH"),
        ("branch", "observed_branch", "BRANCH_MISMATCH"),
        ("scope_hash", "observed_scope_hash", "SCOPE_MISMATCH"),
    )
    mismatch_reasons = [reason for left, right, reason in identity_pairs if observation[left] != observation[right]]
    if mismatch_reasons:
        return _decision(
            observation=observation, outcome="SCOPE_MISMATCH", reasons=mismatch_reasons,
            may_write=False, requires_reconciliation=True,
            reconciliation_route="REAPPROVAL_REQUIRED", next_node="runtime_checkpoint.state-reconciliation",
            next_action="reconcile_scope_and_request_reapproval",
        )

    if observation["base_sha"] != observation["observed_base_sha"]:
        return _decision(
            observation=observation, outcome="BASE_DRIFT", reasons=["BASE_SHA_MISMATCH"],
            may_write=False, requires_reconciliation=True,
            reconciliation_route="REAPPROVAL_REQUIRED", next_node="runtime_checkpoint.state-reconciliation",
            next_action="refresh_base_and_request_reapproval",
        )

    if observation["lease_owner"] != observation["observed_lease_owner"]:
        return _decision(
            observation=observation, outcome="LEASE_OWNER_MISMATCH",
            reasons=["STALE_OR_DUPLICATE_AGENT"], may_write=False,
            requires_reconciliation=True, reconciliation_route="ABORT_STALE_WORKER",
            next_node="runtime_checkpoint.state-reconciliation",
            next_action="abort_stale_worker_and_reconcile_owner",
        )

    if observation["lease_token"] != observation["observed_lease_token"]:
        return _decision(
            observation=observation, outcome="LEASE_STALE", reasons=["LEASE_TOKEN_MISMATCH"],
            may_write=False, requires_reconciliation=True,
            reconciliation_route="ABORT_STALE_WORKER", next_node="runtime_checkpoint.state-reconciliation",
            next_action="abort_stale_worker_and_reconcile_lease",
        )

    if observation["fencing_token"] != observation["observed_fencing_token"]:
        return _decision(
            observation=observation, outcome="FENCING_MISMATCH",
            reasons=["STALE_FENCING_TOKEN"], may_write=False,
            requires_reconciliation=True, reconciliation_route="ABORT_STALE_WORKER",
            next_node="runtime_checkpoint.state-reconciliation",
            next_action="abort_stale_worker_and_reconcile_fencing",
        )

    idempotency_key = str(observation["idempotency_key"])
    committed_effect = committed_effects.get(idempotency_key)
    if isinstance(committed_effect, Mapping):
        effect_mismatch = _effect_binding_mismatch(observation, committed_effect)
        if effect_mismatch is not None:
            outcome, mismatch, route, action = effect_mismatch
            return _decision(
                observation=observation, outcome=outcome, reasons=mismatch,
                may_write=False, requires_reconciliation=True,
                reconciliation_route=route, next_node="runtime_checkpoint.state-reconciliation",
                next_action=action,
            )
        return _decision(
            observation=observation, outcome="DUPLICATE_EFFECT_REPLAYED",
            reasons=["IDEMPOTENT_EFFECT_ALREADY_COMMITTED_AND_BOUND"], may_write=False,
            requires_reconciliation=False, reconciliation_route="RESUME",
            next_node=None, next_action="return_committed_effect_readback",
            committed_effect=committed_effect,
        )

    assert lease_expiry is not None and observed_at is not None
    if observed_at >= lease_expiry:
        return _decision(
            observation=observation, outcome="LEASE_EXPIRED", reasons=["LEASE_EXPIRED_AT_WRITE"],
            may_write=False, requires_reconciliation=True,
            reconciliation_route="REAPPROVAL_REQUIRED", next_node="runtime_checkpoint.state-reconciliation",
            next_action="renew_lease_or_request_reapproval",
        )

    if observation["expected_revision"] != observation["observed_revision"]:
        return _decision(
            observation=observation, outcome="CAS_MISMATCH", reasons=["REVISION_MISMATCH"],
            may_write=False, requires_reconciliation=True,
            reconciliation_route="REPAIR", next_node="runtime_checkpoint.state-reconciliation",
            next_action="reload_latest_state_and_reconcile_without_auto_retry",
        )

    return _decision(
        observation=observation, outcome="ALLOW_WRITE", reasons=["CAS_BINDINGS_MATCH"],
        may_write=True, requires_reconciliation=False, reconciliation_route=None,
        next_node=None, next_action="perform_single_guarded_write",
    )


__all__ = ["CASWriteDecision", "canonical_json", "digest_payload", "evaluate_cas_write"]
