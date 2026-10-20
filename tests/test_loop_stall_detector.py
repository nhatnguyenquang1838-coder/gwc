"""Stall detector tests: repeated identical firings must escalate once."""
from __future__ import annotations

from tools.node_architect.loop_stall_detector import detect_stall

ROW = {"activity": "M8", "reason_code": "ENGINEERING_FRONTIER_WAIT_INPUT", "status": "WAIT", "source_head": "a" * 40}


def test_no_telemetry_is_not_a_stall() -> None:
    out = detect_stall([])
    assert out["stalled"] is False
    assert out["stage"] == "NO_TELEMETRY"


def test_two_identical_firings_are_within_threshold() -> None:
    out = detect_stall([ROW, dict(ROW)], threshold=3)
    assert out["stalled"] is False
    assert out["streak"] == 2
    assert out["stage"] == "WITHIN_THRESHOLD"


def test_three_identical_firings_escalate_once() -> None:
    out = detect_stall([ROW, dict(ROW), dict(ROW)], threshold=3)
    assert out["stalled"] is True
    assert out["streak"] == 3
    assert out["reason_code"] == "ENGINEERING_STALL_ESCALATION_REQUIRED"
    assert out["authority_granted"] is False
    assert out["stall_key"]


def test_source_head_change_breaks_the_streak() -> None:
    moved = dict(ROW, source_head="b" * 40)
    out = detect_stall([moved, dict(ROW), dict(ROW)], threshold=2)
    assert out["stalled"] is False
    assert out["streak"] == 1


def test_selected_work_is_progress_not_stall() -> None:
    out = detect_stall([dict(ROW, selected_work={"id": "CF-RED"})], threshold=2)
    assert out["stalled"] is False
    assert out["stage"] == "PROGRESS"


def test_material_status_is_progress_not_stall() -> None:
    out = detect_stall([dict(ROW, status="VERIFIED")], threshold=2)
    assert out["stalled"] is False
    assert out["stage"] == "PROGRESS"
