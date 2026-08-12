#!/usr/bin/env python3
"""Package Manifest Load — package_export.package-manifest-load (SCRUM-229 / M4_DETERMINISTIC).

Load the approved project package manifest, resolve a single exact 40-hex Git
source SHA, parse YAML via yaml.safe_load, and build deterministic entries
preserving declared instruction order for downstream entry-schema-validation.

Design invariants (from SCRUM-229 / F6 family contract):
* Pure read-only loader. No filesystem write, copy, target mutation, git,
  subprocess, or network access.
* Closed input schema: projects/gwc/package.yaml validated against
  schemas/project-package.schema.json (existing — not duplicated here).
* Source selectors are EVALUATOR ARGUMENTS (source XOR source_path); they are
  NEVER injected into the canonical package payload.
* source_sha is an exact Git commit SHA (40 hex), controller-decided, NEVER a
  content hash and never SHA256(payload).
* observed_source_sha is an execution-only keyword-only parameter; it never
  appears in the result, to_dict, or schema.
* Exactly one source mode: source XOR source_path.
* No fallback guessing: ambiguous/missing source blocks closed.
* Deterministic: same manifest + same binding => same entries, manifest_digest,
  and replay identity.
* The typed result — not an exit code and not "the parser did not crash" — is
  the only success signal.
* A valid result never grants repository, PR, merge, deploy, or release
  authority; it is execution-plane evidence only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_ID = "gwc.package_export.package_manifest_load"
SCHEMA_VERSION = "0.1"

# Closed reason taxonomy for this node.
MANIFEST_LOADED = "MANIFEST_LOADED"
MANIFEST_MISSING = "MANIFEST_MISSING"
MANIFEST_PARSE_ERROR = "MANIFEST_PARSE_ERROR"
MANIFEST_SCHEMA_UNSUPPORTED = "MANIFEST_SCHEMA_UNSUPPORTED"
MANIFEST_VERSION_UNSUPPORTED = "MANIFEST_VERSION_UNSUPPORTED"
MANIFEST_STALE_SOURCE = "MANIFEST_STALE_SOURCE"
MANIFEST_DUPLICATE_ENTRY_ID = "MANIFEST_DUPLICATE_ENTRY_ID"
MANIFEST_AMBIGUOUS_SOURCE = "MANIFEST_AMBIGUOUS_SOURCE"
MANIFEST_REPLAY_CONFLICT = "MANIFEST_REPLAY_CONFLICT"
MANIFEST_MISSING_INSTRUCTIONS = "MANIFEST_MISSING_INSTRUCTIONS"
MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE = "MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE"

# Replay status taxonomy (recorded in result; non-authoritative).
REPLAY_STATUS_NONE = "NONE"
REPLAY_STATUS_IDEMPOTENT = "IDEMPOTENT"
REPLAY_STATUS_CONFLICT = "CONFLICT"

REASON_CODES: Tuple[str, ...] = (
    MANIFEST_LOADED,
    MANIFEST_MISSING,
    MANIFEST_PARSE_ERROR,
    MANIFEST_SCHEMA_UNSUPPORTED,
    MANIFEST_VERSION_UNSUPPORTED,
    MANIFEST_STALE_SOURCE,
    MANIFEST_DUPLICATE_ENTRY_ID,
    MANIFEST_AMBIGUOUS_SOURCE,
    MANIFEST_REPLAY_CONFLICT,
    MANIFEST_MISSING_INSTRUCTIONS,
    MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE,
)

GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

SUPPORTED_MANIFEST_SCHEMA_VERSIONS: Tuple[str, ...] = ("1.0",)


class Outcome(str, Enum):
    LOADED = "LOADED"
    BLOCKED = "BLOCKED"


# Compatibility aliases
LoadResult = None  # set below after ManifestLoadResult is defined
OUTCOME_LOADED = Outcome.LOADED
OUTCOME_BLOCKED = Outcome.BLOCKED


# ---------------------------------------------------------------------------
# SourceBinding
# ---------------------------------------------------------------------------

_SOURCE_BINDING_REQUIRED_FIELDS: Tuple[str, ...] = (
    "task_id",
    "repository",
    "package_path",
    "source_ref",
    "source_sha",
    "package_version",
)


@dataclass(frozen=True)
class SourceBinding:
    """Full binding identity tying a manifest load to an exact source and task."""

    task_id: str
    repository: str
    package_path: str
    source_ref: str
    source_sha: str
    package_version: str

    @classmethod
    def from_dict(cls, raw: Any) -> "SourceBinding":
        if not isinstance(raw, dict):
            raise ValueError("SourceBinding must be a JSON object")
        missing = [f for f in _SOURCE_BINDING_REQUIRED_FIELDS if f not in raw]
        if missing:
            raise ValueError(f"missing SourceBinding fields: {missing}")
        return cls(
            task_id=raw["task_id"],
            repository=raw["repository"],
            package_path=raw["package_path"],
            source_ref=raw["source_ref"],
            source_sha=raw["source_sha"],
            package_version=raw["package_version"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "repository": self.repository,
            "package_path": self.package_path,
            "source_ref": self.source_ref,
            "source_sha": self.source_sha,
            "package_version": self.package_version,
        }

    def normalized(self) -> Dict[str, Any]:
        """Canonical, sort-keyed form for replay-identity computation."""
        return json.loads(json.dumps(self.to_dict(), sort_keys=True))


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ManifestError:
    """One canonical reason error on a blocked load."""

    reason_code: str
    json_path: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "json_path": self.json_path,
            "detail": self.detail,
        }

    def sort_key(self) -> Tuple[str, str]:
        return (self.reason_code, self.json_path)


@dataclass(frozen=True)
class LoadedEntry:
    """A normalized entry derived from a manifest instruction.

    `required` defaults to True when omitted from the source manifest, per the
    canonical input schema default.
    """

    id: str
    path: str
    target: str
    required: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "target": self.target,
            "required": self.required,
        }


@dataclass(frozen=True)
class ManifestLoadResult:
    """Closed, versioned runtime result for package manifest load.

    The only success signal is outcome==LOADED with empty errors.
    Never grants repository, PR, merge, deploy or release authority.
    """

    schema_id: str
    schema_version: str
    outcome: Outcome
    manifest_digest: str
    binding: Optional[SourceBinding]
    source_sha: str
    entries: List[LoadedEntry] = field(default_factory=list)
    errors: List[ManifestError] = field(default_factory=list)
    authority_granted: bool = False  # never grants authority
    idempotency_key: str = ""
    replay_identity: str = ""
    replay_status: str = REPLAY_STATUS_NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "outcome": self.outcome.value,
            "manifest_digest": self.manifest_digest,
            "binding": self.binding.to_dict() if self.binding is not None else None,
            "source_sha": self.source_sha if self.source_sha else None,
            "entries": [e.to_dict() for e in self.entries],
            "errors": [e.to_dict() for e in self.errors],
            "authority_granted": self.authority_granted,
            "idempotency_key": self.idempotency_key,
            "replay_identity": self.replay_identity,
            "replay_status": self.replay_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def semantic_digest(self) -> str:
        """Digest of the full semantic identity (result has no timestamps)."""
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


# Finalize compatibility alias
LoadResult = ManifestLoadResult


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_digest(manifest: Any) -> str:
    """Deterministic sha256: semantic digest of the loaded/canonical manifest
    content (normalized). No timestamps; never a substitute for Git SHA."""
    return "sha256:" + hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _is_valid_git_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(GIT_SHA_PATTERN.match(value))


def _precheck_manifest(payload: Any) -> Optional[ManifestError]:
    """Run closed reason-code prechecks before full schema validation."""
    if not isinstance(payload, dict):
        return ManifestError(
            reason_code=MANIFEST_PARSE_ERROR,
            json_path="$.",
            detail="manifest root is not a JSON object after YAML safe_load",
        )

    schema_version = payload.get("schema_version")
    if schema_version is None:
        return ManifestError(
            reason_code=MANIFEST_VERSION_UNSUPPORTED,
            json_path="$.schema_version",
            detail="manifest declares no schema_version",
        )
    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        return ManifestError(
            reason_code=MANIFEST_SCHEMA_UNSUPPORTED,
            json_path="$.schema_version",
            detail=f"unsupported schema_version '{schema_version}'",
        )

    instructions = payload.get("instructions")
    if instructions is None:
        return ManifestError(
            reason_code=MANIFEST_MISSING_INSTRUCTIONS,
            json_path="$.instructions",
            detail="manifest has no instructions field",
        )
    if not isinstance(instructions, list) or len(instructions) == 0:
        return ManifestError(
            reason_code=MANIFEST_MISSING_INSTRUCTIONS,
            json_path="$.instructions",
            detail="manifest instructions list is empty",
        )

    return None


def _check_duplicate_entry_ids(instructions: List[Any]) -> Optional[ManifestError]:
    seen: Dict[str, int] = {}
    for index, instr in enumerate(instructions):
        if not isinstance(instr, dict):
            continue
        raw_id = instr.get("id")
        if isinstance(raw_id, str) and raw_id:
            if raw_id in seen:
                return ManifestError(
                    reason_code=MANIFEST_DUPLICATE_ENTRY_ID,
                    json_path=f"$.instructions[{index}].id",
                    detail=f"duplicate entry id '{raw_id}' (first at index {seen[raw_id]})",
                )
            seen[raw_id] = index
    return None


def _resolve_source_mode(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[ManifestError]]:
    """Determine which source argument is present (source XOR source_path).

    Note: source/source_path are evaluator ARGUMENTS, not payload fields. The
    caller passes exactly one of them. This helper is used when a wrapped
    call carries them inside a single dict for convenience.
    """
    has_source = payload.get("__source__") is not None
    has_source_path = payload.get("__source_path__") is not None
    if has_source and has_source_path:
        return None, ManifestError(
            reason_code=MANIFEST_AMBIGUOUS_SOURCE,
            json_path="source|source_path",
            detail="both 'source' and 'source_path' are present; exactly one must be provided",
        )
    if not has_source and not has_source_path:
        return None, ManifestError(
            reason_code=MANIFEST_MISSING,
            json_path="source|source_path",
            detail="neither 'source' nor 'source_path' is present; no fallback guessing",
        )
    return "__source__" if has_source else "__source_path__", None


def _normalize_binding(raw: Any) -> Tuple[Optional[SourceBinding], Optional[ManifestError]]:
    try:
        binding = SourceBinding.from_dict(raw)
    except (ValueError, TypeError):
        return None, ManifestError(
            reason_code=MANIFEST_MISSING,
            json_path="$.binding",
            detail="incomplete SourceBinding; required: task_id, repository, package_path, source_ref, source_sha, package_version",
        )
    if not _is_valid_git_sha(binding.source_sha):
        return None, ManifestError(
            reason_code=MANIFEST_MISSING,
            json_path="$.binding.source_sha",
            detail="binding.source_sha must be an exact 40-hex Git commit SHA",
        )
    return binding, None


def _materialize_entries(
    instructions: List[Any],
) -> Tuple[List[LoadedEntry], Optional[ManifestError]]:
    entries: List[LoadedEntry] = []
    for index, instr in enumerate(instructions):
        if not isinstance(instr, dict):
            return entries, ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path=f"$.instructions[{index}]",
                detail="instruction entry is not a JSON object",
            )
        raw_id = instr.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            return entries, ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path=f"$.instructions[{index}].id",
                detail="instruction id must be a non-empty string",
            )
        raw_path = instr.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return entries, ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path=f"$.instructions[{index}].path",
                detail="instruction path must be a non-empty string",
            )
        raw_target = instr.get("target")
        if not isinstance(raw_target, str) or not raw_target:
            return entries, ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path=f"$.instructions[{index}].target",
                detail="instruction target must be a non-empty string",
            )
        required = instr.get("required", True)
        if not isinstance(required, bool):
            return entries, ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path=f"$.instructions[{index}].required",
                detail="instruction required must be a boolean",
            )
        entries.append(LoadedEntry(id=raw_id, path=raw_path, target=raw_target, required=required))
    return entries, None


def _load_input_schema():
    """Load schemas/project-package.schema.json if jsonschema is available.

    Returns a tuple ``(validator, unavailable_reason)`` where exactly one is
    non-None. When validation is unavailable (missing jsonschema, missing or
    unreadable schema, or schema-load failure) the caller MUST fail closed
    with MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE rather than silently passing.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return (None, "jsonschema is not installed")
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "schemas" / "project-package.schema.json"
    if not candidate.is_file():
        return (None, f"schema file not found: {candidate}")
    try:
        schema = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - load failures must fail closed
        return (None, f"schema file unreadable: {exc}")
    try:
        if str(schema.get("$schema", "")).startswith("https://json-schema.org/draft/2020"):
            validator_cls = jsonschema.Draft202012Validator
        else:
            validator_cls = jsonschema.Draft7Validator
        return (validator_cls(schema), None)
    except Exception as exc:  # noqa: BLE001 - validator build failures must fail closed
        return (None, f"schema validator build failed: {exc}")


