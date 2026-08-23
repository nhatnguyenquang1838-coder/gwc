#!/usr/bin/env node
/**
 * Node.js reference verifier for GWC canonical digest (SCRUM-396, AC19).
 *
 * Implements the SAME canonicalization rule as the Python reference
 * (sort_keys=True, separators=(",",":"), ensure_ascii=False, UTF-8 sha256)
 * as an independent implementation for cross-runtime conformance.
 *
 * NOTE: this is intentionally NOT a full RFC 8785 JCS implementation —
 * Python sort_keys uses Unicode code-point ordering, not JCS UTF-16 code-unit
 * ordering. Full JCS conformance is a separate governed change.
 *
 * Usage: node verify_canonical_node.mjs <vectors.json>
 * Exit 0 = all cases match; non-zero = mismatch.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

function canonicalJson(value) {
  if (value === null) return "null";
  const t = typeof value;
  if (t === "boolean") return value ? "true" : "false";
  if (t === "number") return String(value);
  if (t === "string") return JSON.stringify(value); // Node keeps non-ASCII raw = ensure_ascii=false
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (t === "object") {
    const keys = Object.keys(value).sort();
    return (
      "{" +
      keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") +
      "}"
    );
  }
  throw new Error(`unsupported value type: ${t}`);
}

function digest(payload) {
  return createHash("sha256").update(canonicalJson(payload), "utf8").digest("hex");
}

const [, , vectorsPath] = process.argv;
if (!vectorsPath) {
  console.error("usage: node verify_canonical_node.mjs <vectors.json>");
  process.exit(2);
}

const vectors = JSON.parse(readFileSync(vectorsPath, "utf8"));
let failures = 0;
for (const c of vectors.cases) {
  const actual = digest(c.input);
  const expected = c.expected_canonical_sha256;
  const ok = actual === expected;
  console.log(`${ok ? "PASS" : "FAIL"} ${c.id} node=${actual} expected=${expected}`);
  if (!ok) failures += 1;
}
console.log(`node verifier: ${vectors.cases.length - failures}/${vectors.cases.length} passed`);
process.exit(failures === 0 ? 0 : 1);
