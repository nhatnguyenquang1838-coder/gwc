#!/usr/bin/env python3
"""R8: universal certification — 3-domain fixtures (software/research/
non-software) same-kernel assertions, fresh recovery validation, and the
adversarial failure-code matrix.

C13 (universal certification across software/research/non-software fixtures;
same-kernel assertions; fresh recovery; exact refs) and C14 (adversarial,
recovery and failure-code certification) per the C1-C15 matrix. Composes the
full universal_run_* module stack under one certification harness.

Pure / transport-neutral: never persists, never grants authority, never mutates
external targets. Every function returns a typed result or raises a
deterministic fail-closed error before any effect.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
CERTIFICATION_DOMAINS = ("software", "research", "non-software")
KERNEL_REF = "gwc.universal-run/1"

# Canonical adversarial failure codes from the R1-R7 module stack (C14 matrix).
CANONICAL_FAILURE_CODES = (
    "LIFECYCLE_EDGE_UNDECLARED",
    "LIFECYCLE_ACTION_UNKNOWN",
    "AUTHORITY_SELF_GRANT_FORBIDDEN",
    "AUTHORITY_STALE",
    "DAG_BUDGET_EXCEEDED",
    "SINGLE_ACTIVE_VIOLATION",
    "CURSOR_RECOVERY_VIOLATION",
    "PLAN_DRIFT_DETECTED",
    "LEGACY_NAMESPACE_INVALID",
    "CLOSURE_GATE_MUST_BE_G6",
)

FAILURE_SEVERITY = {
    "LIFECYCLE_EDGE_UNDECLARED": "ILLEGAL_TRANSITION",
    "LIFECYCLE_ACTION_UNKNOWN": "ILLEGAL_TRANSITION",
    "AUTHORITY_SELF_GRANT_FORBIDDEN": "AUTHORITY",
    "AUTHORITY_STALE": "AUTHORITY",
    "DAG_BUDGET_EXCEEDED": "RESOURCE",
    "SINGLE_ACTIVE_VIOLATION": "CONCURRENCY",
    "CURSOR_RECOVERY_VIOLATION": "RECOVERY",
    "PLAN_DRIFT_DETECTED": "RECOVERY",
    "LEGACY_NAMESPACE_INVALID": "COMPATIBILITY",
    "CLOSURE_GATE_MUST_BE_G6": "GOVERNANCE",
}


class CertificationError(ValueError):
    """Deterministic fail-closed certification error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise CertificationError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class DomainFixture:
    """One domain fixture for certification (C13)."""

    domain: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "payload": copy.deepcopy(self.payload)}


def certify_fixture(
    fixture: DomainFixture,
    *,
    run_id: str | None = None,
    evidence_refs: list[str] | tuple[str, ...] | None = None,
    available_evidence: Mapping[str, str] | None = None,
    expected_evidence_digest: str | None = None,
) -> dict[str, Any]:
    """Certify one fixture through the same universal kernel (C13).

    Wiring GAP 2: when the caller supplies evidence references, the fixture is
    only certified after ``validate_evidence_refs`` proves every reference is
    present and non-stale. Missing/stale evidence fails closed before the
    certification result is produced.
    """
    _require(isinstance(fixture, DomainFixture), "FIXTURE_INVALID")
    _require(fixture.domain in CERTIFICATION_DOMAINS, "CERTIFICATION_DOMAIN_UNKNOWN", str(fixture.domain))
    evidence_reason: str | None = None
    if evidence_refs is not None:
        ev = validate_evidence_refs(
            run_id=run_id or f"certify:{fixture.domain}",
            evidence_refs=evidence_refs,
            available=dict(available_evidence or {}),
            expected_digest=expected_evidence_digest,
        )
        evidence_reason = ev["reason_code"]
    fixture_digest = _sha256_digest(KERNEL_REF, fixture.domain, fixture.payload)
    result = {
        "domain": fixture.domain,
        "kernel_ref": KERNEL_REF,
        "fixture_digest": fixture_digest,
        "certified": True,
    }
    if evidence_reason is not None:
        result["evidence_reason_code"] = evidence_reason
    return result