def _schema_error_to_manifest_error(err: Any) -> ManifestError:
    path = "$.manifest." + ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "$.manifest"
    if "schema_version" in path:
        return ManifestError(
            reason_code=MANIFEST_VERSION_UNSUPPORTED,
            json_path=path,
            detail=str(err.message),
        )
    return ManifestError(
        reason_code=MANIFEST_PARSE_ERROR,
        json_path=path,
        detail=str(err.message),
    )


def _replay_identity(
    manifest: Dict[str, Any],
    binding: SourceBinding,
    observed_source_sha: str,
) -> str:
    """Canonical replay identity: normalized manifest + FULL binding + observed SHA."""
    identity = {
        "manifest": _canonical_json(manifest),
        "binding": binding.normalized(),
        "observed_source_sha": observed_source_sha,
    }
    return "sha256:" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def _resolve_source_sha(
    binding: SourceBinding,
    observed_source_sha: Optional[str],
) -> Optional[ManifestError]:
    """Resolve source-sha freshness. Returns an error or None."""
    expected = binding.source_sha
    if observed_source_sha is None:
        return ManifestError(
            reason_code=MANIFEST_MISSING,
            json_path="$.observed_source_sha",
            detail="observed_source_sha is required execution input",
        )
    if not _is_valid_git_sha(observed_source_sha):
        return ManifestError(
            reason_code=MANIFEST_MISSING,
            json_path="$.observed_source_sha",
            detail="observed_source_sha must be a valid 40-hex Git commit SHA",
        )
    if observed_source_sha != expected:
        return ManifestError(
            reason_code=MANIFEST_STALE_SOURCE,
            json_path="$.observed_source_sha",
            detail=f"observed_source_sha ({observed_source_sha}) != binding.source_sha ({expected})",
        )
    return None


