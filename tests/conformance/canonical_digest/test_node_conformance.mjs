/**
 * gwc-jcs-v1 Node.js conformance test (SCRUM-397 WP3).
 *
 * Runs every golden vector from tests/conformance/canonical_digest/golden_vectors.yaml
 * through the independent Node reference canonicalizer and asserts:
 *   - POSITIVE vectors: canonical UTF-8 bytes (hex) + framed SHA-256 exactly match
 *     the language-neutral expected values.
 *   - NEGATIVE vectors: the exact deterministic DIGEST_* taxonomy error is raised.
 * The corpus was generated only after the Python and Node references agreed
 * byte-for-byte, so this test also guards cross-runtime stability.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";
import {
  canonicalizeJsonText,
  framedSha256,
  CanonicalDigestError,
} from "../../../tools/node_architect/canonical_digest/reference_canonicalizer.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const corpusPath = resolve(__dirname, "golden_vectors.yaml");
// The corpus file is JSON text (valid YAML 1.2) so no YAML dependency is needed.
const doc = JSON.parse(readFileSync(corpusPath, "utf8"));
const vectors = doc.vectors;
const positive = vectors.filter((v) => v.category === "POSITIVE");
const negative = vectors.filter((v) => v.category === "NEGATIVE");

test("corpus is non-empty and balanced", () => {
  assert.ok(positive.length >= 20);
  assert.ok(negative.length >= 10);
});

for (const vec of positive) {
  test(`POSITIVE ${vec.vector_id}: canonical bytes + framed SHA-256`, () => {
    const canonical = canonicalizeJsonText(vec.input, { domain: vec.domain });
    assert.equal(
      canonical.toString("hex"),
      vec.expected_canonical_bytes_hex,
      `canonical bytes mismatch for ${vec.vector_id}`
    );
    assert.equal(
      framedSha256(canonical, { domain: vec.domain }),
      vec.expected_sha256_framed,
      `framed SHA-256 mismatch for ${vec.vector_id}`
    );
  });
}

for (const vec of negative) {
  test(`NEGATIVE ${vec.vector_id}: exact taxonomy ${vec.expected_error}`, () => {
    assert.throws(
      () => canonicalizeJsonText(vec.input, { domain: vec.domain }),
      (err) => err instanceof CanonicalDigestError && err.code === vec.expected_error
    );
  });
}

test("framing is length-prefixed (u32be tag len || tag || u64be preimage len || preimage)", () => {
  const canonical = canonicalizeJsonText('{"a":1}', { domain: doc.domain });
  const tag = Buffer.from(doc.domain, "utf8");
  const frame = Buffer.concat([
    u32be(tag.length),
    tag,
    u64be(canonical.length),
    canonical,
  ]);
  assert.equal(
    createHash("sha256").update(frame).digest("hex"),
    framedSha256(canonical, { domain: doc.domain })
  );
});

function u32be(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32BE(n >>> 0, 0);
  return b;
}
function u64be(n) {
  const b = Buffer.alloc(8);
  b.writeBigUInt64BE(BigInt(n), 0);
  return b;
}
