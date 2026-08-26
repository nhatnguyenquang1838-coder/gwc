#!/usr/bin/env python3
"""SCRUM-533 durable external-audit delivery outbox (delivery-domain).

Persists every send intent BEFORE any network call (outbox-before-send), owns
the closed delivery state machine, and provides lease/fencing so concurrent
reconcilers never double-send. Reuses the SCRUM-396 WAL/CAS/readback pattern as
a *pattern only* — this module is delivery-domain and must never be conflated
with checkpoint storage.

Closed delivery states:
    PENDING -> IN_FLIGHT -> ACK_CONFIRMED | ACK_UNKNOWN | RETRY_SCHEDULED
        -> DEAD_LETTERED | PERMANENT_FAILURE | SUPERSEDED | QUARANTINE

Never grants write/approval/merge/deploy/production authority. All G2-G6
authority flags are fixed false.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "delivery-outbox-record"

# SCRUM-533 v3.1 closed state set (incl. QUARANTINE added by V3.1.3).
PENDING = "PENDING"
IN_FLIGHT = "IN_FLIGHT"
ACK_CONFIRMED = "ACK_CONFIRMED"
ACK_UNKNOWN = "ACK_UNKNOWN"
RETRY_SCHEDULED = "RETRY_SCHEDULED"
DEAD_LETTERED = "DEAD_LETTERED"
PERMANENT_FAILURE = "PERMANENT_FAILURE"
SUPERSEDED = "SUPERSEDED"
QUARANTINE = "QUARANTINE"

CLOSED_STATES = frozenset({
    PENDING, IN_FLIGHT, ACK_CONFIRMED, ACK_UNKNOWN, RETRY_SCHEDULED,
    DEAD_LETTERED, PERMANENT_FAILURE, SUPERSEDED, QUARANTINE,
})

# Canonical reason codes (SCRUM-533 v3 + v3.1, §8-compatible).
EVENT_SOURCE_BINDING_CONFLICT = "EVENT_SOURCE_BINDING_CONFLICT"
DESTINATION_UNREGISTERED = "DESTINATION_UNREGISTERED"
DESTINATION_REDIRECT_BLOCKED = "DESTINATION_REDIRECT_BLOCKED"
DESTINATION_PRIVATE_IP_BLOCKED = "DESTINATION_PRIVATE_IP_BLOCKED"
DESTINATION_REVOKED = "DESTINATION_REVOKED"
DESTINATION_POLICY_DRIFT = "DESTINATION_POLICY_DRIFT"
OUTBOX_ILLEGAL_TRANSITION = "OUTBOX_ILLEGAL_TRANSITION"
OUTBOX_LEASE_LOST = "OUTBOX_LEASE_LOST"
OUTBOX_LEASE_CONTENTION = "OUTBOX_LEASE_CONTENTION"
OUTBOX_STORE_UNAVAILABLE = "OUTBOX_STORE_UNAVAILABLE"
OUTBOX_STORE_CORRUPTION = "OUTBOX_STORE_CORRUPTION"
DLQ_REPLAY_TRUST_REVALIDATION_FAILED = "DLQ_REPLAY_TRUST_REVALIDATION_FAILED"
LATE_ACK_REJECTED = "LATE_ACK_REJECTED"
DELIVERY_READY = "DELIVERY_READY"

# Defaults (SCRUM-533 v3.1).
DEFAULT_LEASE_TTL_S = 60
DEFAULT_ACK_FRESHNESS_S = 60
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_MAX_AGE_S = 7 * 24 * 3600
DEFAULT_BACKOFF_MS = 1000
DEFAULT_JITTER_MS = 250

# Guard against transitive imports of checkpoint storage.
_CHECKPOINT_IMPORTS = frozenset({"checkpoint_sqlite", "diff_readback"})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS delivery_outbox (
    projection_target TEXT NOT NULL,
    event_source TEXT,
    event_id TEXT NOT NULL,
    canonical_state_digest TEXT NOT NULL,
    delivery_generation INTEGER NOT NULL DEFAULT 1,
    event_payload_digest TEXT NOT NULL,
    destination_policy_digest TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL,
    reason_class TEXT,
    max_attempts INTEGER NOT NULL,
    max_age_s INTEGER NOT NULL,
    backoff_ms INTEGER NOT NULL,
    jitter_ms INTEGER NOT NULL,
    lease_holder TEXT,
    lease_expires_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    lineage_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (projection_target, event_source, event_id, canonical_state_digest, delivery_generation)
);
CREATE TABLE IF NOT EXISTS delivery_outbox_attempts (
    attempt_id TEXT PRIMARY KEY,
    semantic_event_id TEXT NOT NULL,
    delivery_generation INTEGER NOT NULL,
    destination_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    request_digest TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    response_class TEXT,
    ack_binding_json TEXT,
    retry_disposition TEXT,
    transport_evidence_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS delivery_outbox_dlq (
    dlq_id TEXT PRIMARY KEY,
    semantic_event_id TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    state TEXT NOT NULL,
    lineage_json TEXT NOT NULL,
    quarantined_at REAL NOT NULL,
    trust_revalidation_json TEXT,
    reason_code TEXT
);
CREATE TABLE IF NOT EXISTS store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class OutboxConflict(RuntimeError):
    """Raised on CAS/lease/binding guard failure (fail-closed)."""


class OutboxStoreUnavailable(RuntimeError):
    """Raised when the canonical store is unavailable (fail-closed)."""


class OutboxStoreCorruption(RuntimeError):
    """Raised on readback/integrity failure (rows must quarantine)."""


def _connect(path: Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(str(path), timeout=5)
    except sqlite3.Error as exc:  # pragma: no cover - environment-dependent
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def _now() -> float:
    return time.time()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _assert_no_checkpoint_import(module_names: Sequence[str]) -> None:
    for name in module_names:
        if name in _CHECKPOINT_IMPORTS:
            raise ImportError(
                f"{name} is SCRUM-396 checkpoint-scoped and must not be imported "
                "by the delivery outbox (SCRUM-533 boundary)."
            )


def _semantic_event_id(projection_target: str, event_source: str | None,
                       event_id: str, canonical_state_digest: str) -> str:
    """Deterministic semantic identity = record key (SCRUM-533 L1.2)."""
    return _digest({
        "projection_target": projection_target,
        "event_source": event_source,
        "event_id": event_id,
        "canonical_state_digest": canonical_state_digest,
    })


def init_store(path: Path) -> None:
    """Create schema if absent (idempotent). Fail-closed on store error."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(path) as conn:
            conn.executescript(_SCHEMA_SQL)
    except sqlite3.Error as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc


