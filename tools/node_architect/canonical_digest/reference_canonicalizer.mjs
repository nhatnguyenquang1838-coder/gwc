#!/usr/bin/env node
/**
 * gwc-jcs-v1 reference canonicalizer — Node.js implementation.
 *
 * Independent RFC-8785/JCS-compatible canonical serialization + framed SHA-256
 * for the WP2 normative profile (SCRUM-397 WP3 cross-runtime conformance).
 *
 * This is a REFERENCE implementation, fully self-contained: it never invokes
 * Python or any other runtime (cross-runtime independence is proven by the
 * conformance tests running the Python and Node references side by side).
 *
 * Normative policies enforced (from governance/digest-profiles/gwc-jcs-v1.yaml):
 *   - strict supported input domain (null/bool/number/string/array/object)
 *   - negative_zero_policy=reject
 *   - non_finite_policy=reject
 *   - non_string_key_policy=reject
 *   - duplicate_raw_key_policy=reject_before_semantic_collapse
 *   - invalid_unicode_policy=reject_unpaired_surrogates
 *   - unicode_normalization=none
 *   - canonical bytes: RFC-8785/JCS (NOT JSON.stringify sort_keys equivalent)
 *   - SHA-256 + explicit length-prefixed domain framing:
 *       sha256( u32be(utf8_len(domain_tag)) || domain_tag_utf8
 *             || u64be(byte_len(preimage)) || preimage )
 *   - bounded resource limits
 *   - deterministic error taxonomy (DIGEST_* codes)
 *
 * The raw JSON text is tokenized lexically so duplicate-key and negative-zero
 * evidence is preserved (semantic parsers would silently collapse it).
 * No production/shared API (that is WP4). CANONICALIZATION_NEVER_GRANTS_AUTHORITY.
 */
import { createHash } from "node:crypto";

// --- Default profile resource limits (mirror gwc-jcs-v1.yaml) ------------
const DEFAULT_RESOURCE_LIMITS = Object.freeze({
  max_preimage_bytes: 1048576,
  max_object_depth: 64,
  max_object_keys: 100000,
  max_array_items: 100000,
  max_string_bytes: 1048576,
});

// Default domain tag bound from governance/digest-profile-registry.yaml.
export const DEFAULT_DOMAIN = "gwc.governance.evidence.canonical.v1";
export const DEFAULT_SCHEMA_REF = "schemas/canonical-digest-profile.schema.json";
export const FRAMING_SCHEME = "gwc-domain-sep-v1";

// Closed deterministic error taxonomy (mirror gwc-jcs-v1.yaml).
export const ERROR = Object.freeze({
  DIGEST_INPUT_DOMAIN_VIOLATION: "DIGEST_INPUT_DOMAIN_VIOLATION",
  DIGEST_NEGATIVE_ZERO_REJECTED: "DIGEST_NEGATIVE_ZERO_REJECTED",
  DIGEST_NON_FINITE_REJECTED: "DIGEST_NON_FINITE_REJECTED",
  DIGEST_NON_STRING_KEY_REJECTED: "DIGEST_NON_STRING_KEY_REJECTED",
  DIGEST_DUPLICATE_RAW_KEY_REJECTED: "DIGEST_DUPLICATE_RAW_KEY_REJECTED",
  DIGEST_INVALID_UNICODE_REJECTED: "DIGEST_INVALID_UNICODE_REJECTED",
  DIGEST_RESOURCE_LIMIT_EXCEEDED: "DIGEST_RESOURCE_LIMIT_EXCEEDED",
  DIGEST_DOMAIN_TAG_MISMATCH: "DIGEST_DOMAIN_TAG_MISMATCH",
  DIGEST_ENVELOPE_BINDING_MISMATCH: "DIGEST_ENVELOPE_BINDING_MISMATCH",
});

export class CanonicalDigestError extends Error {
  constructor(code, detail = "") {
    super(detail ? `${code}: ${detail}` : code);
    this.name = "CanonicalDigestError";
    this.code = code;
  }
}

