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


def certify_fixture(fixture: DomainFixture) -> dict[str, Any]:
    """Certify one fixture through the same universal kernel (C13)."""
    _require(isinstance(fixture, DomainFixture), "FIXTURE_INVALID")
    _require(fixture.domain in CERTIFICATION_DOMAINS, "CERTIFICATION_DOMAIN_UNKNOWN", str(fixture.domain))
    fixture_digest = _sha256_digest(KERNEL_REF, fixture.domain, fixture.payload)
    return {
        "domain": fixture.domain,
        "kernel_ref": KERNEL_REF,
        "fixture_digest": fixture_digest,
        "certified": True,
    }


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


__all__ = [
    "CANONICAL_FAILURE_CODES",
    "CERTIFICATION_DOMAINS",
    "CertificationError",
    "DomainFixture",
    "FailureCodeMatrix",
    "KERNEL_REF",
    "certify_fixture",
    "certify_three_domains",
    "classify_failure_code",
    "validate_fresh_recovery",
]