def _readback_digest(conn: sqlite3.Connection, path: Path) -> str:
    """Fail-closed integrity readback of the canonical store."""
    rows = conn.execute(
        "SELECT projection_target, event_source, event_id, canonical_state_digest, "
        "delivery_generation, event_payload_digest, destination_policy_digest, "
        "destination_id, state, attempt_no FROM delivery_outbox"
    ).fetchall()
    return _digest([tuple(r) for r in rows])


def _readback_after_write(path: Path, expected: str) -> None:
    try:
        with _connect(path) as conn:
            actual = _readback_digest(conn, path)
    except sqlite3.Error as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc
    if actual != expected:
        raise OutboxStoreCorruption(OUTBOX_STORE_CORRUPTION)


def enqueue(
    path: Path,
    *,
    projection_target: str,
    event_source: str | None,
    event_id: str,
    canonical_state_digest: str,
    event_payload_digest: str,
    destination_policy_digest: str,
    destination_id: str,
    delivery_generation: int = 1,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_age_s: int = DEFAULT_MAX_AGE_S,
    backoff_ms: int = DEFAULT_BACKOFF_MS,
    jitter_ms: int = DEFAULT_JITTER_MS,
    enforce_source: bool = True,
) -> dict[str, Any]:
    """Persist a send intent as PENDING BEFORE any network call (outbox-before-send).

    Raises OutboxConflict when the semantic identity already exists in a
    non-terminal state, or when event_source is inconsistent (SCRUM-533 L1.1).
    """
    if enforce_source and event_source is not None:
        import re
        if not re.fullmatch(r"gwc\.[a-z0-9]+(?:[.-][a-z0-9]+)*\.v[0-9]+\.[0-9]+", event_source):
            raise OutboxConflict(EVENT_SOURCE_BINDING_CONFLICT)
        expected = f"gwc.node-architect.{projection_target}.v{SCHEMA_VERSION}"
        if event_source != expected:
            raise OutboxConflict(EVENT_SOURCE_BINDING_CONFLICT)

    now = _now()
    rec = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "semantic_event_id": _semantic_event_id(
            projection_target, event_source, event_id, canonical_state_digest),
        "projection_target": projection_target,
        "event_source": event_source,
        "event_id": event_id,
        "canonical_state_digest": canonical_state_digest,
        "event_payload_digest": event_payload_digest,
        "destination_policy_digest": destination_policy_digest,
        "destination_id": destination_id,
        "delivery_generation": delivery_generation,
        "state": PENDING,
        "attempt_no": 0,
        "created_at": now,
        "updated_at": now,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    try:
        with _connect(path) as conn:
            try:
                conn.execute(
                    "INSERT INTO delivery_outbox (projection_target, event_source, event_id, "
                    "canonical_state_digest, delivery_generation, event_payload_digest, "
                    "destination_policy_digest, destination_id, state, attempt_no, next_attempt_at, "
                    "reason_class, max_attempts, max_age_s, backoff_ms, jitter_ms, lease_holder, "
                    "lease_expires_at, created_at, updated_at, lineage_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,NULL,NULL,?,?,'[]')",
                    (projection_target, event_source, event_id, canonical_state_digest,
                     delivery_generation, event_payload_digest, destination_policy_digest,
                     destination_id, PENDING, 0, max_attempts, max_age_s, backoff_ms, jitter_ms,
                     now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise OutboxConflict("DELIVERY_IDENTITY_ALREADY_ENQUEUED") from exc
            expected = _readback_digest(conn, path)
        _readback_after_write(path, expected)
    except (sqlite3.Error, OutboxStoreUnavailable) as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc
    return rec


def acquire_lease(
    path: Path,
    *,
    projection_target: str,
    event_source: str | None,
    event_id: str,
    canonical_state_digest: str,
    delivery_generation: int,
    worker_id: str,
    lease_ttl_s: int = DEFAULT_LEASE_TTL_S,
) -> dict[str, Any]:
    """CAS-atomic lease acquisition (SCRUM-533 v3.1 L3.3).

    Returns the leased row on success. Raises OutboxConflict(OUTBOX_LEASE_CONTENTION)
    when another worker holds an unexpired lease.
    """
    try:
        with _connect(path) as conn:
            key = (projection_target, event_source, event_id, canonical_state_digest, delivery_generation)
            row = conn.execute(
                "SELECT * FROM delivery_outbox WHERE projection_target=? AND "
                "event_source IS ? AND event_id=? AND canonical_state_digest=? AND delivery_generation=?",
                key,
            ).fetchone()
            if row is None:
                raise OutboxConflict("DELIVERY_RECORD_NOT_FOUND")
            if row["state"] in (ACK_CONFIRMED, DEAD_LETTERED, PERMANENT_FAILURE, SUPERSEDED):
                raise OutboxConflict("DELIVERY_TERMINAL_STATE")
            if row["lease_holder"] is not None and row["lease_expires_at"] > _now():
                raise OutboxConflict(OUTBOX_LEASE_CONTENTION)
            now = _now()
            conn.execute(
                "UPDATE delivery_outbox SET lease_holder=?, lease_expires_at=?, state=?, "
                "updated_at=? WHERE projection_target=? AND event_source IS ? AND event_id=? "
                "AND canonical_state_digest=? AND delivery_generation=? AND "
                "(lease_holder IS NULL OR lease_expires_at < ?)",
                (worker_id, now + lease_ttl_s, IN_FLIGHT, now,
                 *key, _now()),
            )
            expected = _readback_digest(conn, path)
        _readback_after_write(path, expected)
        return {
            "semantic_event_id": _semantic_event_id(
                projection_target, event_source, event_id, canonical_state_digest),
            "lease_holder": worker_id,
            "lease_expires_at": now + lease_ttl_s,
            "state": IN_FLIGHT,
        }
    except (sqlite3.Error, OutboxStoreUnavailable) as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc


def _verify_lease(path: Path, *, key: tuple, worker_id: str) -> sqlite3.Row:
    """Fence: re-verify the worker still holds the lease before any send/transition."""
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM delivery_outbox WHERE projection_target=? AND event_source IS ? "
            "AND event_id=? AND canonical_state_digest=? AND delivery_generation=?",
            key,
        ).fetchone()
    if row is None or row["lease_holder"] != worker_id or row["lease_expires_at"] <= _now():
        raise OutboxConflict(OUTBOX_LEASE_LOST)
    return row


def transition(
    path: Path,
    *,
    projection_target: str,
    event_source: str | None,
    event_id: str,
    canonical_state_digest: str,
    delivery_generation: int,
    worker_id: str,
    to_state: str,
    reason_class: str | None = None,
) -> dict[str, Any]:
    """Guard-railed state transition (SCRUM-533 v3 L3.1). Fence first; illegal
    transitions fail closed (OUTBOX_ILLEGAL_TRANSITION)."""
    if to_state not in CLOSED_STATES:
        raise OutboxConflict(OUTBOX_ILLEGAL_TRANSITION)
    key = (projection_target, event_source, event_id, canonical_state_digest, delivery_generation)
    try:
        row = _verify_lease(path, key=key, worker_id=worker_id)
        allowed = {
            IN_FLIGHT: {ACK_CONFIRMED, ACK_UNKNOWN, RETRY_SCHEDULED, DEAD_LETTERED,
                        PERMANENT_FAILURE, QUARANTINE},
            RETRY_SCHEDULED: {IN_FLIGHT, DEAD_LETTERED, PERMANENT_FAILURE, QUARANTINE},
            ACK_UNKNOWN: {RETRY_SCHEDULED, DEAD_LETTERED, PERMANENT_FAILURE, QUARANTINE},
            PENDING: {IN_FLIGHT, DEAD_LETTERED, PERMANENT_FAILURE, QUARANTINE, SUPERSEDED},
            QUARANTINE: {DEAD_LETTERED, PERMANENT_FAILURE, RETRY_SCHEDULED},
        }
        if to_state not in allowed.get(row["state"], set()):
            raise OutboxConflict(OUTBOX_ILLEGAL_TRANSITION)
        now = _now()
        attempt_no = row["attempt_no"]
        if to_state == RETRY_SCHEDULED:
            attempt_no += 1
            next_attempt = now + (row["backoff_ms"] / 1000.0) * (2 ** (attempt_no - 1)) + (row["jitter_ms"] / 1000.0)
        else:
            next_attempt = None
        with _connect(path) as conn:
            conn.execute(
                "UPDATE delivery_outbox SET state=?, reason_class=COALESCE(?, reason_class), "
                "attempt_no=?, next_attempt_at=?, lease_holder=NULL, lease_expires_at=NULL, "
                "updated_at=? WHERE projection_target=? AND event_source IS ? AND event_id=? "
                "AND canonical_state_digest=? AND delivery_generation=?",
                (to_state, reason_class, attempt_no, next_attempt, now, *key),
            )
            expected = _readback_digest(conn, path)
        _readback_after_write(path, expected)
    except (sqlite3.Error, OutboxStoreUnavailable) as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc
    return {"state": to_state, "attempt_no": attempt_no, "next_attempt_at": next_attempt}


def record_attempt(
    path: Path,
    *,
    semantic_event_id: str,
    delivery_generation: int,
    destination_id: str,
    attempt_no: int,
    request_digest: str,
    response_class: str,
    ack_binding: dict[str, Any] | None = None,
    retry_disposition: str | None = None,
    transport_evidence: dict[str, Any] | None = None,
) -> None:
    """Append an attempt row (immutable transport evidence)."""
    try:
        with _connect(path) as conn:
            conn.execute(
                "INSERT INTO delivery_outbox_attempts (attempt_id, semantic_event_id, "
                "delivery_generation, destination_id, attempt_no, request_digest, started_at, "
                "ended_at, response_class, ack_binding_json, retry_disposition, "
                "transport_evidence_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"{semantic_event_id[:16]}:{delivery_generation}:{attempt_no}",
                    semantic_event_id, delivery_generation, destination_id, attempt_no,
                    request_digest, _now(), _now(), response_class,
                    _canonical_json(ack_binding) if ack_binding else None,
                    retry_disposition,
                    _canonical_json(transport_evidence) if transport_evidence else "{}",
                ),
            )
            expected = _readback_digest(conn, path)
        _readback_after_write(path, expected)
    except (sqlite3.Error, OutboxStoreUnavailable) as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc


