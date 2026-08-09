#!/usr/bin/env python3
"""Pure, replay-safe package manifest loader — package_export.package-manifest-load.

Reads an approved package manifest source (dict, bytes, or file path), preserves
its stable entry order, and emits a deterministic digest.  The loader NEVER
mutates the source, performs export, publishes, or grants authority.

Design invariants:

* Pure evaluator.  Side effects are limited to optional read-only file I/O.
* Deterministic digest: identical source → identical digest and decision.
* Replay-safe: identical idempotency key with changed source → REPLAY_CONFLICT.
* Authority boundary: NEVER grants repository, PR, merge, deploy or production
  authority.  `authority_granted()` always returns False.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_ID = "gwc.package_export.package_manifest_load"
SCHEMA_VERSION = "0.1"
LOADER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Stable outcomes
# ---------------------------------------------------------------------------

OUTCOME_LOADED = "LOADED"
OUTCOME_BLOCKED = "BLOCKED"

REASON_MANIFEST_LOAD_INVALID = "MANIFEST_LOAD_INVALID"
REASON_READ_FAILED = "MANIFEST_READ_FAILED"
REASON_REPLAY_CONFLICT = "MANIFEST_REPLAY_CONFLICT"

OUTCOMES = (OUTCOME_LOADED, OUTCOME_BLOCKED)


class Outcome(str, Enum):
    LOADED = OUTCOME_LOADED
    BLOCKED = OUTCOME_BLOCKED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canon(obj: Any) -> str:
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k}:{_canon(v)}" for k, v in sorted(obj.items())) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in obj) + "]"
    return str(obj)


def _digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(_canon(p).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def _source_canon(manifest: Dict[str, Any]) -> str:
    """Canonical form of manifest for digest, excluding its own digest field."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class LoadResult:
    schema_id: str = SCHEMA_ID
    schema_version: str = SCHEMA_VERSION
    loader_version: str = LOADER_VERSION
    outcome: str = Outcome.LOADED
    reason_code: str = ""
    decision_digest: str = ""
    manifest: Dict[str, Any] = field(default_factory=dict)
    manifest_digest: str = ""
    entry_count: int = 0
    entry_order_preserved: bool = True
    idempotency_key: str = ""
    decided_at: str = ""
    replay_status: str = "IDEMPOTENT"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "loader_version": self.loader_version,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "decision_digest": self.decision_digest,
            "manifest": self.manifest,
            "manifest_digest": self.manifest_digest,
            "entry_count": self.entry_count,
            "entry_order_preserved": self.entry_order_preserved,
            "idempotency_key": self.idempotency_key,
            "decided_at": self.decided_at,
            "replay_status": self.replay_status,
            "authority_authorized": False,
            "reason": self.reason,
        }
        return d


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

_PREHASH_SKIP_FIELDS = {"manifest_digest", "decision_digest"}


def _normalize_manifest(raw: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    """Return (manifest_without_digest_field, manifest_digest)."""
    stripped = {k: v for k, v in raw.items() if k not in _PREHASH_SKIP_FIELDS}
    return stripped, _digest(stripped)


def _record_digest(result: LoadResult, manifest_without_digest: Dict[str, Any]) -> None:
    manifest_digest = _digest(manifest_without_digest)
    canonical = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "loader_version": LOADER_VERSION,
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "manifest": manifest_without_digest,
        "manifest_digest": manifest_digest,
        "entry_count": result.entry_count,
        "entry_order_preserved": result.entry_order_preserved,
        "idempotency_key": result.idempotency_key,
        "replay_status": result.replay_status,
    }
    result.decision_digest = _digest(canonical)
    result.manifest_digest = manifest_digest


