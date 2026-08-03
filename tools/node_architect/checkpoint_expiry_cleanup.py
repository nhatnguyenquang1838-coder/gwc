#!/usr/bin/env python3
"""Deterministic expiry cleanup for GWC runtime_checkpoint nodes.

Implements the ``runtime_checkpoint.checkpoint-expiry-cleanup`` node
(MAT-F4-N09, target maturity M5_REPLAY_SAFE).

The node removes *expired, disposable* checkpoint hints and interrupt frames
without touching append-only runtime events, governance artifacts, or audit
evidence. It models a small in-memory registry of cleanup entries and a
declarative ``CleanupPolicy`` so the same input always yields the same plan,
tombstone markers, and cleanup digest (EARS #4, replay-safe).

Design (consistent with ``checkpoint_store.py`` / ``lease_expiry_recovery.py``):
- ``canonical_json`` / ``digest_payload`` produce a stable, sort-keyed digest.
- Disposable entries carry ``retention_class == "disposable"`` and a finite
  ``expires_at_epoch_ms``; governance and audit entries are exempt and never
  selected for cleanup.
- Cleanup TOMBSTONES disposable expired entries (it never deletes retained
  governance/audit/append-only evidence), and appends one auditable cleanup
  event so the operation is replay-readable.
- A still-valid active resume path wins over cleanup: if ``active_resume``
  points at an entry whose resume token has not expired, that entry is
  retained even when its hint would otherwise be expired (EARS #3).

This module is local and data-oriented. It does not call GitHub, Jira, Slack,
or production services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

# Retention classes exempt from expiry cleanup (retained verbatim).
EXEMPT_RETENTION_CLASSES = frozenset({"governance", "audit"})
# Disposable artifact types eligible for expiry cleanup.
DISPOSABLE_ARTIFACT_TYPES = frozenset({"resume-hint", "interrupt-frame"})
# Append-only / governed artifact types that are never deleted or tombstoned.
RETAINED_ARTIFACT_TYPES = frozenset(
    {"governance-evidence", "audit-evidence", "runtime-event"}
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CleanupEntry:
    """One registry entry subject to expiry cleanup.

    ``expires_at_epoch_ms`` is ``None`` for governance/audit entries that must
    never expire (retained verbatim). ``tombstoned`` marks a disposable entry
    that cleanup has already neutralized.
    """

    entry_id: str
    artifact_type: str
    retention_class: str
    created_at_epoch_ms: int
    expires_at_epoch_ms: int | None
    tombstoned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "artifact_type": self.artifact_type,
            "retention_class": self.retention_class,
            "created_at_epoch_ms": self.created_at_epoch_ms,
            "expires_at_epoch_ms": self.expires_at_epoch_ms,
            "tombstoned": self.tombstoned,
        }


@dataclass(frozen=True)
class CleanupPolicy:
    """Declarative expiry policy (time-boxed, deterministic)."""

    now_epoch_ms: int
    retention_window_ms: int
    # Optional active resume binding: the entry_id of the live resume path and
    # the epoch ms at which its resume token expires. While the token is valid
    # (now < resume_token_expires_epoch_ms), that entry is retained even if its
    # hint would otherwise be expired (EARS #3).
    active_resume_entry_id: str | None = None
    resume_token_expires_epoch_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "now_epoch_ms": self.now_epoch_ms,
            "retention_window_ms": self.retention_window_ms,
            "active_resume_entry_id": self.active_resume_entry_id,
            "resume_token_expires_epoch_ms": self.resume_token_expires_epoch_ms,
        }


def _is_expired(entry: CleanupEntry, now_epoch_ms: int) -> bool:
    if entry.expires_at_epoch_ms is None:
        return False
    return now_epoch_ms >= entry.expires_at_epoch_ms


def _is_active_resume(entry: CleanupEntry, policy: CleanupPolicy) -> bool:
    if policy.active_resume_entry_id is None or policy.resume_token_expires_epoch_ms is None:
        return False
    if entry.entry_id != policy.active_resume_entry_id:
        return False
    # Resume token still valid -> the active resume path wins over cleanup.
    return policy.now_epoch_ms < policy.resume_token_expires_epoch_ms


def classify_entry(entry: CleanupEntry, policy: CleanupPolicy) -> str:
    """Classify one entry's cleanup disposition.

    Returns one of: ``RETAIN_GOVERNANCE``, ``RETAIN_AUDIT``,
    ``RETAIN_APPEND_ONLY``, ``RETAIN_ACTIVE_RESUME`` (valid resume beats
    cleanup), ``TOMBSTONE_EXPIRED``, or ``RETAIN_VALID`` (unexpired disposable).
    """
    # Retained verbatim: governance / audit evidence never expires.
    if entry.retention_class in EXEMPT_RETENTION_CLASSES:
        if entry.retention_class == "governance":
            return "RETAIN_GOVERNANCE"
        return "RETAIN_AUDIT"
    # Append-only runtime events are never deleted or tombstoned.
    if entry.artifact_type in RETAINED_ARTIFACT_TYPES and entry.retention_class != "disposable":
        return "RETAIN_APPEND_ONLY"
    # Still-valid active resume path wins over cleanup (EARS #3).
    if _is_active_resume(entry, policy):
        return "RETAIN_ACTIVE_RESUME"
    # Disposable, already tombstoned -> no-op.
    if entry.tombstoned:
        return "RETAIN_VALID" if not _is_expired(entry, policy.now_epoch_ms) else "TOMBSTONE_EXPIRED"
    # Disposable expired resume hints / interrupt frames -> tombstone.
    if (
        entry.artifact_type in DISPOSABLE_ARTIFACT_TYPES
        and entry.retention_class == "disposable"
        and _is_expired(entry, policy.now_epoch_ms)
    ):
        return "TOMBSTONE_EXPIRED"
    return "RETAIN_VALID"


def plan_cleanup(entries: Sequence[CleanupEntry], policy: CleanupPolicy) -> dict[str, Any]:
    """Determine, without mutating, which entries to tombstone.

    EARS #1/#2/#3: only expired disposable hints and interrupt frames are
    selected; governance/audit/append-only evidence is retained; a valid
    active resume path is retained.
    """
    plan = {
        "tombstone": [],
        "retain": [],
    }
    for entry in entries:
        disposition = classify_entry(entry, policy)
        if disposition == "TOMBSTONE_EXPIRED":
            plan["tombstone"].append(entry.entry_id)
        else:
            plan["retain"].append(entry.entry_id)
    return {
        "schema_version": "1.0",
        "artifact_type": "cleanup-plan",
        "policy": policy.to_dict(),
        "tombstone": sorted(plan["tombstone"]),
        "retain": sorted(plan["retain"]),
        "plan_digest": digest_payload(
            {"policy": policy.to_dict(), "tombstone": sorted(plan["tombstone"]), "retain": sorted(plan["retain"])}
        ),
    }


def apply_cleanup(
    entries: Sequence[CleanupEntry],
    policy: CleanupPolicy,
    *,
    cleanup_id: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Tombstone eligible expired entries and emit auditable cleanup evidence.

    Returns an immutable result carrying the post-cleanup registry, the
    tombstone markers, and a cleanup digest for replay verification (EARS #4).
    Governance/audit/append-only evidence is never removed (EARS #2).
    """
    plan = plan_cleanup(entries, policy)
    tombstoned_ids = set(plan["tombstone"])

    updated: list[CleanupEntry] = []
    tombstones: list[dict[str, Any]] = []
    for entry in entries:
        if entry.entry_id in tombstoned_ids and not entry.tombstoned:
            new_entry = CleanupEntry(
                entry_id=entry.entry_id,
                artifact_type=entry.artifact_type,
                retention_class=entry.retention_class,
                created_at_epoch_ms=entry.created_at_epoch_ms,
                expires_at_epoch_ms=entry.expires_at_epoch_ms,
                tombstoned=True,
            )
            marker = {
                "entry_id": entry.entry_id,
                "artifact_type": entry.artifact_type,
                "retention_class": entry.retention_class,
                "tombstoned_at_epoch_ms": policy.now_epoch_ms,
                "reason": "EXPIRED_DISPOSABLE_HINT",
                "marker": "TOMBSTONE",
            }
            marker["tombstone_digest"] = digest_payload(marker)
            tombstones.append(marker)
        else:
            new_entry = entry
        updated.append(new_entry)

    result = {
        "schema_version": "1.0",
        "artifact_type": "cleanup-result",
        "cleanup_id": cleanup_id,
        "policy": policy.to_dict(),
        "observed_at": observed_at or _now(),
        "tombstoned": tombstones,
        "retained_governance_or_audit": sorted(
            e.entry_id for e in entries if e.retention_class in EXEMPT_RETENTION_CLASSES
        ),
        "registry": [e.to_dict() for e in updated],
        "entries_tombstoned": len(tombstones),
        "entries_retained": len(updated) - len(tombstones),
    }
    result["cleanup_digest"] = digest_payload(
        {k: v for k, v in result.items() if k != "cleanup_digest"}
    )
    return result


