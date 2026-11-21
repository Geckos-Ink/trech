// TRECH deterministic host math for V8 (Node or an embedded V8 host).
//
// QuickJS computes Math.* and `**` with trech_dmath (src/js/DeterministicMath.c), one
// fdlibm-derived implementation compiled without fused multiply-add. V8's own Math differs
// from it in the last bit on some inputs: Node's arm64 build fuses multiply-add inside V8's
// fdlibm, Node defaults to the platform pow, and V8's Math.hypot uses another algorithm.
// This module runs the same C code compiled to WebAssembly (js/trech_dmath_wasm_data.js;
// WebAssembly f64 arithmetic never fuses) and installs it as Math.*, with the same JavaScript
// wrappers QuickJS applies, so both engines return identical bits.
//
// Limits: the `**` operator cannot be replaced from JavaScript, so in V8 it keeps V8's pow;
// write Math.pow(x, y) where byte replay across engines matters. Math.random is untouched.
//
//   const dmath = require('./trech_dmath_v8.js');
//   dmath.install(Math);              // or the Math object of a vm context
//   dmath.raw.exp(1);                 // the C function itself (C99 pow/hypot special cases)
'use strict';

const DATA = (typeof module === 'object' && module && module.exports)
  ? require('./trech_dmath_wasm_data.js')
  : globalThis.TRECH_DMATH_WASM_DATA;

function decodeBase64(text) {
  if (typeof Buffer === 'function') return new Uint8Array(Buffer.from(text, 'base64'));
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

let cachedRaw = null;

// Synchronous compile/instantiate: allowed for any module size in Node and embedded V8.
function instantiate() {
  if (cachedRaw) return cachedRaw;
  const module = new WebAssembly.Module(decodeBase64(DATA.base64));
  const instance = new WebAssembly.Instance(module, {});
  const raw = {};
  for (const name of DATA.unary.concat(DATA.binary)) {
    const fn = instance.exports['trech_dmath_' + name];
    if (typeof fn !== 'function') throw new Error('trech_dmath WebAssembly export missing: ' + name);
    raw[name] = fn;
  }
  cachedRaw = Object.freeze(raw);
  return cachedRaw;
}

function define(math, name, fn) {
  Object.defineProperty(math, name, { value: fn, writable: true, enumerable: false, configurable: true });
}

// The JavaScript-level wrappers mirror QuickJS (thirds/quickjs/quickjs/quickjs.c): arguments
// are converted with ToNumber in order; pow returns NaN for |x| = 1 with a non-finite y
// (IEEE/C99 return 1); hypot folds its arguments pairwise through the C hypot.
function wrappers(raw) {
  const out = {};
  for (const name of DATA.unary) {
    const f = raw[name];
    out[name] = { [name](x) { return f(+x); } }[name];
  }
  const atan2 = raw.atan2;
  out.atan2 = { atan2(y, x) { const a = +y; return atan2(a, +x); } }.atan2;
  const pow = raw.pow;
  out.pow = {
    pow(x, y) {
      const a = +x;
      const b = +y;
      if (!Number.isFinite(b) && (a === 1 || a === -1)) return NaN;
      return pow(a, b);
    },
  }.pow;
  const hypot = raw.hypot;
  out.hypot = {
    hypot(x, y) {
      const n = arguments.length;
      if (n === 0) return 0;
      let r = +arguments[0];
      if (n === 1) return Math.abs(r);
      for (let i = 1; i < n; i++) r = hypot(r, +arguments[i]);
      return r;
    },
  }.hypot;
  return out;
}

// Replace the 22 transcendental functions of `math` (default: this realm's Math) and return
// the list of names installed. Exact functions (sqrt, abs, floor, ...) are left alone:
// IEEE-754 already defines their results bit for bit.
function install(math) {
  const target = math || Math;
  const installed = wrappers(instantiate());
  for (const name of Object.keys(installed)) define(target, name, installed[name]);
  define(target, '__trech_dmath', DATA.id);
  return Object.keys(installed);
}

const api = {
  id: DATA.id,
  sourceSha256: DATA.sourceSha256,
  headerSha256: DATA.headerSha256,
  compiler: DATA.compiler,
  functions: DATA.unary.concat(DATA.binary),
  instantiate,
  install,
  get raw() { return instantiate(); },
};

if (typeof module === 'object' && module && module.exports) module.exports = api;
else globalThis.TRECH_DMATH_V8 = api;