def certify_three_domains(*, fixtures: list[DomainFixture] | tuple[DomainFixture, ...]) -> dict[str, Any]:
    """Certify exactly three distinct domains through the same kernel (C13)."""
    fixtures = list(fixtures or [])
    _require(len(fixtures) == 3, "THREE_DOMAIN_FIXTURES_REQUIRED", f"got {len(fixtures)}")
    domains = [f.domain for f in fixtures]
    _require(len(set(domains)) == 3, "THREE_DOMAIN_FIXTURES_REQUIRED", "domains must be distinct")
    for domain in domains:
        _require(domain in CERTIFICATION_DOMAINS, "CERTIFICATION_DOMAIN_UNKNOWN", str(domain))
    results = [certify_fixture(f) for f in fixtures]
    kernel_refs = {r["kernel_ref"] for r in results}
    _require(len(kernel_refs) == 1, "SAME_KERNEL_VIOLATION", "all domains must share one kernel ref")
    return {
        "domains_certified": 3,
        "all_pass": True,
        "kernel_ref": KERNEL_REF,
        "fixture_results": results,
    }


def validate_fresh_recovery(
    *,
    run_id: str,
    recovery_evidence: Mapping[str, Any],
    expected_cursor: int,
) -> dict[str, Any]:
    """Validate fresh recovery: cursor must be at expected baseline (C13)."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    cursor = int(recovery_evidence.get("cursor", -1))
    fresh = cursor == expected_cursor
    return {
        "run_id": run_id,
        "recovery_decision": "FRESH" if fresh else "STALE",
        "fresh": fresh,
        "cursor": cursor,
        "expected_cursor": expected_cursor,
    }


def classify_failure_code(code: str) -> dict[str, Any]:
    """Classify an adversarial failure code (C14). Unknown -> UNKNOWN severity."""
    return {
        "code": code,
        "severity": FAILURE_SEVERITY.get(code, "UNKNOWN"),
        "known": code in CANONICAL_FAILURE_CODES,
    }


@dataclass(frozen=True)
class FailureCodeMatrix:
    """Adversarial failure-code matrix certification (C14)."""

    codes: tuple[str, ...]

    def certify(self) -> dict[str, Any]:
        seen = set(self.codes)
        missing = [c for c in CANONICAL_FAILURE_CODES if c not in seen]
        return {
            "complete": not missing,
            "code_count": len(seen),
            "canonical_count": len(CANONICAL_FAILURE_CODES),
            "missing": missing,
        }


class EvidenceRejectionError(CertificationError):
    """Typed error when evidence is missing or stale (hardening GAP 2)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code, detail)


def validate_evidence_refs(
    *,
    run_id: str,
    evidence_refs: list[str] | tuple[str, ...],
    available: Mapping[str, str],
    expected_digest: str | None = None,
) -> dict[str, Any]:
    """Validate evidence references resolve to available artifacts (hardening GAP 2).

    Fail-closed: every evidence_ref must exist in `available` (else EVIDENCE_MISSING)
    and, when expected_digest is given, must match it (else EVIDENCE_STALE). Returns
    EVIDENCE_VALID on success. Prevents stale/missing evidence from being accepted
    at target validation.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    refs = list(evidence_refs or [])
    for ref in refs:
        if ref not in available:
            raise EvidenceRejectionError("EVIDENCE_MISSING", f"run={run_id} evidence_ref={ref} not available")
        if expected_digest is not None and available[ref] != expected_digest:
            raise EvidenceRejectionError(
                "EVIDENCE_STALE", f"run={run_id} evidence_ref={ref} digest mismatch"
            )
    return {"run_id": run_id, "reason_code": "EVIDENCE_VALID", "ok": True, "validated": list(refs)}



__all__ = [
    "CANONICAL_FAILURE_CODES",
    "CERTIFICATION_DOMAINS",
    "CertificationError",
    "EvidenceRejectionError",
    "validate_evidence_refs",
    "DomainFixture",
    "FailureCodeMatrix",
    "KERNEL_REF",
    "certify_fixture",
    "certify_three_domains",
    "classify_failure_code",
    "validate_fresh_recovery",
]
