"""
SCRUM-269 Rev4 — G1 TDD RED tests for the 4 cryptographic/integrity boundaries.

Per @bmad RED spec (grounded on ledger_replay_verifier.py @ cfdc05f0):
  RED-1 Ed25519 forged signature  -> reason DSSE_SIGNATURE_INVALID
  RED-2 digest_chain tamper       -> reason DIGEST_CHAIN_MISMATCH
  RED-3 root Merkle leaf tamper   -> reason ROOT_MERKLE_MISMATCH
  RED-4 witness threshold 2/3     -> reason WITNESS_THRESHOLD_NOT_MET

Each test asserts a deterministic ReasonCode + observable FAIL state.
RED-by-design: these use ADVERSARIAL/tampered inputs, so they do NOT regress the
20/20 positive-path baseline (which uses well-formed fixtures).

NOTE (grounding correction): on cfdc05f0, RED-1 and RED-4 are already GREEN
(the verifier performs real Ed25519 verify + enforces threshold < required).
RED-2 and RED-3 are genuinely RED (missing enforcement). This file records the
true state so G1 GREEN = implement RED-2 + RED-3 only.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tools.node_architect.ledger_replay_verifier import (
    FixtureType,
    ReasonCode,
    VerificationResult,
    compute_merkle_root,
    find_trusted_key,
    load_bootstrap_config,
    verify_digest_chain_consistency,
    verify_dsse_signature,
    verify_root_merkle,
    verify_witness_threshold,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO_ROOT / "tools" / "node_architect" / "ledger_trusted_bootstrap.json"


def _load_fixture_events() -> list[dict]:
    """Load the committed Rev4 runtime-events fixture (3 well-formed v2 records)."""
    fixture = REPO_ROOT / ".gwc" / "test_runtime_events.jsonl"
    if not fixture.exists():
        pytest.skip("runtime-events fixture not present in working tree")
    events = []
    for line in fixture.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _bootstrap() -> dict:
    return load_bootstrap_config(BOOTSTRAP)


# ---------------------------------------------------------------------------
# RED-1: Ed25519 forged signature MUST be rejected
# ---------------------------------------------------------------------------
def test_red1_ed25519_forged_signature_rejected():
    events = _load_fixture_events()
    bootstrap = _bootstrap()
    # Apply the verifier's own FORGED_SIGNATURE fixture (bit-flips last byte of sig)
    from tools.node_architect.ledger_replay_verifier import apply_fixture

    tampered = apply_fixture(copy.deepcopy(events), FixtureType.FORGED_SIGNATURE)
    ok, reason, _ = verify_dsse_signature(tampered[0], bootstrap)
    assert ok is False, "forged signature must NOT verify"
    assert reason == ReasonCode.DSSE_SIGNATURE_INVALID, f"expected DSSE_SIGNATURE_INVALID, got {reason}"


# ---------------------------------------------------------------------------
# RED-2: digest_chain payload_digest tamper MUST be detected
# ---------------------------------------------------------------------------
def test_red2_digest_chain_payload_tamper_detected():
    events = _load_fixture_events()
    # Tamper: set digest_chain.payload_digest to a value that does NOT match the
    # canonical event_digest of the record.
    ev = copy.deepcopy(events[0])
    dc = dict(ev.get("digest_chain", {}))
    dc["payload_digest"] = "sha256:" + "00" * 32  # mismatched
    ev["digest_chain"] = dc
    results = verify_digest_chain_consistency([ev])
    r = results[0]
    assert r.status == "FAIL", f"digest_chain tamper must FAIL, got {r.status}"
    assert r.reason == ReasonCode.DIGEST_CHAIN_MISMATCH, f"expected DIGEST_CHAIN_MISMATCH, got {r.reason}"


# ---------------------------------------------------------------------------
# RED-3: root Merkle leaf tamper MUST be detected
# ---------------------------------------------------------------------------
def test_red3_root_merkle_leaf_tamper_detected():
    events = _load_fixture_events()
    # Capture the legitimately computed root first (proves structure works).
    legit = verify_root_merkle(events)
    assert legit.status == "PASS"
    legit_root = legit.details["computed_root"]

    # Tamper one leaf's record_digest (bitflip) — a real tamper outside the chain.
    tampered = copy.deepcopy(events)
    rd = tampered[0]["record_digest"]
    raw = bytes.fromhex(rd.replace("sha256:", ""))
    flipped = raw[:-1] + bytes([raw[-1] ^ 0x01])
    tampered[0]["record_digest"] = "sha256:" + flipped.hex()

    res = verify_root_merkle(tampered, expected_root=legit_root)
    # GREEN expectation after implementation: a stored/expected root is compared,
    # so a tampered leaf MUST FAIL with ROOT_MERKLE_MISMATCH.
    assert res.status == "FAIL", "tampered Merkle leaf must FAIL"
    assert res.reason == ReasonCode.ROOT_MERKLE_MISMATCH, f"expected ROOT_MERKLE_MISMATCH, got {res.reason}"


# ---------------------------------------------------------------------------
# RED-4: witness threshold 2/3 MUST be rejected
# ---------------------------------------------------------------------------
def test_red4_witness_threshold_subthreshold_rejected():
    events = _load_fixture_events()
    bootstrap = _bootstrap()
    # Build an event requiring witness threshold but supplying only 2/3 witnesses.
    ev = copy.deepcopy(events[0])
    ev["artifact_type"] = "node-decision"
    ev["witnesses"] = bootstrap["witness_set"][:2]  # 2 of 3
    res = verify_witness_threshold([ev], bootstrap)
    assert res.status == "FAIL", "sub-threshold witnesses must FAIL"
    assert res.reason == ReasonCode.WITNESS_THRESHOLD_NOT_MET, f"expected WITNESS_THRESHOLD_NOT_MET, got {res.reason}"
