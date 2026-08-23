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


def _utf16_code_units(s: str) -> tuple:
    """UTF-16 code units (RFC-8785 key ordering), not code points.

    Big-endian UTF-16 bytes preserve lexicographic code-unit order: comparing
    two keys byte-by-byte on utf-16-be equals comparing their UTF-16 code-unit
    sequences. (utf-16-le would reverse pair order.)
    """
    return tuple(s.encode("utf-16-be"))


# --- Lexical JSON tokenizer ------------------------------------------------
# JSON whitespace is EXACTLY four characters: SP/TAB/CR/LF. Anything else
# (e.g. NBSP U+00A0) is a syntax error -> DIGEST_INPUT_DOMAIN_VIOLATION.
_JSON_WS = {" ", "\t", "\r", "\n"}


class _JsonTokenizer:
    def __init__(self, text: str, limits: dict):
        self.text = text
        self.pos = 0
        self.limits = limits

    def err(self, code: str):
        raise CanonicalDigestError(code)

    def _skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in _JSON_WS:
            self.pos += 1
        # Reject non-JSON whitespace (e.g. NBSP U+00A0): it is a syntax error,
        # not a key/separator token.
        if self.pos < len(self.text) and self.text[self.pos].isspace() \
                and self.text[self.pos] not in _JSON_WS:
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)

    def _peek(self):
        self._skip_ws()
        return self.text[self.pos] if self.pos < len(self.text) else None

    def _parse_string(self) -> str:
        self._skip_ws()
        if self.pos >= len(self.text) or self.text[self.pos] != '"':
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text):
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            ch = self.text[self.pos]
            if ch == '"':
                self.pos += 1
                break
            if ch == "\\":
                self.pos += 1
                if self.pos >= len(self.text):
                    self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
                e = self.text[self.pos]
                simple = {'"': '"', "\\": "\\", "/": "/",
                          "b": "\b", "f": "\f", "n": "\n",
                          "r": "\r", "t": "\t"}
                if e in simple:
                    out.append(simple[e]); self.pos += 1
                elif e == "u":
                    hexs = self.text[self.pos + 1:self.pos + 5]
                    if len(hexs) != 4 or any(c not in "0123456789abcdefABCDEF" for c in hexs):
                        self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
                    cp = int(hexs, 16)
                    self.pos += 5
                    # Surrogate pair: \uD83D\uDE00 -> single non-BMP code point.
                    if 0xD800 <= cp <= 0xDBFF and self.pos + 1 < len(self.text) \
                            and self.text[self.pos:self.pos + 2] == "\\u":
                        low_hex = self.text[self.pos + 2:self.pos + 6]
                        if len(low_hex) == 4 and all(c in "0123456789abcdefABCDEF" for c in low_hex):
                            low = int(low_hex, 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                out.append(chr(0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)))
                                self.pos += 6
                                continue
                    out.append(chr(cp))
                else:
                    self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            else:
                cc = ord(ch)
                if cc < 0x20:
                    self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
                out.append(ch)
                self.pos += 1
        s = "".join(out)
        # Reject UNPAIRED surrogates (invalid Unicode) — NOT normalization.
        i = 0
        n = len(s)
        while i < n:
            cc = ord(s[i])
            if 0xD800 <= cc <= 0xDBFF:
                nxt = ord(s[i + 1]) if i + 1 < n else 0
                if 0xDC00 <= nxt <= 0xDFFF:
                    i += 2
                    continue
                self.err(DIGEST_INVALID_UNICODE_REJECTED)
            elif 0xDC00 <= cc <= 0xDFFF:
                self.err(DIGEST_INVALID_UNICODE_REJECTED)
            i += 1
        # Length check only after surrogate rejection (lone surrogates cannot
        # be UTF-8 encoded, so they must be rejected first).
        if len(s.encode("utf-8")) > self.limits["max_string_bytes"]:
            self.err(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        return s

    def _parse_number(self):
        self._skip_ws()
        start = self.pos
        if self.pos < len(self.text) and self.text[self.pos] == "-":
            self.pos += 1
        if self.pos >= len(self.text):
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        if self.text[self.pos] == "0":
            self.pos += 1
        elif self.text[self.pos].isdigit():
            while self.pos < len(self.text) and self.text[self.pos].isdigit():
                self.pos += 1
        else:
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        if self.pos < len(self.text) and self.text[self.pos] == ".":
            self.pos += 1
            if self.pos >= len(self.text) or not self.text[self.pos].isdigit():
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            while self.pos < len(self.text) and self.text[self.pos].isdigit():
                self.pos += 1
        if self.pos < len(self.text) and self.text[self.pos] in ("e", "E"):
            self.pos += 1
            if self.pos < len(self.text) and self.text[self.pos] in ("+", "-"):
                self.pos += 1
            if self.pos >= len(self.text) or not self.text[self.pos].isdigit():
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            while self.pos < len(self.text) and self.text[self.pos].isdigit():
                self.pos += 1
        tok = self.text[start:self.pos]
        # Lexical negative-zero detection (token-level, NOT a global scan).
        if tok.startswith("-"):
            rest = tok[1:]
            rest = re.sub(r"[eE][+-]?\d+$", "", rest)
            if rest.replace(".", "").strip("0") == "":
                self.err(DIGEST_NEGATIVE_ZERO_REJECTED)
        value = float(tok)  # IEEE-754 binary64 semantics (like JS Number)
        if value != value or value in (math.inf, -math.inf):
            self.err(DIGEST_NON_FINITE_REJECTED)
        return value

    def _parse_value(self, depth: int):
        if depth > self.limits["max_object_depth"]:
            self.err(DIGEST_RESOURCE_LIMIT_EXCEEDED)
        c = self._peek()
        if c is None:
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        if self.text.startswith("-Infinity", self.pos):
            self.err(DIGEST_NON_FINITE_REJECTED)
        if c == "{":
            return self._parse_object(depth)
        if c == "[":
            return self._parse_array(depth)
        if c == '"':
            return self._parse_string()
        if c == "-" or (c is not None and c.isdigit()):
            return self._parse_number()
        self._skip_ws()
        rest = self.text[self.pos:]
        if rest.startswith("true"):
            self.pos += 4; return True
        if rest.startswith("false"):
            self.pos += 5; return False
        if rest.startswith("null"):
            self.pos += 4; return None
        if rest.startswith("NaN") or rest.startswith("Infinity"):
            self.err(DIGEST_NON_FINITE_REJECTED)
        self.err(DIGEST_INPUT_DOMAIN_VIOLATION)

    def _parse_array(self, depth: int):
        self.pos += 1  # '['
        arr = []
        self._skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == "]":
            self.pos += 1
            return arr
        while True:
            arr.append(self._parse_value(depth + 1))
            if len(arr) > self.limits["max_array_items"]:
                self.err(DIGEST_RESOURCE_LIMIT_EXCEEDED)
            self._skip_ws()
            if self.pos >= len(self.text):
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            if self.text[self.pos] == "]":
                self.pos += 1
                break
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        return arr

    def _parse_object(self, depth: int):
        self.pos += 1  # '{'
        obj = {}
        seen = set()
        self._skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == "}":
            self.pos += 1
            return obj
        while True:
            self._skip_ws()
            if self.pos >= len(self.text) or self.text[self.pos] != '"':
                # Non-string object key -> reject (also covers bare keys).
                self.err(DIGEST_NON_STRING_KEY_REJECTED)
            key = self._parse_string()
            if key in seen:
                self.err(DIGEST_DUPLICATE_RAW_KEY_REJECTED)
            seen.add(key)
            self._skip_ws()
            if self.pos >= len(self.text) or self.text[self.pos] != ":":
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            self.pos += 1
            obj[key] = self._parse_value(depth + 1)
            if len(obj) > self.limits["max_object_keys"]:
                self.err(DIGEST_RESOURCE_LIMIT_EXCEEDED)
            self._skip_ws()
            if self.pos >= len(self.text):
                self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            if self.text[self.pos] == "}":
                self.pos += 1
                break
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        return obj

    def parse(self):
        value = self._parse_value(1)
        self._skip_ws()
        if self.pos != len(self.text):
            self.err(DIGEST_INPUT_DOMAIN_VIOLATION)
        return value


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
        # RFC-8785 key ordering: lexicographic by UTF-16 CODE UNITS.
        for key in sorted(value, key=_utf16_code_units):
            members.append(
                _escape_string(key, max_string_bytes=limits["max_string_bytes"])
                + ":"
                + _canonicalize_value(value[key], depth + 1, limits)
            )
        return "{" + ",".join(members) + "}"
    raise CanonicalDigestError(DIGEST_INPUT_DOMAIN_VIOLATION)


# --- Public reference API ----------------------------------------------------
def canonicalize_json_text(
    raw_text: str,
    *,
    resource_limits: dict | None = None,
    domain: str = DEFAULT_DOMAIN,
) -> bytes:
    """Canonicalize raw JSON text to exact RFC-8785/JCS UTF-8 bytes.

    Returns the canonical preimage bytes. Raises CanonicalDigestError with a
    deterministic DIGEST_* code on any strict-domain violation. Parsing is a
    full lexical tokenizer so duplicate keys, negative zero, and invalid
    Unicode are detected on the raw lexical tokens (never on string content),
    and every number is read with IEEE-754 binary64 semantics.
    """
    limits = {**DEFAULT_RESOURCE_LIMITS, **(resource_limits or {})}
    if len(raw_text.encode("utf-8")) > limits["max_preimage_bytes"]:
        raise CanonicalDigestError(DIGEST_RESOURCE_LIMIT_EXCEEDED)
    value = _JsonTokenizer(raw_text, limits).parse()
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