def verify_ack(path: Path, *, ack: dict[str, Any], worker_id: str) -> tuple[bool, str]:
    """ACK_VERIFIED 5-way binding + freshness + replay resistance (SCRUM-533 L2.2).

    A bare 2xx (no authenticated 5-way binding) is never ACK_CONFIRMED; it routes
    to ACK_UNKNOWN. Returns (verified, reason_code).
    """
    try:
        with _connect(path) as conn:
            row = conn.execute(
                "SELECT * FROM delivery_outbox WHERE event_id=? ORDER BY delivery_generation DESC LIMIT 1",
                (ack.get("event_id"),),
            ).fetchone()
    except sqlite3.Error as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc
    if row is None:
        return False, "DELIVERY_RECORD_NOT_FOUND"
    required = {
        "destination_id", "event_source", "event_id", "delivery_generation",
        "request_digest", "payload_digest", "created",
    }
    if not isinstance(ack, dict) or not required.issubset(ack):
        return False, "ACK_BINDING_INCOMPLETE"
    if ack["destination_id"] != row["destination_id"] or ack["event_id"] != row["event_id"]:
        return False, "ACK_WRONG_DESTINATION"
    if ack["delivery_generation"] < row["delivery_generation"]:
        return False, LATE_ACK_REJECTED
    if ack["delivery_generation"] > row["delivery_generation"]:
        return False, "ACK_FUTURE_GENERATION"
    try:
        created = float(ack["created"])
    except (TypeError, ValueError):
        return False, "ACK_FRESHNESS_INVALID"
    if _now() - created > DEFAULT_ACK_FRESHNESS_S:
        return False, "ACK_STALE"
    if not ack.get("signature_proof"):
        return False, "ACK_NOT_AUTHENTICATED"
    if not _verify_lease(path, key=(
        row["projection_target"], row["event_source"], row["event_id"],
        row["canonical_state_digest"], row["delivery_generation"],
    ), worker_id=worker_id)["lease_holder"]:
        return False, OUTBOX_LEASE_LOST
    return True, "ACK_VERIFIED"


