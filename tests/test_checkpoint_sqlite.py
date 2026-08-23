#!/usr/bin/env python3
"""Tests for SQLite checkpoint store (SCRUM-396, AC11 durable commit)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.node_architect.checkpoint_sqlite import (
    SQLiteCheckpointConflict,
    read_checkpoint,
    store_meta_get,
    store_meta_set,
    write_checkpoint,
)


class SQLiteCheckpointTests(unittest.TestCase):
    def _tmp(self) -> Path:
        d = tempfile.mkdtemp(prefix="sqlite_ckpt_")
        return Path(d) / "store.sqlite"

    def test_write_and_readback(self) -> None:
        p = self._tmp()
        result = write_checkpoint(
            p,
            task_id="SCRUM-396",
            run_id="R1",
            node_id="N1",
            idempotency_key="k-1",
            payload={"revision": 1, "events": []},
            state_digest="sha256:" + "a" * 64,
            record_digest="sha256:" + "b" * 64,
            occurred_at="2026-08-24T01:00:00Z",
            expected_revision=0,
        )
        self.assertEqual(result["task_id"], "SCRUM-396")
        self.assertEqual(result["record_digest"], "sha256:" + "b" * 64)

    def test_cas_conflict_fail_closed(self) -> None:
        p = self._tmp()
        write_checkpoint(
            p,
            task_id="SCRUM-396",
            run_id="R1",
            node_id="N1",
            idempotency_key="k-1",
            payload={"revision": 1},
            state_digest="sha256:" + "a" * 64,
            record_digest="sha256:" + "b" * 64,
            occurred_at="2026-08-24T01:00:00Z",
            expected_revision=0,
        )
        with self.assertRaises(SQLiteCheckpointConflict):
            write_checkpoint(
                p,
                task_id="SCRUM-396",
                run_id="R1",
                node_id="N2",
                idempotency_key="k-2",
                payload={"revision": 2},
                state_digest="sha256:" + "c" * 64,
                record_digest="sha256:" + "d" * 64,
                occurred_at="2026-08-24T01:01:00Z",
                expected_revision=0,  # stale — should conflict
            )

    def test_lease_invalid_fenced(self) -> None:
        p = self._tmp()
        with self.assertRaises(SQLiteCheckpointConflict):
            write_checkpoint(
                p,
                task_id="SCRUM-396",
                run_id="R1",
                node_id="N1",
                idempotency_key="k-3",
                payload={"revision": 1},
                state_digest="sha256:" + "a" * 64,
                record_digest="sha256:" + "b" * 64,
                occurred_at="2026-08-24T01:00:00Z",
                lease_valid=False,
            )

    def test_idempotency_key_unique(self) -> None:
        p = self._tmp()
        write_checkpoint(
            p,
            task_id="SCRUM-396",
            run_id="R1",
            node_id="N1",
            idempotency_key="dup",
            payload={"revision": 1},
            state_digest="sha256:" + "a" * 64,
            record_digest="sha256:" + "b" * 64,
            occurred_at="2026-08-24T01:00:00Z",
        )
        with self.assertRaises(Exception):
            write_checkpoint(
                p,
                task_id="SCRUM-396",
                run_id="R1",
                node_id="N1",
                idempotency_key="dup",  # duplicate
                payload={"revision": 2},
                state_digest="sha256:" + "c" * 64,
                record_digest="sha256:" + "d" * 64,
                occurred_at="2026-08-24T01:01:00Z",
            )

    def test_meta_roundtrip(self) -> None:
        p = self._tmp()
        store_meta_set(p, "cutover_epoch", "2026-08-24T00:00:00Z")
        self.assertEqual(store_meta_get(p, "cutover_epoch"), "2026-08-24T00:00:00Z")

    def test_read_missing_returns_none(self) -> None:
        p = self._tmp()
        self.assertIsNone(read_checkpoint(p, task_id="X", run_id="Y", node_id="Z"))


if __name__ == "__main__":
    unittest.main()
