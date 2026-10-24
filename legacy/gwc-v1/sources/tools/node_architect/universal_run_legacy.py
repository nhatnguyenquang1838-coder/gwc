#!/usr/bin/env python3
"""R7: namespaced legacy compatibility, translation provenance, evidence-strength
rules, and the never-reinterpret invariant.

C12 (compatibility/migration is namespaced, provenance-bound and never
reinterprets legacy semantics) per the C1-C15 matrix. Composes E1 kernel digest
primitives and evidence-strength semantics from evidence_quality_check.

Pure / transport-neutral: never persists, never grants authority, never mutates
external targets. Every function returns a typed result or raises a
deterministic fail-closed error before any effect.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
LEGACY_NAMESPACE_PREFIX = "gwc.legacy."
EVIDENCE_STRENGTHS = ("OBSERVED", "INFERRED", "PROJECTED")


class LegacyError(ValueError):
    """Deterministic fail-closed legacy compatibility error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


class NamespacingError(LegacyError):
    """Typed error when a translation is not namespaced (C12)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("LEGACY_NAMESPACE_INVALID", detail)


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise LegacyError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


def _is_legacy_namespace(namespace: str) -> bool:
    return isinstance(namespace, str) and namespace.startswith(LEGACY_NAMESPACE_PREFIX) and len(namespace) > len(LEGACY_NAMESPACE_PREFIX)


@dataclass(frozen=True)
class LegacyTranslation:
    """Immutable namespaced legacy translation with provenance (C12)."""

    run_id: str
    legacy_profile: dict[str, Any]
    legacy_payload: dict[str, Any]
    namespace: str
    source_ref: str | None
    translation_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "legacy-translation",
            "run_id": self.run_id,
            "legacy_profile": copy.deepcopy(self.legacy_profile),
            "legacy_payload": copy.deepcopy(self.legacy_payload),
            "namespace": self.namespace,
            "source_ref": self.source_ref,
            "translation_digest": self.translation_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LegacyTranslation":
        return cls(
            run_id=str(data.get("run_id", "")),
            legacy_profile=dict(data.get("legacy_profile", {})),
            legacy_payload=dict(data.get("legacy_payload", {})),
            namespace=str(data.get("namespace", "")),
            source_ref=data.get("source_ref"),
            translation_digest=str(data.get("translation_digest", "")),
        )


def build_legacy_translation(
    *,
    run_id: str,
    legacy_profile: Mapping[str, Any],
    legacy_payload: Mapping[str, Any],
    namespace: str,
    source_ref: str | None = None,
) -> LegacyTranslation:
    """Build a namespaced, provenance-bound legacy translation (C12).

    Never-reinterpret invariant: the legacy profile must NOT be the universal
    profile (a universal record can never be treated as legacy), the payload is
    preserved byte-for-byte, and the namespace must be under gwc.legacy.*.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID")
    profile = dict(legacy_profile or {})
    _require(bool(profile.get("id")), "LEGACY_PROFILE_ID_REQUIRED")
    # Universal must never be aliased into the legacy path (C12 invariant).
    if profile.get("id") == UNIVERSAL_PROFILE.get("id"):
        raise LegacyError("UNIVERSAL_NOT_LEGACY", "universal profile cannot be translated as legacy")
    _require(_is_legacy_namespace(namespace), "LEGACY_NAMESPACE_INVALID", namespace)
    payload = dict(legacy_payload or {})
    _require(bool(payload), "LEGACY_PAYLOAD_EMPTY")
    digest = _sha256_digest(
        run_id, profile, payload, namespace, source_ref,
    )
    return LegacyTranslation(
        run_id=run_id, legacy_profile=profile, legacy_payload=payload,
        namespace=namespace, source_ref=source_ref, translation_digest=digest,
    )


def validate_legacy_translation(translation: LegacyTranslation) -> bool:
    """Verify translation digest against its canonical fields (C12)."""
    try:
        expected = _sha256_digest(
            translation.run_id, translation.legacy_profile,
            translation.legacy_payload, translation.namespace,
            translation.source_ref,
        )
        return translation.translation_digest == expected
    except Exception:
        return False


def classify_evidence_strength(strength: str, *, namespace: str) -> str:
    """Classify evidence strength under a legacy namespace (C12)."""
    _require(_is_legacy_namespace(namespace), "LEGACY_NAMESPACE_INVALID", namespace)
    _require(strength in EVIDENCE_STRENGTHS, "EVIDENCE_STRENGTH_UNKNOWN", str(strength))
    return strength


__all__ = [
    "EVIDENCE_STRENGTHS",
    "LEGACY_NAMESPACE_PREFIX",
    "LegacyError",
    "LegacyTranslation",
    "NamespacingError",
    "build_legacy_translation",
    "classify_evidence_strength",
    "validate_legacy_translation",
]