def discover_restart(path: Path) -> list[dict[str, Any]]:
    """SCRUM-533 L3.2: scan non-terminal states after restart."""
    try:
        with _connect(path) as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_outbox WHERE state IN "
                "('PENDING','IN_FLIGHT','ACK_UNKNOWN','RETRY_SCHEDULED')"
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc


def quarantine(
    path: Path,
    *,
    semantic_event_id: str,
    destination_id: str,
    reason_code: str,
    trust_revalidation: dict[str, Any] | None = None,
) -> None:
    """Route a row to QUARANTINE (SCRUM-533 v3.1 V3.1.3 / L3.9 corruption or
    ACK_UNKNOWN exhaustion boundary)."""
    try:
        with _connect(path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO delivery_outbox_dlq (dlq_id, semantic_event_id, "
                "destination_id, state, lineage_json, quarantined_at, trust_revalidation_json, reason_code) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"{semantic_event_id[:16]}:q", semantic_event_id, destination_id, QUARANTINE,
                 _canonical_json([{"state": QUARANTINE, "at": _now()}]), _now(),
                 _canonical_json(trust_revalidation) if trust_revalidation else None,
                 reason_code),
            )
            expected = _readback_digest(conn, path)
        _readback_after_write(path, expected)
    except (sqlite3.Error, OutboxStoreUnavailable) as exc:
        raise OutboxStoreUnavailable(OUTBOX_STORE_UNAVAILABLE) from exc


def replay_trust_revalidate(path: Path, *, destination: dict[str, Any],
                            profile: dict[str, Any], credential_version: int) -> dict[str, bool]:
    """SCRUM-533 v3.1 V3.1.1: 5-step DLQ-replay trust re-validation.

    Returns a dict of check->bool. Replay is only permitted when ALL pass;
    any failure fails closed (DLQ_REPLAY_TRUST_REVALIDATION_FAILED).
    """
    checks = {
        "registered": bool(profile.get("destination_id")),
        "not_revoked": not (profile.get("revocation", {}).get("revoked_at")),
        "credential_current": (profile.get("auth", {}).get("credential_version", 0) >= credential_version),
        "policy_digest_match": (
            profile.get("destination_policy_digest")
            == _digest({k: v for k, v in destination.items() if k != "destination_policy_digest"})
        ),
        "ack_capable": bool(profile.get("supports_ack", True)),
    }
    return checks
