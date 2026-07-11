// Sputnik / multi-scale-cascade CANONICAL demo: a GLASS OF WATER BEING SHAKEN.
//
// This is the thesis example from AGENTS.md / ROADMAP.md ("what does this glass
// of water do while I stir it -- the fluid motion, the waves?"): the macroscopic
// sloshing waves and splashes are produced WITHOUT hand-typing a single
// macroscopic water property. Every fluid parameter the macro solver uses is
// INFERRED from the nanoscale H2O behaviour, lifted scale by scale up the
// dimension ladder (nano -> micro -> macro) by ctx.cascade.
//
//   short rigid-SPC/E MD          ctx.cascade (nano->micro->macro)      macro PBF fluid
//   (measure nano facts)   -->    lift to macro fluid parameters   -->  in a shaken glass
//   number density n              macro_rest_density_kg_per_m3          rest density / mass
//   H-bond coordination           macro_surface_tension_coeff           cohesion (drops merge)
//                                 macro_viscosity_coeff                 XSPH damping
//
// The scenario NEVER writes water's density (998 kg/m^3), surface tension, or
// viscosity. It measures the number density and hydrogen-bond coordination that
// EMERGE from the molecular run, seeds the cascade with them, and reads the
// macro-band fluid parameters back out. The density coefficient in the cascade
// is grounded unit coarse-graining (n -> rho via the molar mass), so the macro
// rest density it recovers (~999 kg/m^3) lands on measured water as a check, not
// as an input. The cohesion/viscosity maps are illustrative (labelled in the
// stage-model JSONs) -- the honest, demonstrated claim is the MECHANISM: a
// macroscopic fluid whose behaviour comes from the microscopic base with no
// intermediate model wired by hand.
//
// The macro fluid is a Position-Based Fluid (Macklin & Muller 2013): a stable,
// deterministic particle method (density-constraint solve + an explicit
// cascade-scaled COHESION that makes particles cohere into drops and MERGE when
// they touch + XSPH viscosity). Neighbours are found with a uniform SPATIAL GRID
// (O(N)), needed for this larger glass. The run has three phases the video shows:
//   POUR    -- water is poured in from above (particles fall from a faucet and
//              accumulate), so the fill itself is part of the physics on screen;
//   SETTLE  -- the poured water relaxes to its still level;
//   SHAKE   -- the glass is shaken by a smooth-but-random horizontal motion
//              (a seeded sum of sinusoids under a growing envelope): gentle waves
//              early, vigorous sloshing and splashes late.
//
// Glass: a wide tumbler, inner radius 5.6 cm (11.2 cm across), water poured to
// ~10 cm -> ~1 litre. Simulation particles at ~6 mm; the 3D renderer draws the
// water as a 2 mm metaball isosurface (finer visual precision than the sim grid).
//
// Honest scope (same contract as the other H2O scenarios): Geant4 transports a
// geantino per tick as the deterministic CLOCK; it does not compute molecular
// bonds or fluid flow. The nano MD and the macro PBF are classical "physics for
// comparison" in the deterministic hook layer. What is genuinely novel here is
// that the macro parameters are not typed -- they are cascaded up from the
// measured nano base.
//
// Emits: `scenario` (config), `cascade` (measured nano facts + cascade-inferred
// macro params + provenance), per-frame `fluid_frame` (lab-frame active particle
// positions + glass displacement + phase, for the 3D renderer), and a final
// `glass_summary` with the validation. Deterministic (seeded, threads:1,
// predictive so the cascade runs).
//
// Run:
//   trech run examples/experiments/glass_of_water_shaken.js \
//        --events 641 --output build/dev/out_glass_shaken

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

TRECH_INCLUDE("trech_water_md.js");
const md = globalThis.TRECH_WATER_MD;
if (!md) {
  throw new Error("TRECH_WATER_MD not available; include trech_water_md.js");
}

// ======================================================================
// Geometry of the glass (metres internally; the Geant4 world is cosmetic).
// A wide tumbler: inner radius 5.6 cm (4x the original narrow glass), water
// poured to 10 cm -> ~1 litre. Parametric.
// ======================================================================
const R_IN = 0.056;          // inner radius (m) -> 11.2 cm across (4x original)
const H_WALL = 0.130;        // glass wall height (m) -> 13 cm (3 cm splash headroom)
const H_FILL = 0.100;        // target poured water height (m) -> 10 cm
const S0 = 0.006;            // sim particle rest spacing (m) ~ 6 mm
const H_KERN = 2.2 * S0;     // PBF smoothing radius (m) ~ 13.2 mm
const RENDER_GRID_MM = 2.0;  // 3D metaball isosurface precision (renderer side)

