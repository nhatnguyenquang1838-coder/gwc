"""
SCRUM-269 Rev4 — G3 TDD RED tests for L3 Runtime & Operational gaps.

Grounded on .kiro/specs/scrum-269-architecture.md L3 (Runtime & Operational):
  G3-A Quarantine routing (L3.3): a FAILED boundary must be routed to a
        quarantine path with reason + detected_at metadata (not silently dropped).
  G3-B SLO timing (L3.5): verify_ledger must report per-boundary latency (p99 budget).
  G3-C Lease TTL (L3.4): a record whose lease (occurred_at) exceeds TTL must be
        flagged STALLED/QUARANTINED, not accepted as COMMITTED.

Each test asserts a deterministic ReasonCode / observable structure.
RED-by-design: these exercise UNIMPLEMENTED L3 behavior -> fail until G3 GREEN.
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from tools.node_architect.ledger_replay_verifier import (
    FixtureType,
    ReasonCode,
    VerificationReport,
    apply_fixture,
    load_bootstrap_config,
    verify_ledger,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO_ROOT / "tools" / "node_architect" / "ledger_trusted_bootstrap.json"
LEDGER = REPO_ROOT / ".gwc" / "test_runtime_events.jsonl"


def _events() -> list[dict]:
    if not LEDGER.exists():
        pytest.skip("runtime-events fixture not present")
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# G3-A: quarantine routing on failure
# ---------------------------------------------------------------------------
def test_g3a_failed_boundary_routed_to_quarantine():
    events = _events()
    bootstrap = load_bootstrap_config(BOOTSTRAP)
    report: VerificationReport = verify_ledger(
        LEDGER, BOOTSTRAP, fixture=FixtureType.FORGED_SIGNATURE
    )
    # Expect a quarantine plan: list of {sequence, reason, detected_at} for FAILs
    assert hasattr(report, "quarantine"), "report must expose quarantine routing"
    q = report.quarantine
    assert isinstance(q, list) and q, "forged-signature failure must be quarantined"
    reasons = {entry["reason"] for entry in q}
    # FORGED_SIGNATURE breaks both DSSE verify AND the hash-linked prev_hash chain,
    # so both reasons appear; at minimum the DSSE failure must be isolated.
    assert ReasonCode.DSSE_SIGNATURE_INVALID.value in reasons, q
    for entry in q:
        assert "detected_at" in entry and entry["detected_at"], entry


# ---------------------------------------------------------------------------
# G3-B: SLO timing reported
# ---------------------------------------------------------------------------
def test_g3b_slo_latency_reported():
    report: VerificationReport = verify_ledger(LEDGER, BOOTSTRAP)
    assert hasattr(report, "timings"), "report must expose per-boundary timings"
    timings = report.timings
    assert isinstance(timings, dict) and timings, "timings must be non-empty"
    # Each boundary timing keyed; values are seconds (float)
    for k, v in timings.items():
        assert isinstance(v, float) and v >= 0.0, f"bad timing for {k}: {v}"


# ---------------------------------------------------------------------------
# G3-C: lease TTL expiry detection
# ---------------------------------------------------------------------------
def test_g3c_lease_expiry_flagged():
    events = _events()
    # Simulate a record whose occurred_at is older than the node-execution lease TTL (30 min)
    import datetime as dt

    ev = copy.deepcopy(events[0])
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    ev["occurred_at"] = old
    stale_events = [ev] + events[1:]
    # Write to a temp ledger so we can verify it
    tmp = LEDGER.parent / "_g3c_tmp_ledger.jsonl"
    tmp.write_text("\n".join(json.dumps(e) for e in stale_events), encoding="utf-8")
    try:
        report = verify_ledger(tmp, BOOTSTRAP)
        assert hasattr(report, "lease_status"), "report must expose lease_status"
        assert report.lease_status.get(str(ev.get("sequence"))) == "STALLED", report.lease_status
    finally:
        tmp.unlink(missing_ok=True)