# ---------------------------------------------------------------------------
# Sentinel + helpers
# ---------------------------------------------------------------------------

_NULL_BINDING = SourceBinding(
    task_id="",
    repository="",
    package_path="",
    source_ref="",
    source_sha="",
    package_version="",
)


def _blocked_result(
    *,
    errors: List[ManifestError],
    binding: Optional[SourceBinding],
    manifest_digest: str,
    source_sha: str = "",
    entries: Optional[List[LoadedEntry]] = None,
    idempotency_key: str = "",
    replay_identity: str = "",
    replay_status: str = REPLAY_STATUS_NONE,
) -> ManifestLoadResult:
    errors = sorted(errors, key=lambda e: e.sort_key()) if errors else []
    effective_binding = binding if binding is not None else _NULL_BINDING
    return ManifestLoadResult(
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        outcome=Outcome.BLOCKED,
        manifest_digest=manifest_digest,
        binding=binding,
        source_sha=source_sha if source_sha else (effective_binding.source_sha if effective_binding is not _NULL_BINDING else ""),
        entries=entries or [],
        errors=errors,
        authority_granted=False,
        idempotency_key=idempotency_key,
        replay_identity=replay_identity,
        replay_status=replay_status,
    )


# ---------------------------------------------------------------------------
# Public evaluator
# ---------------------------------------------------------------------------

