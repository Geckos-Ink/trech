// Shared numerical utilities, without scenario coefficients or physical laws.
globalThis.TRECH_MATH = (function () {
  "use strict";
  function clamp(value, lo, hi) { return Math.max(lo, Math.min(hi, Number(value))); }
  function clamp01(value) { return clamp(value, 0.0, 1.0); }
  function mix(a, b, t) { return a + (b - a) * t; }
  function mix3(a, b, t) {
    return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];
  }
  function round3(value) { return Math.round(value * 1e3) / 1e3; }
  function round4(value) { return Math.round(value * 1e4) / 1e4; }
  function smoothstep(value) {
    const x = clamp01(value);
    return x * x * (3.0 - 2.0 * x);
  }
  function finite(value, label) {
    const x = Number(value);
    if (!Number.isFinite(x)) throw new Error("non-finite inferred " + label);
    return x;
  }
  return { clamp, clamp01, mix, mix3, round3, round4, smoothstep, finite };
})();
