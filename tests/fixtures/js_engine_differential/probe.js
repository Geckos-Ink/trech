// Same-input JS engine differential probe (QuickJS host vs an installed Node/V8).
//
// Evaluates the engine-neutral numerical JavaScript TRECH ships, with fixed inputs, and records
// every double as its exact IEEE-754 bit pattern so two engines can be compared bit for bit:
//   1. Math builtins on a fixed argument grid (the engines' own libm implementations);
//   2. js/trech_random.js (integer mulberry32 stream + Box-Muller gaussians);
//   3. js/trech_water_mw.js: a small mW ice/liquid box, velocity-Verlet steps, CHILL+ phases.
// The result goes to TRECH_CONFIG.hooks.inputs.js_engine_differential, which `trech inspect`
// prints. Nothing here is physics validation; it measures whether hook-layer numerics replay
// identically across JavaScript engines (scripts/js_engine_differential.py compares them).
TRECH_INCLUDE("../../../js/trech_random.js");
TRECH_INCLUDE("../../../js/trech_water_mw.js");

(function () {
  "use strict";
  const view = new DataView(new ArrayBuffer(8));
  function bits(x) {
    view.setFloat64(0, x);
    let out = "";
    for (let i = 0; i < 8; i++) out += (view.getUint8(i) + 0x100).toString(16).slice(1);
    return out;
  }
  const allBits = (values) => Array.from(values, bits);

  // 1. Builtins over a fixed, irregular argument grid.
  const grid = [];
  for (let i = 0; i < 48; i++) grid.push(((i * 0.7919) % 11) - 5.5 + i * 1.0e-3);
  const positive = grid.map((x) => Math.abs(x) + 1.0e-3);
  const unit = grid.map((x) => x / 6);
  const builtins = {
    exp: grid.map(Math.exp), expm1: grid.map(Math.expm1), log: positive.map(Math.log),
    log1p: positive.map(Math.log1p), log10: positive.map(Math.log10), log2: positive.map(Math.log2),
    sqrt: positive.map(Math.sqrt), cbrt: grid.map(Math.cbrt),
    sin: grid.map(Math.sin), cos: grid.map(Math.cos), tan: grid.map(Math.tan),
    asin: unit.map(Math.asin), acos: unit.map(Math.acos), atan: grid.map(Math.atan),
    atan2: grid.map((x, i) => Math.atan2(x, grid[(i * 7) % grid.length])),
    sinh: grid.map(Math.sinh), cosh: grid.map(Math.cosh), tanh: grid.map(Math.tanh),
    pow: positive.map((x, i) => Math.pow(x, grid[(i * 5) % grid.length] / 2)),
    hypot: grid.map((x, i) => Math.hypot(x, grid[(i * 3) % grid.length], 0.5)),
  };
  const builtinBits = {};
  for (const name of Object.keys(builtins)) builtinBits[name] = allBits(builtins[name]);

  // 2. Deterministic random streams.
  const rng = globalThis.TRECH_RANDOM.mulberry32(20261116);
  const uniforms = [];
  for (let i = 0; i < 32; i++) uniforms.push(rng());
  const gaussRng = globalThis.TRECH_RANDOM.mulberry32(7);
  const gaussians = [];
  for (let i = 0; i < 32; i++) gaussians.push(globalThis.TRECH_RANDOM.gaussian(gaussRng));

  // 3. mW water: a 3x2 ice Ih cell, two layers, the lower half fixed, the rest heated and
  //    stepped (the box is the smallest the mW cell list accepts: >= 3 cutoffs per side).
  const mw = globalThis.TRECH_WATER_MW;
  const lattice = mw.iceIhSites(4.52, 3, 2, 2, 1.0);
  const [a, b, c] = lattice.cell;
  const box = [3 * a, 2 * b, 2 * c + 12.0];
  const fixed = lattice.sites.map((s) => s[2] < 1.0 + c / 2);
  const sim = mw.create({ box, positions: lattice.sites, fixed, dt: 10, seed: 11, initialK: 260 });
  const temperatures = [];
  for (let step = 0; step < 40; step++) {
    sim.step();
    if (step % 10 === 9) {
      temperatures.push(sim.temperature());
      sim.thermostat(250, 0.2);
    }
  }
  const phases = mw.chillPlus(sim, 3.5);

  const result = {
    schema: "trech_js_engine_differential_v1",
    builtins: builtinBits,
    random: { uniforms: allBits(uniforms), gaussians: allBits(gaussians) },
    water_mw: {
      sites: lattice.sites.length,
      x: allBits(sim.x), y: allBits(sim.y), z: allBits(sim.z),
      temperatures: allBits(temperatures),
      phases: Array.from(phases.phase),
    },
  };
  globalThis.TRECH_CONFIG = {
    run: { nEvents: 1, seed: 1 },
    hooks: { inputs: { js_engine_differential: result } },
  };
})();
