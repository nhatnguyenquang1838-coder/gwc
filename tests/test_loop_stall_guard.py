"""Deadlock guard: a stable stall suppresses a fresh Controller dispatch.

A stall is stable across ticks: same activity + reason_code + status +
source_head and no selected work. Re-dispatching the same blocker every firing
is the repeated identical WAIT the user flagged. One report per stall_key;
the original request stays open and is not re-sent.
"""
from __future__ import annotations

import sqlite3

from tools.node_architect.loop_stall_detector import detect_stall


def _seed(db, run, rows):
    db.execute(
        "CREATE TABLE IF NOT EXISTS engineering_firing_telemetry "
        "(run TEXT,firing TEXT,activity TEXT,reason_code TEXT,status TEXT,"
        "source_head TEXT,result_digest TEXT,request_created INTEGER,"
        "PRIMARY KEY(run,firing))"
    )
    for i, (act, reason, status, head) in enumerate(rows):
        db.execute(
            "INSERT OR REPLACE INTO engineering_firing_telemetry "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run, f"native:{100+i}", act, reason, status, head, f"d{i}", 0),
        )
    db.commit()


def test_stall_key_is_stable_and_idempotent(tmp_path):
    db = sqlite3.connect(tmp_path / "cp.sqlite")
    _seed(db, "r", [("M8", "ENGINEERING_FRONTIER_WAIT_INPUT", "WAIT", "h" * 40)] * 3)
    a = detect_stall(_rows(db, "r"))
    b = detect_stall(_rows(db, "r"))
    assert a["stall_key"] == b["stall_key"]
    assert a["stalled"] is True and b["stalled"] is True


def test_frontier_move_invalidates_stall(tmp_path):
    db = sqlite3.connect(tmp_path / "cp.sqlite")
    _seed(db, "r", [("M8", "ENGINEERING_FRONTIER_WAIT_INPUT", "WAIT", "h" * 40)] * 3)
    assert detect_stall(_rows(db, "r"))["stalled"] is True
    db.execute(
        "INSERT OR REPLACE INTO engineering_firing_telemetry VALUES (?,?,?,?,?,?,?,?)",
        ("r", "native:103", "M3", "PLAN_DRIVEN_FRONTIER_SELECTED", "PASS", "h" * 40, "d3", 0),
    )
    db.commit()
    out = detect_stall(_rows(db, "r"))
    assert out["stalled"] is False
    assert out["streak"] == 1


def test_source_head_change_invalidates_stall(tmp_path):
    db = sqlite3.connect(tmp_path / "cp.sqlite")
    _seed(db, "r", [("M8", "ENGINEERING_FRONTIER_WAIT_INPUT", "WAIT", "h" * 40)] * 3)
    assert detect_stall(_rows(db, "r"))["stalled"] is True
    db.execute(
        "INSERT OR REPLACE INTO engineering_firing_telemetry VALUES (?,?,?,?,?,?,?,?)",
        ("r", "native:103", "M8", "ENGINEERING_FRONTIER_WAIT_INPUT", "WAIT", "i" * 40, "d3", 0),
    )
    db.commit()
    assert detect_stall(_rows(db, "r"))["stalled"] is False


def _rows(db, run):
    cur = db.execute(
        "SELECT activity,reason_code,status,source_head "
        "FROM engineering_firing_telemetry WHERE run=? ORDER BY rowid DESC LIMIT 12",
        (run,),
    )
    return [dict(zip(("activity", "reason_code", "status", "source_head"), r)) for r in cur.fetchall()]