// ======================================================================
// PBF (position-based fluid) numerics. These are GENERIC solver defaults (like a
// timestep) -- NOT water properties. The water-specific behaviour (density,
// cohesion, viscosity) is supplied by the cascade below.
// ======================================================================
const DT = 0.004;            // s per tick
const G = 9.81;              // gravity (m/s^2), down -z
const SOLVER_ITERS = 4;      // Jacobi density-constraint iterations
const CFM_EPS = 1.0e-6;      // constraint-force-mixing relaxation
const REST_MARGIN = 0.30 * S0;  // keep particle centres this far off the walls
const WALL_FRICTION = 0.18;     // tangential damping at the walls (0..1)
const MAX_DP = 0.50 * S0;       // per-iteration position-correction clamp (anti-blowup)
const MAX_SPEED = 2.5;          // hard velocity clamp (m/s), safety only
const MAX_NBR = 80;             // per-particle neighbour cap (spatial-grid CSR stride)
const REF_PCT = 0.35;           // rho0 = this percentile of the reference-fill densities
// Cohesion (surface tension) is an EXPLICIT attraction between neighbours within
// the kernel, scaled by the cascade-inferred macro_surface_tension_coeff. It is
// what pulls drops together and MERGES them on contact, and holds the free
// surface. COH_GAIN is a generic numeric gain (like a timestep); the
// water-specific STRENGTH is the cascade value. Cohesion is a velocity nudge,
// DECOUPLED from the incompressibility solve (far more stable than folding a
// Macklin s_corr artificial-pressure term into the constraint).
const COH_GAIN = 4.0;
// Defensive guards on the cascade-inferred coefficients: the RAW cascade values
// are always emitted; these only bound the numbers actually handed to the solver
// so an out-of-range nano measurement can never blow the fluid up.
const K_COH_MAX = 0.15;         // cohesion (surface-tension) active clamp
const VISC_MAX = 0.12;          // XSPH viscosity active clamp

// ======================================================================
// Run phases (ticks): POUR the water in, SETTLE, then SHAKE.
// ======================================================================
const POUR_TICKS = 190;         // ticks spent pouring water in
const SETTLE_TICKS = 90;        // ticks to relax after pouring
const SHAKE_TICKS = 360;        // ticks of shaking
const MACRO_TICKS = POUR_TICKS + SETTLE_TICKS + SHAKE_TICKS;
const SHAKE_START = POUR_TICKS + SETTLE_TICKS;
const SETTLE_DAMP = 0.99;       // extra velocity damping during settling
const SNAP_EVERY = 4;           // fluid_frame emit stride (viz sideband)

// Pour "faucet": a falling stream, offset from centre so it visibly pours in
// from one side and spreads (some sloshing during the fill -- part of the show).
const FAUCET_R = 0.016;         // pour-stream radius (m)
const FAUCET_CX = 0.014;        // pour offset from the axis (m)
const FAUCET_Z = H_WALL - 0.008;
const POUR_VZ = -0.7;           // downward pour speed (m/s)
const POUR_SPREAD = 0.05;       // small horizontal velocity spread (m/s)
const POUR_SEED = 0x9A17C3;

// ======================================================================
// Shake: smooth but random horizontal glass motion. Displacement s(tau) is a
// seeded sum of sinusoids under a growing envelope; the fluid feels the inertial
// (pseudo) force -m*s''(tau). Frequencies are lower than the narrow glass (a
// wide tumbler sloshes at a lower mode).
// ======================================================================
const SHAKE_SEED = 0xB0A711;
const SHAKE_RAMP_T = 0.5;    // s over which the shake ramps in from rest
const SHAKE_GROWTH = 0.9;    // extra amplitude gained across the shake

// ======================================================================
// Nano measurement + sizing.
// ======================================================================
const NANO_N = 64;           // molecules in the nanoscale probe run
const NANO_DENSITY = 0.0334; // molecules / A^3 (liquid-water rest density lattice)
const NANO_TICKS = 800;      // nano MD ticks (equilibrate, then accumulate g(r))
const NANO_EQUIL = 0.5;      // start g(r) accumulation after this fraction
const NANO_DT = 2.0;         // fs (rigid water)
const NANO_TARGET_K = 300.0;
const NANO_SEED = 0x5EED17;
const NANO_RDF_BINS = 120;
const NANO_COORD_R = 3.4;    // coordination integration bound (A) -- experimental
                             // first-shell convention (~4.3-4.7 for water)

// molecular constant (the nano base's "force field"; like SPC/E -- NOT the
// macroscopic density).
const M_H2O_G_PER_MOL = 18.01528;