// --- Lexical JSON tokenizer preserving duplicate-key / -0 evidence -------

const WS = /\s/;
const DIGIT = /[0-9]/;

class Tokenizer {
  constructor(text) {
    this.text = text;
    this.pos = 0;
  }
  error(code, detail) {
    throw new CanonicalDigestError(code, detail);
  }
  skipWs() {
    while (this.pos < this.text.length && WS.test(this.text[this.pos])) this.pos++;
  }
  peek() {
    this.skipWs();
    return this.pos < this.text.length ? this.text[this.pos] : null;
  }
  // Parse a string token; returns the DECODED JS string (lone surrogates rejected).
  parseString() {
    this.skipWs();
    if (this.text[this.pos] !== '"') this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "expected string");
    this.pos++; // opening quote
    let out = "";
    while (true) {
      if (this.pos >= this.text.length) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "unterminated string");
      const ch = this.text[this.pos];
      if (ch === '"') { this.pos++; break; }
      if (ch === "\\") {
        this.pos++;
        const e = this.text[this.pos];
        if (e === undefined) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad escape");
        switch (e) {
          case '"': out += '"'; this.pos++; break;
          case "\\": out += "\\"; this.pos++; break;
          case "/": out += "/"; this.pos++; break;
          case "b": out += "\b"; this.pos++; break;
          case "f": out += "\f"; this.pos++; break;
          case "n": out += "\n"; this.pos++; break;
          case "r": out += "\r"; this.pos++; break;
          case "t": out += "\t"; this.pos++; break;
          case "u": {
            const hex = this.text.slice(this.pos + 1, this.pos + 5);
            if (!/^[0-9a-fA-F]{4}$/.test(hex)) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad \\u escape");
            const cp = parseInt(hex, 16);
            out += String.fromCharCode(cp);
            this.pos += 5;
            break;
          }
          default: this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad escape");
        }
      } else {
        const cc = ch.charCodeAt(0);
        if (cc < 0x20) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "raw control in string");
        out += ch;
        this.pos++;
      }
    }
    // Reject UNPAIRED surrogates (invalid Unicode) — NOT normalization.
    // Valid surrogate PAIRS (non-BMP characters) are allowed.
    for (let i = 0; i < out.length; i++) {
      const cc = out.charCodeAt(i);
      if (cc >= 0xd800 && cc <= 0xdbff) {
        // high surrogate: must be followed by a low surrogate
        const next = i + 1 < out.length ? out.charCodeAt(i + 1) : 0;
        if (next >= 0xdc00 && next <= 0xdfff) { i++; continue; }
        this.error(ERROR.DIGEST_INVALID_UNICODE_REJECTED, "unpaired surrogate");
      } else if (cc >= 0xdc00 && cc <= 0xdfff) {
        this.error(ERROR.DIGEST_INVALID_UNICODE_REJECTED, "unpaired surrogate");
      }
    }
    return out;
  }
  parseNumber() {
    this.skipWs();
    const start = this.pos;
    // JSON number grammar.
    if (this.text[this.pos] === "-") this.pos++;
    if (this.text[this.pos] === "0") this.pos++;
    else if (DIGIT.test(this.text[this.pos] ?? "")) { while (DIGIT.test(this.text[this.pos] ?? "")) this.pos++; }
    else this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad number");
    if (this.text[this.pos] === ".") {
      this.pos++;
      if (!DIGIT.test(this.text[this.pos] ?? "")) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad fraction");
      while (DIGIT.test(this.text[this.pos] ?? "")) this.pos++;
    }
    if (this.text[this.pos] === "e" || this.text[this.pos] === "E") {
      this.pos++;
      if (this.text[this.pos] === "+" || this.text[this.pos] === "-") this.pos++;
      if (!DIGIT.test(this.text[this.pos] ?? "")) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad exponent");
      while (DIGIT.test(this.text[this.pos] ?? "")) this.pos++;
    }
    const tok = this.text.slice(start, this.pos);
    // Negative zero detection (lexical): value exactly -0.
    if (tok.startsWith("-")) {
      const rest = tok.slice(1).replace(/[eE][+-]?\d+$/, "");
      if (rest.replace(".", "").replace(/0/g, "").length === 0) {
        this.error(ERROR.DIGEST_NEGATIVE_ZERO_REJECTED, "negative zero");
      }
    }
    const value = Number(tok);
    if (!Number.isFinite(value)) {
      this.error(ERROR.DIGEST_NON_FINITE_REJECTED, "non-finite number");
    }
    return value;
  }
  parseValue(depth, limits) {
    if (depth > limits.max_object_depth) this.error(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "depth");
    const c = this.peek();
    if (c === null) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "unexpected end");
    if (this.text.slice(this.pos).startsWith("-Infinity")) {
      this.error(ERROR.DIGEST_NON_FINITE_REJECTED, "non-finite literal");
    }
    if (c === "{") return this.parseObject(depth, limits);
    if (c === "[") return this.parseArray(depth, limits);
    if (c === '"') return this.parseString();
    if (c === "-" || DIGIT.test(c)) return this.parseNumber();
    this.skipWs();
    const rest = this.text.slice(this.pos);
    if (rest.startsWith("true")) { this.pos += 4; return true; }
    if (rest.startsWith("false")) { this.pos += 5; return false; }
    if (rest.startsWith("null")) { this.pos += 4; return null; }
    if (rest.startsWith("NaN") || rest.startsWith("Infinity") || rest.startsWith("-Infinity")) {
      this.error(ERROR.DIGEST_NON_FINITE_REJECTED, "non-finite literal");
    }
    this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "unexpected token");
  }
  parseArray(depth, limits) {
    this.pos++; // '['
    const arr = [];
    this.skipWs();
    if (this.text[this.pos] === "]") { this.pos++; return arr; }
    while (true) {
      arr.push(this.parseValue(depth + 1, limits));
      if (arr.length > limits.max_array_items) this.error(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "array items");
      this.skipWs();
      const c = this.text[this.pos];
      if (c === ",") { this.pos++; continue; }
      if (c === "]") { this.pos++; break; }
      this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad array");
    }
    return arr;
  }
  parseObject(depth, limits) {
    this.pos++; // '{'
    const obj = {};
    const seen = new Set();
    this.skipWs();
    if (this.text[this.pos] === "}") { this.pos++; return obj; }
    while (true) {
      this.skipWs();
      if (this.text[this.pos] !== '"') {
        // Non-string object key -> reject.
        this.error(ERROR.DIGEST_NON_STRING_KEY_REJECTED, "non-string key");
      }
      const key = this.parseString();
      if (seen.has(key)) {
        this.error(ERROR.DIGEST_DUPLICATE_RAW_KEY_REJECTED, "duplicate key");
      }
      seen.add(key);
      this.skipWs();
      if (this.text[this.pos] !== ":") this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "expected ':'");
      this.pos++;
      obj[key] = this.parseValue(depth + 1, limits);
      if (Object.keys(obj).length > limits.max_object_keys) this.error(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "object keys");
      this.skipWs();
      const c = this.text[this.pos];
      if (c === ",") { this.pos++; continue; }
      if (c === "}") { this.pos++; break; }
      this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "bad object");
    }
    return obj;
  }
  parse() {
    const value = this.parseValue(1, DEFAULT_RESOURCE_LIMITS);
    this.skipWs();
    if (this.pos !== this.text.length) this.error(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "trailing tokens");
    return value;
  }
}

