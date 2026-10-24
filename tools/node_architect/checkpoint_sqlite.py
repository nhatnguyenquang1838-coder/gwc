#!/usr/bin/env python3
"""SQLite transactional checkpoint store for GWC node execution (SCRUM-396, AC11).

Durable commit via a single SQLite transaction (atomic expected-revision CAS at
the storage boundary), lease/fencing validation before commit, and independent
reload/readback before success. Never mutates historical evidence in place;
copy-on-write semantics via revision rows.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoint_events (
    revision INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    state_digest TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS store_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SQLiteCheckpointConflict(RuntimeError):
    """Raised when a checkpoint write fails its CAS/binding guard."""


def _connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
    conn.row_factory = sqlite3.Row
    return conn


def init_store(path: Path) -> None:
    """Create schema if absent (idempotent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(SCHEMA_SQL)


def _expected_revision(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(revision), 0) AS r FROM checkpoint_events").fetchone()
    return int(row["r"])


def write_checkpoint(
    path: Path,
    *,
    task_id: str,
    run_id: str,
    node_id: str,
    idempotency_key: str,
    payload: Mapping[str, Any],
    state_digest: str,
    record_digest: str,
    occurred_at: str,
    expected_revision: int | None = None,
    lease_id: str | None = None,
    fencing_token: str | int | None = None,
    lease_valid: bool = True,
) -> dict[str, Any]:
    """Commit one checkpoint row atomically with expected-revision CAS.

    - expected_revision must equal the current MAX(revision) or the write fails
      closed (SQLiteCheckpointConflict) — prevents cross-process lost update.
    - lease_valid=False fails closed (fencing).
    - On success, reload + readback the committed row and verify record_digest.
    """
    if not lease_valid:
        raise SQLiteCheckpointConflict("lease/fencing invalid")
    init_store(path)
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = _expected_revision(conn)
        if expected_revision is not None and current != expected_revision:
            raise SQLiteCheckpointConflict(
                f"CAS mismatch: expected {expected_revision}, got {current}"
            )
        if not lease_valid:
            raise SQLiteCheckpointConflict("lease/fencing invalid")

        payload_json = json.dumps(dict(payload), sort_keys=True)
        conn.execute(
            "INSERT INTO checkpoint_events "
            "(task_id, run_id, node_id, idempotency_key, payload_json, state_digest, record_digest, occurred_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (task_id, run_id, node_id, idempotency_key, payload_json, state_digest, record_digest, occurred_at),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Independent reload + readback before success (AC11).
    readback = read_checkpoint(path, task_id=task_id, run_id=run_id, node_id=node_id)
    if readback is None or readback.get("record_digest") != record_digest:
        raise SQLiteCheckpointConflict("readback digest mismatch after commit")
    return readback


def read_checkpoint(
    path: Path, *, task_id: str, run_id: str, node_id: str
) -> dict[str, Any] | None:
    """Read the latest row without creating a store, schema or WAL policy."""
    if not path.is_file():
        return None
    conn = _connect(path, read_only=True)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkpoint_events'").fetchone() is None:
            return None
        row = conn.execute(
            "SELECT * FROM checkpoint_events "
            "WHERE task_id=? AND run_id=? AND node_id=? "
            "ORDER BY revision DESC LIMIT 1",
            (task_id, run_id, node_id),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        return {
            "revision": row["revision"],
            "task_id": row["task_id"],
            "run_id": row["run_id"],
            "node_id": row["node_id"],
            "idempotency_key": row["idempotency_key"],
            "payload": payload,
            "state_digest": row["state_digest"],
            "record_digest": row["record_digest"],
            "occurred_at": row["occurred_at"],
        }
    finally:
        conn.close()


def store_meta_get(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    conn = _connect(path, read_only=True)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='store_meta'").fetchone() is None:
            return None
        row = conn.execute("SELECT value FROM store_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def store_meta_set(path: Path, key: str, value: str) -> None:
    init_store(path)
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO store_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