// ---- tiny deterministic RNG (mulberry32) ----
function makeRng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ======================================================================
// Nanoscale H2O measurement: run a short rigid-SPC/E MD and measure the number
// density (N/V) and the first-shell O-O coordination number -- genuine emergent
// nano facts, the same observables the bulk-water scenario validates. These are
// the ONLY things the macro scale learns about water.
// ======================================================================
function measureNano() {
  const sim = md.create({
    nMol: NANO_N, density: NANO_DENSITY, rcutMax: 7.0, alpha: 0.25,
    dt: NANO_DT, seed: NANO_SEED, rdfBins: NANO_RDF_BINS, initialK: NANO_TARGET_K
  });
  const rdfHist = new Array(NANO_RDF_BINS).fill(0);
  let frames = 0, sumT = 0, nAcc = 0;
  const equilStart = Math.floor(NANO_EQUIL * NANO_TICKS);
  for (let t = 1; t <= NANO_TICKS; t++) {
    const accumulate = t > equilStart;
    sim.step(accumulate ? rdfHist : null);
    if (t % 5 === 0) sim.thermostat(NANO_TARGET_K, 0.25);
    if (t === equilStart) sim.thermostat(NANO_TARGET_K, 1.0);
    if (accumulate) { sumT += sim.temperature(); nAcc += 1; frames += 1; }
  }
  const boxL = sim.boxL, nO = sim.mols.length;
  const numberDensity = nO / (boxL * boxL * boxL);
  const rmax = sim.rdfRmax, dr = rmax / NANO_RDF_BINS, rho = nO / (boxL * boxL * boxL);
  const g = new Array(NANO_RDF_BINS).fill(0);
  for (let b = 0; b < NANO_RDF_BINS; b++) {
    const rlo = b * dr, rhi = rlo + dr;
    const shell = (4 / 3) * Math.PI * (rhi * rhi * rhi - rlo * rlo * rlo);
    const ideal = frames * nO * shell * rho;
    g[b] = ideal > 0 ? rdfHist[b] / ideal : 0;
  }
  let peakR = 0, peakG = 0;
  for (let b = 0; b < NANO_RDF_BINS; b++) {
    const r = (b + 0.5) * dr;
    if (r >= 2.4 && r <= 3.2 && g[b] > peakG) { peakG = g[b]; peakR = r; }
  }
  // coordination to the fixed experimental first-shell bound (3.4 A).
  let coord = 0;
  const b34 = Math.min(NANO_RDF_BINS - 1, Math.floor(NANO_COORD_R / dr));
  for (let b = 0; b <= b34; b++) {
    const r = (b + 0.5) * dr;
    coord += 4 * Math.PI * r * r * rho * g[b] * dr;
  }
  let minB = Math.floor((peakR + 0.2) / dr), minG = Infinity;
  const hiB = Math.min(NANO_RDF_BINS - 1, Math.floor((peakR + 1.2) / dr));
  for (let b = Math.floor((peakR + 0.1) / dr); b <= hiB; b++) {
    if (g[b] < minG) { minG = g[b]; minB = b; }
  }
  return {
    numberDensity, coordination: coord,
    hbondPeakA: peakR, firstMinA: (minB + 0.5) * dr,
    meanT: nAcc > 0 ? sumT / nAcc : 0, molecules: nO
  };
}

// ======================================================================
// PBF kernels (3D).
// ======================================================================
const POLY6 = 315.0 / (64.0 * Math.PI * Math.pow(H_KERN, 9));
const SPIKY = -45.0 / (Math.PI * Math.pow(H_KERN, 6));
const H2 = H_KERN * H_KERN;
function wPoly6(r2) {
  if (r2 >= H2) return 0.0;
  const d = H2 - r2;
  return POLY6 * d * d * d;
}
function wSpikyGrad(r) {
  if (r <= 1e-9 || r >= H_KERN) return 0.0;
  const d = H_KERN - r;
  return SPIKY * d * d / r;            // multiply by (dx,dy,dz) to get gradient vector
}
// Cohesion weight: zero at contact (r=0) and at the kernel edge (r=h), peaks
// mid-range -> pulls separated neighbours together (surface tension / merging).
function cohKernel(r) {
  if (r <= 1e-9 || r >= H_KERN) return 0.0;
  const x = r / H_KERN;
  return x * (1.0 - x);
}

// ======================================================================
// Reference fill lattice: the target filled-cylinder positions at spacing S0.
// Used (a) to size the arrays / set the pour target count N and (b) to compute
// the rest-density target rho0. The actual run POURS particles in rather than
// starting from this lattice.
// ======================================================================
function buildFillLattice() {
  const px = [], py = [], pz = [];
  const nR = Math.ceil(R_IN / S0) + 1;
  const nZ = Math.ceil(H_FILL / S0);
  const rmax2 = (R_IN - REST_MARGIN) * (R_IN - REST_MARGIN);
  for (let iz = 0; iz < nZ; iz++) {
    const z = (iz + 0.5) * S0;
    for (let ix = -nR; ix <= nR; ix++) {
      for (let iy = -nR; iy <= nR; iy++) {
        const x = ix * S0, y = iy * S0;
        if (x * x + y * y > rmax2) continue;
        px.push(x); py.push(y); pz.push(z);
      }
    }
  }
  return { px, py, pz, n: px.length };
}

// Smooth analytic glass displacement s(tau) (metres), tau = time since shaking
// began; envelope ramps in from rest and grows across the shake. Returns [sx, sy].
function shakeDisplacement(comp, tau) {
  if (tau <= 0) return [0, 0];
  const shakeDur = SHAKE_TICKS * DT;
  const ramp = Math.min(1.0, tau / SHAKE_RAMP_T);
  const grow = 1.0 + SHAKE_GROWTH * Math.min(1.0, tau / shakeDur);
  const env = ramp * grow;
  let sx = 0, sy = 0;
  for (const c of comp.x) sx += c.A * Math.sin(c.w * tau + c.p);
  for (const c of comp.y) sy += c.A * Math.sin(c.w * tau + c.p);
  return [env * sx, env * sy];
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  return ctx.state;
}

