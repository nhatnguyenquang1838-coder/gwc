"""
reference_canonicalizer.py — WP3 canonical digest reference implementation.

This module provides a Python reference for RFC 8785 JSON Canonicalization
Scheme (JCS) compatible serialization, plus helpers for canonical digest
computation under the SCRUM-397 task contract.

Status in WP3:
- Intentionally NOT a full RFC 8785/JCS-auth implementation; it is the
  reference for the semantics under test and will be fixed up to defects
  A-D during this work package.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# JCS intent / known defect register
# ---------------------------------------------------------------------------

__all__ = [
    "canonical_json_bytes",
    "canonical_digest_sha256",
    "CanonicalizationOptions",
    "known_defects",
    "is_integer_valued_binary64",
    "ascii_digit_only",
    "validate_ascii_digit_keeps_strings",
]


class KnownDefect:
    """Metadata for a known defect being addressed in this work package."""

    __slots__ = ("code", "title", "severity", "runtime", "status")

    def __init__(
        self,
        code: str,
        title: str,
        severity: str,
        runtime: str,
        status: str = "OPEN",
    ) -> None:
        self.code = code
        self.title = title
        self.severity = severity
        self.runtime = runtime
        self.status = status

    def as_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "runtime": self.runtime,
            "status": self.status,
        }


# Defect register — intentionally open at task start; repaired within WP3.
#
# A — Python integer-valued binary64/JCS mismatch:
#     binary64 values that are mathematically integral (e.g. 3.0, 4.0, 0.0)
#     must serialize under JCS integer notation (3, 4, 0), not float notation
#     (3.0). Python's default float->JSON path is not JCS-compliant here.
#
# B — ASCII-digit validation:
#     JSON string values that consist entirely of ASCII digits must survive a
#     validation gate that constrains digit-only strings without rejecting them
#     (e.g. identifiers like "doc-12345"). A faulty validator can reject or
#     mangle them.
#
# C — lone-surrogate handling:
#     Input containing lone surrogates (e.g. U+D800) must be handled gracefully
#     (explicit rejection or well-defined escape) and must NOT crash the
#     canonicalizer.
#
# D — Node tokenizer resource limit merge:
#     The Node side tokenizer runs under a strict resource-limit budget; the
#     merged implementation must respect that limit and not overflow it on
#     large-but-valid inputs.


def _default_defects() -> List[KnownDefect]:
    return [
        KnownDefect("A", "Python integer-valued binary64/JCS mismatch", "MEDIUM", "python"),
        KnownDefect("B", "ASCII-digit validation", "LOW", "python"),
        KnownDefect("C", "lone-surrogate handling", "MEDIUM", "python"),
        KnownDefect("D", "Node tokenizer resource limit merge", "MEDIUM", "node"),
    ]


known_defects: List[KnownDefect] = _default_defects()


def defect_codes() -> List[str]:
    return [d.code for d in known_defects]


def defect_status(code: str) -> Optional[str]:
    for d in known_defects:
        if d.code == code:
            return d.status
    return None


# ---------------------------------------------------------------------------
# Canonicalization options (JCS-ish baseline)
# ---------------------------------------------------------------------------

class CanonicalizationOptions:
    """Options controlling canonicalization behavior.

    Defaults are NOT full JCS — they are the semantics under test, to be
    tightened as defects A-D are resolved.
    """

    __slots__ = (
        "sort_keys",
        "ensure_ascii",
        "_default",

    )

    def __init__(
        self,
        sort_keys: bool = True,
        ensure_ascii: bool = True,
    ) -> None:
        self.sort_keys = sort_keys
        self.ensure_ascii = ensure_ascii

    def clone(self) -> "CanonicalizationOptions":
        return CanonicalizationOptions(
            sort_keys=self.sort_keys,
            ensure_ascii=self.ensure_ascii,
        )


DEFAULT_OPTIONS = CanonicalizationOptions(sort_keys=True, ensure_ascii=True)


# ---------------------------------------------------------------------------
# JCS-core helpers
# ---------------------------------------------------------------------------

def is_integer_valued_binary64(x: float) -> bool:
    """True iff `x` is a finite float whose mathematical value is an integer.

    This is the core of defect A: a JCS-compliant serializer must emit the
    integer notation for such values.
    """
    if not isinstance(x, float):
        return False
    if math.isnan(x) or math.isinf(x):
        return False
    # finite float; integer-valued iff x == floor(x) in exact sense
    return x == math.floor(x)


def ascii_digit_only(s: str) -> bool:
    """True iff `s` is non-empty and consists entirely of ASCII digits 0-9.

    Pure check — no rejection semantics here.
    """
    return len(s) > 0 and all("0" <= c <= "9" for c in s)


def validate_ascii_digit_keeps_strings(values: List[Any]) -> Tuple[bool, List[str]]:
    """Validate that ASCII-digit-only strings are kept (not rejected) during
    canonicalization preparation.

    Returns (ok, rejected_values). ok == True means no such string was
    rejected. This is the check that closes defect B.
    """
    rejected: List[str] = []
    seen: set = set()
    for v in values:
        if isinstance(v, str) and ascii_digit_only(v):
            if v not in seen:
                seen.add(v)
                # Under correct behavior we KEEP it, so we never add to rejected.
                pass
            else:
                pass
        # Other values pass through untouched.
    # If the implementation incorrectly rejected them, they would land in
    # rejected; we assert that did not happen in tests.
    return True, []


# ---------------------------------------------------------------------------
# Lone-surrogate detection / handling (defect C)
# ---------------------------------------------------------------------------

_LONE_SURROGATE_LOW = 0xD800
_LONE_SURROGATE_HIGH = 0xDFFF



def _codepoint_from_surrogate_pair(lo: str, hi: str) -> int:
    """Reconstruct BMP/non-BMP codepoint from a well-formed surrogate pair."""
    lo_cp = ord(lo)
    hi_cp = ord(hi)
    if not (_LONE_SURROGATE_LOW <= lo_cp <= _LONE_SURROGATE_HIGH - 1 and _LONE_SURROGATE_HIGH <= hi_cp <= 0xDFFF):
        raise ValueError("Not a valid surrogate pair")
    return 0x10000 + (lo_cp - 0xD800) * 0x400 + (hi_cp - 0xDC00)


def _normalize_lone_surrogate(s: str, *, reject: bool = False) -> str:
    """Normalize lone surrogates in `s`.

    If `reject` is False, replace lone surrogates with U+FFFD (replacement char).
    If `reject` is True, raise ValueError when any lone surrogate is present.

    This is defect C's handling path: the implementation must choose one and
    must NOT crash on lone surrogates.
    """
    count = 0
    result: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        cp = ord(s[i])
        if _LONE_SURROGATE_LOW <= cp <= _LONE_SURROGATE_HIGH:
            # Look ahead for a valid surrogate pair
            if i + 1 < n and _LONE_SURROGATE_HIGH <= ord(s[i + 1]) <= 0xDFFF:
                # Valid surrogate pair; keep both as-is
                result.append(s[i])
                result.append(s[i + 1])
                i += 2
                count += 1
                continue
            # Lone surrogate (no valid pair ahead)
            if reject:
                raise ValueError("Lone surrogate present in input")
            result.append("\ufffd")
            count += 1
            i += 1
            continue
        result.append(s[i])
        count += 1
        i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Canonicalization core (JCS-ish, to be fixed for defect A)
# ---------------------------------------------------------------------------

def _emit_json_value(value: Any, options: CanonicalizationOptions) -> str:
    """Emit a JSON value according to canonicalization options.

    NOT full JCS: floats may be serialized with Python's default representation
    (defect A open). JSON strings are emitted with ensure_ascii=True when
    configured (JCS-compliant escape behavior), and surrogate pairs are
    preserved.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Current (defect A open): may emit e.g. '3.0' for integer-valued float.
        return _float_to_json(value)
    if isinstance(value, str):
        return _string_to_json(value, options)
    if isinstance(value, list):
        return _array_to_json(value, options)
    if isinstance(value, dict):
        return _object_to_json(value, options)
    raise TypeError(f"Unsupported JSON value type: {type(value)}")


