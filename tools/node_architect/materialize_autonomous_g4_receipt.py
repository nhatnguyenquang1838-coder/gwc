#!/usr/bin/env python3
"""Validate the standing-policy G4 receipt for the autonomous pre-prod merge.

Wraps the SCRUM-272 G4 receipt schema (``autonomous-preprod-g4-receipt.schema.json``)
and the standing-policy binding rules. A receipt is accepted only when it:

* validates against the schema;
* is not expired (``expires_at`` is in the future relative to ``now``);
* is bound to the exact approved head SHA and the current task scope prefix;
* targets ``pre-prod`` (never ``main``);
* carries ``decision: ALLOW`` and ``authorized_action: merge_approved_pr``.

Pure and data-only. It never grants authority; it only validates an already
materialized trusted receipt and reports whether it is current and bound.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "autonomous-preprod-g4-receipt.schema.json"


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be ISO-8601 UTC ending in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def materialize_g4_receipt(
    *,
    receipt: Mapping[str, Any],
    expected_head_sha: str,
    expected_scope_hash_prefix: str,
    expected_policy_revision: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a G4 receipt against schema, freshness, and exact bindings."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []

    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = [
            f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt), key=lambda x: list(x.path))
        ]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
    if errors:
        reasons.append("AUTONOMOUS_G4_RECEIPT_SCHEMA_INVALID")
        reasons.extend(errors)

    if not reasons:
        if receipt.get("target_branch") != "pre-prod":
            reasons.append("AUTONOMOUS_G4_TARGET_NOT_PREPROD")
        if receipt.get("decision") != "ALLOW":
            reasons.append("AUTONOMOUS_G4_DECISION_NOT_ALLOW")
        if receipt.get("authorized_action") != "merge_approved_pr":
            reasons.append("AUTONOMOUS_G4_ACTION_NOT_MERGE")
        if receipt.get("approved_head_sha") != expected_head_sha:
            reasons.append("AUTONOMOUS_G4_HEAD_DRIFT")
        if receipt.get("parent_scope_hash_prefix") != expected_scope_hash_prefix:
            reasons.append("AUTONOMOUS_G4_SCOPE_PREFIX_MISMATCH")
        if receipt.get("policy_revision") != expected_policy_revision:
            reasons.append("AUTONOMOUS_G4_POLICY_REVISION_MISMATCH")
        try:
            expires = _parse_utc(str(receipt["expires_at"]))
            if expires <= now:
                reasons.append("AUTONOMOUS_G4_RECEIPT_EXPIRED")
        except (KeyError, ValueError) as exc:
            reasons.append(f"AUTONOMOUS_G4_RECEIPT_TIME_INVALID: {exc}")

    outcome = "RECEIPT_VALID" if not reasons else "REJECTED"
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-g4-receipt-validation",
        "outcome": outcome,
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_G4_RECEIPT_CURRENT"],
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-scope-hash-prefix", required=True)
    parser.add_argument("--expected-policy-revision", required=True)
    parser.add_argument("--now", help="Override current UTC time (ISO-8601 Z)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    now = _parse_utc(args.now) if args.now else None
    result = materialize_g4_receipt(
        receipt=receipt,
        expected_head_sha=args.expected_head_sha,
        expected_scope_hash_prefix=args.expected_scope_hash_prefix,
        expected_policy_revision=args.expected_policy_revision,
        now=now,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['outcome']}: {', '.join(result['reason_codes'])}")
    return 0 if result["outcome"] == "RECEIPT_VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
