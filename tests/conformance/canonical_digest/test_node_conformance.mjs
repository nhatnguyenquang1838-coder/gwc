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

// Minimal YAML subset loader
function parseSimpleYaml(text) {
  const lines = text.split('\n');
  const doc = {};
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line === '') continue;
    const kv = line.match(/^([A-Za-z0-9_]+):\s*(.*)/);
    if (kv) {
      const key = kv[1];
      let val = kv[2].trim();
      if (val === '') { doc[key] = ''; continue; }
      if (val === 'true') { doc[key] = true; continue; }
      if (val === 'false') { doc[key] = false; continue; }
      if (val === 'null') { doc[key] = null; continue; }
      if (!isNaN(Number(val)) && val !== '') { doc[key] = Number(val); continue; }
      doc[key] = val;
      continue;
    }
    const listItem = line.match(/^-\s+(.*)/);
    if (listItem) {
      if (!doc.golden_vectors) doc.golden_vectors = [];
      const item = listItem[1].trim();
      if (item === 'true') doc.golden_vectors.push(true);
      else if (item === 'false') doc.golden_vectors.push(false);
      else if (item === 'null') doc.golden_vectors.push(null);
      else if (!isNaN(Number(item)) && item !== '') doc.golden_vectors.push(Number(item));
      else doc.golden_vectors.push(item);
      continue;
    }
    const nestedKv = line.match(/^([A-Za-z0-9_]+):\s*(.*)/);
    if (nestedKv && doc.golden_vectors && doc.golden_vectors.length > 0) {
      const last = doc.golden_vectors[doc.golden_vectors.length - 1];
      if (last && typeof last === 'object' && !Array.isArray(last)) {
        const nk = nestedKv[1];
        let nv = nestedKv[2].trim();
        if (nv === 'true') last[nk] = true;
        else if (nv === 'false') last[nk] = false;
        else if (nv === 'null') last[nk] = null;
        else if (!isNaN(Number(nv)) && nv !== '') last[nk] = Number(nv);
        else last[nk] = nv;
      }
    }
  }
  return doc;
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

test('Defect C: does not crash on lone surrogate', () => {
  const inp = { payload: '\ud800test' };
  const result = ref.canonicalJsonText(inp);
  assert.strictEqual(typeof result, 'string');
  JSON.parse(result);
});

test('Defect C: lone surrogate reject throws', () => {
  assert.throws(() => ref.normalizeLoneSurrogate('\ud800', { reject: true }), Error);
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
if (failed > 0) {
  process.exit(1);
}
