#!/usr/bin/env node
// trech_dmath compiled to WebAssembly (js/trech_dmath_wasm_data.js, installed by
// js/trech_dmath_v8.js) must reproduce the C library bit for bit on V8.
//
// 1. Staleness: the committed module names the SHA-256 of the C source and header it was
//    compiled from; both must match the checkout (rerun scripts/build_dmath_wasm.py).
// 2. Cross-host identity: the same 4096-input FNV-1a 64 digests as
//    tests/test_deterministic_math.cpp, parsed from that file, for all 22 raw functions.
// 3. Special cases with exact bits, and the QuickJS-compatible JavaScript wrappers that
//    install() puts on a Math object (pow NaN cases, variadic hypot, ToNumber, names).
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const dmath = require(path.join(ROOT, 'js', 'trech_dmath_v8.js'));
const raw = dmath.raw;
let failures = 0;
function check(name, fn) {
  try {
    fn();
  } catch (error) {
    failures += 1;
    process.stderr.write(`FAIL ${name}: ${error.message}\n`);
  }
}

const f64 = new Float64Array(1);
const u64 = new BigUint64Array(f64.buffer);
const bitsOf = (x) => { f64[0] = x; return u64[0]; };
const fromBits = (b) => { u64[0] = b; return f64[0]; };
const hex = (b) => b.toString(16).padStart(16, '0');
const MASK = (1n << 64n) - 1n;

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(path.join(ROOT, file))).digest('hex');
}

check('module matches the C source', () => {
  assert.equal(dmath.sourceSha256, sha256('src/js/DeterministicMath.c'),
               'src/js/DeterministicMath.c changed: rerun scripts/build_dmath_wasm.py');
  assert.equal(dmath.headerSha256, sha256('include/trech/js/DeterministicMath.h'),
               'DeterministicMath.h changed: rerun scripts/build_dmath_wasm.py');
  const header = fs.readFileSync(path.join(ROOT, 'include/trech/js/DeterministicMath.h'), 'utf8');
  assert.equal(dmath.id, /#define TRECH_DMATH_ID "([^"]+)"/.exec(header)[1]);
  assert.equal(dmath.functions.length, 22);
});

// Generator and digest exactly as in tests/test_deterministic_math.cpp.
class XorShift {
  constructor(state) { this.state = state; }
  next() {
    let s = this.state;
    s ^= (s << 13n) & MASK;
    s ^= s >> 7n;
    s ^= (s << 17n) & MASK;
    this.state = s;
    return s;
  }
  unit() { return Number(this.next() >> 11n) * (1.0 / 9007199254740992.0); }
  anyFinite() {
    for (;;) {
      const value = fromBits(this.next());
      if (Number.isFinite(value)) return value;
    }
  }
}
function seeded(seed, name) {
  const rng = new XorShift(seed);
  for (const c of Buffer.from(name, 'latin1')) rng.state = (rng.state * 31n + BigInt(c)) & MASK;
  return rng;
}
class Fnv {
  constructor() { this.hash = 1469598103934665603n; }
  add(value) {
    const bits = bitsOf(value);
    for (let i = 0n; i < 8n; i++) {
      this.hash ^= (bits >> (8n * i)) & 0xffn;
      this.hash = (this.hash * 1099511628211n) & MASK;
    }
  }
}

// Parse {"name", trech_dmath_name, <ref>, [lo, hi,] maxUlp, 0x...ull} rows from the C test.
const cppTest = fs.readFileSync(path.join(ROOT, 'tests/test_deterministic_math.cpp'), 'utf8');
const rows = [];
const rowPattern = /\{"(\w+)", trech_dmath_\w+, \[\]\([^)]*\) \{ return std::\w+\([^)]*\); \},\s*([^{}]*?)0x([0-9a-f]{16})ull\}/g;
for (let m; (m = rowPattern.exec(cppTest));) {
  const numbers = m[2].split(',').map((s) => s.trim()).filter(Boolean).map(Number);
  rows.push({ name: m[1], numbers, golden: BigInt('0x' + m[3]) });
}
check('golden table parsed', () => assert.equal(rows.length, 22));

