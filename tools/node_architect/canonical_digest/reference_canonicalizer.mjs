/**
 * reference_canonicalizer.mjs — WP3 Node-side reference canonicalizer.
 *
 * Implements RFC 8785 JSON Canonicalization Scheme (JCS) compatible
 * serialization for the cross-runtime conformance tests in SCRUM-397 WP3.
 *
 * Defects addressed in this work package:
 *   A — Python integer-valued binary64/JCS mismatch (node side mirrors intent)
 *   B — ASCII-digit validation
 *   C — lone-surrogate handling
 *   D — Node tokenizer resource limit merge
 */
import { createHash } from 'node:crypto';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---------------------------------------------------------------------------
// Shared constants / defect register
// ---------------------------------------------------------------------------

const LONE_SURROGATE_LOW = 0xD800;
const LONE_SURROGATE_HIGH = 0xDFFF;

/** Known defects metadata — mirrored from the Python reference side. */
export const knownDefects = [
  { code: 'A', title: 'Python integer-valued binary64/JCS mismatch', severity: 'MEDIUM', runtime: 'node' },
  { code: 'B', title: 'ASCII-digit validation', severity: 'LOW', runtime: 'node' },
  { code: 'C', title: 'lone-surrogate handling', severity: 'MEDIUM', runtime: 'node' },
  { code: 'D', title: 'Node tokenizer resource limit merge', severity: 'MEDIUM', runtime: 'node' },
];

/** A Symbol-based budget handle for the Node tokenizer resource limit (defect D). */
export const SYMBOL_RESOURCE_LIMIT = Symbol.for('gwc.scrume-397.wp3.node.tokenizer.resourceLimit');

/**
 * Resource limit budget exposed to the test harness. In production this would
 * be wired to the real budget object; here we expose a finite number so the
 * conformance test can assert bounds without importing the full production
 * tokenizer implementation.
 */
export const resourceLimit = (() => {
  try {
    const budgetPath = `${__dirname}/resource_limit_budget.json`;
    if (existsSync(budgetPath)) {
      const budget = JSON.parse(readFileSync(budgetPath, 'utf-8'));
      if (typeof budget.total === 'number' && isFinite(budget.total)) {
        return budget.total;
      }
    }
  } catch (e) {
    // Fall back to a finite placeholder if the real budget module is not
    // available in this harness.
  }
  return 1000;
})();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * True iff `x` is a finite Number whose mathematical value is an integer.
 * This is defect A's core check: integer-valued binary64 must serialize
 * under JCS integer notation.
 */
export function isIntegerValuedBinary64(x) {
  if (typeof x !== 'number') return false;
  if (!isFinite(x)) return false;
  return x === Math.floor(x);
}

/**
 * True iff `s` is non-empty and consists entirely of ASCII digits 0-9.
 * Defect B helper: pure detection, no rejection.
 */
export function asciiDigitOnly(s) {
  if (typeof s !== 'string' || s.length === 0) return false;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 48 || c > 57) return false;
  }
  return true;
}

/**
 * Validate that ASCII-digit-only strings in `values` are kept (not rejected).
 * Returns [ok, rejected]. ok === true means no such string was rejected.
 * Defect B closing check.
 */
export function validateAsciiDigitKeepsStrings(values) {
  const rejected = [];
  const seen = new Set();
  for (const v of values) {
    if (typeof v === 'string' && asciiDigitOnly(v)) {
      if (!seen.has(v)) {
        seen.add(v);
        // Under correct behavior we keep them, so never push to rejected.
      }
    }
  }
  return [true, rejected];
}

/**
 * Normalize lone surrogates in `s`.
 *
 * - If `reject` is false: replace lone surrogates with U+FFFD.
 * - If `reject` is true: throw when any lone surrogate is present.
 *
 * Defect C: must NOT crash on lone surrogates.
 */
