#!/usr/bin/env python3
"""gwc-jcs-v1 Python conformance test (SCRUM-397 WP3).

Runs every golden vector from tests/conformance/canonical_digest/golden_vectors.yaml
through the independent Python reference canonicalizer and asserts:
  - POSITIVE vectors: canonical UTF-8 bytes (hex) + framed SHA-256 exactly match
    the language-neutral expected values.
  - NEGATIVE vectors: the exact deterministic DIGEST_* taxonomy error is raised.
The corpus itself was generated only after the Python and Node references agreed
byte-for-byte, so this test also guards cross-runtime stability.
"""

import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "node_architect" / "canonical_digest"))  # noqa: E402

from reference_canonicalizer import (  # noqa: E402
    CanonicalDigestError,
    canonicalize_json_text,
    framed_sha256,
)

CORPUS = REPO / "tests" / "conformance" / "canonical_digest" / "golden_vectors.yaml"


def load_corpus():
    with CORPUS.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc


class PythonConformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_corpus()
        cls.vectors = cls.doc["vectors"]
        cls.positive = [v for v in cls.vectors if v["category"] == "POSITIVE"]
        cls.negative = [v for v in cls.vectors if v["category"] == "NEGATIVE"]

    def test_corpus_nonempty_and_balanced(self):
        self.assertGreaterEqual(len(self.positive), 20)
        self.assertGreaterEqual(len(self.negative), 10)

    def test_positive_vectors_canonical_bytes_and_digest(self):
        for vec in self.positive:
            with self.subTest(vector=vec["vector_id"]):
                canonical = canonicalize_json_text(
                    vec["input"], domain=vec["domain"]
                )
                self.assertEqual(
                    canonical.hex(),
                    vec["expected_canonical_bytes_hex"],
                    f"canonical bytes mismatch for {vec['vector_id']}",
                )
                self.assertEqual(
                    framed_sha256(canonical, domain=vec["domain"]),
                    vec["expected_sha256_framed"],
                    f"framed SHA-256 mismatch for {vec['vector_id']}",
                )

    def test_negative_vectors_exact_taxonomy(self):
        for vec in self.negative:
            with self.subTest(vector=vec["vector_id"]):
                with self.assertRaises(CanonicalDigestError) as ctx:
                    canonicalize_json_text(vec["input"], domain=vec["domain"])
                self.assertEqual(ctx.exception.code, vec["expected_error"])

    def test_framing_is_length_prefixed(self):
        # Sanity: the framed digest is sha256(u32be(tag_len)||tag||u64be(len)||preimage)
        # over a known small input — cross-checked with Node during generation.
        import hashlib
        import struct
        canonical = canonicalize_json_text('{"a":1}', domain=self.doc["domain"])
        tag = self.doc["domain"].encode("utf-8")
        frame = (
            struct.pack(">I", len(tag))
            + tag
            + struct.pack(">Q", len(canonical))
            + canonical
        )
        self.assertEqual(hashlib.sha256(frame).hexdigest(),
                         framed_sha256(canonical, domain=self.doc["domain"]))


if __name__ == "__main__":
    unittest.main()
