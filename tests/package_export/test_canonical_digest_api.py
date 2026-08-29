#!/usr/bin/env python3
"""Tests for gwc-jcs-v1 shared runtime canonical digest API (SCRUM-397 WP4).

Scope: WP4 ONLY — the shared runtime digest API in
``tools/node_architect/package_export/canonical_digest_api.py``:

  * registry-aware, fail-closed ProfilePolicy resolution;
  * CANONICALIZATION_NEVER_GRANTS_AUTHORITY;
  * RFC-8785/JCS canonicalization of the gwc-jcs-v1 strict input domain
    (integer-valued binary64 -> integer notation, negative zero / non-finite /
    non-string key / duplicate raw key / invalid Unicode / resource limits all
    rejected deterministically);
  * canonical_digest fail-closed new-write refusal (gwc-jcs-v1 REJECTED,
    legacy VERIFY_ONLY, unknown profile UNKNOWN);
  * verify_digest verification-only behavior.

Deliberately EXCLUDED: legacy-python-json-v1 verification (WP4 legacy
verifier file, its own test module); cross-runtime golden corpus (WP3);
consumer migration (WP5); registry activation.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "tools"
        / "node_architect"
        / "package_export"
    ),
)  # noqa: E402

import canonical_digest_api as api  # noqa: E402
from deterministic_hash_verification import (  # noqa: E402
    PROFILE_DIGEST_ENVELOPE_OK,
    PROFILE_DIGEST_ENVELOPE_MISMATCH,
)


class TestProfilePolicy(unittest.TestCase):
    def test_registry_loads_and_is_fail_closed(self):
        reg = api.load_registry()
        self.assertIn("gwc-jcs-v1", reg)
        self.assertIn("legacy-python-json-v1", reg)
        gwc = reg["gwc-jcs-v1"]
        self.assertEqual(gwc.lifecycle_state, "REJECTED")
        self.assertFalse(gwc.new_write_allowed)
        self.assertFalse(gwc.verify_only_allowed)
        leg = reg["legacy-python-json-v1"]
        self.assertEqual(leg.lifecycle_state, "VERIFY_ONLY")
        self.assertFalse(leg.new_write_allowed)
        self.assertTrue(leg.verify_only_allowed)

    def test_missing_registry_raises_unavailable(self):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.load_registry(Path("/nonexistent/registry.yaml"))
        self.assertEqual(ctx.exception.code, api.DIGEST_REGISTRY_UNAVAILABLE)

    def test_canonicalization_never_grants_authority(self):
        self.assertTrue(api.CANONICALIZATION_NEVER_GRANTS_AUTHORITY)


class TestCanonicalizeFailClosed(unittest.TestCase):
    def _reject(self, raw, code):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.canonicalize_gwc_jcs_v1(raw)
        self.assertEqual(ctx.exception.code, code, raw)

    def test_integer_valued_binary64_emits_integer_notation(self):
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"value":3.0}'), b'{"value":3}'
        )
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"value":0.0}'), b'{"value":0}'
        )
        # Non-integer float keeps fractional notation (JCS shortest).
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"value":3.14}'), b'{"value":3.14}'
        )

    def test_negative_zero_rejected(self):
        self._reject('{"value":-0.0}', api.DIGEST_NEGATIVE_ZERO_REJECTED)

    def test_non_finite_rejected(self):
        self._reject('{"value":NaN}', api.DIGEST_NON_FINITE_REJECTED)
        self._reject('{"value":Infinity}', api.DIGEST_NON_FINITE_REJECTED)

    def test_duplicate_raw_key_rejected(self):
        self._reject('{"a":1,"a":2}', api.DIGEST_DUPLICATE_RAW_KEY_REJECTED)

    def test_non_string_key_rejected(self):
        self._reject('{1:2}', api.DIGEST_NON_STRING_KEY_REJECTED)

    def test_invalid_unicode_lone_surrogate_rejected(self):
        # Raw text containing a lone surrogate must raise INVALID_UNICODE,
        # never crash with UnicodeEncodeError.
        self._reject('{"s":"\ud800"}', api.DIGEST_INVALID_UNICODE_REJECTED)

    def test_c2_malformed_low_low_surrogate_rejected(self):
        # C2: a LOW+LOW sequence (DC00 DC00) is NOT a valid pair; both code
        # units are lone surrogates and must be rejected deterministically.
        self._reject('{"s":"\udc00\udc00"}', api.DIGEST_INVALID_UNICODE_REJECTED)
        # Isolated LOW surrogate also rejected.
        self._reject('{"s":"x\udc00y"}', api.DIGEST_INVALID_UNICODE_REJECTED)

    def test_c2_valid_high_low_pair_preserved(self):
        # C2: a VALID HIGH+LOW surrogate pair forms one non-BMP code point and
        # is preserved byte-for-byte.
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"astral":"\U00010000"}'),
            '{"astral":"\U00010000"}'.encode("utf-8"),
        )

    def test_c3_lone_surrogate_key_rejected_deterministic(self):
        # C3: a lone-surrogate KEY must raise the controlled
        # DIGEST_INVALID_UNICODE_REJECTED (not a raw UnicodeEncodeError during
        # sort-key computation).
        self._reject('{"\ud800":"v"}', api.DIGEST_INVALID_UNICODE_REJECTED)

    def test_resource_limit_exceeded(self):
        big = '{"big":"' + "x" * 5_000_000 + '"}'
        self._reject(big, api.DIGEST_RESOURCE_LIMIT_EXCEEDED)

    def test_valid_json_canonicalizes_sorted(self):
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"b":1,"a":2}'), b'{"a":2,"b":1}'
        )

    def test_review_2_non_bmp_key_ordering_utf16_code_units(self):
        # REV-2: non-BMP keys ordered by UTF-16 code units, not Python code
        # points. U+10000 (units D800 DC00) sorts before U+1D400 (D835 DC00).
        raw = '{"\U0001D400":1,"\U0001D401":2,"\U00010000":0}'
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1(raw),
            '\u007b"\U00010000":0,"\U0001D400":1,"\U0001D401":2}'.encode("utf-8"),
        )

    def test_review_2_non_ascii_minimal_serialization(self):
        # REV-2: jcs_minimal string serialization emits raw UTF-8, not \uXXXX.
        self.assertEqual(
            api.canonicalize_gwc_jcs_v1('{"msg":"café"}'),
            '{"msg":"café"}'.encode("utf-8"),
        )


class TestCanonicalDigestFailClosed(unittest.TestCase):
    def test_gwc_jcs_v1_new_write_refused(self):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.canonical_digest('{"a":1}')
        self.assertEqual(ctx.exception.code, api.DIGEST_PROFILE_NOT_ACTIVATED)

    def test_legacy_new_write_refused(self):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.canonical_digest('{"a":1}', profile_id="legacy-python-json-v1")
        self.assertEqual(ctx.exception.code, api.DIGEST_LEGACY_VERIFY_ONLY)

    def test_unknown_profile_refused(self):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.canonical_digest('{"a":1}', profile_id="does-not-exist")
        self.assertEqual(ctx.exception.code, api.DIGEST_PROFILE_UNKNOWN)


class TestVerifyDigest(unittest.TestCase):
    def test_unknown_profile_verify_refused(self):
        with self.assertRaises(api.CanonicalDigestAPIError) as ctx:
            api.verify_digest('{"a":1}', {"profile_id": "does-not-exist"})
        self.assertEqual(ctx.exception.code, api.DIGEST_PROFILE_UNKNOWN)

    def test_legacy_verify_ok(self):
        # Build a legacy envelope via the canonical framing primitives and
        # verify it matches.
        canonical = b'{"a":1}'
        envelope = api.build_digest_envelope(
            profile_id="legacy-python-json-v1",
            canonical_bytes=canonical,
            domain="gwc.governance.evidence.legacy.v1",
            schema_ref="schemas/digest-envelope.schema.json",
        )
        # verify_digest for legacy profile is allowed (VERIFY_ONLY).
        result = api.verify_digest('{"a":1}', envelope)
        self.assertEqual(result, PROFILE_DIGEST_ENVELOPE_OK)
        result_mismatch = api.verify_digest('{"a":2}', envelope)
        self.assertEqual(result_mismatch, PROFILE_DIGEST_ENVELOPE_MISMATCH)


if __name__ == "__main__":
    unittest.main()
