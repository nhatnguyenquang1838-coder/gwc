#!/usr/bin/env python3
"""gwc-jcs-v1 shared runtime API (SCRUM-397 WP4).

Registry-aware, fail-closed canonical digest API for the gwc-jcs-v1 profile
(WP2 normative contract). This is the *shared runtime interface* consumers will
use (wired at WP5); it:

  * loads governance/digest-profile-registry.yaml (read-only) and derives a
    ProfilePolicy per profile;
  * FAILS CLOSED: lifecycle REJECTED (e.g. gwc-jcs-v1 until WP3/WP4 prereqs)
    refuses every new-write digest request; VERIFY_ONLY permits verification
    only (never new writes); unknown profiles are REJECTED;
  * canonicalizes gwc-jcs-v1 input to exact RFC-8785/JCS UTF-8 bytes with a
    self-contained production canonicalizer (mirrors the WP2 strict domain:
    negative zero / non-finite / non-string key / duplicate raw key / invalid
    Unicode reject; unicode_normalization=none);
  * builds/verifies the length-prefixed framed SHA-256 digest envelope via the
    shared primitives in deterministic_hash_verification.py (extend, not
    duplicate);
  * never grants authority: CANONICALIZATION_NEVER_GRANTS_AUTHORITY.

Legacy-python-json-v1 new-write is refused; legacy *verification* lives in
legacy_digest_verifier.py. Raw-file/raw-byte hashes are untouched.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Dict, Optional

from deterministic_hash_verification import (  # type: ignore  (repo-local import path)
    build_digest_envelope,
    framed_profile_sha256,
    verify_digest_envelope,
    PROFILE_DIGEST_ENVELOPE_OK,
    PROFILE_DIGEST_ENVELOPE_MISMATCH,
)

CANONICALIZATION_NEVER_GRANTS_AUTHORITY = True

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "governance" / "digest-profile-registry.yaml"
DEFAULT_PROFILE_SCHEMA_REF = "schemas/canonical-digest-profile.schema.json"
DEFAULT_ENVELOPE_SCHEMA_REF = "schemas/digest-envelope.schema.json"
DEFAULT_DOMAIN = "gwc.governance.evidence.canonical.v1"

# Registry-level deterministic error codes (distinct from WP2 canonicalization
# taxonomy; still deterministic and closed).
DIGEST_PROFILE_UNKNOWN = "DIGEST_PROFILE_UNKNOWN"
DIGEST_PROFILE_NOT_ACTIVATED = "DIGEST_PROFILE_NOT_ACTIVATED"
DIGEST_LEGACY_VERIFY_ONLY = "DIGEST_LEGACY_VERIFY_ONLY"
DIGEST_REGISTRY_UNAVAILABLE = "DIGEST_REGISTRY_UNAVAILABLE"

# Canonicalization taxonomy (mirror gwc-jcs-v1.yaml).
DIGEST_INPUT_DOMAIN_VIOLATION = "DIGEST_INPUT_DOMAIN_VIOLATION"
DIGEST_NEGATIVE_ZERO_REJECTED = "DIGEST_NEGATIVE_ZERO_REJECTED"
DIGEST_NON_FINITE_REJECTED = "DIGEST_NON_FINITE_REJECTED"
DIGEST_NON_STRING_KEY_REJECTED = "DIGEST_NON_STRING_KEY_REJECTED"
DIGEST_DUPLICATE_RAW_KEY_REJECTED = "DIGEST_DUPLICATE_RAW_KEY_REJECTED"
DIGEST_INVALID_UNICODE_REJECTED = "DIGEST_INVALID_UNICODE_REJECTED"
DIGEST_RESOURCE_LIMIT_EXCEEDED = "DIGEST_RESOURCE_LIMIT_EXCEEDED"

DEFAULT_RESOURCE_LIMITS = {
    "max_preimage_bytes": 1048576,
    "max_object_depth": 64,
    "max_object_keys": 100000,
    "max_array_items": 100000,
    "max_string_bytes": 1048576,
}


class CanonicalDigestAPIError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


class ProfilePolicy:
    """Fail-closed view of one digest-profile-registry entry."""

    __slots__ = (
        "profile_id", "lifecycle_state", "new_write_allowed",
        "verify_only_allowed", "reason", "domain", "schema_ref", "hash_algorithm",
    )

    def __init__(self, entry: Dict[str, Any]):
        self.profile_id = entry.get("profile_id")
        self.lifecycle_state = entry.get("lifecycle_state")
        self.new_write_allowed = bool(entry.get("new_write_allowed", False))
        self.verify_only_allowed = bool(entry.get("verify_only_allowed", False))
        self.reason = entry.get("reason", "")
        self.domain = entry.get("domain", "")
        self.schema_ref = entry.get("schema_ref")
        self.hash_algorithm = entry.get("hash_algorithm", "SHA-256")

    @property
    def is_gwc_jcs_v1(self) -> bool:
        return self.profile_id == "gwc-jcs-v1"


def load_registry(registry_path: Optional[Path] = None) -> Dict[str, ProfilePolicy]:
    """Read governance/digest-profile-registry.yaml into ProfilePolicy objects.

    Read-only; fail-closed: any load/parse problem raises DIGEST_REGISTRY_UNAVAILABLE.
    """
    import yaml
    path = Path(registry_path) if registry_path is not None else DEFAULT_REGISTRY_PATH
    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        entries = doc["entries"]
        return {pid: ProfilePolicy(e) for pid, e in entries.items()}
    except Exception as exc:  # pragma: no cover - defensive
        raise CanonicalDigestAPIError(DIGEST_REGISTRY_UNAVAILABLE, str(exc)) from exc


# --- RFC-8785/JCS canonicalization (self-contained production impl) -------

_NUM_RE = re.compile(r"^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$")
_ESCAPES = {
    0x22: '\\"',
    0x5C: "\\\\",
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
}
_JSON_NUMBER_TOKEN = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _has_negative_zero(raw_text: str) -> bool:
    for m in _JSON_NUMBER_TOKEN.finditer(raw_text):
        tok = m.group(0)
        if not tok.startswith("-"):
            continue
        rest = re.sub(r"[eE][+-]?\d+$", "", tok[1:])
        if rest.replace(".", "").strip("0") == "":
            return True
    return False


def _reject_duplicate_or_nonstring_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if not isinstance(key, str):
            raise CanonicalDigestAPIError(DIGEST_NON_STRING_KEY_REJECTED)
        if key in seen:
            raise CanonicalDigestAPIError(DIGEST_DUPLICATE_RAW_KEY_REJECTED)
        seen.add(key)
    return dict(pairs)


def _parse_constant(name):
    raise CanonicalDigestAPIError(DIGEST_NON_FINITE_REJECTED)


def is_integer_valued_binary64(x: float) -> bool:
    """True iff `x` is a finite float whose mathematical value is an integer.

    Mirrors the reference canonicalizer's JCS integer-notation rule.
    """
    if not isinstance(x, float):
        return False
    if math.isnan(x) or math.isinf(x):
        return False
    return x == math.floor(x)


def _shortest_digits(value: float):
    r = repr(value)
    m = _NUM_RE.match(r)
    if not m:  # pragma: no cover
        raise AssertionError(f"unexpected repr: {r!r}")
    sign, ipart, fpart, exp = m.groups()
    exp = int(exp) if exp else 0
    digits = (ipart + (fpart or "")).lstrip("0") or "0"
    k = len(digits)
    frac_len = len(fpart) if fpart else 0
    return sign, digits, k - 1 + exp - frac_len


def _js_number(value: float) -> str:
    """Emit a finite double as ECMAScript/JSON shortest-round-trip text.

    Matches Node ``JSON.stringify`` / RFC 8785 JCS ``jcs_shortest_round_trip``:
    - non-finite rejected; negative zero rejected (C5b);
    - shortest digits come from Python ``repr``, re-derived under the ES
      fixed/exponential rule: fixed when decimal exponent e in [-6, 21),
      exponential otherwise, with explicit '+' in the exponent;
    - a fixed-form integer-valued double (e.g. 3.0) keeps JCS integer notation
      (trailing '.0' stripped -> "3"); a large integer double whose ES form is
      exponential (e.g. 1e21) stays "1e+21", matching Node.
    """
    if value != value or value in (math.inf, -math.inf):
        raise CanonicalDigestAPIError(DIGEST_NON_FINITE_REJECTED)
    if value == 0.0 and math.copysign(1.0, value) < 0:
        raise CanonicalDigestAPIError(DIGEST_NEGATIVE_ZERO_REJECTED)
    if value == 0.0:
        return "0"
    s = repr(value)
    sign = ""
    if s.startswith("-"):
        sign = "-"
        s = s[1:]
    if "e" in s or "E" in s:
        mant, exp = s.split("e") if "e" in s else s.split("E")
        exp = int(exp)
        digits = mant.replace(".", "")
        if -6 <= exp < 21:
            pos = exp + 1
            if pos <= 0:
                out = "0." + "0" * (-pos) + digits
            elif pos >= len(digits):
                out = digits + "0" * (pos - len(digits))
            else:
                out = digits[:pos] + "." + digits[pos:]
        else:
            out = digits[0]
            if len(digits) > 1:
                out += "." + digits[1:]
            out += "e" + ("+" if exp >= 0 else "-") + str(abs(exp))
        return sign + out
    if s.endswith(".0"):
        s = s[:-2]
    return sign + s


def _escape_string(s: str, *, max_string_bytes: int) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        cp = ord(s[i])
        if 0xD800 <= cp <= 0xDBFF and i + 1 < n and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            # Valid surrogate pair (non-BMP code point) — preserved as-is.
            out.append(s[i])
            out.append(s[i + 1])
            i += 2
            continue
        if 0xD800 <= cp <= 0xDFFF:
            # Lone surrogate (isolated, or high not followed by low) — rejected.
            raise CanonicalDigestAPIError(DIGEST_INVALID_UNICODE_REJECTED)
        esc = _ESCAPES.get(cp)
        if esc is not None:
            out.append(esc)
        elif cp < 0x20:
            out.append("\\u%04x" % cp)
        else:
            out.append(s[i])
        i += 1
    result = '"' + "".join(out) + '"'
    if len(result.encode("utf-8")) > max_string_bytes:
        raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    return result


def _canonicalize_value(value, depth: int, limits: Dict[str, int]) -> str:
    if depth > limits["max_object_depth"]:
        raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _escape_string(value, max_string_bytes=limits["max_string_bytes"])
    if isinstance(value, list):
        if len(value) > limits["max_array_items"]:
            raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        return "[" + ",".join(
            _canonicalize_value(item, depth + 1, limits) for item in value
        ) + "]"
    if isinstance(value, dict):
        if len(value) > limits["max_object_keys"]:
            raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        members = []
        # C3: validate every key's Unicode BEFORE sorting so a lone-surrogate key
        # raises the controlled DIGEST_INVALID_UNICODE_REJECTED (not a raw
        # UnicodeEncodeError from .encode() during sort-key computation).
        for key in value:
            _escape_string(key, max_string_bytes=limits["max_string_bytes"])

        def _utf16_code_units(s: str) -> List[int]:
            # Surrogate-safe UTF-16 code-unit expansion (see reference canonicalizer).
            units: List[int] = []
            for ch in s:
                cp = ord(ch)
                if cp >= 0x10000:
                    cp -= 0x10000
                    units.append(0xD800 + (cp >> 10))
                    units.append(0xDC00 + (cp & 0x3FF))
                else:
                    units.append(cp)
            return units

        # RFC-8785/JCS: keys sorted lexicographically by UTF-16 code-unit
        # order (NOT Python code points), so non-BMP keys order identically to
        # JS runtimes.
        for key in sorted(value, key=_utf16_code_units):
            members.append(
                _escape_string(key, max_string_bytes=limits["max_string_bytes"])
                + ":"
                + _canonicalize_value(value[key], depth + 1, limits)
            )
        return "{" + ",".join(members) + "}"
    raise CanonicalDigestAPIError(DIGEST_INPUT_DOMAIN_VIOLATION)


def canonicalize_gwc_jcs_v1(
    raw_text: str,
    *,
    resource_limits: Optional[Dict[str, int]] = None,
) -> bytes:
    """Canonicalize raw JSON text to exact RFC-8785/JCS UTF-8 bytes.

    Enforces the full gwc-jcs-v1 strict input domain (duplicate raw keys and
    negative zero are detected lexically on the raw text). Raises
    CanonicalDigestAPIError with a deterministic DIGEST_* code on violation.
    """
    limits = {**DEFAULT_RESOURCE_LIMITS, **(resource_limits or {})}
    try:
        preimage_size = len(raw_text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise CanonicalDigestAPIError(
            DIGEST_INVALID_UNICODE_REJECTED, "lone surrogate in raw text"
        ) from exc
    if preimage_size > limits["max_preimage_bytes"]:
        raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    if _has_negative_zero(raw_text):
        raise CanonicalDigestAPIError(DIGEST_NEGATIVE_ZERO_REJECTED)
    try:
        value = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_or_nonstring_keys,
            parse_constant=_parse_constant,
        )
    except json.JSONDecodeError as exc:
        if "Expecting property name" in str(exc):
            raise CanonicalDigestAPIError(DIGEST_NON_STRING_KEY_REJECTED) from exc
        raise CanonicalDigestAPIError(DIGEST_INPUT_DOMAIN_VIOLATION) from exc
    canonical = _canonicalize_value(value, 1, limits)
    out = canonical.encode("utf-8")
    if len(out) > limits["max_preimage_bytes"]:
        raise CanonicalDigestAPIError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    return out


def _legacy_canonical_bytes(raw_text: str) -> bytes:
    """legacy-python-json-v1 canonical form: python json.dumps sort_keys UTF-8.

    Represented strictly as compatibility metadata (VERIFY_ONLY); never used for
    new writes and never widened.
    """
    value = json.loads(raw_text)
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return blob.encode("utf-8")


def canonical_digest(
    raw_text: str,
    *,
    profile_id: str = "gwc-jcs-v1",
    domain: Optional[str] = None,
    schema_ref: str = DEFAULT_PROFILE_SCHEMA_REF,
    registry: Optional[Dict[str, ProfilePolicy]] = None,
) -> Dict[str, Any]:
    """Request a NEW canonical digest envelope for the profile.

    FAILS CLOSED: returns/raises a deterministic error unless the profile is in
    lifecycle NEW_WRITE_ALLOWED. gwc-jcs-v1 is REJECTED (pending WP3/WP4) so any
    new-write request is refused with DIGEST_PROFILE_NOT_ACTIVATED; legacy
    profile new-write is refused with DIGEST_LEGACY_VERIFY_ONLY.
    """
    reg = registry if registry is not None else load_registry()
    policy = reg.get(profile_id)
    if policy is None:
        raise CanonicalDigestAPIError(DIGEST_PROFILE_UNKNOWN, profile_id)
    if not policy.new_write_allowed:
        if policy.is_gwc_jcs_v1 or policy.lifecycle_state == "REJECTED":
            raise CanonicalDigestAPIError(
                DIGEST_PROFILE_NOT_ACTIVATED,
                f"{profile_id} lifecycle={policy.lifecycle_state} reason={policy.reason}",
            )
        raise CanonicalDigestAPIError(DIGEST_LEGACY_VERIFY_ONLY, profile_id)
    if policy.hash_algorithm != "SHA-256":
        raise CanonicalDigestAPIError(DIGEST_PROFILE_NOT_ACTIVATED, "unsupported hash")

    use_domain = domain or policy.domain or DEFAULT_DOMAIN
    canonical = canonicalize_gwc_jcs_v1(raw_text)
    envelope = build_digest_envelope(
        profile_id=profile_id,
        canonical_bytes=canonical,
        domain=use_domain,
        schema_ref=schema_ref,
    )
    return envelope


def verify_digest(
    raw_text: str,
    envelope: Dict[str, Any],
    *,
    registry: Optional[Dict[str, ProfilePolicy]] = None,
) -> str:
    """Verify a digest envelope against the canonicalized input.

    Returns PROFILE_DIGEST_ENVELOPE_OK on exact match, else
    PROFILE_DIGEST_ENVELOPE_MISMATCH. Verification-only profile entries are
    allowed here; unknown profiles fail closed with DIGEST_PROFILE_UNKNOWN.
    """
    reg = registry if registry is not None else load_registry()
    policy = reg.get(envelope.get("profile_id", ""))
    if policy is None:
        raise CanonicalDigestAPIError(DIGEST_PROFILE_UNKNOWN)
    if not (policy.verify_only_allowed or policy.new_write_allowed):
        raise CanonicalDigestAPIError(DIGEST_PROFILE_NOT_ACTIVATED)
    try:
        canonical = canonicalize_gwc_jcs_v1(raw_text)
    except CanonicalDigestAPIError:
        return PROFILE_DIGEST_ENVELOPE_MISMATCH
    return verify_digest_envelope(envelope, canonical)
