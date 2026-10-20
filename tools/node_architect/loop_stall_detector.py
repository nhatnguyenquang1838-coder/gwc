"""Detect repeated identical Q0 engineering firings that produced no progress.

A firing that returns the same activity/reason/source head and no selected work
several times in a row is a *stall*, not progress. The detector is read-only: it
classifies, it never escalates, pauses, mints authority or mutates loop state.

Callers (the engineering loop CLI / host wrapper) use the result to emit one
`ENGINEERING_STALL_ESCALATION_REQUIRED` report instead of silently repeating
`ENGINEERING_FRONTIER_WAIT_INPUT`.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

DEFAULT_THRESHOLD = 3

_MATERIAL_STATUSES = {"PROGRESS", "VERIFIED", "SELECTED", "EXECUTED"}


def _key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("activity") or ""),
        str(row.get("reason_code") or ""),
        str(row.get("status") or ""),
        str(row.get("source_head") or ""),
    )


def detect_stall(
    rows: Iterable[Mapping[str, Any]],
    *,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Classify the newest firings. `rows` must be newest-first."""
    ordered = [dict(r) for r in rows]
    if threshold < 2:
        raise ValueError("STALL_THRESHOLD_INVALID")
    if not ordered:
        return {"stalled": False, "streak": 0, "stage": "NO_TELEMETRY", "escalate": False}

    head_status = str(ordered[0].get("status") or "")
    if head_status.upper() in _MATERIAL_STATUSES or ordered[0].get("selected_work"):
        return {"stalled": False, "streak": 0, "stage": "PROGRESS", "escalate": False}

    base = _key(ordered[0])
    streak = 0
    for row in ordered:
        if _key(row) != base:
            break
        streak += 1

    stalled = streak >= threshold
    return {
        "stalled": stalled,
        "streak": streak,
        "stage": "STALL_DETECTED" if stalled else "WITHIN_THRESHOLD",
        "escalate": stalled,
        "stall_key": "|".join(base) if stalled else None,
        "reason_code": "ENGINEERING_STALL_ESCALATION_REQUIRED" if stalled else base[1],
        "threshold": threshold,
        "authority_granted": False,
    }
