"""SQLite-backed runtime store for the GWC pilot runtime."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteRuntimeStore:
    """Minimal durable runtime store backed by SQLite."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or ":memory:"
        self._local = threading.local()
        self._initialize()

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.connection = conn
        return conn

    def _initialize(self) -> None:
        conn = self._connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS durable_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                parent_event_id TEXT,
                event_type TEXT NOT NULL,
                occurred_at_utc TEXT NOT NULL,
                actor_kind TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_execution_mode TEXT,
                gate TEXT NOT NULL,
                node_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                runtime_version TEXT NOT NULL,
                node_version TEXT NOT NULL,
                checkpoint_revision INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT,
                evidence_refs TEXT NOT NULL DEFAULT '[]',
                payload TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS durable_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                expected_revision INTEGER NOT NULL,
                lease_owner TEXT,
                lease_expires_at_utc TEXT,
                fencing_token INTEGER,
                current_node_id TEXT NOT NULL,
                current_node_version TEXT NOT NULL,
                next_node_id TEXT,
                next_action TEXT,
                gate TEXT NOT NULL,
                status TEXT NOT NULL,
                pending_action_ids TEXT NOT NULL DEFAULT '[]',
                scope_hash TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_actions (
                action_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                readback_required INTEGER NOT NULL DEFAULT 1,
                readback_status TEXT NOT NULL DEFAULT 'pending',
                external_reference TEXT,
                readback_evidence_refs TEXT NOT NULL DEFAULT '[]',
                last_error TEXT,
                requested_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_run_sequence ON durable_events(run_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_events_run_type ON durable_events(run_id, event_type);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON durable_checkpoints(run_id);
            CREATE INDEX IF NOT EXISTS idx_pending_run ON pending_actions(run_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_idempotency ON pending_actions(run_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
            """
        )
        conn.commit()

    def close(self) -> None:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.connection = None

    def append_event(self, event: Mapping[str, Any]) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO durable_events (
                event_id, run_id, sequence, parent_event_id, event_type, occurred_at_utc,
                actor_kind, actor_id, actor_execution_mode, gate, node_id, outcome,
                runtime_version, node_version, checkpoint_revision, idempotency_key,
                evidence_refs, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["run_id"],
                event["sequence"],
                event.get("parent_event_id"),
                event["event_type"],
                event["occurred_at_utc"],
                event["actor"]["kind"],
                event["actor"]["id"],
                event["actor"].get("execution_mode"),
                event["gate"],
                event["node_id"],
                event["outcome"],
                event["runtime_version"],
                event["node_version"],
                event.get("checkpoint_revision", 0),
                event.get("idempotency_key"),
                json.dumps(event.get("evidence_refs", [])),
                json.dumps(event.get("payload", {})),
            ),
        )
        conn.commit()

    def read_events(self, run_id: str, from_sequence: int = 0, limit: int = 100) -> Sequence[dict[str, Any]]:
        conn = self._connection()
        rows = conn.execute(
            """
            SELECT * FROM durable_events
            WHERE run_id = ? AND sequence >= ?
            ORDER BY sequence ASC
            LIMIT ?
            """,
            (run_id, from_sequence, limit),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def read_last_event(self, run_id: str) -> dict[str, Any] | None:
        conn = self._connection()
        row = conn.execute(
            """
            SELECT * FROM durable_events
            WHERE run_id = ?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        return self._row_to_event(row) if row else None

    def write_checkpoint(self, checkpoint: Mapping[str, Any]) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO durable_checkpoints (
                checkpoint_id, run_id, revision, expected_revision, lease_owner,
                lease_expires_at_utc, fencing_token, current_node_id, current_node_version,
                next_node_id, next_action, gate, status, pending_action_ids, scope_hash,
                created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint["checkpoint_id"],
                checkpoint["run_id"],
                checkpoint["revision"],
                checkpoint["cas"]["expected_revision"],
                checkpoint.get("lease", {}).get("owner"),
                checkpoint.get("lease", {}).get("expires_at_utc"),
                checkpoint.get("lease", {}).get("fencing_token"),
                checkpoint["current_node_id"],
                checkpoint["current_node_version"],
                checkpoint.get("next_node_id"),
                checkpoint.get("next_action"),
                checkpoint["gate"],
                checkpoint["status"],
                json.dumps(checkpoint.get("pending_action_ids", [])),
                checkpoint.get("scope_hash"),
                checkpoint["created_at_utc"],
                checkpoint["updated_at_utc"],
            ),
        )
        conn.commit()

    def read_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        conn = self._connection()
        row = conn.execute(
            "SELECT * FROM durable_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        return self._row_to_checkpoint(row) if row else None

    def compare_and_swap_checkpoint(self, checkpoint_id: str, expected_revision: int, updates: Mapping[str, Any]) -> bool:
        checkpoint = self.read_checkpoint(checkpoint_id)
        if checkpoint is None or checkpoint["revision"] != expected_revision:
            return False
        merged = dict(checkpoint)
        merged.update(updates)
        merged["revision"] = expected_revision + 1
        merged["cas"] = {"expected_revision": merged["revision"]}
        merged["updated_at_utc"] = _utcnow()
        self.write_checkpoint(merged)
        return True

    def acquire_lease(self, checkpoint_id: str, owner: str, ttl_seconds: int, fencing_token: int) -> bool:
        checkpoint = self.read_checkpoint(checkpoint_id)
        if checkpoint is None:
            return False
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        updates = {
            "lease": {
                "owner": owner,
                "expires_at_utc": expires.isoformat(),
                "fencing_token": fencing_token,
            }
        }
        return self.compare_and_swap_checkpoint(checkpoint_id, checkpoint["revision"], updates)

    def renew_lease(self, checkpoint_id: str, owner: str, fencing_token: int, ttl_seconds: int) -> bool:
        checkpoint = self.read_checkpoint(checkpoint_id)
        if checkpoint is None:
            return False
        lease = checkpoint.get("lease") or {}
        if lease.get("owner") != owner or lease.get("fencing_token") != fencing_token:
            return False
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        updates = {"lease": {"owner": owner, "expires_at_utc": expires.isoformat(), "fencing_token": fencing_token}}
        return self.compare_and_swap_checkpoint(checkpoint_id, checkpoint["revision"], updates)

    def submit_pending_action(self, action: Mapping[str, Any]) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO pending_actions (
                action_id, run_id, adapter_id, operation, idempotency_key, status,
                attempt_count, readback_required, readback_status, external_reference,
                readback_evidence_refs, last_error, requested_at_utc, updated_at_utc, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action["action_id"],
                action["run_id"],
                action["adapter_id"],
                action["operation"],
                action["idempotency_key"],
                action["status"],
                action["attempt_count"],
                action.get("readback_required", True),
                action.get("readback_status", "pending"),
                action.get("external_reference"),
                json.dumps(action.get("readback_evidence_refs", [])),
                action.get("last_error"),
                action["requested_at_utc"],
                action["updated_at_utc"],
                json.dumps(action.get("payload", {})),
            ),
        )
        conn.commit()

    def update_pending_action(self, action_id: str, updates: Mapping[str, Any]) -> bool:
        conn = self._connection()
        sets = []
        values = []
        for key, value in updates.items():
            sets.append(f"{key} = ?")
            values.append(value)
        values.append(_utcnow())
        values.append(action_id)
        cursor = conn.execute(
            f"UPDATE pending_actions SET {', '.join(sets)}, updated_at_utc = ? WHERE action_id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0

    def read_pending_action(self, action_id: str) -> dict[str, Any] | None:
        conn = self._connection()
        row = conn.execute(
            "SELECT * FROM pending_actions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        return self._row_to_pending_action(row) if row else None

    def find_pending_action_by_idempotency_key(self, run_id: str, idempotency_key: str) -> dict[str, Any] | None:
        conn = self._connection()
        row = conn.execute(
            "SELECT * FROM pending_actions WHERE run_id = ? AND idempotency_key = ?",
            (run_id, idempotency_key),
        ).fetchone()
        return self._row_to_pending_action(row) if row else None

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "durable-event",
            "event_id": row["event_id"],
            "run_id": row["run_id"],
            "sequence": row["sequence"],
            "parent_event_id": row["parent_event_id"],
            "event_type": row["event_type"],
            "occurred_at_utc": row["occurred_at_utc"],
            "actor": {
                "kind": row["actor_kind"],
                "id": row["actor_id"],
                "execution_mode": row["actor_execution_mode"],
            },
            "gate": row["gate"],
            "node_id": row["node_id"],
            "outcome": row["outcome"],
            "runtime_version": row["runtime_version"],
            "node_version": row["node_version"],
            "checkpoint_revision": row["checkpoint_revision"],
            "idempotency_key": row["idempotency_key"],
            "evidence_refs": json.loads(row["evidence_refs"]),
            "payload": json.loads(row["payload"]),
        }

    @staticmethod
    def _row_to_checkpoint(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "durable-checkpoint",
            "checkpoint_id": row["checkpoint_id"],
            "run_id": row["run_id"],
            "revision": row["revision"],
            "cas": {"expected_revision": row["expected_revision"]},
            "lease": {
                "owner": row["lease_owner"],
                "expires_at_utc": row["lease_expires_at_utc"],
                "fencing_token": row["fencing_token"],
            } if row["lease_owner"] else None,
            "current_node_id": row["current_node_id"],
            "current_node_version": row["current_node_version"],
            "next_node_id": row["next_node_id"],
            "next_action": row["next_action"],
            "gate": row["gate"],
            "status": row["status"],
            "pending_action_ids": json.loads(row["pending_action_ids"]),
            "scope_hash": row["scope_hash"],
            "created_at_utc": row["created_at_utc"],
            "updated_at_utc": row["updated_at_utc"],
        }

    @staticmethod
    def _row_to_pending_action(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "pending-action",
            "action_id": row["action_id"],
            "run_id": row["run_id"],
            "adapter_id": row["adapter_id"],
            "operation": row["operation"],
            "idempotency_key": row["idempotency_key"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "readback_required": bool(row["readback_required"]),
            "readback_status": row["readback_status"],
            "external_reference": row["external_reference"],
            "readback_evidence_refs": json.loads(row["readback_evidence_refs"]),
            "last_error": row["last_error"],
            "requested_at_utc": row["requested_at_utc"],
            "updated_at_utc": row["updated_at_utc"],
            "payload": json.loads(row["payload"]),
        }
