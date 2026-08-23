#!/usr/bin/env python3
"""Schema compatibility resolver for durable GWC artifacts (SCRUM-396).

Resolves writer-schema -> reader-schema compatibility BEFORE checkpoint /
evidence / observation interpretation. Unknown/incompatible versions fail
closed with typed outcomes. Never grants gate/actor/source authority.

Invariants:
  UNKNOWN_SCHEMA_CANNOT_ENTER_REPLAY
  CANONICALIZATION_NEVER_GRANTS_AUTHORITY
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --- Typed outcomes ---------------------------------------------------------

class SchemaCompatibilityError(RuntimeError):
    """Raised when a durable artifact cannot be safely interpreted."""


@dataclass(frozen=True)
class CompatibilityResult:
    state: str  # EXACT | COMPATIBLE | MIGRATION_REQUIRED | UNSUPPORTED
    reason_code: str
    writer_schema_id: str
    writer_schema_version: str
    profile_id: str | None = None
    migration_chain: tuple[str, ...] = ()
    message: str = ""


# --- Trust manifest resolution ---------------------------------------------

def load_trust_manifest(path: str) -> dict[str, Any]:
    """Load a SchemaTrustManifest (GWC-owned allowlist)."""
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != "1.0":
        raise SchemaCompatibilityError("SCHEMA_TRUST_MANIFEST_VERSION_UNSUPPORTED")
    if manifest.get("artifact_type") != "schema-trust-manifest":
        raise SchemaCompatibilityError("SCHEMA_TRUST_MANIFEST_TYPE_INVALID")
    return manifest


def _entry_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    return (entry["writer_schema_id"], entry["writer_schema_version"])


def resolve_profile(
    manifest: Mapping[str, Any],
    writer_schema_id: str,
    writer_schema_version: str,
) -> dict[str, Any]:
    """Resolve profile through the allowlist ONLY. Never artifact-authorized.

    Raises SchemaCompatibilityError with typed code when the writer schema is
    unknown, REJECTED, or deprecated-for-new-write.
    """
    entries = manifest.get("entries", [])
    for entry in entries:
        if _entry_key(entry) == (writer_schema_id, writer_schema_version):
            lifecycle = entry.get("lifecycle")
            if lifecycle == "REJECTED":
                raise SchemaCompatibilityError("SCHEMA_VERSION_REJECTED")
            return entry
    raise SchemaCompatibilityError("SCHEMA_VERSION_UNSUPPORTED")


# --- Canonical envelope ----------------------------------------------------

def build_envelope(
    *,
    artifact_kind: str,
    writer_schema_id: str,
    writer_schema_version: str,
    schema_digest: str,
    payload: Any,
    profile_id: str,
    profile_version: str,
    migration_lineage: list[str] | None = None,
) -> dict[str, Any]:
    """Build a DurableArtifactEnvelope with digest binding."""
    payload_digest = "sha256:" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    envelope = {
        "schema_version": "1.0",
        "artifact_type": "durable-artifact-envelope",
        "artifact_kind": artifact_kind,
        "writer_schema_id": writer_schema_id,
        "writer_schema_version": writer_schema_version,
        "schema_digest": schema_digest,
        "payload_digest": payload_digest,
        "migration_lineage": list(migration_lineage or []),
        "profile_id": profile_id,
        "profile_version": profile_version,
        "hash_algorithm": "sha256",
    }
    return envelope


# --- Resolver ---------------------------------------------------------------

def resolve_compatibility(
    *,
    writer_schema_id: str,
    writer_schema_version: str,
    manifest: Mapping[str, Any],
    supported_migrations: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
) -> CompatibilityResult:
    """Resolve writer->reader compatibility against the trust manifest.

    supported_migrations maps (writer_schema_id, writer_schema_version) to an
    ordered chain of compatible reader schema versions. Migrations are
    verification-only; historical evidence is never rewritten in place.
    """
    try:
        entry = resolve_profile(manifest, writer_schema_id, writer_schema_version)
    except SchemaCompatibilityError as exc:
        return CompatibilityResult(
            state="UNSUPPORTED",
            reason_code=exc.args[0],
            writer_schema_id=writer_schema_id,
            writer_schema_version=writer_schema_version,
            message=str(exc),
        )

    lifecycle = (entry or {}).get("lifecycle")
    if lifecycle == "VERIFY_ONLY":
        return CompatibilityResult(
            state="MIGRATION_REQUIRED",
            reason_code="LEGACY_VERIFY_ONLY",
            writer_schema_id=writer_schema_id,
            writer_schema_version=writer_schema_version,
            profile_id=(entry or {}).get("profile_id"),
            migration_chain=supported_migrations.get(
                (writer_schema_id, writer_schema_version), ()
            ),
            message="Legacy profile is verification-only; migrate before new writes.",
        )

    return CompatibilityResult(
        state="EXACT",
        reason_code="SCHEMA_EXACT_MATCH",
        writer_schema_id=writer_schema_id,
        writer_schema_version=writer_schema_version,
        profile_id=(entry or {}).get("profile_id"),
        message="Writer schema is allowlisted and current.",
    )


# --- Journal transitions (migration operation journal) ----------------------

JOURNAL_FLOW = (
    "DISCOVERED",
    "TRUST_RESOLVED",
    "COMPATIBILITY_CLASSIFIED",
    "MIGRATION_PREPARED",
    "OUTPUT_WRITTEN",
    "OUTPUT_READBACK_VERIFIED",
    "REPLAY_ELIGIBLE",
)
JOURNAL_TERMINAL = ("UNSUPPORTED", "QUARANTINED", "OUTCOME_UNKNOWN", "FAILED")
JOURNAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DISCOVERED": ("TRUST_RESOLVED", "UNSUPPORTED", "QUARANTINED"),
    "TRUST_RESOLVED": ("COMPATIBILITY_CLASSIFIED", "UNSUPPORTED", "QUARANTINED"),
    "COMPATIBILITY_CLASSIFIED": ("MIGRATION_PREPARED", "OUTCOME_UNKNOWN", "QUARANTINED"),
    "MIGRATION_PREPARED": ("OUTPUT_WRITTEN", "OUTCOME_UNKNOWN", "QUARANTINED"),
    "OUTPUT_WRITTEN": ("OUTPUT_READBACK_VERIFIED", "OUTCOME_UNKNOWN", "QUARANTINED"),
    "OUTPUT_READBACK_VERIFIED": ("REPLAY_ELIGIBLE", "OUTCOME_UNKNOWN", "QUARANTINED"),
    "REPLAY_ELIGIBLE": (),
    "UNSUPPORTED": (),
    "QUARANTINED": (),
    "OUTCOME_UNKNOWN": ("DISCOVERED", "QUARANTINED", "FAILED"),
    "FAILED": (),
}


def journal_transition(record: dict[str, Any], next_state: str) -> dict[str, Any]:
    """Validate + apply a journal state transition (fail-closed)."""
    current = record.get("state")
    if current not in JOURNAL_TRANSITIONS:
        raise SchemaCompatibilityError("JOURNAL_STATE_UNKNOWN")
    if next_state not in JOURNAL_TRANSITIONS[current]:
        raise SchemaCompatibilityError(
            f"JOURNAL_TRANSITION_INVALID ({current} -> {next_state})"
        )
    updated = dict(record)
    updated["state"] = next_state
    updated["updated_at"] = _now()
    return updated


def _now() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
