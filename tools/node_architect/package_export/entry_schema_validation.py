#!/usr/bin/env python3
"""Entry Schema Validation — package_export.entry-schema-validation (M4_DETERMINISTIC).

Validates every loaded package instruction entry against one canonical closed
schema *before* any path evaluation, filesystem access or export.

Design invariants (from SCRUM-230 / F7 family contract):

* Pure evaluator. No filesystem read, no copy, no target mutation, no network.
* Closed schema: unknown fields are rejected, never ignored.
* Deterministic: the same manifest bytes + schema version produce the same
  ordered error list and the same semantic digest.
* Schema validation is kept strictly separate from filesystem existence and
  path-root safety checks (those belong to SCRUM-231 / SCRUM-232).
* The typed result — not an exit code and not "the parser did not crash" — is
  the only PASS signal.
* A valid result never grants repository, PR, merge, deploy or release
  authority; it is execution-plane evidence only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_ID = "gwc.package_export.entry_schema_validation"
SCHEMA_VERSION = "0.1"
SUPPORTED_ENTRY_VERSIONS: Tuple[str, ...] = ("0.1",)

# ---------------------------------------------------------------------------
# Stable reason codes (closed taxonomy — do not extend without a schema bump)
# ---------------------------------------------------------------------------

ENTRY_SCHEMA_VALID = "ENTRY_SCHEMA_VALID"
ENTRY_SCHEMA_INVALID = "ENTRY_SCHEMA_INVALID"
ENTRY_REQUIRED_FIELD_MISSING = "ENTRY_REQUIRED_FIELD_MISSING"
ENTRY_TYPE_INVALID = "ENTRY_TYPE_INVALID"
ENTRY_ID_INVALID = "ENTRY_ID_INVALID"
ENTRY_UNKNOWN_FIELD = "ENTRY_UNKNOWN_FIELD"
ENTRY_VERSION_UNSUPPORTED = "ENTRY_VERSION_UNSUPPORTED"
ENTRY_DUPLICATE_ID = "ENTRY_DUPLICATE_ID"

REASON_CODES: Tuple[str, ...] = (
    ENTRY_SCHEMA_VALID,
    ENTRY_SCHEMA_INVALID,
    ENTRY_REQUIRED_FIELD_MISSING,
    ENTRY_TYPE_INVALID,
    ENTRY_ID_INVALID,
    ENTRY_UNKNOWN_FIELD,
    ENTRY_VERSION_UNSUPPORTED,
    ENTRY_DUPLICATE_ID,
)


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Closed entry schema
# ---------------------------------------------------------------------------

ENTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

REQUIRED_FIELDS: Tuple[str, ...] = ("id", "path", "target", "required")
OPTIONAL_FIELDS: Tuple[str, ...] = ("entry_version", "description", "category")
ALLOWED_FIELDS: Tuple[str, ...] = tuple(sorted(REQUIRED_FIELDS + OPTIONAL_FIELDS))

_FIELD_TYPES: Dict[str, Tuple[type, ...]] = {
    "id": (str,),
    "path": (str,),
    "target": (str,),
    "required": (bool,),
    "entry_version": (str,),
    "description": (str,),
    "category": (str,),
}


@dataclass(frozen=True)
class EntryError:
    """One canonical, ordered validation error."""

    entry_index: int
    entry_id: str
    json_path: str
    keyword: str
    reason_code: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_index": self.entry_index,
            "entry_id": self.entry_id,
            "json_path": self.json_path,
            "keyword": self.keyword,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }

    def sort_key(self) -> Tuple[str, int, str, str]:
        return (self.entry_id, self.entry_index, self.json_path, self.reason_code)


@dataclass(frozen=True)
class EntryVerdict:
    entry_index: int
    entry_id: str
    accepted: bool
    reason_code: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_index": self.entry_index,
            "entry_id": self.entry_id,
            "accepted": self.accepted,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class EntrySchemaValidationResult:
    """Closed, versioned runtime result for entry schema validation."""

    schema_id: str
    schema_version: str
    outcome: Outcome
    manifest_digest: str
    schema_digest: str
    source_sha: Optional[str]
    inventory: List[EntryVerdict] = field(default_factory=list)
    errors: List[EntryError] = field(default_factory=list)
    authority_granted: bool = False  # never grants authority

    @property
    def accepted_entry_ids(self) -> List[str]:
        return [v.entry_id for v in self.inventory if v.accepted]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "outcome": self.outcome.value,
            "manifest_digest": self.manifest_digest,
            "schema_digest": self.schema_digest,
            "source_sha": self.source_sha,
            "inventory": [v.to_dict() for v in self.inventory],
            "errors": [e.to_dict() for e in self.errors],
            "authority_granted": self.authority_granted,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def semantic_digest(self) -> str:
        """Digest of the semantic identity only.

        Observational fields (generation time, run ids) are deliberately not
        part of the result contract, so the whole result is semantic.
        """
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_digest(manifest: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()


def compute_schema_digest() -> str:
    spec = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "required_fields": list(REQUIRED_FIELDS),
        "optional_fields": list(OPTIONAL_FIELDS),
        "field_types": {k: sorted(t.__name__ for t in v) for k, v in _FIELD_TYPES.items()},
        "entry_id_pattern": ENTRY_ID_PATTERN.pattern,
        "supported_entry_versions": list(SUPPORTED_ENTRY_VERSIONS),
        "reason_codes": list(REASON_CODES),
    }
    return "sha256:" + hashlib.sha256(_canonical_json(spec).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Per-entry validation
# ---------------------------------------------------------------------------


def _entry_label(entry: Any, index: int) -> str:
    if isinstance(entry, dict):
        raw = entry.get("id")
        if isinstance(raw, str) and raw:
            return raw
    return f"<index:{index}>"


def _validate_entry(entry: Any, index: int) -> List[EntryError]:
    label = _entry_label(entry, index)
    errors: List[EntryError] = []

    if not isinstance(entry, dict):
        return [
            EntryError(
                entry_index=index,
                entry_id=label,
                json_path=f"$.entries[{index}]",
                keyword="type",
                reason_code=ENTRY_TYPE_INVALID,
                detail="entry must be an object",
            )
        ]

    for name in sorted(entry.keys()):
        if name not in ALLOWED_FIELDS:
            errors.append(
                EntryError(
                    entry_index=index,
                    entry_id=label,
                    json_path=f"$.entries[{index}].{name}",
                    keyword="additionalProperties",
                    reason_code=ENTRY_UNKNOWN_FIELD,
                    detail=f"unknown field '{name}'",
                )
            )

    for name in REQUIRED_FIELDS:
        if name not in entry:
            errors.append(
                EntryError(
                    entry_index=index,
                    entry_id=label,
                    json_path=f"$.entries[{index}].{name}",
                    keyword="required",
                    reason_code=ENTRY_REQUIRED_FIELD_MISSING,
                    detail=f"required field '{name}' is missing",
                )
            )

    for name in sorted(entry.keys()):
        if name not in _FIELD_TYPES:
            continue
        expected = _FIELD_TYPES[name]
        value = entry[name]
        # bool is a subclass of int; guard string fields explicitly.
        if isinstance(value, bool) and expected != (bool,):
            ok = False
        else:
            ok = isinstance(value, expected)
        if not ok:
            errors.append(
                EntryError(
                    entry_index=index,
                    entry_id=label,
                    json_path=f"$.entries[{index}].{name}",
                    keyword="type",
                    reason_code=ENTRY_TYPE_INVALID,
                    detail=(
                        f"field '{name}' must be "
                        f"{'/'.join(t.__name__ for t in expected)}"
                    ),
                )
            )

    raw_id = entry.get("id")
    if isinstance(raw_id, str) and not ENTRY_ID_PATTERN.match(raw_id):
        errors.append(
            EntryError(
                entry_index=index,
                entry_id=label,
                json_path=f"$.entries[{index}].id",
                keyword="pattern",
                reason_code=ENTRY_ID_INVALID,
                detail="id must match " + ENTRY_ID_PATTERN.pattern,
            )
        )

    for name in ("path", "target"):
        value = entry.get(name)
        if isinstance(value, str) and value.strip() == "":
            errors.append(
                EntryError(
                    entry_index=index,
                    entry_id=label,
                    json_path=f"$.entries[{index}].{name}",
                    keyword="minLength",
                    reason_code=ENTRY_SCHEMA_INVALID,
                    detail=f"field '{name}' must not be empty",
                )
            )

    version = entry.get("entry_version")
    if isinstance(version, str) and version not in SUPPORTED_ENTRY_VERSIONS:
        errors.append(
            EntryError(
                entry_index=index,
                entry_id=label,
                json_path=f"$.entries[{index}].entry_version",
                keyword="enum",
                reason_code=ENTRY_VERSION_UNSUPPORTED,
                detail=f"unsupported entry_version '{version}'",
            )
        )

    return errors


# ---------------------------------------------------------------------------
# Public evaluator
# ---------------------------------------------------------------------------


def validate_entries(
    manifest: Any,
    *,
    source_sha: Optional[str] = None,
) -> EntrySchemaValidationResult:
    """Validate a loaded package manifest's entries against the closed schema.

    ``manifest`` is the already-loaded structure from
    ``package_export.package-manifest-load`` (SCRUM-229): an object with an
    ``entries`` list. No filesystem access is performed here.
    """
    manifest_digest = compute_manifest_digest(manifest)
    schema_digest = compute_schema_digest()

    errors: List[EntryError] = []
    inventory: List[EntryVerdict] = []

    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        errors.append(
            EntryError(
                entry_index=-1,
                entry_id="<manifest>",
                json_path="$.entries",
                keyword="type",
                reason_code=ENTRY_SCHEMA_INVALID,
                detail="manifest must be an object with an 'entries' array",
            )
        )
        return EntrySchemaValidationResult(
            schema_id=SCHEMA_ID,
            schema_version=SCHEMA_VERSION,
            outcome=Outcome.FAIL,
            manifest_digest=manifest_digest,
            schema_digest=schema_digest,
            source_sha=source_sha,
            inventory=inventory,
            errors=errors,
        )

    entries = manifest["entries"]
    per_entry_errors: Dict[int, List[EntryError]] = {}
    for index, entry in enumerate(entries):
        per_entry_errors[index] = _validate_entry(entry, index)

    # Duplicate semantic identity (entry id) — reported on every duplicate.
    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            continue
        if raw_id in seen:
            per_entry_errors[index].append(
                EntryError(
                    entry_index=index,
                    entry_id=raw_id,
                    json_path=f"$.entries[{index}].id",
                    keyword="uniqueItems",
                    reason_code=ENTRY_DUPLICATE_ID,
                    detail=f"duplicate entry id '{raw_id}' (first seen at index {seen[raw_id]})",
                )
            )
        else:
            seen[raw_id] = index

    for index, entry in enumerate(entries):
        entry_errors = per_entry_errors[index]
        errors.extend(entry_errors)
        inventory.append(
            EntryVerdict(
                entry_index=index,
                entry_id=_entry_label(entry, index),
                accepted=not entry_errors,
                reason_code=(
                    ENTRY_SCHEMA_VALID
                    if not entry_errors
                    else sorted(e.reason_code for e in entry_errors)[0]
                ),
            )
        )

    errors.sort(key=lambda e: e.sort_key())

    return EntrySchemaValidationResult(
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        outcome=Outcome.FAIL if errors else Outcome.PASS,
        manifest_digest=manifest_digest,
        schema_digest=schema_digest,
        source_sha=source_sha,
        inventory=inventory,
        errors=errors,
    )
