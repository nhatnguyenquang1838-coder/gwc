#!/usr/bin/env python3
"""Pure entry-schema-validation evaluator for the package_export node family.

This module validates every loaded package instruction entry against one
canonical closed schema *before* path evaluation or export. It is a pure
function: it performs **no** filesystem read, copy or target mutation. The
manifest and schema are passed in as data; the exact source SHA is supplied by
the caller (it is a binding, never computed by reading files here).

Stable reason codes (contract-fixed):

    ENTRY_SCHEMA_VALID
    ENTRY_SCHEMA_INVALID
    ENTRY_REQUIRED_FIELD_MISSING
    ENTRY_TYPE_INVALID
    ENTRY_ID_INVALID
    ENTRY_UNKNOWN_FIELD
    ENTRY_VERSION_UNSUPPORTED
    ENTRY_DUPLICATE_ID

Determinism contract:

* The same manifest/schema bytes always produce the same ordered result.
* Errors within an entry are ordered by (json_path, keyword, reason_code).
* Entry results are ordered by entry id.
* ``manifest_digest`` and ``schema_digest`` are canonical (sorted-key) SHA-256.

"Exit code or parser success alone cannot produce PASS when the typed result
is invalid": callers MUST inspect ``ValidationOutcome.overall``; the CLI wrapper
returns a non-zero exit code on any rejection. The pure function never raises
for invalid data (only for malformed inputs such as a non-40-hex source SHA).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # jsonschema is a repo dependency (see other node_architect validators)
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - import guard for isolated callers
    Draft202012Validator = None  # type: ignore[assignment]

SUPPORTED_SCHEMA_VERSION = "entry-schema-v1"

# Stable reason-code vocabulary (contract-fixed, do not extend casually).
REASON_SCHEMA_VALID = "ENTRY_SCHEMA_VALID"
REASON_SCHEMA_INVALID = "ENTRY_SCHEMA_INVALID"
REASON_REQUIRED_MISSING = "ENTRY_REQUIRED_FIELD_MISSING"
REASON_TYPE_INVALID = "ENTRY_TYPE_INVALID"
REASON_ID_INVALID = "ENTRY_ID_INVALID"
REASON_UNKNOWN_FIELD = "ENTRY_UNKNOWN_FIELD"
REASON_VERSION_UNSUPPORTED = "ENTRY_VERSION_UNSUPPORTED"
REASON_DUPLICATE_ID = "ENTRY_DUPLICATE_ID"

_STATUS_ACCEPTED = "accepted"
_STATUS_REJECTED = "rejected"

_OVERALL_VALID = REASON_SCHEMA_VALID
_OVERALL_INVALID = REASON_SCHEMA_INVALID

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_RE = re.compile(r"'([^']+)' is a required property")
_UNKNOWN_RE = re.compile(r"'([^']+)' is not allowed")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json_bytes(model: Any) -> bytes:
    return json.dumps(model, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_path(absolute_path: Any, leaf: str | None = None) -> str:
    parts: list[str] = []
    for seg in absolute_path:
        if isinstance(seg, int):
            parts.append(f"[{seg}]")
        else:
            parts.append(f".{seg}")
    base = "$" + "".join(parts)
    if leaf is not None:
        base = f"{base}.{leaf}" if base != "$" else f"$.{leaf}"
    return base


@dataclass(frozen=True)
class EntryError:
    """One canonicalized validation error bound to an entry."""

    entry_id: str
    json_path: str
    keyword: str
    reason_code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "entry_id": self.entry_id,
            "json_path": self.json_path,
            "keyword": self.keyword,
            "reason_code": self.reason_code,
            "message": self.message,
        }


@dataclass
class EntryResult:
    """Per-entry outcome with deterministic, ordered errors."""

    entry_id: str
    status: str
    errors: list[EntryError] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.errors


@dataclass
class ValidationOutcome:
    """Whole-manifest validation outcome bound to digest/version/SHA."""

    manifest_digest: str
    schema_digest: str
    schema_version: str
    source_sha: str
    entries: list[EntryResult]
    overall: str

    @property
    def accepted(self) -> bool:
        return self.overall == _OVERALL_VALID

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_digest": self.manifest_digest,
            "schema_digest": self.schema_digest,
            "schema_version": self.schema_version,
            "source_sha": self.source_sha,
            "overall": self.overall,
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "status": e.status,
                    "errors": [err.as_dict() for err in e.errors],
                }
                for e in self.entries
            ],
        }


def _map_jsonschema_error(entry_id: str, err: Any) -> EntryError:
    validator = getattr(err, "validator", None)
    abs_path = getattr(err, "absolute_path", [])
    message = getattr(err, "message", str(err))
    if validator == "required":
        m = _REQUIRED_RE.search(message)
        leaf = m.group(1) if m else (list(abs_path)[-1] if abs_path else "")
        return EntryError(
            entry_id=entry_id,
            json_path=_json_path(abs_path, leaf),
            keyword="required",
            reason_code=REASON_REQUIRED_MISSING,
            message=message,
        )
    if validator == "additionalProperties":
        m = _UNKNOWN_RE.search(message)
        leaf = m.group(1) if m else (list(abs_path)[-1] if abs_path else "")
        return EntryError(
            entry_id=entry_id,
            json_path=_json_path(abs_path, leaf),
            keyword="additionalProperties",
            reason_code=REASON_UNKNOWN_FIELD,
            message=message,
        )
    if validator == "type":
        leaf = list(abs_path)[-1] if abs_path else ""
        return EntryError(
            entry_id=entry_id,
            json_path=_json_path(abs_path, leaf),
            keyword="type",
            reason_code=REASON_TYPE_INVALID,
            message=message,
        )
    if validator == "minLength":
        # Empty path/target and similar length violations are typed failures.
        leaf = list(abs_path)[-1] if abs_path else ""
        return EntryError(
            entry_id=entry_id,
            json_path=_json_path(abs_path, leaf),
            keyword="minLength",
            reason_code=REASON_TYPE_INVALID,
            message=message,
        )
    if validator == "pattern":
        # Always the "id" property in this schema.
        return EntryError(
            entry_id=entry_id,
            json_path=_json_path(abs_path, "id"),
            keyword="pattern",
            reason_code=REASON_ID_INVALID,
            message=message,
        )
    return EntryError(
        entry_id=entry_id,
        json_path=_json_path(abs_path),
        keyword=str(validator) if validator else "schema",
        reason_code=REASON_SCHEMA_INVALID,
        message=message,
    )


def default_schema() -> dict[str, Any]:
    """Load the bundled closed schema (bounded module-relative read only)."""
    here = Path(__file__).resolve()
    schema_path = (
        here.parents[3]
        / "schemas"
        / "node-architect"
        / "package-export"
        / "entry-schema-v1.json"
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_entries(
    manifest: dict[str, Any],
    schema: dict[str, Any],
    *,
    source_sha: str,
    supported_schema_version: str = SUPPORTED_SCHEMA_VERSION,
) -> ValidationOutcome:
    """Validate every entry in ``manifest`` against the closed ``schema``.

    Pure: no filesystem read/copy/target mutation. ``source_sha`` is an exact
    40-hex binding supplied by the caller.
    """
    if not isinstance(manifest, dict):
        raise TypeError("manifest must be a mapping")
    if not isinstance(schema, dict):
        raise TypeError("schema must be a mapping")
    if not _SHA_RE.match(source_sha or ""):
        raise ValueError(f"source_sha must be a 40-hex SHA, got {source_sha!r}")

    if Draft202012Validator is None:
        raise RuntimeError("jsonschema is required for entry-schema-validation")

    manifest_digest = hashlib.sha256(_canonical_json_bytes(manifest)).hexdigest()
    schema_digest = hashlib.sha256(_canonical_json_bytes(schema)).hexdigest()
    declared_version = manifest.get("schema_version")
    schema_version_effective = supported_schema_version

    validator = Draft202012Validator(schema)
    raw_entries = manifest.get("entries", [])
    if not isinstance(raw_entries, list):
        raw_entries = []

    # Preserve the order in which entries appear, but key results by id.
    seen_ids: dict[str, int] = {}
    per_entry_errors: dict[Any, list[EntryError]] = {}

    # Version-drift gate (applies to every entry deterministically).
    version_drift = declared_version != supported_schema_version

    for idx, entry in enumerate(raw_entries):
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        entry_id = entry_id if isinstance(entry_id, str) else f"<entry#{idx}>"
        errs: list[EntryError] = []
        if version_drift:
            errs.append(
                EntryError(
                    entry_id=entry_id,
                    json_path="$.schema_version",
                    keyword="const",
                    reason_code=REASON_VERSION_UNSUPPORTED,
                    message=(
                        f"unsupported entry schema version {declared_version!r}; "
                        f"supported {supported_schema_version!r}"
                    ),
                )
            )
        if isinstance(entry, dict):
            for err in sorted(validator.iter_errors(entry), key=lambda e: list(e.absolute_path)):
                errs.append(_map_jsonschema_error(entry_id, err))
        else:
            errs.append(
                EntryError(
                    entry_id=entry_id,
                    json_path=f"$.entries[{idx}]",
                    keyword="type",
                    reason_code=REASON_TYPE_INVALID,
                    message="entry must be an object",
                )
            )
        # Duplicate semantic identity.
        if entry_id in seen_ids:
            errs.append(
                EntryError(
                    entry_id=entry_id,
                    json_path="$.id",
                    keyword="unique",
                    reason_code=REASON_DUPLICATE_ID,
                    message=f"duplicate entry id {entry_id!r}",
                )
            )
        else:
            seen_ids[entry_id] = idx
        per_entry_errors[entry_id] = errs

    results: list[EntryResult] = []
    for entry_id in sorted(per_entry_errors, key=lambda x: (x.startswith("<entry#"), x)):
        errs = sorted(
            per_entry_errors[entry_id],
            key=lambda e: (e.json_path, e.keyword, e.reason_code, e.message),
        )
        results.append(
            EntryResult(
                entry_id=entry_id,
                status=_STATUS_ACCEPTED if not errs else _STATUS_REJECTED,
                errors=errs,
            )
        )

    overall = _OVERALL_VALID if all(r.accepted for r in results) else _OVERALL_INVALID
    return ValidationOutcome(
        manifest_digest=manifest_digest,
        schema_digest=schema_digest,
        schema_version=schema_version_effective,
        source_sha=source_sha,
        entries=results,
        overall=overall,
    )


def _cli() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Validate package_export entries against the closed schema.")
    parser.add_argument("--source-sha", required=True, help="Exact 40-hex source SHA binding.")
    parser.add_argument("--schema", default=None, help="Optional schema JSON path (defaults to bundled).")
    parser.add_argument("--manifest", default=None, help="Optional manifest JSON path (defaults to stdin).")
    args = parser.parse_args()

    if args.schema:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    else:
        schema = default_schema()
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    else:
        manifest = json.loads(sys.stdin.read())

    outcome = validate_entries(manifest, schema, source_sha=args.source_sha)
    print(json.dumps(outcome.as_dict(), indent=2))
    return 0 if outcome.accepted else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
