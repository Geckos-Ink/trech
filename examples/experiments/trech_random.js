// Shared deterministic sampling. Importing this file draws no random values.
globalThis.TRECH_RANDOM = (function () {
  "use strict";
  function mulberry32(seed) {
    let state = seed >>> 0;
    const uniform = () => {
      state = (state + 0x6D2B79F5) | 0;
      let t = Math.imul(state ^ (state >>> 15), 1 | state);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    // Callable for local samplers; the same method protocol as ctx.rng for
    // gaussian(). Engine RNG methods must retain their receiver when called.
    uniform.uniform = uniform;
    return uniform;
  }
  function gaussian(rng) {
    let u1 = rng.uniform();
    if (u1 <= 1e-12) u1 = 1e-12;
    const u2 = rng.uniform();
    // Deliberately no spare-sample cache: every call consumes exactly two draws.
    return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  }
  function parcelNoise01(id, stream) {
    let x = (((id + 1) * 1664525) + ((stream + 1) * 1013904223)) >>> 0;
    x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
    return (x >>> 0) / 4294967296.0;
  }
  return { mulberry32, gaussian, parcelNoise01 };
})();
