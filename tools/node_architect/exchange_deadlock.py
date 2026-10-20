"""Deadlock detection for Controller↔Executor exchange mode.

The engineering workflow has its own stall guard (``loop_stall_detector``) for
M8 WAIT firings. The *exchange* mode is a different surface: a single reserved
request can be re-staged, re-typed or re-read on every wakeup while the
Controller never answers, which produces the same "repeated identical attempt"
deadlock in a different place.

This module classifies that pattern. It is read-only: it never sends, reserves,
reconciles, mints authority or mutates outbox state.

A stall here is: the SAME request (same ``request_digest`` / ``marker`` /
``conversation_url``) left in the SAME unresolved status for ``threshold``
consecutive attempts, with no Controller response in between.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

DEFAULT_THRESHOLD = 3

# Statuses that mean "we are still waiting on the Controller".
UNRESOLVED = {"EXCHANGE_REQUESTED", "MESSAGE_SENT_VERIFIED", "CONTROLLER_ACTION_REQUIRED"}


def _key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("request_digest") or ""),
        str(row.get("marker") or ""),
        str(row.get("status") or ""),
    )


def detect_exchange_stall(
    attempts: Iterable[Mapping[str, Any]],
    *,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Classify consecutive exchange attempts for the same request.

    ``attempts`` must be newest-first. Only unresolved statuses can form a
    stall; a Controller response (``CONTROLLER_RESPONSE_VERIFIED``) or any
    terminal/blocked outcome breaks the run.
    """
    ordered = [dict(a) for a in attempts]
    if threshold < 2:
        raise ValueError("EXCHANGE_STALL_THRESHOLD_INVALID")
    if not ordered:
        return {"stalled": False, "streak": 0, "stage": "NO_ATTEMPTS", "escalate": False}

    head_status = str(ordered[0].get("status") or "")
    if head_status not in UNRESOLVED:
        return {"stalled": False, "streak": 0, "stage": "RESOLVED_OR_BLOCKED", "escalate": False}

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
        "stage": "EXCHANGE_STALL_DETECTED" if stalled else "WITHIN_THRESHOLD",
        "escalate": stalled,
        "stall_key": "|".join(base) if stalled else None,
        "reason_code": "EXCHANGE_STALL_ESCALATION_REQUIRED" if stalled else base[2],
        "threshold": threshold,
        "authority_granted": False,
    }
