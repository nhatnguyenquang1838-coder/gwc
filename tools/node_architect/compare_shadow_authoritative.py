#!/usr/bin/env python3
"""Exact-identity comparison of shadow and authoritative decisions."""
from __future__ import annotations

from typing import Any

IDENTITY_FIELDS = ("task_id", "run_id", "gate", "exact_revision")


def compare_decisions(shadow: dict[str, Any], authoritative: dict[str, Any]) -> dict[str, Any]:
    mismatches = [field for field in IDENTITY_FIELDS if shadow.get(field) != authoritative.get(field)]
    if mismatches:
        return {"classification": "NOT_COMPARABLE", "identity_mismatches": mismatches}
    shadow_decision = str(shadow.get("shadow_decision", ""))
    auth_decision = str(authoritative.get("decision", ""))
    if not shadow_decision or not auth_decision:
        return {"classification": "INSUFFICIENT_EVIDENCE", "identity_mismatches": []}
    if shadow_decision == auth_decision:
        classification = "AGREEMENT"
    elif shadow_decision in {"BLOCK", "BLOCKED", "DENY"} and auth_decision == "ALLOW":
        classification = "SHADOW_MORE_CONSERVATIVE"
    elif shadow_decision == "ALLOW" and auth_decision in {"BLOCK", "DENY"}:
        classification = "SHADOW_MORE_PERMISSIVE_DENIED"
    else:
        classification = "CONTRADICTION_UNRESOLVED"
    return {
        "classification": classification,
        "identity_mismatches": [],
        "shadow_decision": shadow_decision,
        "authoritative_decision": auth_decision,
    }