// --- RFC-8785 escaping ----------------------------------------------------
const ESCAPES = Object.freeze({
  0x22: '\\"',
  0x5c: "\\\\",
  0x08: "\\b",
  0x09: "\\t",
  0x0a: "\\n",
  0x0c: "\\f",
  0x0d: "\\r",
});

function escapeString(s, limits) {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const cp = s.charCodeAt(i);
    if (cp >= 0xd800 && cp <= 0xdbff) {
      // high surrogate: valid only when paired with a following low surrogate
      const next = i + 1 < s.length ? s.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        out += s[i] + s[i + 1]; // non-BMP character, output literally
        i++;
        continue;
      }
      throw new CanonicalDigestError(ERROR.DIGEST_INVALID_UNICODE_REJECTED, "unpaired surrogate");
    }
    if (cp >= 0xdc00 && cp <= 0xdfff) {
      throw new CanonicalDigestError(ERROR.DIGEST_INVALID_UNICODE_REJECTED, "unpaired surrogate");
    }
    const esc = ESCAPES[cp];
    if (esc !== undefined) out += esc;
    else if (cp < 0x20) out += "\\u" + cp.toString(16).padStart(4, "0");
    else out += s[i];
  }
  out += '"';
  if (Buffer.byteLength(out, "utf8") > limits.max_string_bytes) {
    throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "string bytes");
  }
  return out;
}