const SAMPLES = 4096;
for (const row of rows) {
  check(`golden ${row.name}`, () => {
    const fn = raw[row.name];
    const digest = new Fnv();
    if (row.numbers.length === 3) {
      const [lo, hi] = row.numbers;
      const rng = seeded(0x9E3779B97F4A7C15n, row.name);
      for (let i = 0; i < SAMPLES; i++) {
        const x = (i % 4) === 3 ? rng.anyFinite() : lo + (hi - lo) * rng.unit();
        digest.add(fn(x));
      }
    } else {
      const rng = seeded(0x243F6A8885A308D3n, row.name);
      for (let i = 0; i < SAMPLES; i++) {
        let x;
        let y;
        if ((i % 4) === 3) {
          x = rng.anyFinite();
          y = rng.anyFinite();
        } else if (row.name === 'pow') {
          x = raw.exp((rng.unit() * 2 - 1) * 20);
          y = (rng.unit() * 2 - 1) * 30;
          if (i % 7 === 0) {
            x = -x;
            y = Math.floor(y);
          }
        } else {
          x = (rng.unit() * 2 - 1) * raw.exp((rng.unit() * 2 - 1) * 40);
          y = (rng.unit() * 2 - 1) * raw.exp((rng.unit() * 2 - 1) * 40);
        }
        digest.add(fn(x, y));
      }
    }
    assert.equal(hex(digest.hash), hex(row.golden), 'cross-host identity broken');
  });
}

const CANONICAL_NAN = 0x7ff8000000000000n;
check('special cases', () => {
  const oddNaN = fromBits(0xfff4000000000123n);
  for (const [what, value] of [['sin(Inf)', raw.sin(Infinity)], ['sin(odd NaN)', raw.sin(oddNaN)],
    ['log(-1)', raw.log(-1)], ['acosh(0.5)', raw.acosh(0.5)], ['pow(-8, 1/3)', raw.pow(-8, 1 / 3)],
    ['atan2(NaN, 1)', raw.atan2(oddNaN, 1)], ['asin(2)', raw.asin(2)]]) {
    assert.equal(hex(bitsOf(value)), hex(CANONICAL_NAN), what);
  }
  assert.equal(hex(bitsOf(raw.exp(1))), '4005bf0a8b145769');
  assert.ok(Object.is(raw.sin(-0), -0) && Object.is(raw.tan(-0), -0) && Object.is(raw.cbrt(-0), -0));
  assert.equal(raw.sin(1e22), -0.8522008497671888);
  assert.equal(raw.cos(1e22), 0.523214785395139);
  assert.equal(raw.sin(1.7976931348623157e308), 0.004961954789184062);
  assert.equal(raw.pow(1, NaN), 1, 'C99 pow(1, NaN) = 1 in the raw function');
});

check('installed JavaScript wrappers', () => {
  const context = vm.createContext({});
  const math = vm.runInContext('Math', context);
  const names = dmath.install(math);
  assert.equal(names.length, 22);
  assert.equal(vm.runInContext('Math.__trech_dmath', context), dmath.id);
  const exp1 = vm.runInContext('Math.exp(1)', context);
  assert.equal(hex(bitsOf(exp1)), '4005bf0a8b145769');
  assert.ok(Number.isNaN(math.pow(1, Infinity)) && Number.isNaN(math.pow(-1, -Infinity)));
  assert.ok(Number.isNaN(math.pow(1, NaN)) && math.pow(NaN, 0) === 1 && math.pow(2, 10) === 1024);
  assert.equal(math.hypot(), 0);
  assert.equal(math.hypot(-3), 3);
  assert.equal(math.hypot(3, 4, 12), 13);
  assert.equal(math.hypot(NaN, -Infinity), Infinity);
  assert.equal(math.exp('1'), exp1, 'ToNumber conversion');
  assert.throws(() => math.sin(1n), TypeError);
  assert.equal(math.atan2.length, 2);
  assert.equal(math.hypot.length, 2);
  assert.equal(math.sin.name, 'sin');
  assert.equal(Object.getOwnPropertyDescriptor(math, 'sin').enumerable, false);
  assert.equal(math.sqrt(2), Math.sqrt(2), 'exact functions untouched');
});

if (failures) {
  process.stderr.write(`${failures} trech_dmath WebAssembly check(s) failed\n`);
  process.exit(1);
}
process.stdout.write(`trech_dmath WebAssembly: all checks passed (${dmath.id}, V8 ${process.versions.v8})\n`);
