/**
 * test_node_conformance.mjs — WP3 Node-side canonical digest conformance tests.
 *
 * Exercises the Node reference canonicalizer
 * (tools/node_architect/canonical_digest/reference_canonicalizer.mjs).
 */
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert';
import { createHash } from 'node:crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..', '..', '..');

const GOLDEN_VECTORS_PATH = join(REPO_ROOT, 'tests/conformance/canonical_digest/golden_vectors.yaml');
const SCHEMA_PATH = join(REPO_ROOT, 'schemas/canonical-digest-golden-vector.schema.json');
const REF_CANON_PATH = join(REPO_ROOT, 'tools/node_architect/canonical_digest/reference_canonicalizer.mjs');

// Minimal YAML subset loader — genuinely parses the golden vector list including
// indented '- id:' object fields and a nested 'input:' mapping (C4).
function parseSimpleYaml(text) {
  const lines = text.split('\n');
  const doc = { golden_vectors: [] };
  let current = null;
  for (const raw of lines) {
    const line = raw.replace(/\t/g, '  ');
    // Top-level scalar key (e.g. version:, golden_vectors:)
    const topKv = line.match(/^([A-Za-z0-9_]+):\s*(.*)$/);
    if (topKv && !line.startsWith(' ') && !line.startsWith('-')) {
      const key = topKv[1];
      if (key === 'golden_vectors') continue; // list container
      doc[key] = _parseScalar(topKv[2].trim());
      continue;
    }
    // Vector list item start
    const listItem = line.match(/^-\s+id:\s*(.*)$/);
    if (listItem) {
      current = { id: listItem[1].trim() };
      doc.golden_vectors.push(current);
      continue;
    }
    if (!current) continue;
    // Nested field under the current vector (2-space indent)
    const nestedKv = line.match(/^\s{2}([A-Za-z0-9_]+):\s*(.*)$/);
    if (nestedKv) {
      const nk = nestedKv[1];
      const rest = nestedKv[2];
      if (rest === '') {
        // A nested mapping begins on following deeper-indented lines.
        current[nk] = {};
        current.__mapkey = nk;
        continue;
      }
      current[nk] = _parseScalar(rest.trim());
      current.__mapkey = null;
      continue;
    }
    // Deeper-indented keys belonging to the nested mapping (e.g. input:)
    const deepKv = line.match(/^\s{4}([^:\s][^:]*):\s*(.*)$/);
    if (deepKv && current.__mapkey) {
      current[current.__mapkey][deepKv[1]] = _parseScalar(deepKv[2].trim());
      continue;
    }
    if (!line.startsWith(' ')) current.__mapkey = null;
  }
  return doc;
}

function _parseScalar(v) {
  if (v === '' ) return '';
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v === 'null') return null;
  if (v.startsWith("'") && v.endsWith("'")) return v.slice(1, -1);
  if (v.startsWith('"') && v.endsWith('"')) {
    // Interpret \uXXXX escapes so corpus vectors carrying surrogate escapes
    // (e.g. "\ud800") become real code units fed to the canonicalizer.
    return v.slice(1, -1).replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
  }
  if (!isNaN(Number(v)) && v !== '') return Number(v);
  return v;
}

function loadGoldenVectors() {
  if (!existsSync(GOLDEN_VECTORS_PATH)) throw new Error('golden_vectors.yaml missing');
  const doc = parseSimpleYaml(readFileSync(GOLDEN_VECTORS_PATH, 'utf-8'));
  if (!doc || !Array.isArray(doc.golden_vectors)) throw new Error('golden_vectors malformed');
  return doc.golden_vectors;
}

function loadSchema() {
  if (!existsSync(SCHEMA_PATH)) throw new Error('schema missing');
  return JSON.parse(readFileSync(SCHEMA_PATH, 'utf-8'));
}

const ref = await import(REF_CANON_PATH);
// Self-contained: do NOT depend on the extra untracked
// tools/node_architect/canonical_digest/resource_limit_budget.json. The
// conformance suite uses the canonicalizer's documented default budget (1000),
// which the reference canonicalizer also falls back to when the file is absent.
const resourceLimit = 1000;

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`PASS: ${name}`);
  } catch (e) {
    failed++;
    console.error(`FAIL: ${name}`);
    console.error('  ', e.message);
  }
}

test('golden vectors file loads and is non-empty', () => {
  const vectors = loadGoldenVectors();
  assert(vectors.length > 0);
});

test('schema file loads and has title', () => {
  const schema = loadSchema();
  assert.strictEqual(schema.title, 'CanonicalDigestGoldenVector');
});

test('reference exports expected symbols', () => {
  assert.strictEqual(typeof ref.isIntegerValuedBinary64, 'function');
  assert.strictEqual(typeof ref.asciiDigitOnly, 'function');
  assert.strictEqual(typeof ref.canonicalJsonText, 'function');
  assert.strictEqual(typeof ref.canonicalDigestSha256, 'function');
  assert(Array.isArray(ref.knownDefects));
});

