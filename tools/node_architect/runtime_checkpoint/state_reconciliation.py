#!/usr/bin/env python3
"""Deterministic state reconciliation for the GWC runtime_checkpoint node family.

Node: ``runtime_checkpoint.state-reconciliation`` (SCRUM-209).

The node is a PURE, AUTHORITY-FREE evidence generator. It reads canonical
evidence (task, repository, branch/PR, checkpoint, runtime event, lease, CAS
revision, approval envelope, CI/status) that has been refreshed by the caller,
compares the checkpoint context with the current evidence, classifies drift and
routes deterministically. It never mutates state, never grants merge/deploy/
production authority, and never silently advances stale worker state.

EARS requirements implemented
-----------------------------
1. On start, canonical evidence MUST be refreshed before a route is selected.
   ``evidence.evidence_refreshed`` must be True, otherwise the node reports
   ``EVIDENCE_UNAVAILABLE`` and STOP_BLOCKED (never PASS).
2. If base/head/scope/approval/lease/CAS drifted, the drift is classified and
   the node does NOT resume blindly.
3. If pending actions were committed before the interruption, the node detects
   this and routes to an idempotent replay instead of repeating the effect.
4. If evidence is unavailable (including exact-head CI evidence), the node
   reports an explicit limitation and does NOT claim PASS.

Route matrix (evaluated top-down; first match wins — deterministic)
-------------------------------------------------------------------
| # | Input condition                                   | drift_classification | route                | reason                          | outcome |
|---|---------------------------------------------------|----------------------|----------------------|---------------------------------|---------|
| 1 | lease missing / expired / owned by another worker | LEASE_DRIFT          | ABORT_STALE_WORKER   | ABORT_STALE_WORKER              | FAIL    |
| 2 | unknown write observed on branch/PR               | UNKNOWN_WRITE        | STOP_BLOCKED         | DRIFT_DETECTED                  | FAIL    |
| 3 | evidence not refreshed / required evidence missing| EVIDENCE_MISSING     | STOP_BLOCKED         | EVIDENCE_UNAVAILABLE            | FAIL    |
| 4 | approval envelope expired / revoked / scope moved | APPROVAL_DRIFT       | REAPPROVAL_REQUIRED  | RECONCILED_REAPPROVAL_REQUIRED  | PASS    |
| 5 | CAS revision mismatch                             | CAS_DRIFT            | REPAIR               | RECONCILED_REPAIR               | PASS    |
| 6 | base / head / scope drift                         | BASE_DRIFT / HEAD_DRIFT / SCOPE_DRIFT | REPAIR | RECONCILED_REPAIR             | PASS    |
| 7 | pending action already committed before response  | COMMITTED_BEFORE_RESPONSE | RESUME          | IDEMPOTENT_REPLAY               | PASS    |
| 8 | no drift, evidence complete                       | NONE                 | RESUME               | RECONCILED_RESUME               | PASS    |

Authority invariant: ``authority_granted(result)`` always returns False.

M5_REPLAY_SAFE invariant: exact-head CI evidence is an EXTERNAL gate. This node
records whether exact-head CI evidence exists (``exact_head_ci_verified``); it
never synthesises a CI PASS. ``m5_claimable(result)`` is only True when the
route is RESUME, the outcome is PASS and exact-head CI is verified externally.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

SCHEMA_ID = "gwc.runtime_checkpoint.state_reconciliation"
SCHEMA_VERSION = "0.1"

# Closed reason-code taxonomy. Do NOT extend without a schema version bump.
REASON_CODES = (
    "RECONCILED_RESUME",
    "RECONCILED_REPAIR",
    "RECONCILED_REAPPROVAL_REQUIRED",
    "ABORT_STALE_WORKER",
    "STOP_BLOCKED",
    "EVIDENCE_UNAVAILABLE",
    "DRIFT_DETECTED",
    "IDEMPOTENT_REPLAY",
)

ROUTES = (
    "RESUME",
    "REPAIR",
    "REAPPROVAL_REQUIRED",
    "ABORT_STALE_WORKER",
    "STOP_BLOCKED",
)

DRIFT_CLASSIFICATIONS = (
    "NONE",
    "BASE_DRIFT",
    "HEAD_DRIFT",
    "SCOPE_DRIFT",
    "APPROVAL_DRIFT",
    "LEASE_DRIFT",
    "CAS_DRIFT",
    "UNKNOWN_WRITE",
    "COMMITTED_BEFORE_RESPONSE",
    "EVIDENCE_MISSING",
)

# Evidence keys that must be present and non-null before a route may be chosen.
REQUIRED_EVIDENCE_KEYS = (
    "task_id",
    "repository",
    "branch",
    "checkpoint",
    "runtime_event",
    "lease",
    "cas_revision",
    "approval",
    "ci",
)

DIGEST_EXCLUDED_FIELDS = frozenset(
    {"result_digest", "observed_at", "run_id", "generated_at", "worker_id"}
)


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class StateReconciliationResult:
    """Deterministic reconciliation evidence. Carries no authority."""

    task_id: str
    outcome: Outcome
    reason: str
    route: str
    drift_classification: str
    idempotency_key: str
    result_digest: str
    limitations: tuple[str, ...] = field(default_factory=tuple)
    exact_head_ci_verified: bool = False
    schema_id: str = SCHEMA_ID
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "idempotency_key": self.idempotency_key,
            "route": self.route,
            "drift_classification": self.drift_classification,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "exact_head_ci_verified": self.exact_head_ci_verified,
            "authority_granted": False,
            "limitations": list(self.limitations),
            "result_digest": self.result_digest,
        }


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _stable(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in DIGEST_EXCLUDED_FIELDS}


def compute_idempotency_key(evidence: Mapping[str, Any]) -> str:
    """Stable key over the identity of the reconciliation attempt."""
    checkpoint = evidence.get("checkpoint") or {}
    seed = {
        "task_id": evidence.get("task_id"),
        "repository": evidence.get("repository"),
        "branch": evidence.get("branch"),
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "pending_action_id": (evidence.get("runtime_event") or {}).get("pending_action_id"),
    }
    return digest_payload(seed)


def _missing_evidence(evidence: Mapping[str, Any]) -> list[str]:
    missing = [k for k in REQUIRED_EVIDENCE_KEYS if evidence.get(k) in (None, "", {})]
    ci = evidence.get("ci") or {}
    if ci and not ci.get("evidence_available", False):
        missing.append("ci.evidence_available")
    return sorted(set(missing))


def classify_drift(evidence: Mapping[str, Any]) -> str:
    """Classify drift between the checkpoint context and current evidence."""
    checkpoint = evidence.get("checkpoint") or {}
    lease = evidence.get("lease") or {}
    approval = evidence.get("approval") or {}
    runtime_event = evidence.get("runtime_event") or {}
    repo_state = evidence.get("repository_state") or {}

    worker_id = evidence.get("worker_id")
    if (
        not lease
        or lease.get("status") in {"EXPIRED", "RELEASED", "MISSING"}
        or (lease.get("holder") is not None and worker_id is not None and lease.get("holder") != worker_id)
    ):
        return "LEASE_DRIFT"

    if repo_state.get("unknown_write_detected"):
        return "UNKNOWN_WRITE"

    if not evidence.get("evidence_refreshed", False) or _missing_evidence(evidence):
        return "EVIDENCE_MISSING"

    if approval.get("status") in {"EXPIRED", "REVOKED"} or (
        approval.get("scope_hash") is not None
        and checkpoint.get("scope_hash") is not None
        and approval.get("scope_hash") != checkpoint.get("scope_hash")
    ):
        return "APPROVAL_DRIFT"

    observed_rev = (evidence.get("cas_revision") or {}).get("observed")
    expected_rev = (evidence.get("cas_revision") or {}).get("expected")
    if observed_rev is not None and expected_rev is not None and observed_rev != expected_rev:
        return "CAS_DRIFT"

    if checkpoint.get("base_sha") is not None and repo_state.get("base_sha") is not None:
        if checkpoint["base_sha"] != repo_state["base_sha"]:
            return "BASE_DRIFT"
    if checkpoint.get("head_sha") is not None and repo_state.get("head_sha") is not None:
        if checkpoint["head_sha"] != repo_state["head_sha"]:
            return "HEAD_DRIFT"
    if checkpoint.get("scope_hash") is not None and repo_state.get("scope_hash") is not None:
        if checkpoint["scope_hash"] != repo_state["scope_hash"]:
            return "SCOPE_DRIFT"

    if runtime_event.get("pending_action_status") == "COMMITTED":
        return "COMMITTED_BEFORE_RESPONSE"

    return "NONE"


_ROUTE_MATRIX: dict[str, tuple[str, str, Outcome]] = {
    # drift -> (route, reason, outcome)
    "LEASE_DRIFT": ("ABORT_STALE_WORKER", "ABORT_STALE_WORKER", Outcome.FAIL),
    "UNKNOWN_WRITE": ("STOP_BLOCKED", "DRIFT_DETECTED", Outcome.FAIL),
    "EVIDENCE_MISSING": ("STOP_BLOCKED", "EVIDENCE_UNAVAILABLE", Outcome.FAIL),
    "APPROVAL_DRIFT": ("REAPPROVAL_REQUIRED", "RECONCILED_REAPPROVAL_REQUIRED", Outcome.PASS),
    "CAS_DRIFT": ("REPAIR", "RECONCILED_REPAIR", Outcome.PASS),
    "BASE_DRIFT": ("REPAIR", "RECONCILED_REPAIR", Outcome.PASS),
    "HEAD_DRIFT": ("REPAIR", "RECONCILED_REPAIR", Outcome.PASS),
    "SCOPE_DRIFT": ("REPAIR", "RECONCILED_REPAIR", Outcome.PASS),
    "COMMITTED_BEFORE_RESPONSE": ("RESUME", "IDEMPOTENT_REPLAY", Outcome.PASS),
    "NONE": ("RESUME", "RECONCILED_RESUME", Outcome.PASS),
}


def reconcile_state(evidence: Mapping[str, Any]) -> StateReconciliationResult:
    """Pure reconciliation: identical evidence -> byte-identical result."""
    drift = classify_drift(evidence)
    route, reason, outcome = _ROUTE_MATRIX[drift]

    limitations: list[str] = []
    if drift == "EVIDENCE_MISSING":
        if not evidence.get("evidence_refreshed", False):
            limitations.append("CANONICAL_EVIDENCE_NOT_REFRESHED")
        for key in _missing_evidence(evidence):
            limitations.append(f"EVIDENCE_MISSING:{key}")

    ci = evidence.get("ci") or {}
    repo_state = evidence.get("repository_state") or {}
    exact_head_ci_verified = bool(
        ci.get("evidence_available")
        and ci.get("conclusion") == "SUCCESS"
        and ci.get("head_sha") is not None
        and ci.get("head_sha") == repo_state.get("head_sha")
    )
    if not exact_head_ci_verified:
        limitations.append("EXACT_HEAD_CI_NOT_VERIFIED")

    body = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "task_id": evidence.get("task_id", ""),
        "idempotency_key": compute_idempotency_key(evidence),
        "route": route,
        "drift_classification": drift,
        "outcome": outcome.value,
        "reason": reason,
        "exact_head_ci_verified": exact_head_ci_verified,
        "authority_granted": False,
        "limitations": sorted(set(limitations)),
    }
    return StateReconciliationResult(
        task_id=body["task_id"],
        outcome=outcome,
        reason=reason,
        route=route,
        drift_classification=drift,
        idempotency_key=body["idempotency_key"],
        result_digest=digest_payload(_stable(body)),
        limitations=tuple(body["limitations"]),
        exact_head_ci_verified=exact_head_ci_verified,
    )


def load_evidence(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def authority_granted(result: StateReconciliationResult) -> bool:
    """This node never grants merge, deploy, or production authority."""
    return False


def m5_claimable(result: StateReconciliationResult) -> bool:
    """M5_REPLAY_SAFE requires an EXTERNAL exact-head CI PASS. Never faked here."""
    return (
        result.outcome is Outcome.PASS
        and result.route == "RESUME"
        and result.exact_head_ci_verified
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reconcile runtime checkpoint state from evidence JSON.")
    parser.add_argument("--evidence", required=True, help="Path to an evidence JSON file.")
    args = parser.parse_args(argv)
    result = reconcile_state(load_evidence(args.evidence))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.outcome is Outcome.PASS else 1


# ---------------------------------------------------------------------------
# NA81 SCRUM-332 extension (2026-08-12, Hermes): three-source reconciliation
# with deterministic source precedence and explicit UNKNOWN handling.
#
# This is a backward-compatible addition to the historical SCRUM-209
# ``reconcile_state`` surface. It does NOT change any existing symbol. The
# node remains a pure, authority-free evidence generator.
#
# Family invariants (SCRUM-332):
#   * Deterministic source precedence: canonical > external_readback > checkpoint.
#   * UNKNOWN must never be guessed into completion (UNKNOWN -> outcome FAIL).
#   * Retry / replay requires an authoritative external readback first.
#   * Conflicting sources are surfaced (conflict=True) and routed to REPAIR
#     only when the readback confirms the authoritative state.
# ---------------------------------------------------------------------------

class SourceState(str, Enum):
    CONFIRMED = "CONFIRMED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    ABSENT = "ABSENT"

    @classmethod
    def from_raw(cls, raw: Any) -> "SourceState":
        if raw is None:
            return cls.ABSENT
        token = str(raw).strip().upper()
        mapping = {
            "CONFIRMED": cls.CONFIRMED,
            "COMPLETE": cls.CONFIRMED,
            "COMPLETED": cls.CONFIRMED,
            "DONE": cls.CONFIRMED,
            "SUCCESS": cls.CONFIRMED,
            "PENDING": cls.PENDING,
            "IN_PROGRESS": cls.PENDING,
            "RUNNING": cls.PENDING,
            "ACTIVE": cls.PENDING,
            "FAILED": cls.FAILED,
            "FAIL": cls.FAILED,
            "ERROR": cls.FAILED,
            "UNKNOWN": cls.UNKNOWN,
        }
        return mapping.get(token, cls.UNKNOWN)


# Deterministic source precedence, highest authority first. Canonical task /
# runtime state is authoritative; external readback is the authoritative re-read
# used to confirm or repair; persisted checkpoint is local memory and may be
# stale.
SOURCE_PRECEDENCE = ("canonical_state", "external_readback", "persisted_checkpoint")

_DETERMINATE = (SourceState.CONFIRMED, SourceState.PENDING, SourceState.FAILED)


@dataclass(frozen=True)
class SourceReconciliationResult:
    """Deterministic three-source reconciliation evidence. Carries no authority."""

    task_id: str
    state: str
    authoritative_source: str | None
    source_precedence: tuple
    conflict: bool
    readback_required: bool
    retry_allowed: bool
    route: str
    outcome: str
    reason: str
    authority_granted: bool = False
    exact_head_ci_verified: bool = False
    result_digest: str = ""
    schema_id: str = "gwc.runtime_checkpoint.state_reconciliation.sources"
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "state": self.state,
            "authoritative_source": self.authoritative_source,
            "source_precedence": list(self.source_precedence),
            "conflict": self.conflict,
            "readback_required": self.readback_required,
            "retry_allowed": self.retry_allowed,
            "route": self.route,
            "outcome": self.outcome,
            "reason": self.reason,
            "authority_granted": self.authority_granted,
            "exact_head_ci_verified": self.exact_head_ci_verified,
            "result_digest": self.result_digest,
        }


def classify_source_state(source: Any) -> SourceState:
    """Map a raw source payload to a deterministic SourceState."""
    if source is None:
        return SourceState.ABSENT
    if isinstance(source, Mapping):
        for key in ("status", "state", "outcome"):
            if key in source and source[key] is not None:
                return SourceState.from_raw(source[key])
        return SourceState.UNKNOWN
    return SourceState.from_raw(source)


def _mk_result(
    evidence: Mapping[str, Any],
    *,
    state: SourceState,
    authoritative_source: str | None,
    conflict: bool,
    readback_required: bool,
    retry_allowed: bool,
    route: str,
    outcome: str,
    reason: str,
    exact_head_ci_verified: bool = False,
) -> SourceReconciliationResult:
    body = {
        "schema_id": "gwc.runtime_checkpoint.state_reconciliation.sources",
        "schema_version": "0.1",
        "task_id": evidence.get("task_id", "") if isinstance(evidence, Mapping) else "",
        "state": state.value,
        "authoritative_source": authoritative_source,
        "source_precedence": list(SOURCE_PRECEDENCE),
        "conflict": conflict,
        "readback_required": readback_required,
        "retry_allowed": retry_allowed,
        "route": route,
        "outcome": outcome,
        "reason": reason,
        "exact_head_ci_verified": exact_head_ci_verified,
    }
    return SourceReconciliationResult(
        task_id=body["task_id"],
        state=body["state"],
        authoritative_source=authoritative_source,
        source_precedence=SOURCE_PRECEDENCE,
        conflict=conflict,
        readback_required=readback_required,
        retry_allowed=retry_allowed,
        route=route,
        outcome=outcome,
        reason=reason,
        authority_granted=False,
        exact_head_ci_verified=exact_head_ci_verified,
        result_digest=digest_payload(_stable(body)),
    )


def reconcile_sources(evidence: Mapping[str, Any]) -> SourceReconciliationResult:
    """Reconcile persisted checkpoint, external readback and canonical state.

    The node never grants authority and never fakes a CI PASS. ``unknown`` is
    never inferred into completion; retry requires an authoritative external
    readback first.
    """
    if not isinstance(evidence, Mapping):
        evidence = {}
    cs = classify_source_state(evidence.get("canonical_state"))
    rs = classify_source_state(evidence.get("external_readback"))
    ps = classify_source_state(evidence.get("persisted_checkpoint"))

    determinate_states = [s for s in (cs, rs, ps) if s in _DETERMINATE]
    conflict = len(set(determinate_states)) > 1

    # pick authoritative source by precedence, skipping ABSENT / UNKNOWN
    auth_source: str | None = None
    auth_state: SourceState | None = None
    for name in SOURCE_PRECEDENCE:
        st = {"canonical_state": cs, "external_readback": rs, "persisted_checkpoint": ps}[name]
        if st not in (SourceState.ABSENT, SourceState.UNKNOWN):
            auth_source, auth_state = name, st
            break

    ci = evidence.get("ci") or {}
    exact_head_ci_verified = bool(
        ci.get("evidence_available") and ci.get("conclusion") == "SUCCESS"
    )

    # Authoritative source indeterminate -> cannot complete; never guess.
    if auth_state is None:
        return _mk_result(
            evidence, state=SourceState.UNKNOWN, authoritative_source=None,
            conflict=False, readback_required=True, retry_allowed=False,
            route="STOP_BLOCKED", outcome="FAIL",
            reason="AUTHORITATIVE_READBACK_UNAVAILABLE",
            exact_head_ci_verified=exact_head_ci_verified,
        )

    if auth_state is SourceState.FAILED:
        return _mk_result(
            evidence, state=SourceState.FAILED, authoritative_source=auth_source,
            conflict=conflict, readback_required=False, retry_allowed=False,
            route="STOP_BLOCKED", outcome="FAIL",
            reason="AUTHORITATIVE_STATE_FAILED",
            exact_head_ci_verified=exact_head_ci_verified,
        )

    # Retry / replay requires an authoritative external readback first.
    readback_ok = rs not in (SourceState.ABSENT, SourceState.UNKNOWN)
    if not readback_ok:
        return _mk_result(
            evidence, state=auth_state, authoritative_source=auth_source,
            conflict=conflict, readback_required=True, retry_allowed=False,
            route="STOP_BLOCKED", outcome="FAIL",
            reason="READBACK_REQUIRED_BEFORE_RETRY",
            exact_head_ci_verified=exact_head_ci_verified,
        )

    if conflict:
        # Persisted checkpoint disagrees with authoritative state. The readback
        # must confirm the authoritative state before we repair the checkpoint.
        if rs == auth_state:
            return _mk_result(
                evidence, state=auth_state, authoritative_source=auth_source,
                conflict=True, readback_required=False, retry_allowed=True,
                route="REPAIR", outcome="PASS", reason="RECONCILED_REPAIR_STALE_CHECKPOINT",
                exact_head_ci_verified=exact_head_ci_verified,
            )
        return _mk_result(
            evidence, state=auth_state, authoritative_source=auth_source,
            conflict=True, readback_required=True, retry_allowed=False,
            route="STOP_BLOCKED", outcome="FAIL", reason="CONFLICTING_SOURCES",
            exact_head_ci_verified=exact_head_ci_verified,
        )

    return _mk_result(
        evidence, state=auth_state, authoritative_source=auth_source,
        conflict=False, readback_required=False, retry_allowed=True,
        route="RESUME", outcome="PASS", reason="RECONCILED_RESUME",
        exact_head_ci_verified=exact_head_ci_verified,
    )


if __name__ == "__main__":
    raise SystemExit(main())