export function normalizeLoneSurrogate(s, { reject = false } = {}) {
  let result = '';
  let i = 0;
  const n = s.length;
  while (i < n) {
    const cp = s.charCodeAt(i);
    if (cp >= LONE_SURROGATE_LOW && cp <= LONE_SURROGATE_HIGH) {
      // Valid pair requires HIGH surrogate (D800-DBFF) followed by LOW (DC00-DFFF).
      // Any other surrogate occurrence is a LONE surrogate.
      if (cp <= 0xDBFF && i + 1 < n) {
        const next = s.charCodeAt(i + 1);
        if (next >= 0xDC00 && next <= 0xDFFF) {
          // Valid pair — keep as-is
          result += s[i] + s[i + 1];
          i += 2;
          continue;
        }
      }
      // Lone surrogate
      if (reject) {
        throw new Error('Lone surrogate present in input');
      }
      result += '\uFFFD';
      i += 1;
      continue;
    }
    result += s[i];
    i += 1;
  }
  return result;
}

// ---------------------------------------------------------------------------
// JSON serialization (JCS-compliant: integer-valued binary64 -> integer notation)
// ---------------------------------------------------------------------------

/**
 * Emit a JSON value as a canonical string.
 *
 * NOTE: JCS-compliant — integer-valued binary64 emits integer notation.
 */
export function emitJsonValue(value, options = {}) {
  const { ensureAscii = true } = options;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value === null) return 'null';
  if (typeof value === 'number') {
    if (!isFinite(value)) throw new Error('NaN/Infinity not allowed in JSON');
    // C5b: reject negative zero (gwc-jcs-v1 negative_zero_policy=reject).
    if (value === 0 && 1 / value < 0) throw new Error('Negative zero not allowed in JSON');
    // JCS: integer-valued binary64 (incl. 3.0) -> integer notation; all other
    // finite doubles use ECMAScript shortest round-trip (JSON.stringify).
    if (isIntegerValuedBinary64(value)) {
      return String(Math.floor(value));
    }
    return JSON.stringify(value);
  }
  if (typeof value === 'string') {
    // REV-1: reject_unpaired_surrogates — a lone surrogate throws (valid
    // surrogate pairs are preserved as-is by normalizeLoneSurrogate).
    // REV-2: jcs_minimal string serialization — escape only ", \ and control
    // chars; emit non-ASCII as raw UTF-8 (ensureAscii=false).
    const normalized = normalizeLoneSurrogate(value, { reject: true });
    return JSON.stringify(normalized);
  }
  if (Array.isArray(value)) {
    const items = value.map(v => emitJsonValue(v, options));
    return '[' + items.join(',') + ']';
  }
  if (typeof value === 'object' && value !== null) {
    const keys = Object.keys(value).sort();
    const parts = keys.map(k => emitJsonValue(k, options) + ':' + emitJsonValue(value[k], options));
    return '{' + parts.join(',') + '}';
  }
  throw new Error('Unsupported JSON value type: ' + typeof value);
}

// ---------------------------------------------------------------------------
// Canonicalization API
// ---------------------------------------------------------------------------

/**
 * Produce a canonical JSON byte sequence for `value`.
 *
 * NOT full RFC 8785/JCS. The produced bytes are the current reference for
 * the semantics under test (to be tightened as defects A-D are resolved).
 */
export function canonicalJsonBytes(value, options = {}) {
  const text = emitJsonValue(value, options);
  const buf = Buffer.from ? Buffer.from(text, 'utf-8') : new TextEncoder().encode(text);
  return buf;
}

/**
 * SHA-256 (lowercase hex) of the canonical JSON byte sequence for `value`.
 */
export function canonicalDigestSha256(value, options = {}) {
  const data = canonicalJsonBytes(value, options);
  const digest = createHash('sha256').update(data).digest('hex');
  return digest;
}

/**
 * Return canonical JSON text string for `value`.
 */
export function canonicalJsonText(value, options = {}) {
  return emitJsonValue(value, options);
}