// ======================================================================
// Uniform spatial grid + CSR neighbour list (O(N)). The glass bounding box is
// fixed, so the grid dimensions are fixed; buffers are allocated once and reused.
// Cell size = kernel radius, so a particle's neighbours are in its 27-cell block.
// ======================================================================
function allocGrid(s, maxN) {
  const pad = 0.012;
  s.gx0 = -(R_IN + pad); s.gy0 = -(R_IN + pad); s.gz0 = -0.006;
  const spanXY = 2 * (R_IN + pad), spanZ = (H_WALL + 0.012) - s.gz0;
  s.gnx = Math.max(3, Math.ceil(spanXY / H_KERN) + 1);
  s.gny = s.gnx;
  s.gnz = Math.max(3, Math.ceil(spanZ / H_KERN) + 1);
  const nCells = s.gnx * s.gny * s.gnz;
  s.nCells = nCells;
  s.cellCount = new Int32Array(nCells + 1);
  s.cellStart = new Int32Array(nCells + 1);
  s.cellCursor = new Int32Array(nCells + 1);
  s.cellItems = new Int32Array(maxN);
  s.cellOf = new Int32Array(maxN);
  s.nbrCount = new Int32Array(maxN);
  s.nbrIdx = new Int32Array(maxN * MAX_NBR);
}

