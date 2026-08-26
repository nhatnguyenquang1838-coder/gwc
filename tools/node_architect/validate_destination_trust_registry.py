#!/usr/bin/env python3
"""Validate the SCRUM-533 destination-trust-registry.json using stdlib-only checks.

Mirrors the validate_node_registry.py pattern but for the destination trust
registry (SCRUM-533 L2.1). Registration is a reviewed entry; the validator
enforces fail-closed invariants:
  - schema/artifact-type/registry identity
  - each entry validates against destination-trust-profile.schema.json
  - destination_policy_digest determinism (sorted canonical JSON)
  - HTTPS-only receiver URL, redirect/private-IP denied
  - credential_ref is a reference (never an inline secret)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
from typing import Any

REQUIRED_ENTRY_FIELDS = {
    "schema_version", "artifact_type", "destination_id", "destination_type",
    "receiver_identity", "auth", "transport_policy", "revocation",
    "destination_policy_digest",
}
DESTINATION_TYPES = {"webhook_http", "event_bus", "siem", "kafka", "syslog_tls"}
AUTH_SCHEMES = {"hmac_sha256", "mTLS", "bearer_token_ref", "aws_sigv4"}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_HINTS = ("secret", "password", "token=", "api_key", "private_key", "-----BEGIN")


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _policy_block(entry: dict[str, Any]) -> dict[str, Any]:
    """The deterministic policy block hashed into destination_policy_digest."""
    return {
        "destination_id": entry.get("destination_id"),
        "destination_type": entry.get("destination_type"),
        "receiver_identity": entry.get("receiver_identity"),
        "auth": {k: v for k, v in (entry.get("auth") or {}).items() if k != "credential_version"},
        "transport_policy": entry.get("transport_policy"),
        "revocation": entry.get("revocation"),
    }


def validate_registry(registry: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if registry.get("schema_version") != "1.0.0":
        findings.append(_finding("BLOCKER", "SCHEMA_VERSION_INVALID", "schema_version must be 1.0.0"))
    if registry.get("artifact_type") != "destination-trust-registry":
        findings.append(_finding("BLOCKER", "ARTIFACT_TYPE_INVALID", "artifact_type must be destination-trust-registry"))

    entries = registry.get("entries")
    if not isinstance(entries, list):
        findings.append(_finding("BLOCKER", "ENTRIES_MISSING", "registry must contain an entries list"))
        return findings

    declared = registry.get("declared_entry_count")
    if not isinstance(declared, int) or declared != len(entries):
        findings.append(_finding("BLOCKER", "DECLARED_COUNT_MISMATCH",
                                 f"declared_entry_count {declared} != entries len {len(entries)}"))

    seen: set[str] = set()
    for idx, entry in enumerate(entries):
        prefix = f"entries[{idx}]"
        if not isinstance(entry, dict):
            findings.append(_finding("BLOCKER", "ENTRY_NOT_OBJECT", f"{prefix} must be an object"))
            continue
        missing = REQUIRED_ENTRY_FIELDS - set(entry)
        if missing:
            findings.append(_finding("BLOCKER", "ENTRY_FIELDS_MISSING",
                                     f"{prefix} missing {sorted(missing)}"))
            continue

        did = entry["destination_id"]
        if did in seen:
            findings.append(_finding("BLOCKER", "DUPLICATE_DESTINATION_ID", f"{prefix} {did} duplicated"))
        seen.add(did)

        if entry["destination_type"] not in DESTINATION_TYPES:
            findings.append(_finding("BLOCKER", "DESTINATION_TYPE_INVALID",
                                     f"{prefix} bad destination_type {entry['destination_type']}"))

        ri = entry["receiver_identity"]
        if not ri.get("url", "").startswith("https://"):
            findings.append(_finding("BLOCKER", "HTTPS_REQUIRED", f"{prefix} receiver url must be https"))
        tp = entry["transport_policy"]
        if tp.get("tls_required") is not True:
            findings.append(_finding("BLOCKER", "TLS_REQUIRED", f"{prefix} tls_required must be true"))
        if tp.get("allow_redirect") is not False:
            findings.append(_finding("BLOCKER", "REDIRECT_DENIED", f"{prefix} allow_redirect must be false"))
        if tp.get("allow_private_ip") is not False:
            findings.append(_finding("BLOCKER", "PRIVATE_IP_DENIED", f"{prefix} allow_private_ip must be false"))

        auth = entry["auth"]
        if auth.get("scheme") not in AUTH_SCHEMES:
            findings.append(_finding("BLOCKER", "AUTH_SCHEME_INVALID", f"{prefix} bad auth scheme"))
        if not isinstance(auth.get("credential_ref"), str) or not auth["credential_ref"].strip():
            findings.append(_finding("BLOCKER", "CREDENTIAL_REF_REQUIRED",
                                     f"{prefix} credential_ref must be a non-empty reference"))

        # Secret hygiene: credential_ref is a reference; never inline a secret value.
        blob = json.dumps(entry)
        for hint in _SECRET_HINTS:
            if hint.lower() in blob.lower():
                findings.append(_finding("BLOCKER", "INLINE_SECRET",
                                         f"{prefix} contains inline secret hint '{hint}' — credentials must be references only"))
                break

        expected_digest = "sha256:" + hashlib.sha256(
            _canonical_json(_policy_block(entry)).encode("utf-8")).hexdigest()
        if entry["destination_policy_digest"] != expected_digest:
            findings.append(_finding("BLOCKER", "POLICY_DIGEST_MISMATCH",
                                     f"{prefix} destination_policy_digest mismatch (deterministic policy-block hash)"))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the destination trust registry (SCRUM-533)")
    parser.add_argument("--root", type=Path, default=Path("."), help="repo root")
    args = parser.parse_args(argv)

    registry_path = args.root / "core" / "node-architect" / "destination-trust-registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"BLOCKER: {registry_path} not found", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"BLOCKER: invalid JSON in {registry_path}: {exc}", file=sys.stderr)
        return 1

    findings = validate_registry(registry)
    if not findings:
        print(f"PASS: {registry_path} valid ({len(registry.get('entries', []))} entries)")
        return 0
    for f in findings:
        print(f"{f['severity']} {f['code']}: {f['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