def is_replay_equivalent(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Replay-safety: cleanup is idempotent across re-runs (M5).

    Two cleanup results are equivalent when their deterministic core (the post-
    cleanup registry, tombstone markers, and retention set) matches, ignoring
    the per-run ``cleanup_id``, observation time, and the derived cleanup
    digest. A second run over the same registry + policy must produce the same
    tombstone outcome as the first (replay-safe, no stray deletions).
    """

    def stable(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "registry": payload.get("registry"),
            "tombstoned": payload.get("tombstoned"),
            "retained_governance_or_audit": payload.get("retained_governance_or_audit"),
            "policy": payload.get("policy"),
        }

    return digest_payload(stable(first)) == digest_payload(stable(second))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply checkpoint expiry cleanup from a JSON payload.")
    parser.add_argument("--payload", required=True, help="Path to JSON payload describing entries + policy + cleanup_id")
    parser.add_argument("--plan-only", action="store_true", help="Emit the cleanup plan without mutating")
    args = parser.parse_args(argv)

    raw = json.loads(__import__("pathlib").Path(args.payload).read_text(encoding="utf-8"))
    entries = [CleanupEntry(**e) for e in raw["entries"]]
    policy = CleanupPolicy(**raw["policy"])
    if args.plan_only:
        print(json.dumps(plan_cleanup(entries, policy), indent=2, sort_keys=True))
        return 0
    result = apply_cleanup(entries, policy, cleanup_id=raw["cleanup_id"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
