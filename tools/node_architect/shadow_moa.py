#!/usr/bin/env python3
"""Contradiction-preserving MoA synthesis for shadow evidence."""
from __future__ import annotations

from typing import Any


def synthesize(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    copied = [dict(item) for item in evidence]
    if not copied:
        return {"outcome": "INSUFFICIENT_EVIDENCE", "evidence": []}
    classes = [str(item.get("classification", "")) for item in copied]
    if any(value in {"", "INSUFFICIENT_EVIDENCE", "NOT_COMPARABLE"} for value in classes):
        outcome = "INSUFFICIENT_EVIDENCE"
    elif all(value == "AGREEMENT" for value in classes):
        outcome = "CONSENSUS"
    else:
        outcome = "CONTRADICTION_UNRESOLVED"
    return {"outcome": outcome, "evidence": copied}