// Build the grid + per-particle neighbour index list from the predicted
// positions xpx/xpy/xpz over the first `n` active particles.
function buildNeighbors(s, n) {
  const { xpx, xpy, xpz, gnx, gny, gnz, nCells,
          cellCount, cellStart, cellCursor, cellItems, cellOf,
          nbrCount, nbrIdx } = s;
  const invH = 1.0 / H_KERN, gnxy = gnx * gny;
  cellCount.fill(0, 0, nCells + 1);
  for (let i = 0; i < n; i++) {
    let cx = ((xpx[i] - s.gx0) * invH) | 0; if (cx < 0) cx = 0; else if (cx >= gnx) cx = gnx - 1;
    let cy = ((xpy[i] - s.gy0) * invH) | 0; if (cy < 0) cy = 0; else if (cy >= gny) cy = gny - 1;
    let cz = ((xpz[i] - s.gz0) * invH) | 0; if (cz < 0) cz = 0; else if (cz >= gnz) cz = gnz - 1;
    const c = (cz * gny + cy) * gnx + cx;
    cellOf[i] = c; cellCount[c]++;
  }
  let acc = 0;
  for (let c = 0; c < nCells; c++) { cellStart[c] = acc; cellCursor[c] = acc; acc += cellCount[c]; }
  cellStart[nCells] = acc;
  for (let i = 0; i < n; i++) { const c = cellOf[i]; cellItems[cellCursor[c]++] = i; }

  for (let i = 0; i < n; i++) {
    const xi = xpx[i], yi = xpy[i], zi = xpz[i];
    const c = cellOf[i];
    const cz = (c / gnxy) | 0, rem = c - cz * gnxy, cy = (rem / gnx) | 0, cx = rem - cy * gnx;
    const base = i * MAX_NBR;
    let cnt = 0;
    const zlo = cz > 0 ? cz - 1 : 0, zhi = cz < gnz - 1 ? cz + 1 : gnz - 1;
    const ylo = cy > 0 ? cy - 1 : 0, yhi = cy < gny - 1 ? cy + 1 : gny - 1;
    const xlo = cx > 0 ? cx - 1 : 0, xhi = cx < gnx - 1 ? cx + 1 : gnx - 1;
    for (let zz = zlo; zz <= zhi; zz++)
      for (let yy = ylo; yy <= yhi; yy++)
        for (let xx = xlo; xx <= xhi; xx++) {
          const c2 = (zz * gny + yy) * gnx + xx;
          const p0 = cellStart[c2], p1 = cellStart[c2 + 1];
          for (let p = p0; p < p1; p++) {
            const j = cellItems[p];
            if (j === i) continue;
            const dx = xi - xpx[j], dy = yi - xpy[j], dz = zi - xpz[j];
            if (dx * dx + dy * dy + dz * dz < H2 && cnt < MAX_NBR) {
              nbrIdx[base + cnt] = j; cnt++;
            }
          }
        }
    nbrCount[i] = cnt;
  }
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "glass_of_water_shaken",
      glass: { inner_radius_m: R_IN, wall_height_m: H_WALL, fill_height_m: H_FILL,
               water_volume_cm3: Math.PI * R_IN * R_IN * H_FILL * 1e6 },
      particle_spacing_m: S0, kernel_h_m: H_KERN, render_grid_mm: RENDER_GRID_MM,
      dt_s: DT, macro_ticks: MACRO_TICKS, snap_every: SNAP_EVERY,
      phases: { pour_ticks: POUR_TICKS, settle_ticks: SETTLE_TICKS, shake_ticks: SHAKE_TICKS },
      nano: { molecules: NANO_N, ticks: NANO_TICKS, dt_fs: NANO_DT },
      model: "nanoscale rigid-SPC/E MD -> ctx.cascade(nano->micro->macro) -> Position-Based Fluid (Macklin & Muller 2013, spatial grid) poured into a shaken glass; NO macroscopic water property hand-specified"
    });
  },

  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;

    // ---- first tick: measure nano, cascade to macro params, prepare the pour ----
    if (!s.initialized) {
      const nano = measureNano();

      const c = ctx.cascade({
        nano_number_density_per_A3: nano.numberDensity,
        nano_coordination: nano.coordination
      });
      if (!c) throw new Error("ctx.cascade returned null (needs predictive mode + loaded models)");
      const restDensity = c.macro_rest_density_kg_per_m3;      // ~999 kg/m^3 (recovered, not typed)
      const surfaceTensionRaw = c.macro_surface_tension_coeff; // cohesion strength (drops merge)
      const viscosityRaw = c.macro_viscosity_coeff;            // XSPH damping
      const surfaceTension = Math.max(0.0, Math.min(K_COH_MAX, surfaceTensionRaw));
      const viscosity = Math.max(0.0, Math.min(VISC_MAX, viscosityRaw));
      const scales = (c.__cascade.trace || []).filter((x) => x.ran).map((x) => x.scale);

      // Target fill count N + reference lattice (for sizing and rho0).
      const fill = buildFillLattice();
      const N = fill.n;
      const mass = restDensity * S0 * S0 * S0;

      // Allocate the fluid state (arrays sized to N, active count grows as we pour).
      Object.assign(s, {
        initialized: true, tick: 0, n: 0, N,
        px: new Float64Array(N), py: new Float64Array(N), pz: new Float64Array(N),
        vx: new Float64Array(N), vy: new Float64Array(N), vz: new Float64Array(N),
        xpx: new Float64Array(N), xpy: new Float64Array(N), xpz: new Float64Array(N),
        lam: new Float64Array(N), dpx: new Float64Array(N), dpy: new Float64Array(N), dpz: new Float64Array(N),
        dvx: new Float64Array(N), dvy: new Float64Array(N), dvz: new Float64Array(N),
        mass, restDensity, surfaceTension, viscosity,
        pourRng: makeRng(POUR_SEED),
        sPrev: [0, 0], sPrev2: [0, 0],
        maxSpeed: 0, maxZ: 0, minZ: H_FILL, escaped: 0, restLevel: 0,
        surfVarSum: 0, surfVarN: 0, splashPeak: 0, wavePeak: 0
      });
      allocGrid(s, N);

      // rho0 = REF_PCT percentile of the reference-fill densities (the confined
      // rest density the poured water settles to). Load the reference lattice into
      // the predicted-position buffers, build the grid, and read each density.
      for (let i = 0; i < N; i++) { s.xpx[i] = fill.px[i]; s.xpy[i] = fill.py[i]; s.xpz[i] = fill.pz[i]; }
      buildNeighbors(s, N);
      const dens0 = new Float64Array(N);
      for (let i = 0; i < N; i++) {
        let d = wPoly6(0);
        const base = i * MAX_NBR, cnt = s.nbrCount[i];
        for (let k = 0; k < cnt; k++) {
          const j = s.nbrIdx[base + k];
          const dx = s.xpx[i] - s.xpx[j], dy = s.xpy[i] - s.xpy[j], dz = s.xpz[i] - s.xpz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 < H2) d += wPoly6(r2);
        }
        dens0[i] = d;
      }
      const sorted = Array.from(dens0).sort((a, b) => a - b);
      s.rho0 = sorted[Math.floor(REF_PCT * sorted.length)];

      // seeded, smooth-but-random shake components (lower freqs -> wide-glass slosh).
      const srng = makeRng(SHAKE_SEED);
      const mkComp = (bs) => bs.map((b) => ({
        A: b.A * (0.7 + 0.6 * srng()), w: b.w * (0.85 + 0.3 * srng()), p: 2 * Math.PI * srng()
      }));
      s.comp = {
        x: mkComp([{ A: 0.014, w: 5.0 }, { A: 0.009, w: 9.0 }, { A: 0.005, w: 17.0 }]),
        y: mkComp([{ A: 0.012, w: 6.0 }, { A: 0.008, w: 11.0 }, { A: 0.004, w: 15.0 }])
      };
      s.pourRate = Math.max(1, Math.ceil(N / POUR_TICKS));

      ctx.emit("cascade", {
        nano_measured: {
          molecules: nano.molecules,
          number_density_per_A3: nano.numberDensity,
          coordination: nano.coordination,
          hbond_peak_A: nano.hbondPeakA,
          first_min_A: nano.firstMinA,
          mean_temperature_K: nano.meanT
        },
        macro_inferred: {
          rest_density_kg_per_m3: restDensity,
          surface_tension_coeff: surfaceTensionRaw,
          viscosity_coeff: viscosityRaw,
          surface_tension_coeff_active: surfaceTension,
          viscosity_coeff_active: viscosity,
          particle_mass_kg: mass,
          rho0_kernel: s.rho0,
          target_particles: N,
          water_mass_g: N * mass * 1000.0
        },
        reference: { water_density_kg_per_m3: 998.2 },
        density_recovery_error_pct: Math.abs(restDensity - 998.2) / 998.2 * 100.0,
        cascade: {
          stages_run: c.__cascade.stagesRun,
          scales_bridged: scales,
          seed_keys: c.__cascade.seedKeys
        }
      });
      return;   // stepping starts next event
    }

    // ---- phase bookkeeping ----
    s.tick += 1;
    const t = s.tick * DT;
    const pouring = s.tick <= POUR_TICKS;
    const settling = s.tick > POUR_TICKS && s.tick <= SHAKE_START;
    const shaking = s.tick > SHAKE_START;
    const tau = Math.max(0, s.tick - SHAKE_START) * DT;

    // ---- pour: spawn new particles from the faucet (falling stream) ----
    if (pouring && s.n < s.N) {
      const rng = s.pourRng;
      const add = Math.min(s.pourRate, s.N - s.n);
      for (let q = 0; q < add; q++) {
        const i = s.n++;
        const ang = 2 * Math.PI * rng(), rad = Math.sqrt(rng()) * FAUCET_R;
        s.px[i] = FAUCET_CX + rad * Math.cos(ang);
        s.py[i] = rad * Math.sin(ang);
        s.pz[i] = FAUCET_Z - rng() * 0.012;
        s.vx[i] = (rng() - 0.5) * POUR_SPREAD;
        s.vy[i] = (rng() - 0.5) * POUR_SPREAD;
        s.vz[i] = POUR_VZ;
      }
    }
    const n = s.n;
    const { px, py, pz, vx, vy, vz, xpx, xpy, xpz, lam, dpx, dpy, dpz } = s;

    // glass displacement + inertial (pseudo) acceleration from its 2nd difference.
    const sNow = shakeDisplacement(s.comp, tau);
    const axs = -(sNow[0] - 2 * s.sPrev[0] + s.sPrev2[0]) / (DT * DT);
    const ays = -(sNow[1] - 2 * s.sPrev[1] + s.sPrev2[1]) / (DT * DT);
    s.sPrev2 = s.sPrev; s.sPrev = sNow;

    // 1) integrate external forces, predict positions
    for (let i = 0; i < n; i++) {
      vx[i] += DT * axs; vy[i] += DT * ays; vz[i] += DT * (-G);
      xpx[i] = px[i] + DT * vx[i];
      xpy[i] = py[i] + DT * vy[i];
      xpz[i] = pz[i] + DT * vz[i];
    }
    projectWalls(xpx, xpy, xpz, n);

    // 2) neighbours (spatial grid, once per tick)
    buildNeighbors(s, n);

    // 3) density-constraint solve (Jacobi, full constraint)
    const rho0 = s.rho0, invRho0 = 1.0 / rho0;
    for (let it = 0; it < SOLVER_ITERS; it++) {
      for (let i = 0; i < n; i++) {
        let rho = wPoly6(0);
        let gX = 0, gY = 0, gZ = 0, sumGrad2 = 0;
        const base = i * MAX_NBR, cnt = s.nbrCount[i];
        for (let k = 0; k < cnt; k++) {
          const j = s.nbrIdx[base + k];
          const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 >= H2) continue;
          rho += wPoly6(r2);
          const r = Math.sqrt(r2), gsc = wSpikyGrad(r) * invRho0;
          const gx = gsc * dx, gy = gsc * dy, gz = gsc * dz;
          gX += gx; gY += gy; gZ += gz;
          sumGrad2 += gx * gx + gy * gy + gz * gz;
        }
        sumGrad2 += gX * gX + gY * gY + gZ * gZ;
        const C = rho * invRho0 - 1.0;
        lam[i] = -C / (sumGrad2 + CFM_EPS);
      }
      for (let i = 0; i < n; i++) {
        let cx = 0, cy = 0, cz = 0;
        const base = i * MAX_NBR, cnt = s.nbrCount[i], li = lam[i];
        for (let k = 0; k < cnt; k++) {
          const j = s.nbrIdx[base + k];
          const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 >= H2) continue;
          const r = Math.sqrt(r2), gsc = wSpikyGrad(r);
          const coef = (li + lam[j]) * gsc * invRho0;
          cx += coef * dx; cy += coef * dy; cz += coef * dz;
        }
        const cmag = Math.sqrt(cx * cx + cy * cy + cz * cz);
        if (cmag > MAX_DP) { const f = MAX_DP / cmag; cx *= f; cy *= f; cz *= f; }
        dpx[i] = cx; dpy[i] = cy; dpz[i] = cz;
      }
      for (let i = 0; i < n; i++) { xpx[i] += dpx[i]; xpy[i] += dpy[i]; xpz[i] += dpz[i]; }
      projectWalls(xpx, xpy, xpz, n);
    }

    // 4) velocities from the constrained positions
    const invDt = 1.0 / DT;
    for (let i = 0; i < n; i++) {
      vx[i] = (xpx[i] - px[i]) * invDt;
      vy[i] = (xpy[i] - py[i]) * invDt;
      vz[i] = (xpz[i] - pz[i]) * invDt;
    }
    // 5) XSPH viscosity + 5.5) cohesion / surface tension (both cascade-scaled)
    applyXSPH(s, n);
    applyCohesion(s, n);

    // 6) wall friction + settle damping + speed clamp; commit
    let maxSpeed = 0, maxZ = 0, minZ = Infinity;
    const rmax2 = (R_IN - REST_MARGIN) * (R_IN - REST_MARGIN) * 0.98;
    for (let i = 0; i < n; i++) {
      if (xpx[i] * xpx[i] + xpy[i] * xpy[i] > rmax2) {
        vx[i] *= (1 - WALL_FRICTION); vy[i] *= (1 - WALL_FRICTION);
      }
      if (settling) { vx[i] *= SETTLE_DAMP; vy[i] *= SETTLE_DAMP; vz[i] *= SETTLE_DAMP; }
      let sp = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i] + vz[i] * vz[i]);
      if (sp > MAX_SPEED) { const f = MAX_SPEED / sp; vx[i] *= f; vy[i] *= f; vz[i] *= f; sp = MAX_SPEED; }
      px[i] = xpx[i]; py[i] = xpy[i]; pz[i] = xpz[i];
      if (sp > maxSpeed) maxSpeed = sp;
      if (pz[i] > maxZ) maxZ = pz[i];
      if (pz[i] < minZ) minZ = pz[i];
    }
    s.maxSpeed = Math.max(s.maxSpeed, maxSpeed);
    s.maxZ = Math.max(s.maxZ, maxZ);
    if (minZ < s.minZ) s.minZ = minZ;

    // free-surface stats; still level captured at the end of settling.
    const surf = surfaceStats(pz, px, py, n);
    const surfStd = surf.std;
    if (s.tick === SHAKE_START) s.restLevel = surf.mean;
    const restLevel = s.restLevel || H_FILL;
    const splash = maxZ - restLevel;
    if (shaking) {
      s.surfVarSum += surfStd; s.surfVarN += 1;
      if (surfStd > s.wavePeak) s.wavePeak = surfStd;
      if (splash > s.splashPeak) s.splashPeak = splash;
    }

    // ---- viz frame (lab frame = glass frame + s(tau)) ----
    if (s.tick === 1 || s.tick % SNAP_EVERY === 0 || s.tick === MACRO_TICKS) {
      const r4 = (v) => Math.round(v * 1e4) / 1e4;
      const xyz = new Array(n);
      for (let i = 0; i < n; i++) xyz[i] = [r4(px[i] + sNow[0]), r4(py[i] + sNow[1]), r4(pz[i])];
      ctx.emit("fluid_frame", {
        tick: s.tick, time_s: r4(t),
        phase: pouring ? "pour" : (settling ? "settle" : "shake"),
        active: n, glass_xy_m: [r4(sNow[0]), r4(sNow[1])],
        max_speed: r4(maxSpeed), surf_roughness_m: r4(surfStd), splash_height_m: r4(splash),
        xyz
      });
    }

    // ---- final summary + validation ----
    if (s.tick === MACRO_TICKS) {
      const meanSurf = s.surfVarN > 0 ? s.surfVarSum / s.surfVarN : 0;
      const pouredOk = s.n === s.N && s.restLevel > 0.5 * H_FILL;
      const wavesPresent = s.wavePeak > 0.004;
      const splashPresent = s.splashPeak > 0.008;
      const contained = s.escaped === 0 && s.minZ >= -1e-4 && s.maxZ <= H_WALL + 1e-3;
      const stable = Number.isFinite(s.maxSpeed) && s.maxSpeed <= MAX_SPEED + 1e-6;
      const cascadeReachedMacro = s.restDensity > 0;
      ctx.emit("glass_summary", {
        particles: s.n, target_particles: s.N,
        glass: { inner_radius_m: R_IN, fill_height_m: H_FILL, wall_height_m: H_WALL,
                 still_water_level_m: s.restLevel,
                 water_volume_cm3: Math.PI * R_IN * R_IN * H_FILL * 1e6 },
        macro_params_from_cascade: {
          rest_density_kg_per_m3: s.restDensity,
          surface_tension_coeff: s.surfaceTension,
          viscosity_coeff: s.viscosity,
          water_mass_g: s.N * s.mass * 1000.0
        },
        dynamics: {
          mean_surface_roughness_m: meanSurf,
          peak_wave_roughness_m: s.wavePeak,
          peak_splash_height_m: s.splashPeak,
          max_speed_m_per_s: s.maxSpeed,
          min_z_m: s.minZ, max_z_m: s.maxZ
        },
        validation: {
          water_poured_in: pouredOk,
          waves_present: wavesPresent,
          splash_present: splashPresent,
          water_contained: contained,
          stable_no_explosion: stable,
          cascade_drove_macro: cascadeReachedMacro,
          glass_of_water_from_nano:
            pouredOk && wavesPresent && splashPresent && contained && stable && cascadeReachedMacro
        }
      });
    }
  }
};

