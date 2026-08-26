#!/usr/bin/env python3
"""Exact-identity comparison of shadow and authoritative decisions."""
from __future__ import annotations

from typing import Any

IDENTITY_FIELDS = ("task_id", "run_id", "gate", "exact_revision")
BLOCKING = {"BLOCK", "BLOCKED", "DENY"}
ALLOWING = {"ALLOW", "PASS", "PROCEED"}


def compare_decisions(shadow: dict[str, Any], authoritative: dict[str, Any]) -> dict[str, Any]:
    mismatches = [field for field in IDENTITY_FIELDS if shadow.get(field) != authoritative.get(field)]
    if mismatches:
        return {"classification": "NOT_COMPARABLE", "identity_mismatches": mismatches}
    shadow_decision = str(shadow.get("shadow_decision", "")).upper()
    auth_decision = str(authoritative.get("decision", "")).upper()
    if not shadow_decision or not auth_decision:
        return {"classification": "INSUFFICIENT_EVIDENCE", "identity_mismatches": []}
    if shadow_decision == auth_decision:
        classification = "AGREEMENT"
    elif shadow_decision in BLOCKING and auth_decision in ALLOWING:
        classification = "SHADOW_MORE_CONSERVATIVE"
    elif shadow_decision in ALLOWING and auth_decision in BLOCKING:
        classification = "SHADOW_MORE_PERMISSIVE_DENIED"
    else:
        classification = "CONTRADICTION_UNRESOLVED"
    return {
        "classification": classification,
        "identity_mismatches": [],
        "shadow_decision": shadow_decision,
        "authoritative_decision": auth_decision,
    }
