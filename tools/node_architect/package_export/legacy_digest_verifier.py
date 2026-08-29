#!/usr/bin/env python3
"""gwc-jcs-v1 legacy-python-json-v1 verifier (SCRUM-397 WP4).

Legacy verification ONLY — never used for new writes. Provides
deterministic verification of legacy-python-json-v1 canonical forms
(sorted-keys compact JSON, UTF-8). Fail-closed: any parse problem
produces a deterministic REJECTED result.

Represents legacy behavior strictly as compatibility metadata; never
widens or grants authority.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from deterministic_hash_verification import (  # type: ignore  (repo-local import path)
    build_digest_envelope,
    framed_profile_sha256,
    verify_digest_envelope,
    PROFILE_DIGEST_ENVELOPE_OK,
    PROFILE_DIGEST_ENVELOPE_MISMATCH,
)

DIGEST_LEGACY_VERIFY_ONLY = "DIGEST_LEGACY_VERIFY_ONLY"
LEGACY_PROFILE_ID = "legacy-python-json-v1"
DEFAULT_DOMAIN = "gwc.governance.evidence.canonical.legacy.v1"


def _legacy_canonical_bytes(raw_text: str) -> bytes:
    """legacy-python-json-v1 canonical form: python json.dumps sort_keys UTF-8.

    Represented strictly as compatibility metadata (VERIFY_ONLY); never used for
    new writes and never widened.
    """
    value = json.loads(raw_text)
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return blob.encode("utf-8")


def verify_legacy_digest(
    raw_text: str,
    envelope: Dict[str, Any],
    *,
    registry: Optional[Dict[str, Any]] = None,
) -> str:
    """Verify a legacy-python-json-v1 digest envelope against the canonicalized input.

    Returns PROFILE_DIGEST_ENVELOPE_OK on exact match, else
    PROFILE_DIGEST_ENVELOPE_MISMATCH. Fail-closed: any parse/verification problem
    returns MISMATCH.
    """
    try:
        canonical = _legacy_canonical_bytes(raw_text)
    except Exception:
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    return verify_digest_envelope(envelope, canonical)


def legacy_digest_envelope(
    raw_text: str,
    *,
    domain: Optional[str] = None,
    schema_ref: str = "schemas/digest-envelope.schema.json",
) -> Dict[str, Any]:
    """Build a legacy-python-json-v1 digest envelope for VERIFY_ONLY contexts.

    Used only for compatibility metadata representation; never for new writes.
    """
    canonical = _legacy_canonical_bytes(raw_text)
    use_domain = domain or DEFAULT_DOMAIN
    return build_digest_envelope(
        profile_id=LEGACY_PROFILE_ID,
        canonical_bytes=canonical,
        domain=use_domain,
        schema_ref=schema_ref,
    )