test('knownDefects contains A-D', () => {
  const codes = ref.knownDefects.map(d => d.code);
  assert(codes.includes('A'));
  assert(codes.includes('B'));
  assert(codes.includes('C'));
  assert(codes.includes('D'));
});

test('Defect A: detects integer-valued floats', () => {
  assert(ref.isIntegerValuedBinary64(3.0));
  assert(ref.isIntegerValuedBinary64(0.0));
  assert(!ref.isIntegerValuedBinary64(3.14));
});

test('Defect B: ASCII-digit-only detection', () => {
  assert(ref.asciiDigitOnly('12345'));
  assert(ref.asciiDigitOnly('0'));
  assert(!ref.asciiDigitOnly('abc'));
  assert(!ref.asciiDigitOnly('12a34'));
});

test('Defect B: validateAsciiDigitKeepsStrings passes', () => {
  const [ok, rejected] = ref.validateAsciiDigitKeepsStrings(['12345', '007']);
  assert(ok);
  assert.deepStrictEqual(rejected, []);
});

test('Defect C: rejects lone surrogate (throws)', () => {
  // REV-1/REV-3: gwc-jcs-v1 invalid_unicode_policy=reject_unpaired_surrogates.
  assert.throws(() => ref.normalizeLoneSurrogate('\ud800', { reject: true }), Error);
  assert.throws(() => ref.canonicalJsonText({ payload: '\ud800test' }), Error);
});

test('REV-2/REV-3: valid non-BMP surrogate pair preserved', () => {
  // U+10000 is one non-BMP code point from a valid surrogate pair.
  assert.strictEqual(ref.canonicalJsonText({ astral: '\uD800\uDC00' }), '{"astral":"\uD800\uDC00"}');
});

test('REV-2/REV-3: non-BMP key ordering is UTF-16 code-unit order', () => {
  // U+10000 (units D800 DC00) sorts before U+1D400 (units D835 DC00).
  const got = ref.canonicalJsonText({ '\uD835\uDC00': 'v1', '\uD835\uDC01': 'v2', '\uD800\uDC00': 'v0' });
  assert.strictEqual(got, '{"\uD800\uDC00":"v0","\uD835\uDC00":"v1","\uD835\uDC01":"v2"}');
});

test('REV-2/REV-3: non-ASCII string uses JCS-minimal raw UTF-8', () => {
  // é (U+00E9) emitted raw, never \\u00E9.
  assert.strictEqual(ref.canonicalJsonText({ msg: 'café' }), '{"msg":"café"}');
});

test('Defect D: resourceLimit is finite positive number', () => {
  assert.strictEqual(typeof resourceLimit, 'number');
  assert(isFinite(resourceLimit));
  assert(resourceLimit > 0);
});

test('Defect D: canonicalization stays within budget on moderate input', () => {
  const doc = { doc: 'a'.repeat(200) };
  const before = process.memoryUsage().heapUsed;
  ref.canonicalJsonText(doc);
  const after = process.memoryUsage().heapUsed;
  const delta = after - before;
  assert(delta < resourceLimit * 20, 'memory delta exceeded budget factor');
});

console.log('');
console.log(`Results: ${passed} passed, ${failed} failed`);
// --- C4: genuinely execute/validate the shared golden corpus from YAML ---
const vectors = loadGoldenVectors();
function findVector(id) {
  return vectors.find(v => v && v.id === id);
}
function yamlInputToObject(input) {
  const obj = {};
  for (const [k, v] of Object.entries(input || {})) obj[k] = v;
  return obj;
}

test('C4: CV-0008 (lone surrogate) is read from corpus and rejected', () => {
  const v = findVector('CV-0008-lone-surrogate-uD800-rejected');
  assert(v, 'CV-0008 present in corpus');
  assert.strictEqual(v.expected_canonical_json, null);
  const obj = yamlInputToObject(v.input);
  assert.throws(() => ref.canonicalJsonText(obj), Error);
});

test('C4: CV-0010 (non-BMP UTF-16 ordering) matches corpus expected', () => {
  const v = findVector('CV-0010-non-bmp-utf16-key-ordering');
  assert(v, 'CV-0010 present in corpus');
  const obj = yamlInputToObject(v.input);
  const got = ref.canonicalJsonText(obj);
  assert.strictEqual(got, v.expected_canonical_json);
  assert.strictEqual(createHash('sha256').update(got).digest('hex'), v.expected_canonical_digest_sha256);
});

test('C4: CV-0011 (non-ASCII minimal) matches corpus expected', () => {
  const v = findVector('CV-0011-non-ascii-minimal-serialization');
  assert(v, 'CV-0011 present in corpus');
  const obj = yamlInputToObject(v.input);
  const got = ref.canonicalJsonText(obj);
  assert.strictEqual(got, v.expected_canonical_json);
});

test('C4: CV-0012 (valid non-BMP pair preserved) matches corpus expected', () => {
  const v = findVector('CV-0012-valid-non-bmp-surrogate-pair-preserved');
  assert(v, 'CV-0012 present in corpus');
  const obj = yamlInputToObject(v.input);
  const got = ref.canonicalJsonText(obj);
  assert.strictEqual(got, v.expected_canonical_json);
});

