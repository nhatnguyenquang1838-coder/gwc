#!/usr/bin/env python3
"""Export Failure Routing — package_export.export-failure-routing (M5_REPLAY_SAFE).

Routes manifest, schema, path, build, hash and smoke failures to one
deterministic bounded next action without publishing an invalid package
or repeating an unknown effect.

Design invariants (SCRUM-237 / F7 family contract):

* Pure routing evaluator. It reads typed upstream outcome, reason codes,
  retry history, checkpoint/readback evidence, package identity and
  authority context; it never writes package content or triggers external
  effects.
* Closed reason-code taxonomy: unknown states are rejected, never ignored.
* Deterministic: identical inputs produce the same route and idempotency
  key. Observational fields (generation time, run ids) are deliberately
  excluded.
* Same evidence and key replay to the same route without duplicate
  build/smoke effect; changed evidence is a new decision or conflict.
* The router recommends and records a route only. It does not repair,
  rebuild, retry, publish, update consumers, merge, deploy, release or
  perform production operations.
* A route decision grants no repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_ID = "gwc.package_export.export_failure_routing"
SCHEMA_VERSION = "0.1"

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

EXPORT_REPAIR_INPUT = "EXPORT_REPAIR_INPUT"
EXPORT_REBUILD_STAGING = "EXPORT_REBUILD_STAGING"
EXPORT_REVERIFY_READBACK = "EXPORT_REVERIFY_READBACK"
EXPORT_BOUNDED_RETRY = "EXPORT_BOUNDED_RETRY"
EXPORT_HUMAN_REQUIRED = "EXPORT_HUMAN_REQUIRED"
EXPORT_FAIL_CLOSED = "EXPORT_FAIL_CLOSED"
EXPORT_RETRY_EXHAUSTED = "EXPORT_RETRY_EXHAUSTED"
EXPORT_UNKNOWN_OUTCOME = "EXPORT_UNKNOWN_OUTCOME"
EXPORT_REPLAY_CONFLICT = "EXPORT_REPLAY_CONFLICT"
EXPORT_AUTHORITY_VIOLATION = "EXPORT_AUTHORITY_VIOLATION"
EXPORT_FAILURE_UNMAPPED = "EXPORT_FAILURE_UNMAPPED"

REASON_CODES: Tuple[str, ...] = (
    EXPORT_REPAIR_INPUT,
    EXPORT_REBUILD_STAGING,
    EXPORT_REVERIFY_READBACK,
    EXPORT_BOUNDED_RETRY,
    EXPORT_HUMAN_REQUIRED,
    EXPORT_FAIL_CLOSED,
    EXPORT_RETRY_EXHAUSTED,
    EXPORT_UNKNOWN_OUTCOME,
    EXPORT_REPLAY_CONFLICT,
    EXPORT_AUTHORITY_VIOLATION,
    EXPORT_FAILURE_UNMAPPED,
)

# ---------------------------------------------------------------------------
# Bounded route actions
# ---------------------------------------------------------------------------

ROUTE_REPAIR_INPUT = "REPAIR_INPUT"
ROUTE_REBUILD_STAGING = "REBUILD_STAGING"
ROUTE_REVERIFY_READBACK = "REVERIFY_READBACK"
ROUTE_BOUNDED_RETRY = "BOUNDED_RETRY"
ROUTE_HUMAN_REQUIRED = "HUMAN_REQUIRED"
ROUTE_FAIL_CLOSED = "FAIL_CLOSED"

ROUTE_ACTIONS: Tuple[str, ...] = (
    ROUTE_REPAIR_INPUT,
    ROUTE_REBUILD_STAGING,
    ROUTE_REVERIFY_READBACK,
    ROUTE_BOUNDED_RETRY,
    ROUTE_HUMAN_REQUIRED,
    ROUTE_FAIL_CLOSED,
)

# ---------------------------------------------------------------------------
# Retryable reasons (bounded retry is allowed only for these)
# ---------------------------------------------------------------------------

RETRYABLE_REASONS: Tuple[str, ...] = (
    EXPORT_REPAIR_INPUT,
    EXPORT_REBUILD_STAGING,
    EXPORT_REVERIFY_READBACK,
    EXPORT_BOUNDED_RETRY,
)

MAX_RETRY_COUNT = 3
DEFAULT_RETRY_DEADLINE_SECONDS = 300


class Outcome(str, Enum):
    ROUTED = "ROUTED"
    FAIL = "FAIL"


@dataclass(frozen=True)
class RouteDecision:
    """A single routing decision for one upstream failure report."""

    outcome: Outcome
    route: str
    reason_code: str
    idempotency_key: str
    retry_count: int = 0
    retry_deadline_seconds: Optional[int] = None
    prohibited_actions: Tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_routed(self) -> bool:
        return self.outcome == Outcome.ROUTED

    @property
    def is_fail_closed(self) -> bool:
        return self.outcome == Outcome.FAIL and self.route == ROUTE_FAIL_CLOSED


@dataclass(frozen=True)
class RoutingResult:
    """Typed result of the routing evaluation."""

    schema_id: str = SCHEMA_ID
    schema_version: str = SCHEMA_VERSION
    task_id: str = "SCRUM-237"
    source_sha: str = ""
    package_version: str = ""
    idempotency_key: str = ""
    decision_digest: str = ""
    outcome: Outcome = Outcome.FAIL
    route: str = ROUTE_FAIL_CLOSED
    reason_code: str = EXPORT_FAILURE_UNMAPPED
    retry_count: int = 0
    retry_deadline_seconds: Optional[int] = None
    prohibited_actions: Tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_routed(self) -> bool:
        return self.outcome == Outcome.ROUTED

    @property
    def is_fail_closed(self) -> bool:
        return self.outcome == Outcome.FAIL and self.route == ROUTE_FAIL_CLOSED

    @property
    def is_human_required(self) -> bool:
        return self.route == ROUTE_HUMAN_REQUIRED


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    """Deterministic JSON serialization (sorted keys, no whitespace)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_decision_digest(
    reason_code: str,
    retry_count: int,
    has_checkpoint: bool,
    package_version: str,
    source_sha: str,
) -> str:
    """Canonical, order-independent semantic digest of the routing input."""
    canonical = {
        "reason_code": reason_code,
        "retry_count": retry_count,
        "has_checkpoint": has_checkpoint,
        "package_version": package_version,
        "source_sha": source_sha,
    }
    return _sha256_bytes(_canonical_json(canonical))


