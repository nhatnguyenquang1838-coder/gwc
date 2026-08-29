#!/usr/bin/env python3
"""Fail-closed canonical readback verifier for live semantic node events.

The verifier does not fetch or invent external state. A trusted connector or
capability must place the observed state in ``event.input_payload`` together
with its identity, evidence reference, and content digest. The verifier only
accepts an exact identity match and a digest computed from that evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_SOURCE_KINDS = {
    "canonical_external_readback",
    "filesystem_readback",
    "github_compare_readback",
}


def digest_evidence(evidence: Mapping[str, Any]) -> str:
    """Return the canonical digest required by ``verify_canonical_readback``."""
    raw = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_canonical_readback(
    binding: Mapping[str, Any],
    semantic: Mapping[str, Any],
    executed_effects: list[Mapping[str, Any]],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify connector-provided readback identity and evidence integrity."""
    del semantic, executed_effects
    input_payload = event.get("input_payload")
    readback = input_payload.get("canonical_readback") if isinstance(input_payload, Mapping) else None
    if not isinstance(readback, Mapping):
        return {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_EVIDENCE_MISSING"}

    if readback.get("status") != "VERIFIED":
        return {
            "status": "BLOCKED",
            "reason_code": str(readback.get("reason_code") or "CANONICAL_READBACK_NOT_VERIFIED"),
        }

    source_kind = str(readback.get("source_kind") or "")
    if source_kind not in _ALLOWED_SOURCE_KINDS:
        return {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_SOURCE_INVALID"}

    expected_identity = {
        "run_id": event.get("run_id"),
        "event_id": event.get("event_id"),
        "node_id": binding.get("node_id"),
        "task_id": event.get("task_id"),
        "repository": event.get("repository"),
        "branch": event.get("branch"),
        "base_sha": event.get("base_sha"),
        "head_sha": event.get("head_sha"),
        "scope_hash": event.get("scope_hash"),
    }
    mismatches = [
        key for key, expected in expected_identity.items()
        if str(readback.get(key) or "") != str(expected or "")
    ]
    if mismatches:
        return {
            "status": "BLOCKED",
            "reason_code": "CANONICAL_READBACK_IDENTITY_MISMATCH",
            "mismatches": mismatches,
        }

    refs = readback.get("evidence_refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
        return {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_EVIDENCE_REF_MISSING"}

    evidence = readback.get("evidence")
    evidence_digest = readback.get("evidence_digest")
    if not isinstance(evidence, Mapping) or not isinstance(evidence_digest, str):
        return {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_EVIDENCE_DIGEST_MISSING"}
    if not _SHA256_RE.fullmatch(evidence_digest) or digest_evidence(evidence) != evidence_digest:
        return {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_EVIDENCE_DIGEST_MISMATCH"}

    return {
        "status": "VERIFIED",
        "source_kind": source_kind,
        "evidence_refs": list(refs),
        "evidence_digest": evidence_digest,
        "identity": expected_identity,
    }


__all__ = ["digest_evidence", "verify_canonical_readback"]
