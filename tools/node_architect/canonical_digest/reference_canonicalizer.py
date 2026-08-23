#!/usr/bin/env python3
"""gwc-jcs-v1 reference canonicalizer — Python implementation.

Independent RFC-8785/JCS-compatible canonical serialization + framed SHA-256
for the WP2 normative profile (SCRUM-397 WP3 cross-runtime conformance).

This is a REFERENCE implementation: it canonicalizes JSON text into the exact
deterministic UTF-8 bytes defined by RFC-8785 (JCS) and computes the framed
SHA-256 digest per gwc-jcs-v1. It is fully self-contained and never invokes
Node or any other runtime (cross-runtime independence is proven by the
conformance tests running the Python and Node references side by side).

Normative policies enforced (from governance/digest-profiles/gwc-jcs-v1.yaml):
  - strict supported input domain (null/bool/number/string/array/object)
  - negative_zero_policy=reject
  - non_finite_policy=reject
  - non_string_key_policy=reject
  - duplicate_raw_key_policy=reject_before_semantic_collapse
  - invalid_unicode_policy=reject_unpaired_surrogates
  - unicode_normalization=none  (valid Unicode preserved byte-for-byte)
  - canonical bytes: RFC-8785/JCS (NOT python json.dumps sort_keys)
  - SHA-256 + explicit length-prefixed domain framing:
      sha256( u32be(utf8_len(domain_tag)) || domain_tag_utf8
            || u64be(byte_len(preimage)) || preimage )
  - bounded resource limits
  - deterministic error taxonomy (DIGEST_* codes)

No production/shared API is provided here (that is WP4). Contract/schema +
conformance only. CANONICALIZATION_NEVER_GRANTS_AUTHORITY.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from decimal import Decimal

# --- Default profile resource limits (mirror gwc-jcs-v1.yaml) -------------
DEFAULT_RESOURCE_LIMITS = {
    "max_preimage_bytes": 1048576,
    "max_object_depth": 64,
    "max_object_keys": 100000,
    "max_array_items": 100000,
    "max_string_bytes": 1048576,
}

# Default domain tag bound from governance/digest-profile-registry.yaml.
DEFAULT_DOMAIN = "gwc.governance.evidence.canonical.v1"
DEFAULT_SCHEMA_REF = "schemas/canonical-digest-profile.schema.json"
FRAMING_SCHEME = "gwc-domain-sep-v1"

# Closed deterministic error taxonomy (mirror gwc-jcs-v1.yaml).
DIGEST_INPUT_DOMAIN_VIOLATION = "DIGEST_INPUT_DOMAIN_VIOLATION"
DIGEST_NEGATIVE_ZERO_REJECTED = "DIGEST_NEGATIVE_ZERO_REJECTED"
DIGEST_NON_FINITE_REJECTED = "DIGEST_NON_FINITE_REJECTED"
DIGEST_NON_STRING_KEY_REJECTED = "DIGEST_NON_STRING_KEY_REJECTED"
DIGEST_DUPLICATE_RAW_KEY_REJECTED = "DIGEST_DUPLICATE_RAW_KEY_REJECTED"
DIGEST_INVALID_UNICODE_REJECTED = "DIGEST_INVALID_UNICODE_REJECTED"
DIGEST_UNICODE_NORMALIZATION_NONE = "DIGEST_UNICODE_NORMALIZATION_NONE"
DIGEST_RESOURCE_LIMIT_EXCEEDED = "DIGEST_RESOURCE_LIMIT_EXCEEDED"
DIGEST_DOMAIN_TAG_MISMATCH = "DIGEST_DOMAIN_TAG_MISMATCH"
DIGEST_ENVELOPE_BINDING_MISMATCH = "DIGEST_ENVELOPE_BINDING_MISMATCH"


class CanonicalDigestError(ValueError):
    """Deterministic, replayable canonicalization failure with a DIGEST_* code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


# --- ES6 Number.prototype.toString compatible formatting (RFC-8785 3.2.2.3) --

_NUM_RE = re.compile(
    r"^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$"
)


