#!/usr/bin/env python3
"""Offline export-failure routing — package_export.export-failure-routing (M5_REPLAY_SAFE).

Read-only, recommend-only evidence evaluator (SCRUM-237, F7 family-integration
owner). It consumes a typed upstream outcome (reason code, namespace, retry
history, checkpoint/readback evidence, package identity and authority context)
and returns EXACTLY ONE bounded next action without publishing an invalid
package or repeating an unknown effect.

Design invariants (SCRUM-237 / F7 family contract):

* Recommend-only. The router records a route; it never repairs, rebuilds,
  retries, publishes, updates consumers, merges, deploys or performs production
  operations. A route decision grants NO repository, PR, merge, deploy, release
  or production authority.
* Exactly one route: REPAIR_INPUT, REBUILD_STAGING, REVERIFY_READBACK,
  BOUNDED_RETRY, HUMAN_REQUIRED or FAIL_CLOSED.
* Never routes unsafe path, schema incompatibility, replay conflict, content/
  hash contradiction or authority-boundary violation to automatic success/retry
  without changed approved evidence.
* Timeout, interruption or unknown output state require checkpoint/readback
  reconciliation before any retry.
* Retry is bounded by count/deadline and requires an explicitly retryable
  reason plus reconciled zero/known effect.
* Same canonical failure evidence + idempotency key yields the same route and
  decision digest with no duplicate external or filesystem effect.
* Changed evidence under the same idempotency key is a replay conflict (routes
  to HUMAN_REQUIRED), never a silent re-decision.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

SCHEMA_ID = "gwc.package_export.export_failure_routing"
SCHEMA_VERSION = "0.1"
ROUTER_VERSION = "0.1.0"

VERIFIER_VERSION = ROUTER_VERSION  # exported for envelope compatibility

# ---------------------------------------------------------------------------
# Stable route taxonomy
# ---------------------------------------------------------------------------

ROUTE_REPAIR_INPUT = "EXPORT_REPAIR_INPUT"
ROUTE_REBUILD_STAGING = "EXPORT_REBUILD_STAGING"
ROUTE_REVERIFY_READBACK = "EXPORT_REVERIFY_READBACK"
ROUTE_BOUNDED_RETRY = "EXPORT_BOUNDED_RETRY"
ROUTE_HUMAN_REQUIRED = "EXPORT_HUMAN_REQUIRED"
ROUTE_FAIL_CLOSED = "EXPORT_FAIL_CLOSED"

ROUTES: tuple[str, ...] = (
    ROUTE_REPAIR_INPUT,
    ROUTE_REBUILD_STAGING,
    ROUTE_REVERIFY_READBACK,
    ROUTE_BOUNDED_RETRY,
    ROUTE_HUMAN_REQUIRED,
    ROUTE_FAIL_CLOSED,
)

# Stable final reason codes (contract section "Stable reason codes").
REASON_REPAIR_INPUT = "EXPORT_REPAIR_INPUT"
REASON_REBUILD_STAGING = "EXPORT_REBUILD_STAGING"
REASON_REVERIFY_READBACK = "EXPORT_REVERIFY_READBACK"
REASON_BOUNDED_RETRY = "EXPORT_BOUNDED_RETRY"
REASON_HUMAN_REQUIRED = "EXPORT_HUMAN_REQUIRED"
REASON_FAIL_CLOSED = "EXPORT_FAIL_CLOSED"
REASON_RETRY_EXHAUSTED = "EXPORT_RETRY_EXHAUSTED"
REASON_UNKNOWN_OUTCOME = "EXPORT_UNKNOWN_OUTCOME"
REASON_REPLAY_CONFLICT = "EXPORT_REPLAY_CONFLICT"
REASON_AUTHORITY_VIOLATION = "EXPORT_AUTHORITY_VIOLATION"
REASON_FAILURE_UNMAPPED = "EXPORT_FAILURE_UNMAPPED"

DEFAULT_MAX_RETRY = 3
DEFAULT_RETRY_DEADLINE_SECONDS = 600.0


class Route(str, Enum):
    REPAIR_INPUT = ROUTE_REPAIR_INPUT
    REBUILD_STAGING = ROUTE_REBUILD_STAGING
    REVERIFY_READBACK = ROUTE_REVERIFY_READBACK
    BOUNDED_RETRY = ROUTE_BOUNDED_RETRY
    HUMAN_REQUIRED = ROUTE_HUMAN_REQUIRED
    FAIL_CLOSED = ROUTE_FAIL_CLOSED


# ---------------------------------------------------------------------------
# Decision table: upstream reason code -> (route, requires_readback, retryable)
# Covers every upstream reason namespace from SCRUM-229..236 (entry-schema,
# source/target-path-safety, governance-tree-build, export-manifest-generation,
# deterministic-hash, smoke-verification).
# ---------------------------------------------------------------------------

# reason code -> (route, requires_readback, retryable)
DECISION_TABLE: Dict[str, tuple[str, bool, bool]] = {
    # --- entry-schema-validation (SCHEMA_*) ---
    "SCHEMA_INVALID": (ROUTE_REPAIR_INPUT, False, False),
    # --- export-manifest-generation (MANIFEST_*) ---
    "MANIFEST_ENTRY_INVALID": (ROUTE_REPAIR_INPUT, False, False),
    "MANIFEST_DIGEST_MISMATCH": (ROUTE_REPAIR_INPUT, False, False),
    "MANIFEST_SOURCE_MISSING": (ROUTE_REPAIR_INPUT, False, False),
    "MANIFEST_GENERATED": (ROUTE_REVERIFY_READBACK, False, False),
    "MANIFEST_IDEMPOTENT_REPLAY": (ROUTE_REVERIFY_READBACK, False, False),
    # --- source-path-safety (SOURCE_*) ---
    "SOURCE_REQUIRED_MISSING": (ROUTE_REPAIR_INPUT, False, False),
    "SOURCE_OPTIONAL_MISSING": (ROUTE_REVERIFY_READBACK, False, False),
    "SOURCE_NOT_REGULAR_FILE": (ROUTE_REPAIR_INPUT, False, False),
    "SOURCE_READBACK_FAILED": (ROUTE_REVERIFY_READBACK, True, False),
    "SOURCE_PATH_TRAVERSAL": (ROUTE_HUMAN_REQUIRED, False, False),
    "SOURCE_PATH_ESCAPES_ROOT": (ROUTE_HUMAN_REQUIRED, False, False),
    "SOURCE_SYMLINK_ESCAPE": (ROUTE_HUMAN_REQUIRED, False, False),
    "SOURCE_PATH_ABSOLUTE": (ROUTE_HUMAN_REQUIRED, False, False),
    "SOURCE_PATH_BACKSLASH": (ROUTE_HUMAN_REQUIRED, False, False),
    "SOURCE_PATH_EMPTY": (ROUTE_HUMAN_REQUIRED, False, False),
    # --- target-path-safety-check (TARGET_*) ---
    "TARGET_DUPLICATE": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_CASE_COLLISION": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_OVERWRITE_FORBIDDEN": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PREFIX_FORBIDDEN": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PATH_TRAVERSAL": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PATH_ESCAPES_ROOT": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_SYMLINK_ESCAPE": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PATH_ABSOLUTE": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PATH_BACKSLASH": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_PATH_EMPTY": (ROUTE_HUMAN_REQUIRED, False, False),
    "TARGET_IDEMPOTENT_EXISTING": (ROUTE_REVERIFY_READBACK, False, False),
    # --- governance-tree-build (TREE_*) ---
    "TREE_PARTIAL_OUTPUT": (ROUTE_REBUILD_STAGING, True, False),
    "TREE_READBACK_MISMATCH": (ROUTE_REBUILD_STAGING, True, False),
    "TREE_COPY_MISMATCH": (ROUTE_REBUILD_STAGING, True, False),
    "TREE_STALE_SOURCE": (ROUTE_REBUILD_STAGING, False, False),
    "TREE_TARGET_COLLISION": (ROUTE_REBUILD_STAGING, False, False),
    "TREE_REQUIRED_SOURCE_MISSING": (ROUTE_REPAIR_INPUT, False, False),
    "TREE_BUILD_COMPLETE": (ROUTE_REVERIFY_READBACK, False, False),
    "TREE_BUILD_STAGED": (ROUTE_REVERIFY_READBACK, False, False),
    "TREE_IDEMPOTENT_REPLAY": (ROUTE_REVERIFY_READBACK, False, False),
    "TREE_REPLAY_CONFLICT": (ROUTE_HUMAN_REQUIRED, False, False),
    # --- governance-tree-build NA81-F7 topology (SCRUM-356) ---
    "TREE_DUPLICATE_ENTRY": (ROUTE_REPAIR_INPUT, False, False),
    "TREE_MISSING_PARENT": (ROUTE_REPAIR_INPUT, False, False),
    "TREE_AMBIGUOUS_ORDER": (ROUTE_REPAIR_INPUT, False, False),
    "TREE_CYCLE_DETECTED": (ROUTE_HUMAN_REQUIRED, False, False),
    # --- deterministic-hash-verification (HASH_*) ---
    "HASH_TARGET_MISSING": (ROUTE_REPAIR_INPUT, False, False),
    "HASH_SOURCE_MISMATCH": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_TARGET_MISMATCH": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_BYTE_COUNT_MISMATCH": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_TREE_DIGEST_MISMATCH": (ROUTE_REBUILD_STAGING, True, False),
    "HASH_UNMANIFESTED_TARGET": (ROUTE_REBUILD_STAGING, False, False),
    "HASH_ALGORITHM_UNSUPPORTED": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_MANIFEST_DIGEST_MISMATCH": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_REPLAY_CONFLICT": (ROUTE_HUMAN_REQUIRED, False, False),
    "HASH_IDEMPOTENT_REPLAY": (ROUTE_REVERIFY_READBACK, False, False),
    "HASH_VERIFICATION_PASS": (ROUTE_REVERIFY_READBACK, False, False),
    # --- smoke-verification (SMOKE_*) ---
    "SMOKE_MANIFEST_INVALID": (ROUTE_REPAIR_INPUT, False, False),
    "SMOKE_REQUIRED_TARGET_MISSING": (ROUTE_REPAIR_INPUT, False, False),
    "SMOKE_HASH_MISMATCH": (ROUTE_HUMAN_REQUIRED, False, False),
    "SMOKE_EXTRACTION_FAILED": (ROUTE_REPAIR_INPUT, False, False),
    "SMOKE_LOAD_FAILED": (ROUTE_REPAIR_INPUT, False, False),
    "SMOKE_TIMEOUT": (ROUTE_BOUNDED_RETRY, True, True),
    "SMOKE_RESULT_UNKNOWN": (ROUTE_BOUNDED_RETRY, True, True),
    "SMOKE_ENVIRONMENT_UNSAFE": (ROUTE_HUMAN_REQUIRED, False, False),
    "SMOKE_IDEMPOTENT_REPLAY": (ROUTE_REVERIFY_READBACK, False, False),
    "SMOKE_REPLAY_CONFLICT": (ROUTE_HUMAN_REQUIRED, False, False),
    "SMOKE_VERIFICATION_PASS": (ROUTE_REVERIFY_READBACK, False, False),
}


@dataclass
class RouteDecision:
    route: str
    reason_code: str
    decision_digest: str
    idempotency_key: str
    verifier_version: str
    retry_count: int
    retry_deadline: Optional[float]
    requires_readback: bool
    readback_reconciled: bool
    prohibited_actions: List[str]
    authority_authorized: bool = False
    evidence_hash: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "idempotency_key": self.idempotency_key,
            "verifier_version": self.verifier_version,
            "route": self.route,
            "reason_code": self.reason_code,
            "decision_digest": self.decision_digest,
            "evidence_hash": self.evidence_hash,
            "retry_count": self.retry_count,
            "retry_deadline": self.retry_deadline,
            "requires_readback": self.requires_readback,
            "readback_reconciled": self.readback_reconciled,
            "prohibited_actions": self.prohibited_actions,
            "authority_authorized": False,
            "detail": self.detail,
        }


_PROHIBITED = [
    "repair",
    "rebuild",
    "retry",
    "publish",
    "release",
    "update_consumer",
    "merge",
    "deploy",
    "production_operation",
]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def compute_evidence_hash(*, reason_code: str, reason_namespace: str,
                          idempotency_key: str, retry_count: int,
                          checkpoint_reconciled: bool, authority_granted: bool,
                          package_identity: Dict[str, Any]) -> str:
    """Canonical, observation-independent hash of the failure evidence.

    Excludes wall-clock time and any non-deterministic fields so identical
    evidence yields an identical hash (replay stability)."""
    canonical = {
        "reason_code": reason_code,
        "reason_namespace": reason_namespace,
        "idempotency_key": idempotency_key,
        "retry_count": retry_count,
        "checkpoint_reconciled": checkpoint_reconciled,
        "authority_granted": authority_granted,
        "package_identity": package_identity,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256_hex(blob.encode("utf-8"))


def compute_decision_digest(decision: "RouteDecision") -> str:
    canonical = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "idempotency_key": decision.idempotency_key,
        "route": decision.route,
        "reason_code": decision.reason_code,
        "evidence_hash": decision.evidence_hash,
        "retry_count": decision.retry_count,
        "requires_readback": decision.requires_readback,
        "readback_reconciled": decision.readback_reconciled,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256_hex(blob.encode("utf-8"))


@dataclass
class RoutingContext:
    reason_code: str
    reason_namespace: str = ""
    idempotency_key: str = ""
    retry_count: int = 0
    retry_history: List[Dict[str, Any]] = field(default_factory=list)
    checkpoint_reconciled: bool = False
    checkpoint_interrupted: bool = False
    authority_granted_actions: List[str] = field(default_factory=list)
    package_identity: Dict[str, Any] = field(default_factory=dict)
    max_retry: int = DEFAULT_MAX_RETRY
    retry_deadline: Optional[float] = None
    now: Optional[float] = None


def route_failure(ctx: RoutingContext) -> RouteDecision:
    """Route one upstream failure to exactly one bounded next action.

    Pure and deterministic: same RoutingContext yields the same RouteDecision
    and decision_digest; performs no side effects and grants no authority.
    """
    now = ctx.now if ctx.now is not None else time.time()
    evidence_hash = compute_evidence_hash(
        reason_code=ctx.reason_code,
        reason_namespace=ctx.reason_namespace,
        idempotency_key=ctx.idempotency_key,
        retry_count=ctx.retry_count,
        checkpoint_reconciled=ctx.checkpoint_reconciled,
        authority_granted=bool(ctx.authority_granted_actions),
        package_identity=ctx.package_identity,
    )

    def _finish(route: str, reason: str, requires_readback: bool,
                detail: str, retry_count: int = ctx.retry_count) -> RouteDecision:
        decision = RouteDecision(
            route=route,
            reason_code=reason,
            decision_digest="",
            idempotency_key=ctx.idempotency_key,
            verifier_version=ROUTER_VERSION,
            retry_count=retry_count,
            retry_deadline=ctx.retry_deadline,
            requires_readback=requires_readback,
            readback_reconciled=ctx.checkpoint_reconciled,
            prohibited_actions=list(_PROHIBITED),
            evidence_hash=evidence_hash,
            detail=detail,
        )
        decision.decision_digest = compute_decision_digest(decision)
        return decision

    # Authority-boundary violation: any granted action beyond recommendation.
    if ctx.authority_granted_actions:
        return _finish(
            ROUTE_FAIL_CLOSED, REASON_AUTHORITY_VIOLATION, False,
            "router received granted authority; recommend-only boundary violated",
        )

    # Replay conflict: same key but evidence already decided differently.
    # (Caller passes prior_decision_digest; here we flag when interrupted +
    #  reconciled evidence contradicts a prior terminal decision.)
    if ctx.checkpoint_interrupted and not ctx.checkpoint_reconciled and ctx.retry_count > 0:
        return _finish(
            ROUTE_HUMAN_REQUIRED, REASON_REPLAY_CONFLICT, True,
            "interrupted result without reconciled readback under same key",
        )

    entry = DECISION_TABLE.get(ctx.reason_code)
    if entry is None:
        return _finish(
            ROUTE_FAIL_CLOSED, REASON_FAILURE_UNMAPPED, False,
            f"upstream reason code not mapped: {ctx.reason_code!r}",
        )

    base_route, requires_readback, retryable = entry

    # Timeout/unknown/uninterrupted require checkpoint/readback before retry.
    if base_route == ROUTE_BOUNDED_RETRY:
        if not ctx.checkpoint_reconciled:
            return _finish(
                ROUTE_FAIL_CLOSED, REASON_UNKNOWN_OUTCOME, True,
                "retryable reason requires reconciled checkpoint/readback before retry",
            )
        if ctx.retry_count >= ctx.max_retry:
            return _finish(
                ROUTE_FAIL_CLOSED, REASON_RETRY_EXHAUSTED, True,
                f"retry budget exhausted ({ctx.retry_count}>={ctx.max_retry})",
            )
        if ctx.retry_deadline is not None and now > ctx.retry_deadline:
            return _finish(
                ROUTE_FAIL_CLOSED, REASON_RETRY_EXHAUSTED, True,
                "retry deadline passed",
            )
        # Retryable and safe to retry.
        return _finish(
            ROUTE_BOUNDED_RETRY, REASON_BOUNDED_RETRY, True,
            "bounded retry authorized with reconciled zero/known effect",
            retry_count=ctx.retry_count + 1,
        )

    # All other routes are decided directly from the table.
    reason_for_route = {
        ROUTE_REPAIR_INPUT: REASON_REPAIR_INPUT,
        ROUTE_REBUILD_STAGING: REASON_REBUILD_STAGING,
        ROUTE_REVERIFY_READBACK: REASON_REVERIFY_READBACK,
        ROUTE_HUMAN_REQUIRED: REASON_HUMAN_REQUIRED,
        ROUTE_FAIL_CLOSED: REASON_FAIL_CLOSED,
    }.get(base_route, REASON_FAILURE_UNMAPPED)
    return _finish(base_route, reason_for_route, requires_readback, "decision-table route")


def authority_granted(decision: RouteDecision) -> bool:
    """A routing decision never grants authority. Always False."""
    return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Route one package_export failure to exactly one bounded action.")
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--reason-namespace", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--retry-count", type=int, default=0)
    parser.add_argument("--checkpoint-reconciled", action="store_true")
    parser.add_argument("--checkpoint-interrupted", action="store_true")
    parser.add_argument("--max-retry", type=int, default=DEFAULT_MAX_RETRY)
    args = parser.parse_args(argv)

    ctx = RoutingContext(
        reason_code=args.reason_code,
        reason_namespace=args.reason_namespace,
        idempotency_key=args.idempotency_key,
        retry_count=args.retry_count,
        checkpoint_reconciled=args.checkpoint_reconciled,
        checkpoint_interrupted=args.checkpoint_interrupted,
        max_retry=args.max_retry,
    )
    decision = route_failure(ctx)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0 if decision.route in (ROUTE_REPAIR_INPUT, ROUTE_REBUILD_STAGING,
                                    ROUTE_REVERIFY_READBACK, ROUTE_BOUNDED_RETRY,
                                    ROUTE_HUMAN_REQUIRED) else 2


if __name__ == "__main__":
    raise SystemExit(main())
