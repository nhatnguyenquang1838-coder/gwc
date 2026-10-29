"""Exchange-mode deadlock: repeated unresolved attempts must escalate, not resend."""
from __future__ import annotations

import pytest

from tools.node_architect.exchange_deadlock import detect_exchange_stall

ATTEMPT = {"request_digest": "sha256:" + "a" * 64, "marker": "DWA-REVIEW-" + "a" * 16,
           "status": "MESSAGE_SENT_VERIFIED"}


def test_no_attempts_is_not_a_stall() -> None:
    out = detect_exchange_stall([])
    assert out["stalled"] is False
    assert out["stage"] == "NO_ATTEMPTS"


def test_two_attempts_within_threshold() -> None:
    out = detect_exchange_stall([ATTEMPT, dict(ATTEMPT)], threshold=3)
    assert out["stalled"] is False
    assert out["streak"] == 2


def test_three_identical_unresolved_attempts_escalate() -> None:
    out = detect_exchange_stall([ATTEMPT, dict(ATTEMPT), dict(ATTEMPT)], threshold=3)
    assert out["stalled"] is True
    assert out["reason_code"] == "EXCHANGE_STALL_ESCALATION_REQUIRED"
    assert out["stall_key"]
    assert out["authority_granted"] is False


def test_controller_response_breaks_the_run() -> None:
    resolved = dict(ATTEMPT, status="CONTROLLER_RESPONSE_VERIFIED")
    out = detect_exchange_stall([resolved, dict(ATTEMPT), dict(ATTEMPT)], threshold=2)
    assert out["stalled"] is False
    assert out["stage"] == "RESOLVED_OR_BLOCKED"


def test_transport_blocked_is_not_an_exchange_stall() -> None:
    blocked = dict(ATTEMPT, status="TRANSPORT_BLOCKED")
    out = detect_exchange_stall([blocked, blocked, blocked], threshold=2)
    assert out["stalled"] is False


def test_different_request_does_not_join_the_run() -> None:
    other = dict(ATTEMPT, request_digest="sha256:" + "b" * 64, marker="DWA-REVIEW-" + "b" * 16)
    out = detect_exchange_stall([other, dict(ATTEMPT), dict(ATTEMPT)], threshold=2)
    assert out["stalled"] is False
    assert out["streak"] == 1


def test_invalid_threshold_fails_closed() -> None:
    with pytest.raises(ValueError, match="EXCHANGE_STALL_THRESHOLD_INVALID"):
        detect_exchange_stall([ATTEMPT], threshold=1)