def _shortest_digits(value: float):
    """Return (digits, decimal_exp) with value == d1.d2...dk * 10^decimal_exp.

    Uses Python's repr which yields the shortest decimal that round-trips to
    the identical IEEE-754 double (same digit sequence as ES6 Number#toString).
    """
    r = repr(value)
    m = _NUM_RE.match(r)
    if not m:  # pragma: no cover - repr always matches
        raise AssertionError(f"unexpected repr: {r!r}")
    sign, ipart, fpart, exp = m.groups()
    exp = int(exp) if exp else 0
    digits = (ipart + (fpart or "")).lstrip("0") or "0"
    # value = INT.FRAC * 10^EXP ; digits = INT+FRAC (len k)
    # value = d1.d2...dk * 10^(k-1 + EXP - len(FRAC))
    k = len(digits)
    frac_len = len(fpart) if fpart else 0
    decimal_exp = k - 1 + exp - frac_len
    return sign, digits, decimal_exp


def _js_number(value: float) -> str:
    """Serialize an IEEE-754 double with exact ES6 Number#toString semantics.

    Raises DIGEST_NON_FINITE_REJECTED / DIGEST_NEGATIVE_ZERO_REJECTED first.
    """
    if value != value or value in (math.inf, -math.inf):
        raise CanonicalDigestError(DIGEST_NON_FINITE_REJECTED)
    if value == 0 and math.copysign(1.0, value) < 0:
        raise CanonicalDigestError(DIGEST_NEGATIVE_ZERO_REJECTED)
    if value == 0:
        return "0"
    # Integer fast path (JS uses plain decimal for exact integers |x| < 1e21).
    if value == int(value) and abs(value) < 1e21:
        return str(int(value))
    sign, digits, e = _shortest_digits(value)
    if abs(value) < 1e-6 or abs(value) >= 1e21:
        # Exponential notation, JS format: d[.ddd]e±X (no leading-zero exponent).
        s = digits[0]
        if len(digits) > 1:
            s += "." + digits[1:]
        s += "e" + ("+" if e >= 0 else "-") + str(abs(e))
    else:
        # Fixed-point notation, JS format.
        pos = e + 1  # number of digits before the decimal point
        if pos <= 0:
            s = "0." + "0" * (-pos) + digits
        elif pos >= len(digits):
            s = digits + "0" * (pos - len(digits))
        else:
            s = digits[:pos] + "." + digits[pos:]
    return ("-" if sign else "") + s


# --- RFC-8785 string escaping (3.2.2.2) -------------------------------------
_ESCAPES = {
    0x22: '\\"',   # "
    0x5C: "\\\\",  # backslash
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
}


def _escape_string(s: str, *, max_string_bytes: int) -> str:
    """RFC-8785 minimal escaping: quote, backslash, C0 controls as \\u00xx.

    Non-ASCII characters are output literally (UTF-8) — no \\u escaping.
    unicode_normalization=none: code points are preserved as-is.
    Lone/unpaired surrogates (U+D800..U+DFFF) are REJECTED (not normalization).
    """
    out = []
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise CanonicalDigestError(DIGEST_INVALID_UNICODE_REJECTED)
        esc = _ESCAPES.get(cp)
        if esc is not None:
            out.append(esc)
        elif cp < 0x20:
            out.append("\\u%04x" % cp)
        else:
            out.append(ch)
    result = '"' + "".join(out) + '"'
    if len(result.encode("utf-8")) > max_string_bytes:
        raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    return result


# --- Negative-zero lexical detection ----------------------------------------
_JSON_NUMBER_TOKEN = re.compile(
    r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?"
)


def _has_negative_zero(raw_text: str) -> bool:
    """Detect any JSON number token whose value is exactly -0.

    Parsers collapse -0 to 0, so this must be checked at the lexical layer on
    the raw input (preserves evidence that semantic parsing would erase).
    """
    for m in _JSON_NUMBER_TOKEN.finditer(raw_text):
        tok = m.group(0)
        if not tok.startswith("-"):
            continue
        rest = re.sub(r"[eE][+-]?\d+$", "", tok[1:])
        if rest.replace(".", "").strip("0") == "":
            return True
    return False


def _reject_duplicate_or_nonstring_keys(pairs):
    """object_pairs_hook: reject duplicate raw keys before semantic collapse
    and reject non-string object keys (DIGEST_* taxonomy)."""
    seen = set()
    for key, _ in pairs:
        if not isinstance(key, str):
            raise CanonicalDigestError(DIGEST_NON_STRING_KEY_REJECTED)
        if key in seen:
            raise CanonicalDigestError(DIGEST_DUPLICATE_RAW_KEY_REJECTED)
        seen.add(key)
    return dict(pairs)