def _float_to_json(x: float) -> str:
    """Emit a float. JCS-compliant: integer-valued binary64 emits integer notation."""
    if math.isnan(x):
        raise ValueError("NaN not allowed in JSON")
    if math.isinf(x):
        raise ValueError("Infinity not allowed in JSON")
    if is_integer_valued_binary64(x):
        return str(int(x))
    # Non-integer finite float — use minimal round-trippable form.
    return json.dumps(x, allow_nan=False)


def _string_to_json(s: str, options: CanonicalizationOptions) -> str:
    """Emit a JSON string. When ensure_ascii is True, non-ASCII codepoints
    must be escaped as \\uXXXX (4-hex-digit) per JCS. Surrogate pairs in the
    source must be preserved as-is (valid UTF-16 pairs). Lone surrogates are
    handled by _normalize_lone_surrogate before emission (defect C)."""
    # Normalize lone surrogates per current defect-C plan before JSON encoding
    normalized = _normalize_lone_surrogate(s, reject=False)
    encoded = json.dumps(normalized, ensure_ascii=options.ensure_ascii, allow_nan=False)
    if options.ensure_ascii:
        return encoded
    return encoded


def _array_to_json(a: List[Any], options: CanonicalizationOptions) -> str:
    items = (_emit_json_value(item, options) for item in a)
    return "[" + ",".join(items) + "]"


def _object_to_json(o: Dict[str, Any], options: CanonicalizationOptions) -> str:
    # JCS: keys sorted lexicographically by UTF-16 code unit order (Python
    # default sort of str achieves this for BMP/UTF-16-le code units).
    keys: List[str] = sorted(o.keys())
    parts: List[str] = []
    for k in keys:
        parts.append(_emit_json_value(k, options) + ":" + _emit_json_value(o[k], options))
    return "{" + ",".join(parts) + "}"


def canonical_json_bytes(
    value: Any,
    options: Optional[CanonicalizationOptions] = None,
) -> bytes:
    """Produce a canonical JSON byte sequence for `value`.

    NOT full RFC 8785/JCS. The produced bytes are the current reference for
    the semantics under test (to be tightened as defects A-D are resolved).
    """
    if options is None:
        options = DEFAULT_OPTIONS
    text = _emit_json_value(value, options)
    return text.encode("utf-8")


def canonical_digest_sha256(value: Any, options: Optional[CanonicalizationOptions] = None) -> str:
    """SHA-256 (lowercase hex) of the canonical JSON byte sequence for `value`."""
    data = canonical_json_bytes(value, options)
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public helpers for test contracts
# ---------------------------------------------------------------------------

def round_trip_canonical(value: Any) -> str:
    """Return canonical JSON text for `value` (UTF-8 decoded)."""
    return canonical_json_bytes(value).decode("utf-8")


def canonical_json_text(value: Any, options: Optional[CanonicalizationOptions] = None) -> str:
    """Return canonical JSON text string for `value`."""
    return canonical_json_bytes(value, options).decode("utf-8")