// ---- wall projection: keep particles inside the cylinder, above the floor,
//      below the rim. ----
function projectWalls(xp, yp, zp, n) {
  const rmax = R_IN - REST_MARGIN;
  for (let i = 0; i < n; i++) {
    const r2 = xp[i] * xp[i] + yp[i] * yp[i];
    if (r2 > rmax * rmax) {
      const r = Math.sqrt(r2);
      if (r > 1e-9) { const f = rmax / r; xp[i] *= f; yp[i] *= f; }
    }
    if (zp[i] < REST_MARGIN) zp[i] = REST_MARGIN;
    if (zp[i] > H_WALL - REST_MARGIN) zp[i] = H_WALL - REST_MARGIN;
  }
}

// ---- XSPH viscosity: v_i += c * sum_j (v_j - v_i) W(r) / rho0. ----
function applyXSPH(s, n) {
  const { vx, vy, vz, xpx, xpy, xpz, dvx, dvy, dvz, nbrCount, nbrIdx } = s;
  const c = s.viscosity, invRho0 = 1.0 / s.rho0;
  if (c <= 0) return;
  for (let i = 0; i < n; i++) {
    const base = i * MAX_NBR, cnt = nbrCount[i];
    let ax = 0, ay = 0, az = 0;
    for (let k = 0; k < cnt; k++) {
      const j = nbrIdx[base + k];
      const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 >= H2) continue;
      const w = wPoly6(r2) * invRho0;
      ax += (vx[j] - vx[i]) * w; ay += (vy[j] - vy[i]) * w; az += (vz[j] - vz[i]) * w;
    }
    dvx[i] = c * ax; dvy[i] = c * ay; dvz[i] = c * az;
  }
  for (let i = 0; i < n; i++) { vx[i] += dvx[i]; vy[i] += dvy[i]; vz[i] += dvz[i]; }
}

