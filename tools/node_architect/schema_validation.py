#!/usr/bin/env python3
"""Schema Validation — validation_quality.schema-validation (SCRUM-334 / GitHub #269).

Validates each changed artifact against the explicitly applicable schema/version
and returns stable, deterministic canonical errors. This is the *missing*
canonical behavior for the `validation_quality.schema-validation` node. It binds
to the canonical runtime-node schema and is deliberately kept distinct from the
separate `package_export.entry-schema-validation` node.

Design invariants (from SCRUM-334 / #269 brief):

* Pure evaluator. No network, no mutation, no repository/PR/merge action.
* Bind declared schema id + version + artifact/head provenance.
* PASS only for supported / current-compatible schema + version.
* Fail closed on missing, malformed, ambiguous, unsupported/incompatible
  schema/version, and on malformed or drifting artifacts.
* Invalidate stale validation when artifact/schema/version/head drifts
  (same idempotency key, different inputs => prior result is stale).
* Deterministic replay / result digest.
* Explicit authority-negative: a PASS grants no G2/G3/G4/G5/G6, merge, deploy
  or production authority. The typed result — not an exit code — is the only
  PASS signal.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from jsonschema import Draft202012Validator

NODE_ID = "validation_quality.schema_validation"

PASS = "PASS"
FAIL = "FAIL"

# Canonical runtime-node schema this node binds to.
RUNTIME_NODE_SCHEMA_ID = "https://gwc.local/schemas/node-architect/runtime-node.schema.json"
SUPPORTED_RUNTIME_NODE_VERSIONS: tuple[str, ...] = ("1.0.0",)

# ---------------------------------------------------------------------------
# Stable, closed reason-code taxonomy (order = canonical error ordering)
# ---------------------------------------------------------------------------

SCHEMA_MISSING = "SCHEMA_MISSING"
SCHEMA_MALFORMED = "SCHEMA_MALFORMED"
SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
SCHEMA_VERSION_INCOMPATIBLE = "SCHEMA_VERSION_INCOMPATIBLE"
SCHEMA_AMBIGUOUS = "SCHEMA_AMBIGUOUS"
ARTIFACT_MALFORMED = "ARTIFACT_MALFORMED"
ARTIFACT_VERSION_DRIFT = "ARTIFACT_VERSION_DRIFT"
ARTIFACT_INVALID = "ARTIFACT_INVALID"
SCHEMA_VALIDATION_STALE = "SCHEMA_VALIDATION_STALE"
SCHEMA_VALID = "SCHEMA_VALID"

REASON_ORDER: tuple[str, ...] = (
    SCHEMA_MISSING,
    SCHEMA_MALFORMED,
    SCHEMA_UNSUPPORTED,
    SCHEMA_VERSION_INCOMPATIBLE,
    SCHEMA_AMBIGUOUS,
    ARTIFACT_MALFORMED,
    ARTIFACT_VERSION_DRIFT,
    ARTIFACT_INVALID,
    SCHEMA_VALIDATION_STALE,
    SCHEMA_VALID,
)

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# ---------------------------------------------------------------------------
# Canonical runtime-node schema registry (lazy, fail-closed on load failure)
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "node-architect"
    / "runtime-node.schema.json"
)

# schema_id -> tuple of resolved schema definitions. Normally 1:1; >1 => ambiguous.
_SUPPORTED_SCHEMAS: dict[str, tuple[dict[str, Any], ...]] = {}


def _init_registry() -> None:
    if _SUPPORTED_SCHEMAS:
        return
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # Leave registry empty -> every validation fails closed (UNSUPPORTED).
        return
    _SUPPORTED_SCHEMAS[RUNTIME_NODE_SCHEMA_ID] = (schema,)


_init_registry()

_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = _SUPPORTED_SCHEMAS.get(RUNTIME_NODE_SCHEMA_ID, (None,))[0]
        if schema is None:
            raise RuntimeError("canonical runtime-node schema is not available")
        _VALIDATOR = Draft202012Validator(schema)
    return _VALIDATOR


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_path(error: Any) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/" + "/".join(parts) if parts else ""


def _authority_boundary() -> dict[str, bool]:
    return {
        "g2_authority_granted": False,
        "g3_authority_granted": False,
        "g4_authority_granted": False,
        "g5_authority_granted": False,
        "g6_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _build(
    status: str,
    reasons: set[str],
    errors: Sequence[dict[str, Any]],
    *,
    artifact_sha: str | None,
    input_digest: str,
    declared_schema_id: str | None,
    declared_schema_version: str | None,
    head_sha: str | None,
    idempotency_key: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    ordered = [code for code in REASON_ORDER if code in reasons]
    result_digest = _sha(
        {
            "status": status,
            "reason_codes": ordered,
            "errors": errors,
            "artifact_sha": artifact_sha,
        }
    )
    return {
        "schema_version": "1.0",
        "artifact_type": "schema-validation",
        "node_id": NODE_ID,
        "task_id": task_id,
        "idempotency_key": idempotency_key,
        "declared_schema_id": declared_schema_id,
        "declared_schema_version": declared_schema_version,
        "resolved_schema_id": declared_schema_id if status == PASS else None,
        "artifact_sha": artifact_sha,
        "head_sha": head_sha,
        "status": status,
        "reason_codes": ordered,
        "errors": list(errors),
        "input_digest": input_digest,
        "result_digest": result_digest,
        "replayed": False,
        "authority_granted": False,
        **_authority_boundary(),
    }


def _stale(
    *,
    artifact_sha: str | None,
    input_digest: str,
    declared_schema_id: str | None,
    declared_schema_version: str | None,
    head_sha: str | None,
    idempotency_key: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    return _build(
        FAIL,
        {SCHEMA_VALIDATION_STALE},
        [],
        artifact_sha=artifact_sha,
        input_digest=input_digest,
        declared_schema_id=declared_schema_id,
        declared_schema_version=declared_schema_version,
        head_sha=head_sha,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )


def _evaluate(
    artifact: Mapping[str, Any],
    *,
    declared_schema_id: str | None,
    declared_schema_version: str | None,
    artifact_sha: str,
    input_digest: str,
    head_sha: str | None,
    idempotency_key: str | None,
    task_id: str | None,
) -> dict[str, Any]:
    reasons: set[str] = set()

    # --- bind declared schema id ---
    if not isinstance(declared_schema_id, str) or not declared_schema_id.strip():
        reasons.add(SCHEMA_MISSING)
    elif declared_schema_id not in _SUPPORTED_SCHEMAS:
        reasons.add(SCHEMA_UNSUPPORTED)
    elif len(_SUPPORTED_SCHEMAS[declared_schema_id]) > 1:
        reasons.add(SCHEMA_AMBIGUOUS)

    # --- bind declared schema version ---
    if not isinstance(declared_schema_version, str) or not declared_schema_version.strip():
        reasons.add(SCHEMA_MISSING)
    elif not _VERSION_RE.fullmatch(declared_schema_version):
        reasons.add(SCHEMA_MALFORMED)
    elif declared_schema_version not in SUPPORTED_RUNTIME_NODE_VERSIONS:
        reasons.add(SCHEMA_VERSION_INCOMPATIBLE)

    if reasons:
        return _build(
            FAIL,
            reasons,
            [],
            artifact_sha=artifact_sha,
            input_digest=input_digest,
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    # --- artifact version drift vs declared version ---
    art_ver = artifact.get("schema_version")
    if isinstance(art_ver, str) and art_ver != declared_schema_version:
        return _build(
            FAIL,
            {ARTIFACT_VERSION_DRIFT},
            [],
            artifact_sha=artifact_sha,
            input_digest=input_digest,
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    # --- validate artifact against the canonical schema ---
    try:
        validator = _get_validator()
        errs = sorted(
            validator.iter_errors(dict(artifact)),
            key=lambda e: (_json_path(e), str(e.validator)),
        )
    except Exception:  # schema unavailable / malformed -> fail closed
        return _build(
            FAIL,
            {SCHEMA_MALFORMED},
            [],
            artifact_sha=artifact_sha,
            input_digest=input_digest,
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    if errs:
        error_list = [
            {
                "json_path": _json_path(e),
                "keyword": str(e.validator),
                "reason_code": ARTIFACT_INVALID,
                "message": e.message,
            }
            for e in errs
        ]
        return _build(
            FAIL,
            {ARTIFACT_INVALID},
            error_list,
            artifact_sha=artifact_sha,
            input_digest=input_digest,
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    return _build(
        PASS,
        {SCHEMA_VALID},
        [],
        artifact_sha=artifact_sha,
        input_digest=input_digest,
        declared_schema_id=declared_schema_id,
        declared_schema_version=declared_schema_version,
        head_sha=head_sha,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )


def validate_schema(
    artifact: Mapping[str, Any],
    *,
    declared_schema_id: str,
    declared_schema_version: str,
    head_sha: str | None = None,
    idempotency_key: str | None = None,
    task_id: str | None = None,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate ``artifact`` against the declared schema id/version.

    Returns a stable, deterministic decision dict. Fails closed on any missing,
    malformed, ambiguous, unsupported/incompatible binding, on malformed or
    version-drifting artifacts, and invalidates stale results when
    artifact/schema/version/head drifts under the same ``idempotency_key``.
    """

    # A non-mapping artifact is malformed; cannot be hashed for drift.
    if not isinstance(artifact, Mapping):
        return _build(
            FAIL,
            {ARTIFACT_MALFORMED},
            [],
            artifact_sha=None,
            input_digest=_sha(
                {
                    "declared_schema_id": declared_schema_id,
                    "declared_schema_version": declared_schema_version,
                    "artifact_sha": None,
                    "head_sha": head_sha,
                }
            ),
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    # Compute artifact digest (deterministic canonical JSON).
    try:
        artifact_sha = _sha(artifact)
    except (TypeError, ValueError):
        return _build(
            FAIL,
            {ARTIFACT_MALFORMED},
            [],
            artifact_sha=None,
            input_digest=_sha(
                {
                    "declared_schema_id": declared_schema_id,
                    "declared_schema_version": declared_schema_version,
                    "artifact_sha": None,
                    "head_sha": head_sha,
                }
            ),
            declared_schema_id=declared_schema_id,
            declared_schema_version=declared_schema_version,
            head_sha=head_sha,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

    input_digest = _sha(
        {
            "declared_schema_id": declared_schema_id,
            "declared_schema_version": declared_schema_version,
            "artifact_sha": artifact_sha,
            "head_sha": head_sha,
        }
    )

    # Replay / drift handling happens before evaluation: a prior cached result
    # whose inputs have drifted is invalidated (fail closed).
    if replay_cache is not None and idempotency_key:
        prev = replay_cache.get(idempotency_key)
        if prev is not None:
            if prev.get("input_digest") == input_digest:
                replay = dict(prev)
                replay["replayed"] = True
                return replay
            return _stale(
                artifact_sha=artifact_sha,
                input_digest=input_digest,
                declared_schema_id=declared_schema_id,
                declared_schema_version=declared_schema_version,
                head_sha=head_sha,
                idempotency_key=idempotency_key,
                task_id=task_id,
            )

    decision = _evaluate(
        artifact,
        declared_schema_id=declared_schema_id,
        declared_schema_version=declared_schema_version,
        artifact_sha=artifact_sha,
        input_digest=input_digest,
        head_sha=head_sha,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )

    if replay_cache is not None and idempotency_key:
        replay_cache[idempotency_key] = dict(decision)

    return decision