def build_idempotency_key(
    reason_code: str,
    retry_count: int,
    decision_digest: str,
) -> str:
    """Stable replay identity. Same key + same decision_digest = idempotent."""
    payload = f"{reason_code}:{retry_count}:{decision_digest}"
    return f"route:{_sha256_bytes(payload.encode())[:32]}"


def route(
    reason_code: str,
    retry_count: int = 0,
    has_checkpoint: bool = False,
    package_version: str = "",
    source_sha: str = "",
    max_retry_count: int = MAX_RETRY_COUNT,
    retry_deadline_seconds: Optional[int] = DEFAULT_RETRY_DEADLINE_SECONDS,
) -> RoutingResult:
    """Route an upstream failure to one bounded next action.

    Parameters
    ----------
    reason_code: One of the 11 stable reason codes. Unknown codes are
        routed to ``EXPORT_FAILURE_UNMAPPED`` → ``FAIL_CLOSED``.
    retry_count: How many retries have already been attempted for this
        evidence key.
    has_checkpoint: Whether a checkpoint/readback reconciliation record
        exists for this failure.
    package_version: Consumer package version identity.
    source_sha: Source snapshot commit SHA the evidence was produced from.
    max_retry_count: Cap on automatic bounded retries.
    retry_deadline_seconds: Maximum seconds a retry may span.

    Returns
    -------
    RoutingResult with outcome ROUTED or FAIL and the single bounded route.
    """
    if reason_code not in REASON_CODES:
        return RoutingResult(
            outcome=Outcome.FAIL,
            route=ROUTE_FAIL_CLOSED,
            reason_code=EXPORT_FAILURE_UNMAPPED,
            idempotency_key=build_idempotency_key(
                EXPORT_FAILURE_UNMAPPED, retry_count,
                compute_decision_digest(
                    EXPORT_FAILURE_UNMAPPED, retry_count, has_checkpoint,
                    package_version, source_sha,
                ),
            ),
            prohibited_actions=(
                "publish",
                "release",
                "merge",
                "deploy",
                "consumer_mutation",
                "later_gate_authority",
            ),
            detail=f"Unknown reason code '{reason_code}' — fail closed.",
        )

    decision_digest = compute_decision_digest(
        reason_code, retry_count, has_checkpoint, package_version, source_sha
    )
    idempotency_key = build_idempotency_key(reason_code, retry_count, decision_digest)

    # --- route mapping (closed, deterministic) ---------------------------
    if reason_code in (EXPORT_AUTHORITY_VIOLATION, EXPORT_REPLAY_CONFLICT):
        route = ROUTE_FAIL_CLOSED
        prohibited = ("publish", "release", "merge", "deploy", "consumer_mutation")
        detail = f"Authority-boundary violation or replay conflict; routing to {ROUTE_FAIL_CLOSED}."
    elif reason_code == EXPORT_FAIL_CLOSED:
        route = ROUTE_FAIL_CLOSED
        prohibited = ("publish", "release", "merge", "deploy", "consumer_mutation")
        detail = "Terminal fail-closed; no further automatic action."
    elif reason_code == EXPORT_RETRY_EXHAUSTED:
        route = ROUTE_FAIL_CLOSED
        prohibited = ("publish", "release", "merge", "deploy", "consumer_mutation")
        detail = "Retry budget exhausted; fail closed."
    elif reason_code == EXPORT_UNKNOWN_OUTCOME:
        route = ROUTE_HUMAN_REQUIRED
        prohibited = ("publish", "release", "merge", "deploy")
        detail = "Unknown outcome requires human reconciliation before any action."
    elif reason_code == EXPORT_HUMAN_REQUIRED:
        route = ROUTE_HUMAN_REQUIRED
        prohibited = ("publish", "release", "merge", "deploy")
        detail = "Explicitly requires human decision."
    elif reason_code == EXPORT_REPAIR_INPUT:
        route = ROUTE_REPAIR_INPUT
        prohibited = ("publish", "release", "merge", "deploy")
        detail = "Input defect detected; repair before retry."
    elif reason_code == EXPORT_REBUILD_STAGING:
        route = ROUTE_REBUILD_STAGING
        prohibited = ("publish", "release", "merge")
        detail = "Staging build failure; rebuild before re-verification."
    elif reason_code == EXPORT_REVERIFY_READBACK:
        route = ROUTE_REVERIFY_READBACK
        prohibited = ("publish", "release", "merge", "deploy")
        detail = "Checkpoint/readback reconciliation required before retry."
    elif reason_code == EXPORT_BOUNDED_RETRY:
        if retry_count >= max_retry_count:
            route = ROUTE_FAIL_CLOSED
            prohibited = ("publish", "release", "merge", "deploy", "consumer_mutation")
            detail = f"Bounded retry exhausted (count={retry_count}, max={max_retry_count})."
        else:
            route = ROUTE_BOUNDED_RETRY
            prohibited = ("publish", "release", "merge", "deploy")
            detail = (
                f"Bounded retry allowed (count={retry_count}, max={max_retry_count}, "
                f"deadline={retry_deadline_seconds}s)."
            )
    else:
        # Safety net — should never reach here due to the unknown-code guard above.
        route = ROUTE_FAIL_CLOSED
        prohibited = ("publish", "release", "merge", "deploy", "consumer_mutation")
        detail = "Internal routing error; fail closed."

    return RoutingResult(
        outcome=Outcome.ROUTED,
        route=route,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        decision_digest=decision_digest,
        retry_count=retry_count,
        retry_deadline_seconds=retry_deadline_seconds if route == ROUTE_BOUNDED_RETRY else None,
        prohibited_actions=prohibited,
        detail=detail,
    )


def route_with_replay_check(
    reason_code: str,
    retry_count: int = 0,
    has_checkpoint: bool = False,
    package_version: str = "",
    source_sha: str = "",
    prior_route: Optional[str] = None,
    prior_key: Optional[str] = None,
) -> RoutingResult:
    """Route with idempotency/replay guard.

    If the same evidence (same reason_code, retry_count, decision_digest)
    was previously routed to the same action, returns the cached route
    without producing a duplicate external effect. A changed evidence
    profile (different reason_code, retry_count, or checkpoint state) is
    treated as a new decision.
    """
    result = route(
        reason_code=reason_code,
        retry_count=retry_count,
        has_checkpoint=has_checkpoint,
        package_version=package_version,
        source_sha=source_sha,
    )

    if prior_route is not None and prior_key is not None:
        if result.route == prior_route and result.idempotency_key == prior_key:
            # Identical replay — return the same result but flag it.
            return RoutingResult(
                **{**result.__dict__, "detail": result.detail + " [idempotent replay; no duplicate effect]"},
            )
        # Different evidence profile — not a conflict, just a new decision.
        return result

    return result