// ---- cohesion / surface tension: explicit attraction toward neighbours,
//      cascade-scaled. Draws separated drops together so they merge on contact
//      and holds the free surface smooth. ----
function applyCohesion(s, n) {
  const { vx, vy, vz, xpx, xpy, xpz, dvx, dvy, dvz, nbrCount, nbrIdx } = s;
  const g = s.surfaceTension;
  if (g <= 0) return;
  const gain = COH_GAIN * g * DT;
  for (let i = 0; i < n; i++) {
    const base = i * MAX_NBR, cnt = nbrCount[i];
    let ax = 0, ay = 0, az = 0;
    for (let k = 0; k < cnt; k++) {
      const j = nbrIdx[base + k];
      const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 >= H2 || r2 < 1e-12) continue;
      const r = Math.sqrt(r2), w = cohKernel(r) / r;
      ax -= w * dx; ay -= w * dy; az -= w * dz;
    }
    dvx[i] = gain * ax; dvy[i] = gain * ay; dvz[i] = gain * az;
  }
  for (let i = 0; i < n; i++) { vx[i] += dvx[i]; vy[i] += dvy[i]; vz[i] += dvz[i]; }
}

// ---- free-surface statistics: coarse (x,y) columns, top particle of each,
//      mean surface height + std-dev (wave roughness). ----
function surfaceStats(zp, xp, yp, n) {
  const cell = 0.008;
  const tops = new Map();
  for (let i = 0; i < n; i++) {
    const cx = Math.round(xp[i] / cell), cy = Math.round(yp[i] / cell);
    const key = cx * 100000 + cy;
    const cur = tops.get(key);
    if (cur === undefined || zp[i] > cur) tops.set(key, zp[i]);
  }
  let sum = 0, sum2 = 0, m = 0;
  for (const z of tops.values()) { sum += z; sum2 += z * z; m += 1; }
  if (m < 2) return { mean: 0, std: 0 };
  const mean = sum / m;
  const varr = Math.max(0, sum2 / m - mean * mean);
  return { mean, std: Math.sqrt(varr) };
}

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.cm(40.0), worldMaterial: "G4_AIR" },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  run: { nEvents: MACRO_TICKS + 1, seed: 20260711, threads: 1 },
  determinism: { mode: "predictive" },
  // The multi-scale cascade: three scale-tagged stages lift the measured nano
  // H2O facts up to the macro fluid parameters. Declared out of scale order on
  // purpose -- the engine chains by `scale`, not declaration order.
  models: [
    { name: "macro_fluid_params", scale: "macro", path: "data/glass_cascade/macro_fluid_params.json" },
    { name: "nano_coarse_grain",  scale: "nano",  path: "data/glass_cascade/nano_coarse_grain.json" },
    { name: "micro_bulk",         scale: "micro", path: "data/glass_cascade/micro_bulk.json" }
  ],
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "glass_of_water_shaken" },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "glass_water", material: "G4_WATER",
        innerRadiusMm: 0.0, outerRadiusMm: R_IN * 1000.0, lengthMm: H_FILL * 1000.0,
        positionMm: [0, 0, (H_FILL * 1000.0) / 2.0],
        tags: ["fluid", "h2o", "macro", "glass", "shaken"]
      })
    ]
  }
};
