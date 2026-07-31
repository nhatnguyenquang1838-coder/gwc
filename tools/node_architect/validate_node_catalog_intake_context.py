#!/usr/bin/env python3
"""Validate the REVAMP-GWC-016 intake_context node family."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_FAMILY = "intake_context"
EXPECTED_COUNT = 9
EXPECTED_GATE = "G0_CONTEXT"
ALLOWED_AUTHORITY = {"read_only", "none"}
ALLOWED_NODE_TYPES = {
    "actor",
    "workflow",
    "gate",
    "tool",
    "schema",
    "state",
    "projection",
    "connector",
}
ALLOWED_CANONICAL = {
    "canonical",
    "delivery_evidence",
    "audit_projection",
    "resume_hint",
}
REQUIRED_KEYS = {
    "node_id",
    "node_type",
    "title",
    "canonical",
    "authority_boundary",
    "gates",
}
TYPED_FIELD_GROUPS = {
    "intake_context.request-intake": {
        "intent",
        "outcome",
        "constraints",
        "exclusions",
        "entry_guards",
        "reason_codes",
    },
    "intake_context.source-resolution": {
        "intent",
        "outcome",
        "constraints",
        "exclusions",
        "entry_guards",
        "reason_codes",
    },
    "intake_context.repo-identity-check": {
        "intent",
        "outcome",
        "constraints",
        "exclusions",
        "entry_guards",
        "reason_codes",
    },
    "intake_context.protected-base-capture": {
        "protected_base_sha",
        "evidence_source",
        "readback_status",
        "drift_state",
        "reason_codes",
        "captured_at",
    },
}
ALLOWED_READBACK_STATUS = {"VERIFIED", "MISMATCH", "STALE", "UNKNOWN"}
ALLOWED_DRIFT_STATE = {"NONE", "STALE", "DRIFTED"}
PROTECTED_BASE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_family_dir() -> Path:
    return _repo_root() / "core" / "node-architect" / "node-catalog" / EXPECTED_FAMILY


def _load_node(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: node file must contain a JSON object")
    return data


def _validate_reason_codes(path: Path, reason_codes: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(reason_codes, (str, dict)):
        errors.append(f"{path}: reason_codes must be a string or object when present")
        return errors
    if isinstance(reason_codes, dict):
        if not all(isinstance(k, str) for k in reason_codes.keys()):
            errors.append(f"{path}: reason_codes object must have string keys")
        if not all(isinstance(v, (str, int, float, bool, type(None))) for v in reason_codes.values()):
            errors.append(f"{path}: reason_codes object must have only primitive values")
    return errors


def _validate_node(path: Path, node: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    node_id = node.get("node_id")
    typed_fields = TYPED_FIELD_GROUPS.get(node_id, set()) if isinstance(node_id, str) else set()
    allowed_keys = REQUIRED_KEYS | typed_fields | {"description"}
    extra = sorted(set(node) - allowed_keys)
    missing = sorted(REQUIRED_KEYS - set(node))
    if missing:
        errors.append(f"{path}: missing required keys: {', '.join(missing)}")
    if extra:
        errors.append(f"{path}: unexpected keys: {', '.join(extra)}")

    if not isinstance(node_id, str) or not node_id.startswith(f"{EXPECTED_FAMILY}."):
        errors.append(f"{path}: node_id must start with {EXPECTED_FAMILY}.")

    node_type = node.get("node_type")
    if node_type not in ALLOWED_NODE_TYPES:
        errors.append(f"{path}: invalid node_type {node_type!r}")

    canonical = node.get("canonical")
    if canonical not in ALLOWED_CANONICAL:
        errors.append(f"{path}: invalid canonical {canonical!r}")

    title = node.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{path}: title must be a non-empty string")

    authority = node.get("authority_boundary")
    if authority not in ALLOWED_AUTHORITY:
        errors.append(
            f"{path}: intake_context nodes must be read-only/none authority, got {authority!r}"
        )

    gates = node.get("gates")
    if gates != [EXPECTED_GATE]:
        errors.append(f"{path}: gates must be exactly [{EXPECTED_GATE!r}]")

    description = node.get("description")
    if description is not None and not isinstance(description, str):
        errors.append(f"{path}: description must be a string when present")

    if node_id in {
        "intake_context.request-intake",
        "intake_context.source-resolution",
        "intake_context.repo-identity-check",
    }:
        intent = node.get("intent")
        if intent is not None and not isinstance(intent, str):
            errors.append(f"{path}: intent must be a string when present")

        outcome = node.get("outcome")
        if outcome is not None and not isinstance(outcome, str):
            errors.append(f"{path}: outcome must be a string when present")

        constraints = node.get("constraints")
        if constraints is not None:
            if not isinstance(constraints, list) or not all(isinstance(c, str) for c in constraints):
                errors.append(f"{path}: constraints must be a list of strings when present")

        exclusions = node.get("exclusions")
        if exclusions is not None:
            if not isinstance(exclusions, list) or not all(isinstance(e, str) for e in exclusions):
                errors.append(f"{path}: exclusions must be a list of strings when present")

        entry_guards = node.get("entry_guards")
        if entry_guards is not None:
            if not isinstance(entry_guards, list) or not all(isinstance(g, str) for g in entry_guards):
                errors.append(f"{path}: entry_guards must be a list of strings when present")

        reason_codes = node.get("reason_codes")
        if reason_codes is not None:
            errors.extend(_validate_reason_codes(path, reason_codes))

    if node_id == "intake_context.protected-base-capture":
        protected_base_sha = node.get("protected_base_sha")
        if not isinstance(protected_base_sha, str) or not PROTECTED_BASE_SHA_PATTERN.fullmatch(protected_base_sha):
            errors.append(f"{path}: protected_base_sha must be a 40-character lowercase hex string")

        evidence_source = node.get("evidence_source")
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            errors.append(f"{path}: evidence_source must be a non-empty string")

        readback_status = node.get("readback_status")
        if readback_status not in ALLOWED_READBACK_STATUS:
            errors.append(
                f"{path}: readback_status must be one of {sorted(ALLOWED_READBACK_STATUS)}"
            )

        drift_state = node.get("drift_state")
        if drift_state not in ALLOWED_DRIFT_STATE:
            errors.append(f"{path}: drift_state must be one of {sorted(ALLOWED_DRIFT_STATE)}")

        captured_at = node.get("captured_at")
        if not isinstance(captured_at, str) or not captured_at.strip():
            errors.append(f"{path}: captured_at must be a non-empty string")

        reason_codes = node.get("reason_codes")
        if reason_codes is not None:
            errors.extend(_validate_reason_codes(path, reason_codes))

    return errors


def validate_family(family_dir: Path) -> list[str]:
    errors: list[str] = []
    files = sorted(family_dir.glob("*.node.json"))

    if len(files) != EXPECTED_COUNT:
        errors.append(
            f"{family_dir}: expected exactly {EXPECTED_COUNT} .node.json files, found {len(files)}"
        )

    seen_ids: set[str] = set()
    for path in files:
        try:
            node = _load_node(path)
        except Exception as exc:  # noqa: BLE001 - CLI validator should report all file failures.
            errors.append(f"{path}: failed to load JSON: {exc}")
            continue

        node_id = node.get("node_id")
        if isinstance(node_id, str):
            if node_id in seen_ids:
                errors.append(f"{path}: duplicate node_id {node_id}")
            seen_ids.add(node_id)

        errors.extend(_validate_node(path, node))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family-dir",
        type=Path,
        default=_default_family_dir(),
        help="Path to intake_context node family directory.",
    )
    args = parser.parse_args()

    errors = validate_family(args.family_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"PASS: {EXPECTED_FAMILY} node family has {EXPECTED_COUNT} valid nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