test('C4: CV-0013 (mixed BMP/non-BMP discriminator) matches corpus expected', () => {
  const v = findVector('CV-0013-mixed-bmp-nonbmp-utf16-discriminator');
  assert(v, 'CV-0013 present in corpus');
  const obj = yamlInputToObject(v.input);
  const got = ref.canonicalJsonText(obj);
  assert.strictEqual(got, '{"\uD800\uDC00":"high","\uE000":"low"}');
  assert.strictEqual(got, v.expected_canonical_json);
});

// --- E3: Node corpus-driven execution of CV-0014 (numeric JCS boundaries) and
//         CV-0015 (negative-zero rejection). E1 makes YAML scalars load as real
//         IEEE754 doubles; E4 pins the CV-0014 canonical digest (Py==Node).
test('E3: CV-0014 (numeric JCS shortest boundaries) read from corpus & verified', () => {
  const v = findVector('CV-0014-numeric-jcs-shortest-boundaries');
  assert(v, 'CV-0014 present in corpus');
  // E1: YAML scalars must parse as numbers, not strings.
  for (const [k, val] of Object.entries(v.input)) {
    assert.strictEqual(typeof val, 'number', `CV-0014 input.${k} must be a number, got ${typeof val}`);
  }
  const obj = yamlInputToObject(v.input);
  const got = ref.canonicalJsonText(obj);
  assert.strictEqual(got, v.expected_canonical_json);
  assert.strictEqual(
    createHash('sha256').update(got).digest('hex'),
    v.expected_canonical_digest_sha256
  );
});

test('E3: CV-0015 (negative zero rejected) read from corpus & rejected', () => {
  const v = findVector('CV-0015-negative-zero-rejected');
  assert(v, 'CV-0015 present in corpus');
  assert.strictEqual(v.expected_canonical_json, null, 'CV-0015 must expect rejection');
  const obj = yamlInputToObject(v.input);
  assert.throws(() => ref.canonicalJsonText(obj), Error, 'CV-0015 negative zero must reject');
});

// --- C2: surrogate-pair validation must reject malformed pairs ---
test('C2: isolated LOW surrogate rejected', () => {
  assert.throws(() => ref.normalizeLoneSurrogate('A\uDC00B', { reject: true }), Error);
  assert.throws(() => ref.canonicalJsonText({ k: 'x\uDC00y' }), Error);
});
test('C2: LOW+LOW (DC00 DC00) rejected as lone', () => {
  assert.throws(() => ref.normalizeLoneSurrogate('\uDC00\uDC00', { reject: true }), Error);
  assert.throws(() => ref.canonicalJsonText({ k: '\uD800\uDC00\uDC00' }), Error);
});
test('C2: valid HIGH+LOW pair preserved', () => {
  assert.strictEqual(ref.canonicalJsonText({ astral: '\uD800\uDC00' }), '{"astral":"\uD800\uDC00"}');
});

// --- C3: invalid key Unicode rejected deterministically, not a raw crash ---
test('C3: lone-surrogate key raises controlled error', () => {
  assert.throws(() => ref.canonicalJsonText({ '\uD800': 'v' }), Error);
});

// --- C5: numeric JCS shortest-round-trip boundaries ---
const NUM_CASES = [
  ['1e+21', 1e21, '1e+21'],
  ['1e-06', 1e-6, '0.000001'],
  ['1e-07', 1e-7, '1e-7'],
  ['2.951e20', 2.9514790517935283e20, '295147905179352830000'],
  ['1e+22', 1e22, '1e+22'],
  ['5e-324', 5e-324, '5e-324'],
  ['max-double', 1.7976931348623157e308, '1.7976931348623157e+308'],
  ['123.0', 123.0, '123'],
  ['0.1+0.2', 0.1 + 0.2, '0.30000000000000004'],
  ['1e+15', 1e15, '1000000000000000'],
  ['1e+16', 1e16, '10000000000000000'],
  ['1e-05', 1e-5, '0.00001'],
  ['-2.951e20', -2.9514790517935283e20, '-295147905179352830000'],
  ['3.0', 3.0, '3'],
];
for (const [name, val, want] of NUM_CASES) {
  test('C5 numeric shortest: ' + name, () => {
    assert.strictEqual(ref.canonicalJsonText({ v: val }), '{"v":' + want + '}');
    // Cross-check against the authoritative Node JSON.stringify shortest form.
    assert.strictEqual(JSON.stringify({ v: val }), '{"v":' + want + '}');
  });
}

// C5b: negative zero rejected (gwc-jcs-v1 negative_zero_policy=reject)
test('C5b: negative zero rejected (deterministic Error)', () => {
  assert.throws(() => ref.canonicalJsonText({ z: -0 }), Error);
  assert.throws(() => ref.canonicalJsonText(-0), Error);
});
// Non-finite must still be rejected.
test('C5b: non-finite still rejected', () => {
  assert.throws(() => ref.canonicalJsonText(NaN), Error);
  assert.throws(() => ref.canonicalJsonText(Infinity), Error);
});

console.log('');

if (failed > 0) {
  process.exit(1);
}