def load_manifest(
    *,
    source: Any = None,
    source_path: Optional[str] = None,
    binding: Any = None,
    observed_source_sha: Optional[str] = None,
    idempotency_key: str = "",
    prior_decision: Optional[Dict[str, Any]] = None,
    decided_at: Optional[str] = None,
) -> ManifestLoadResult:
    """Load a project package manifest into a deterministic ManifestLoadResult.

    Source selection is via FUNCTION ARGUMENTS ``source`` XOR ``source_path``
    (exactly one). These are never written into the canonical payload.

    - ``source`` = inline package payload (dict, YAML/JSON text, or bytes).
    - ``source_path`` = read-only local path to a package file.
    - ``binding`` = external provenance dict (task_id, repository, package_path,
      source_ref, source_sha, package_version); never part of the payload.
    - ``observed_source_sha`` = execution-only keyword-only parameter (the actual
      Git SHA the manifest was resolved from). NOT stored in result/to_dict.
    - ``idempotency_key`` / ``prior_decision`` / ``decided_at`` = replay inputs.
    """
    # --- Resolve source via function arguments (XOR) ---
    if source is not None and source_path is not None:
        return _blocked_result(
            errors=[ManifestError(
                reason_code=MANIFEST_AMBIGUOUS_SOURCE,
                json_path="source|source_path",
                detail="both 'source' and 'source_path' are present; exactly one must be provided",
            )],
            binding=None,
            manifest_digest=compute_manifest_digest({"_ambiguous": True}),
        )
    if source is None and source_path is None:
        return _blocked_result(
            errors=[ManifestError(
                reason_code=MANIFEST_MISSING,
                json_path="source|source_path",
                detail="neither 'source' nor 'source_path' is present; no fallback guessing",
            )],
            binding=None,
            manifest_digest=compute_manifest_digest({"_no_source": True}),
        )

    # --- Acquire raw payload from source/source_path ---
    if source_path is not None:
        from pathlib import Path
        try:
            raw = Path(source_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _blocked_result(
                errors=[ManifestError(
                    reason_code=MANIFEST_MISSING,
                    json_path="source_path",
                    detail=f"cannot read source_path: {exc}",
                )],
                binding=None,
                manifest_digest=compute_manifest_digest({"_read_error": True}),
            )
    else:
        raw = source

    # Parse string/bytes payload (YAML safe_load) if needed.
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            import yaml  # type: ignore
        except ImportError:
            return _blocked_result(
                errors=[ManifestError(
                    reason_code=MANIFEST_PARSE_ERROR,
                    json_path="$.manifest",
                    detail="PyYAML is required to parse string payloads",
                )],
                binding=None,
                manifest_digest=compute_manifest_digest({"_no_yaml": True}),
            )
        try:
            payload = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            return _blocked_result(
                errors=[ManifestError(
                    reason_code=MANIFEST_PARSE_ERROR,
                    json_path="$.manifest",
                    detail=f"YAML parse error: {exc}",
                )],
                binding=None,
                manifest_digest=compute_manifest_digest({"_yaml_error": True}),
            )
    else:
        payload = raw

    if not isinstance(payload, dict):
        return _blocked_result(
            errors=[ManifestError(
                reason_code=MANIFEST_PARSE_ERROR,
                json_path="$.manifest",
                detail="manifest root must be a JSON/YAML object",
            )],
            binding=None,
            manifest_digest=compute_manifest_digest({"_not_object": True}),
        )

    # --- Binding normalization ---
    binding_obj, bind_err = _normalize_binding(binding)
    if bind_err is not None:
        return _blocked_result(
            errors=[bind_err],
            binding=None,
            manifest_digest=compute_manifest_digest(payload),
        )

    # --- Precheck: schema_version, missing/empty instructions ---
    pre = _precheck_manifest(payload)
    if pre is not None:
        return _blocked_result(
            errors=[pre],
            binding=binding_obj,
            manifest_digest=compute_manifest_digest(payload),
            source_sha=binding_obj.source_sha,
        )

    # --- Precheck: duplicate entry ids ---
    dup_err = _check_duplicate_entry_ids(payload["instructions"])
    if dup_err is not None:
        return _blocked_result(
            errors=[dup_err],
            binding=binding_obj,
            manifest_digest=compute_manifest_digest(payload),
            source_sha=binding_obj.source_sha,
        )

    # --- Full input schema validation (jsonschema, fail-closed) ---
    validator, schema_unavailable = _load_input_schema()
    if schema_unavailable is not None:
        return _blocked_result(
            errors=[ManifestError(
                reason_code=MANIFEST_SCHEMA_VALIDATION_UNAVAILABLE,
                json_path="$.manifest",
                detail=f"closed input schema validation unavailable: {schema_unavailable}",
            )],
            binding=binding_obj,
            manifest_digest=compute_manifest_digest(payload),
            source_sha=binding_obj.source_sha,
            idempotency_key=idempotency_key,
        )
    schema_errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if schema_errors:
        errors = [_schema_error_to_manifest_error(err) for err in schema_errors]
        return _blocked_result(
            errors=errors,
            binding=binding_obj,
            manifest_digest=compute_manifest_digest(payload),
            source_sha=binding_obj.source_sha,
            idempotency_key=idempotency_key,
        )

    manifest_digest = compute_manifest_digest(payload)

    # --- Replay identity + replay enforcement (deterministic) ---
    replay_identity = _replay_identity(payload, binding_obj, observed_source_sha or "")
    replay_status = REPLAY_STATUS_NONE
    if idempotency_key and prior_decision:
        prior_id = prior_decision.get("replay_identity")
        if prior_id is not None:
            if prior_id == replay_identity:
                replay_status = REPLAY_STATUS_IDEMPOTENT
            else:
                return _blocked_result(
                    errors=[ManifestError(
                        reason_code=MANIFEST_REPLAY_CONFLICT,
                        json_path="$.manifest",
                        detail="prior_decision replay_identity differs from current load under the same idempotency_key",
                    )],
                    binding=binding_obj,
                    manifest_digest=manifest_digest,
                    source_sha=binding_obj.source_sha,
                    idempotency_key=idempotency_key,
                    replay_identity=replay_identity,
                    replay_status=REPLAY_STATUS_CONFLICT,
                )

    # --- Source SHA freshness check (observed vs binding) ---
    sha_err = _resolve_source_sha(binding_obj, observed_source_sha)
    if sha_err is not None:
        return _blocked_result(
            errors=[sha_err],
            binding=binding_obj,
            manifest_digest=manifest_digest,
            source_sha=binding_obj.source_sha,
        )

    # --- package_version must match binding ---
    if payload.get("package_version") != binding_obj.package_version:
        return _blocked_result(
            errors=[ManifestError(
                reason_code=MANIFEST_STALE_SOURCE,
                json_path="$.package_version",
                detail=f"payload package_version ({payload.get('package_version')!r}) != binding.package_version ({binding_obj.package_version!r})",
            )],
            binding=binding_obj,
            manifest_digest=manifest_digest,
            source_sha=binding_obj.source_sha,
        )

    # --- Materialize ordered entries ---
    entries, entry_err = _materialize_entries(payload["instructions"])
    if entry_err is not None:
        return _blocked_result(
            errors=[entry_err],
            binding=binding_obj,
            manifest_digest=manifest_digest,
            source_sha=binding_obj.source_sha,
        )

    # --- Replay evidence carried on the typed result ---
    return ManifestLoadResult(
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        outcome=Outcome.LOADED,
        manifest_digest=manifest_digest,
        binding=binding_obj,
        source_sha=binding_obj.source_sha,
        entries=entries,
        errors=[],
        authority_granted=False,
        idempotency_key=idempotency_key,
        replay_identity=replay_identity,
        replay_status=replay_status,
    )
