#!/usr/bin/env python3
"""Tests for legacy-python-json-v1 verification (SCRUM-397 WP4).

Scope: WP4 ONLY — ``tools/node_architect/package_export/legacy_digest_verifier.py``:

  * legacy-python-json-v1 canonical form (json.dumps sort_keys compact UTF-8)
    as compatibility metadata ONLY;
  * verify_legacy_digest: deterministic OK/MISMATCH against a digest envelope;
  * legacy_digest_envelope: builds the VERIFY_ONLY envelope;
  * fail-closed on malformed input (parse error -> MISMATCH, never raise).

Deliberately EXCLUDED: gwc-jcs-v1 new writes / shared API (its own test
module); consumer migration (WP5); registry activation.
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

import legacy_digest_verifier as lv  # noqa: E402
from deterministic_hash_verification import (  # noqa: E402
    PROFILE_DIGEST_ENVELOPE_OK,
    PROFILE_DIGEST_ENVELOPE_MISMATCH,
)


class TestLegacyCanonicalForm(unittest.TestCase):
    def test_profile_id_and_domain(self):
        self.assertEqual(lv.LEGACY_PROFILE_ID, "legacy-python-json-v1")
        self.assertEqual(lv.DEFAULT_DOMAIN, "gwc.governance.evidence.canonical.legacy.v1")

    def test_legacy_canonical_bytes_sorted_keys(self):
        raw = '{"b":1,"a":2}'
        canonical = lv._legacy_canonical_bytes(raw)
        self.assertEqual(canonical, b'{"a":2,"b":1}')


class TestLegacyDigestEnvelope(unittest.TestCase):
    def test_envelope_built(self):
        env = lv.legacy_digest_envelope('{"a":1}')
        self.assertEqual(env["profile_id"], "legacy-python-json-v1")
        self.assertEqual(env["domain"], "gwc.governance.evidence.canonical.legacy.v1")
        self.assertEqual(env["hash_algorithm"], "SHA-256")
        self.assertEqual(env["preimage_framing_scheme"], "gwc-domain-sep-v1")
        self.assertEqual(env["preimage_byte_length"], 7)
        self.assertEqual(len(env["hexdigest"]), 64)


class TestVerifyLegacyDigest(unittest.TestCase):
    def test_verify_match(self):
        env = lv.legacy_digest_envelope('{"a":1}')
        result = lv.verify_legacy_digest('{"a":1}', env)
        self.assertEqual(result, PROFILE_DIGEST_ENVELOPE_OK)

    def test_verify_mismatch(self):
        env = lv.legacy_digest_envelope('{"a":1}')
        result = lv.verify_legacy_digest('{"a":2}', env)
        self.assertEqual(result, PROFILE_DIGEST_ENVELOPE_MISMATCH)

    def test_verify_whitespace_insensitive(self):
        # Canonical form collapses insignificant whitespace; semantically
        # identical inputs verify OK.
        env = lv.legacy_digest_envelope('{"a":1}')
        result = lv.verify_legacy_digest('{  "a"  :  1  }', env)
        self.assertEqual(result, PROFILE_DIGEST_ENVELOPE_OK)

    def test_verify_malformed_input_fails_closed(self):
        env = lv.legacy_digest_envelope('{"a":1}')
        # Malformed JSON -> legacy canonicalization fails -> MISMATCH (never raise).
        result = lv.verify_legacy_digest("{ not valid json", env)
        self.assertEqual(result, PROFILE_DIGEST_ENVELOPE_MISMATCH)


if __name__ == "__main__":
    unittest.main()