def load_manifest(
    *,
    source: Any = None,
    source_path: Optional[str] = None,
    idempotency_key: str = "",
    prior_decision: Optional[Dict[str, Any]] = None,
    decided_at: Optional[str] = None,
) -> LoadResult:
    """Load a package manifest and produce a replay-safe decision record.

    Parameters:
        source: dict, bytes or str payload.  Preferred over source_path.
        source_path: optional filesystem path to read.  Read-only.
        idempotency_key: caller-supplied stable key for replay detection.
        prior_decision: previous decision for the same idempotency key.
        decided_at: ISO-8601 timestamp; defaults to now UTC.

    Returns:
        LoadResult with outcome, digest, and loaded manifest (or error detail).
    """
    result = LoadResult()
    result.idempotency_key = str(idempotency_key)
    result.decided_at = decided_at or _now_iso()

    # Read source.
    raw: Any
    if source is not None:
        if isinstance(source, dict):
            raw = source
        elif isinstance(source, (bytes, bytearray)):
            try:
                raw = json.loads(source)
            except json.JSONDecodeError as exc:
                result.outcome = Outcome.BLOCKED
                result.reason_code = REASON_READ_FAILED
                result.reason = str(exc)
                _record_digest(result, {})
                return result
        elif isinstance(source, str):
            p = Path(source)
            if p.is_file():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    result.outcome = Outcome.BLOCKED
                    result.reason_code = REASON_READ_FAILED
                    result.reason = str(exc)
                    _record_digest(result, {})
                    return result
            else:
                raw = source
        else:
            result.outcome = Outcome.BLOCKED
            result.reason_code = REASON_MANIFEST_LOAD_INVALID
            result.reason = f"unsupported source type: {type(source).__name__}"
            _record_digest(result, {})
            return result
    elif source_path is not None:
        try:
            raw = json.loads(Path(source_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.outcome = Outcome.BLOCKED
            result.reason_code = REASON_READ_FAILED
            result.reason = str(exc)
            _record_digest(result, {})
            return result
    else:
        result.outcome = Outcome.BLOCKED
        result.reason_code = REASON_MANIFEST_LOAD_INVALID
        result.reason = "no source or source_path provided"
        _record_digest(result, {})
        return result

    if not isinstance(raw, dict):
        result.outcome = Outcome.BLOCKED
        result.reason_code = REASON_MANIFEST_LOAD_INVALID
        result.reason = f"manifest root must be an object, got {type(raw).__name__}"
        _record_digest(result, {})
        return result

    if not isinstance(raw.get("entries"), list):
        result.outcome = Outcome.BLOCKED
        result.reason_code = REASON_MANIFEST_LOAD_INVALID
        result.reason = "manifest must contain an 'entries' list"
        _record_digest(result, {})
        return result

    # Replay conflict: same key, different semantic input.
    if prior_decision:
        prior_manifest = (prior_decision.get("manifest") or {}) if isinstance(prior_decision, dict) else {}
        if _canon(raw) != _canon(prior_manifest):
            result.outcome = Outcome.BLOCKED
            result.reason_code = REASON_REPLAY_CONFLICT
            result.replay_status = "CONFLICT"
            _record_digest(result, raw)
            return result
        result.replay_status = "IDEMPOTENT"

    manifest_without_digest, manifest_digest = _normalize_manifest(raw)
    result.outcome = Outcome.LOADED
    result.reason_code = ""
    result.manifest = manifest_without_digest
    result.manifest_digest = manifest_digest
    result.entry_count = len(manifest_without_digest.get("entries", []))
    # preserve order means list entry order matches original
    result.entry_order_preserved = True
    _record_digest(result, manifest_without_digest)
    return result


def authority_granted(decision: LoadResult) -> bool:
    """A manifest load decision never grants authority.  Always False."""
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load a package manifest.")
    parser.add_argument("--source", default=None)
    parser.add_argument("--source-path", default=None)
    parser.add_argument("--idempotency-key", default="")
    args = parser.parse_args(argv)

    decision = load_manifest(source=args.source, source_path=args.source_path,
                             idempotency_key=args.idempotency_key)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0 if decision.outcome == Outcome.LOADED else 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
