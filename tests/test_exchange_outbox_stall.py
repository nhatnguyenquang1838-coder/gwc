"""ExchangeOutbox.stall(): repeated unresolved attempts for one request escalate."""
from __future__ import annotations

import sqlite3

from tools.node_architect.controller_exchange_adapter import ExchangeOutbox

REQ = {"request_digest": "sha256:" + "c" * 64, "marker": "DWA-REVIEW-" + "c" * 16,
       "task_context_digest": "sha256:" + "d" * 64}


def _seed(path, status, times):
    box = ExchangeOutbox(path)
    with box._db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS exchange_attempts "
                   "(id INTEGER PRIMARY KEY, key TEXT NOT NULL, marker TEXT NOT NULL, "
                   "status TEXT NOT NULL, context_digest TEXT, at TEXT NOT NULL)")
        for _ in range(times):
            db.execute("INSERT INTO exchange_attempts(key,marker,status,context_digest,at) "
                       "VALUES (?,?,?,?,?)",
                       (REQ["request_digest"], REQ["marker"], status,
                        REQ["task_context_digest"], "2026-10-21T00:00:00+00:00"))
    return box


def test_outbox_reports_stall_after_threshold(tmp_path):
    box = _seed(tmp_path / "outbox.sqlite", "MESSAGE_SENT_VERIFIED", 3)
    out = box.stall(REQ)
    assert out["stalled"] is True
    assert out["streak"] == 3
    assert out["reason_code"] == "EXCHANGE_STALL_ESCALATION_REQUIRED"


def test_outbox_without_attempts_is_not_stalled(tmp_path):
    box = ExchangeOutbox(tmp_path / "outbox.sqlite")
    out = box.stall(REQ)
    assert out["stalled"] is False
    assert out["stage"] == "NO_ATTEMPTS"


def test_outbox_resolved_attempt_breaks_stall(tmp_path):
    box = _seed(tmp_path / "outbox.sqlite", "CONTROLLER_RESPONSE_VERIFIED", 3)
    out = box.stall(REQ)
    assert out["stalled"] is False
    assert out["stage"] == "RESOLVED_OR_BLOCKED"
