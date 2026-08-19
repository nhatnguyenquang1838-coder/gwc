"""Deterministic execution of stdlib validators for SCRUM-335.

Runs a declared set of stdlib-backed validators over a request payload and
captures each validator's deterministic return code. The node is read-only and
never grants later-gate authority.

Mirrors the established helper contract used by sibling validation_quality
nodes (e.g. ``evidence_quality_check``): a module-level ``NODE_ID``, ``PASS`` /
``BLOCKED`` sentinels, a single pure decision function, and a declared
``__all__``. No descriptor metadata is touched (provenance-safe).
"""
from __future__ import annotations

import re
from typing import Any, Mapping

NODE_ID = "validation_quality.validator-execution"
PASS = "PASS"
BLOCKED = "BLOCKED"

# Deterministic return codes (nonzero == failure). Standard process exit-code
# semantics so downstream consumers can rely on stable, comparable codes.
RC_OK = 0
RC_MISSING = 1
RC_MALFORMED = 2
RC_MISMATCH = 3

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_IDENTITY_FIELDS = ("task_id", "repository", "branch", "base_sha", "head_sha", "scope_hash")


def _validate_sha(value: object) -> int:
    text = value if isinstance(value, str) else ""
    if not text:
        return RC_MISSING
    return RC_OK if _SHA_RE.fullmatch(text) else RC_MALFORMED


def _validate_scope_hash(value: object) -> int:
    text = value if isinstance(value, str) else ""
    if not text:
        return RC_MISSING
    return RC_OK if _SCOPE_RE.fullmatch(text) else RC_MALFORMED


def _validate_identity_complete(payload: Mapping[str, Any]) -> int:
    return RC_OK if all(str(payload.get(f, "")).strip() for f in _IDENTITY_FIELDS) else RC_MISSING


# Built-in stdlib validator registry. Each entry is a pure function returning a
# deterministic int return code. Adding a validator here is the supported
# extension point; no descriptor metadata is touched (provenance-safe).
BUILTIN_VALIDATORS = {
    "head_sha_format": lambda p: _validate_sha(p.get("head_sha")),
    "base_sha_format": lambda p: _validate_sha(p.get("base_sha")),
    "scope_hash_format": lambda p: _validate_scope_hash(p.get("scope_hash")),
    "identity_complete": _validate_identity_complete,
}


def run_validator_execution(
    payload: Mapping[str, Any],
    *,
    validators: list[str] | None = None,
) -> dict[str, Any]:
    """Run the requested (or all built-in) validators and capture return codes.

    Returns a stable decision dict. Deterministic: identical input yields
    identical output. ``validators`` restricts which built-ins execute; an
    unknown name yields ``RC_MALFORMED`` for that entry rather than raising.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    request = dict(payload)
    names = list(validators) if validators is not None else list(BUILTIN_VALIDATORS)
    return_codes: dict[str, int] = {}
    for name in names:
        fn = BUILTIN_VALIDATORS.get(name)
        return_codes[name] = RC_MALFORMED if fn is None else int(fn(request))
    overall = max(return_codes.values()) if return_codes else RC_OK
    identity = {f: str(request.get(f, "")).strip() for f in _IDENTITY_FIELDS}
    return {
        "schema_version": "1.0",
        "artifact_type": "validator-execution-decision",
        "node_id": NODE_ID,
        **identity,
        "status": PASS if overall == RC_OK else BLOCKED,
        "overall_return_code": overall,
        "return_codes": return_codes,
        "replayed": False,
    }


__all__ = [
    "BLOCKED",
    "BUILTIN_VALIDATORS",
    "NODE_ID",
    "PASS",
    "RC_OK",
    "RC_MALFORMED",
    "RC_MISSING",
    "RC_MISMATCH",
    "run_validator_execution",
]