# --- Canonical serialization walk ------------------------------------------
def _canonicalize_value(value, depth: int, limits: dict) -> str:
    if depth > limits["max_object_depth"]:
        raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, int):
        # JSON integer (non-float) — from a strict-JSON parser these are the
        # values that are exactly integers; serialize as plain decimal.
        return str(value)
    if isinstance(value, str):
        return _escape_string(value, max_string_bytes=limits["max_string_bytes"])
    if isinstance(value, list):
        if len(value) > limits["max_array_items"]:
            raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        return "[" + ",".join(
            _canonicalize_value(item, depth + 1, limits) for item in value
        ) + "]"
    if isinstance(value, dict):
        if len(value) > limits["max_object_keys"]:
            raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        members = []
        for key in sorted(value, key=lambda k: tuple(ord(c) for c in k)):
            # RFC-8785 key ordering: lexicographic by UTF-16 code units.
            members.append(
                _escape_string(key, max_string_bytes=limits["max_string_bytes"])
                + ":"
                + _canonicalize_value(value[key], depth + 1, limits)
            )
        return "{" + ",".join(members) + "}"
    raise CanonicalDigestError(DIGEST_INPUT_DOMAIN_VIOLATION)


def _parse_constant(name):
    # NaN / Infinity / -Infinity literals (and overflowed literals handled in walk)
    raise CanonicalDigestError(DIGEST_NON_FINITE_REJECTED)


# --- Public reference API ----------------------------------------------------
def canonicalize_json_text(
    raw_text: str,
    *,
    resource_limits: dict | None = None,
    domain: str = DEFAULT_DOMAIN,
) -> bytes:
    """Canonicalize raw JSON text to exact RFC-8785/JCS UTF-8 bytes.

    Returns the canonical preimage bytes. Raises CanonicalDigestError with a
    deterministic DIGEST_* code on any strict-domain violation.
    """
    limits = {**DEFAULT_RESOURCE_LIMITS, **(resource_limits or {})}
    if len(raw_text.encode("utf-8")) > limits["max_preimage_bytes"]:
        raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    if _has_negative_zero(raw_text):
        raise CanonicalDigestError(DIGEST_NEGATIVE_ZERO_REJECTED)
    try:
        value = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_or_nonstring_keys,
            parse_constant=_parse_constant,
        )
    except json.JSONDecodeError as exc:
        # Non-string object keys are rejected by the stdlib parser before the
        # object_pairs_hook is consulted; map to the deterministic taxonomy.
        if "Expecting property name" in str(exc):
            raise CanonicalDigestError(DIGEST_NON_STRING_KEY_REJECTED) from exc
        raise CanonicalDigestError(DIGEST_INPUT_DOMAIN_VIOLATION) from exc
    canonical = _canonicalize_value(value, 1, limits)
    out = canonical.encode("utf-8")
    if len(out) > limits["max_preimage_bytes"]:
        raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    return out


def framed_sha256(
    canonical_bytes: bytes,
    *,
    domain: str = DEFAULT_DOMAIN,
) -> str:
    """Framed SHA-256 per gwc-jcs-v1 domain separation:
    sha256( u32be(utf8_len(domain_tag)) || domain_tag_utf8
         || u64be(byte_len(preimage)) || preimage )."""
    domain_utf8 = domain.encode("utf-8")
    frame = (
        struct.pack(">I", len(domain_utf8))
        + domain_utf8
        + struct.pack(">Q", len(canonical_bytes))
        + canonical_bytes
    )
    return hashlib.sha256(frame).hexdigest()


def canonical_digest(
    raw_text: str,
    *,
    domain: str = DEFAULT_DOMAIN,
    schema_ref: str = DEFAULT_SCHEMA_REF,
    resource_limits: dict | None = None,
) -> dict:
    """Return a digest-envelope for the given raw JSON text.

    Envelope binds profile/hash/domain/schema/framing/digest. Raises
    CanonicalDigestError on any strict-domain violation (no envelope produced).
    """
    preimage = canonicalize_json_text(
        raw_text, resource_limits=resource_limits, domain=domain
    )
    digest = framed_sha256(preimage, domain=domain)
    return {
        "schema_version": "1.0",
        "artifact_type": "digest-envelope",
        "profile_id": "gwc-jcs-v1",
        "hash_algorithm": "SHA-256",
        "domain": domain,
        "schema_ref": schema_ref,
        "preimage_framing_scheme": FRAMING_SCHEME,
        "preimage_byte_length": len(preimage),
        "hexdigest": digest,
    }