// --- Canonicalization walk ------------------------------------------------
function canonicalizeValue(value, depth, limits) {
  if (depth > limits.max_object_depth) throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "depth");
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new CanonicalDigestError(ERROR.DIGEST_NON_FINITE_REJECTED, "non-finite");
    if (Object.is(value, -0)) throw new CanonicalDigestError(ERROR.DIGEST_NEGATIVE_ZERO_REJECTED, "negative zero");
    // ES6 Number#toString = RFC-8785 number serialization.
    return String(value);
  }
  if (typeof value === "string") return escapeString(value, limits);
  if (Array.isArray(value)) {
    if (value.length > limits.max_array_items) throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "array items");
    const parts = value.map((v) => canonicalizeValue(v, depth + 1, limits));
    return "[" + parts.join(",") + "]";
  }
  if (typeof value === "object") {
    const keys = Object.keys(value);
    if (keys.length > limits.max_object_keys) throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "object keys");
    // RFC-8785 key ordering: lexicographic by UTF-16 code units.
    keys.sort();
    const members = keys.map(
      (k) => escapeString(k, limits) + ":" + canonicalizeValue(value[k], depth + 1, limits)
    );
    return "{" + members.join(",") + "}";
  }
  throw new CanonicalDigestError(ERROR.DIGEST_INPUT_DOMAIN_VIOLATION, "unsupported value");
}

// --- Public reference API -------------------------------------------------
export function canonicalizeJsonText(rawText, opts = {}) {
  const limits = { ...DEFAULT_RESOURCE_LIMITS, ...(opts.resource_limits || {}) };
  if (Buffer.byteLength(rawText, "utf8") > limits.max_preimage_bytes) {
    throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "preimage bytes");
  }
  const tokenizer = new Tokenizer(rawText);
  const value = tokenizer.parse();
  const canonical = canonicalizeValue(value, 1, limits);
  const out = Buffer.from(canonical, "utf8");
  if (out.length > limits.max_preimage_bytes) {
    throw new CanonicalDigestError(ERROR.DIGEST_RESOURCE_LIMIT_EXCEEDED, "preimage bytes");
  }
  return out;
}

export function framedSha256(canonicalBytes, opts = {}) {
  const domain = opts.domain ?? DEFAULT_DOMAIN;
  const domainUtf8 = Buffer.from(domain, "utf8");
  const frame = Buffer.concat([
    u32be(domainUtf8.length),
    domainUtf8,
    u64be(canonicalBytes.length),
    canonicalBytes,
  ]);
  return createHash("sha256").update(frame).digest("hex");
}

export function canonicalDigest(rawText, opts = {}) {
  const domain = opts.domain ?? DEFAULT_DOMAIN;
  const schemaRef = opts.schema_ref ?? DEFAULT_SCHEMA_REF;
  const preimage = canonicalizeJsonText(rawText, opts);
  const hexdigest = framedSha256(preimage, { domain });
  return {
    schema_version: "1.0",
    artifact_type: "digest-envelope",
    profile_id: "gwc-jcs-v1",
    hash_algorithm: "SHA-256",
    domain,
    schema_ref: schemaRef,
    preimage_framing_scheme: FRAMING_SCHEME,
    preimage_byte_length: preimage.length,
    hexdigest,
  };
}

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
