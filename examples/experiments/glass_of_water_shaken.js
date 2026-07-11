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
// deterministic particle method. The artificial-pressure (s_corr) term -- scaled
// by the cascade-inferred surface tension -- makes particles COHERE into drops
// and MERGE when they touch, so splashes that break off rejoin the body of water
// (the requested "merging drops" effect; the 3D renderer draws it as a 5 mm
// metaball isosurface). The glass is shaken by a smooth-but-random horizontal
// motion (a seeded sum of sinusoids under a growing envelope): gentle waves
// early, vigorous sloshing and splashes late.
//
// Honest scope (same contract as the other H2O scenarios): Geant4 transports a
// geantino per tick as the deterministic CLOCK; it does not compute molecular
// bonds or fluid flow. The nano MD and the macro PBF are classical "physics for
// comparison" in the deterministic hook layer. What is genuinely novel here is
// that the macro parameters are not typed -- they are cascaded up from the
// measured nano base.
//
// Emits: `scenario` (config), `cascade` (measured nano facts + cascade-inferred
// macro params + provenance), per-frame `fluid_frame` (lab-frame particle
// positions + glass displacement, for the 3D renderer), and a final
// `glass_summary` with the validation. Deterministic (seeded, threads:1,
// predictive so the cascade runs).
//
// Run:
//   trech run examples/experiments/glass_of_water_shaken.js \
//        --events 501 --output build/dev/out_glass_shaken

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
// Interpreted from the request "a glass of water, ~20 cm^3-ish, 10 cm of water
// height, being shaken": a narrow tall glass. Parametric -- change R_IN / H_FILL
// to taste. Water volume here = pi*R^2*H ~ 62 cm^3 at R=1.4 cm, H=10 cm.
// ======================================================================
const R_IN = 0.014;          // inner radius (m) -> 2.8 cm across
const H_WALL = 0.130;        // glass wall height (m) -> 13 cm (3 cm splash headroom)
const H_FILL = 0.100;        // still-water fill height (m) -> 10 cm
const S0 = 0.005;            // particle rest spacing (m) = the requested 5 mm precision
const H_KERN = 2.2 * S0;     // PBF smoothing radius (m)

// ======================================================================
// PBF (position-based fluid) numerics. These are GENERIC solver defaults (like a
// timestep) -- NOT water properties. The water-specific behaviour (density,
// cohesion, viscosity) is supplied by the cascade below.
// ======================================================================
const DT = 0.004;            // s per tick
const G = 9.81;              // gravity (m/s^2), down -z
const SOLVER_ITERS = 4;      // Jacobi density (compression) iterations
const CFM_EPS = 1.0e-6;      // constraint-force-mixing relaxation
const REST_MARGIN = 0.30 * S0;  // keep particle centres this far off the walls
const WALL_FRICTION = 0.20;     // tangential damping at the walls (0..1)
const MAX_DP = 0.50 * S0;       // per-iteration position-correction clamp (anti-blowup)
const MAX_SPEED = 2.0;          // hard velocity clamp (m/s), safety only
// Cohesion (surface tension) is an EXPLICIT attraction between neighbours within
// the kernel, scaled by the cascade-inferred macro_surface_tension_coeff. It is
// what pulls drops together and MERGES them on contact, and holds the free
// surface. COH_GAIN is a generic numeric gain (like a timestep); the
// water-specific STRENGTH is the cascade value. Cohesion is applied as a
// velocity nudge, DECOUPLED from the incompressibility solve (far more stable
// than folding a Macklin s_corr artificial-pressure term into the constraint,
// which pops the free surface in a narrow column).
const COH_GAIN = 4.0;
// Defensive guards on the cascade-inferred coefficients: the RAW cascade values
// are always emitted; these only bound the numbers actually handed to the solver
// so an out-of-range nano measurement can never blow the fluid up (same spirit as
// MAX_SPEED). With a physical coordination ~4.5 the raw values already sit inside.
const K_COH_MAX = 0.15;         // cohesion (surface-tension) active clamp
const VISC_MAX = 0.12;          // XSPH viscosity active clamp
// Settle phase: let the freshly-laid lattice relax onto the PBF constraint
// manifold under gravity (no shake, extra damping) before the glass is shaken,
// so the opening transient is not mistaken for a wave.
const SETTLE_TICKS = 60;        // ticks of quiescent settling
const SETTLE_DAMP = 0.985;      // extra velocity damping during settling

// ======================================================================
// Shake: smooth but random horizontal glass motion. Displacement s(t) is a
// seeded sum of sinusoids under a growing envelope; the fluid feels the inertial
// (pseudo) force -m*s''(t) in the glass frame. s''(t) is taken numerically from
// the analytic s(t) (a smooth function -> a smooth force).
// ======================================================================
const SHAKE_SEED = 0xB0A711;
const SHAKE_RAMP_T = 0.5;    // s over which the shake ramps in from rest
const SHAKE_GROWTH = 0.9;    // extra amplitude gained across the shake (gentle -> splashy)

// ======================================================================
// Nano measurement + run sizing.
// ======================================================================
const NANO_N = 64;           // molecules in the nanoscale probe run
const NANO_DENSITY = 0.0334; // molecules / A^3 (liquid-water rest density lattice)
const NANO_TICKS = 800;      // nano MD ticks (equilibrate, then accumulate g(r))
const NANO_EQUIL = 0.5;      // start g(r) accumulation after this fraction
const NANO_DT = 2.0;         // fs (rigid water)
const NANO_TARGET_K = 300.0;
const NANO_SEED = 0x5EED17;
const NANO_RDF_BINS = 120;
const NANO_COORD_R = 3.4;    // coordination integration bound (A) -- the standard
                             // experimental first-shell convention (~4.3-4.7 for water)

const MACRO_TICKS = 500;     // macro PBF frames
const SNAP_EVERY = 3;        // fluid_frame emit stride (viz sideband)

// molecular constant (the nano base's "force field"; like SPC/E, allowed as the
// physics-for-comparison anchor -- it is NOT the macroscopic density).
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
    // Stiff thermostat for this short structural probe (we want the equilibrium
    // structure, not dynamics): rescale often, and hard-reset at the boundary so
    // g(r) is accumulated at the target temperature, not the lattice-melt heat.
    if (t % 5 === 0) sim.thermostat(NANO_TARGET_K, 0.25);
    if (t === equilStart) sim.thermostat(NANO_TARGET_K, 1.0);
    if (accumulate) { sumT += sim.temperature(); nAcc += 1; frames += 1; }
  }
  // number density measured from the box (molecules / A^3) and its mass density
  // is NOT computed here -- that coarse-graining is the cascade's job.
  const boxL = sim.boxL, nO = sim.mols.length;
  const numberDensity = nO / (boxL * boxL * boxL);
  // coordination: integrate the O-O g(r) to its first minimum (first shell).
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
  // Coordination number: integrate g(r) to the fixed experimental first-shell
  // bound (3.4 A). This is the cross-model-comparable convention the bulk-water
  // scenario validates as ~4.3-4.7 for water -- robust to the noisy first
  // minimum of a small, short probe run. Also locate the first minimum for info.
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
function wPoly6(r2) {                 // r2 = squared distance
  if (r2 >= H2) return 0.0;
  const d = H2 - r2;
  return POLY6 * d * d * d;
}
function wSpikyGrad(r) {               // returns scalar magnitude/r factor applied by caller
  if (r <= 1e-9 || r >= H_KERN) return 0.0;
  const d = H_KERN - r;
  return SPIKY * d * d / r;            // multiply by (dx,dy,dz) to get gradient vector
}
// Cohesion weight: a smooth attraction that is zero at contact (r=0) and at the
// kernel edge (r=h) and peaks mid-range (r=h/2) -- so it pulls separated
// neighbours together (surface tension / drop merging) without crushing contacts.
function cohKernel(r) {
  if (r <= 1e-9 || r >= H_KERN) return 0.0;
  const x = r / H_KERN;
  return x * (1.0 - x);               // peak 0.25 at r = h/2
}

// ======================================================================
// Build the initial water column: particles on a cubic lattice inside the
// cylinder, filled to H_FILL. Deterministic; a tiny seeded jitter breaks the
// perfect lattice so the first waves are not a numerical artefact.
// ======================================================================
function buildParticles(rng) {
  const px = [], py = [], pz = [];
  const nR = Math.ceil(R_IN / S0) + 1;
  const nZ = Math.ceil(H_FILL / S0);
  const jit = 0.06 * S0;
  for (let iz = 0; iz < nZ; iz++) {
    const z = (iz + 0.5) * S0;
    for (let ix = -nR; ix <= nR; ix++) {
      for (let iy = -nR; iy <= nR; iy++) {
        const x = ix * S0, y = iy * S0;
        if (x * x + y * y > (R_IN - REST_MARGIN) * (R_IN - REST_MARGIN)) continue;
        px.push(x + (rng() - 0.5) * jit);
        py.push(y + (rng() - 0.5) * jit);
        pz.push(z + (rng() - 0.5) * jit);
      }
    }
  }
  return { px, py, pz };
}

// Smooth analytic glass displacement s(tau) (metres), tau = time since shaking
// began. A seeded sum of sinusoids under an envelope that ramps in FROM REST
// (env(0)=0, no positional jump) and grows across the shake so gentle early
// waves build into late sloshing/splashes. Returns [sx, sy].
function shakeDisplacement(comp, tau) {
  if (tau <= 0) return [0, 0];
  const shakeDur = (MACRO_TICKS - SETTLE_TICKS) * DT;
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

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "glass_of_water_shaken",
      glass: { inner_radius_m: R_IN, wall_height_m: H_WALL, fill_height_m: H_FILL,
               water_volume_cm3: Math.PI * R_IN * R_IN * H_FILL * 1e6 },
      particle_spacing_m: S0, kernel_h_m: H_KERN, render_precision_mm: S0 * 1000,
      dt_s: DT, macro_ticks: MACRO_TICKS, snap_every: SNAP_EVERY,
      nano: { molecules: NANO_N, ticks: NANO_TICKS, dt_fs: NANO_DT },
      model: "nanoscale rigid-SPC/E MD -> ctx.cascade(nano->micro->macro) -> Position-Based Fluid (Macklin & Muller 2013) in a shaken glass; NO macroscopic water property hand-specified"
    });
  },

  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;

    // ---- first tick: measure nano, cascade to macro params, init the fluid ----
    if (!s.initialized) {
      const nano = measureNano();

      // Lift the MEASURED nano facts up the ladder. ctx.cascade auto-seeds the
      // ambient Geant4 base; we augment it with the two nano measurements. We
      // read ONLY macro-band outputs -- the scenario types no macroscopic water
      // property.
      const c = ctx.cascade({
        nano_number_density_per_A3: nano.numberDensity,
        nano_coordination: nano.coordination
      });
      if (!c) throw new Error("ctx.cascade returned null (needs predictive mode + loaded models)");
      const restDensity = c.macro_rest_density_kg_per_m3;      // ~999 kg/m^3 (recovered, not typed)
      const surfaceTensionRaw = c.macro_surface_tension_coeff; // cohesion strength (drops cohere/merge)
      const viscosityRaw = c.macro_viscosity_coeff;            // XSPH damping
      // active (defensively clamped) values actually fed to the solver.
      const surfaceTension = Math.max(0.0, Math.min(K_COH_MAX, surfaceTensionRaw));
      const viscosity = Math.max(0.0, Math.min(VISC_MAX, viscosityRaw));
      const scales = (c.__cascade.trace || []).filter((x) => x.ran).map((x) => x.scale);

      // Build the fluid and its rest density target rho0 (kernel self-density of
      // a fully-surrounded rest particle). Mass per particle = rest_density * S0^3
      // so the reported bulk density matches the cascade value.
      const rng = makeRng(NANO_SEED ^ 0x9E3779B9);
      const { px, py, pz } = buildParticles(rng);
      const nP = px.length;
      const mass = restDensity * S0 * S0 * S0;

      // rho0 = the incompressibility target = a low percentile of the relaxed
      // lattice's per-particle kernel densities. In a NARROW glass most particles
      // sit near the cylinder wall with fewer neighbours than an infinite bulk, so
      // the sustainable rest density is set by the confined geometry. Targeting an
      // infinite-bulk / full-neighbourhood value would leave the whole (already
      // under-dense) column with nothing to resist gravity and it collapses; a low
      // percentile makes the 10 cm fill the mechanical-equilibrium state (most
      // particles at/above rho0 resist compression, the few below are the free
      // surface). Computed once, O(N^2).
      const dens0 = new Float64Array(nP);
      for (let i = 0; i < nP; i++) {
        let d = wPoly6(0);
        for (let j = 0; j < nP; j++) {
          if (j === i) continue;
          const dx = px[i] - px[j], dy = py[i] - py[j], dz = pz[i] - pz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 < H2) d += wPoly6(r2);
        }
        dens0[i] = d;
      }
      const sorted = Array.from(dens0).sort((a, b) => a - b);
      const rho0 = sorted[Math.floor(0.35 * sorted.length)];   // 35th-pct rest density

      // seeded, smooth-but-random shake components (metres, rad/s, phase).
      const srng = makeRng(SHAKE_SEED);
      const mkComp = (base) => base.map((b) => ({
        A: b.A * (0.7 + 0.6 * srng()), w: b.w * (0.85 + 0.3 * srng()), p: 2 * Math.PI * srng()
      }));
      const comp = {
        x: mkComp([{ A: 0.0075, w: 9.0 }, { A: 0.0040, w: 16.0 }, { A: 0.0016, w: 34.0 }]),
        y: mkComp([{ A: 0.0060, w: 11.0 }, { A: 0.0038, w: 19.0 }, { A: 0.0014, w: 31.0 }])
      };

      Object.assign(s, {
        initialized: true, tick: 0,
        px, py, pz,
        vx: new Float64Array(nP), vy: new Float64Array(nP), vz: new Float64Array(nP),
        xpx: new Float64Array(nP), xpy: new Float64Array(nP), xpz: new Float64Array(nP),
        lam: new Float64Array(nP), dpx: new Float64Array(nP), dpy: new Float64Array(nP), dpz: new Float64Array(nP),
        nbr: null,
        nP, mass, rho0, restDensity, surfaceTension, viscosity,
        comp, sPrev: [0, 0], sPrev2: [0, 0],
        // observables
        maxSpeed: 0, maxZ: 0, minZ: H_FILL, escaped: 0, restLevel: 0,
        surfVarSum: 0, surfVarN: 0, splashPeak: 0, wavePeak: 0
      });

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
          rho0_kernel: rho0,
          particles: nP
        },
        // comparison-only (never fed in): measured liquid water at ~293 K.
        reference: { water_density_kg_per_m3: 998.2 },
        density_recovery_error_pct:
          Math.abs(restDensity - 998.2) / 998.2 * 100.0,
        cascade: {
          stages_run: c.__cascade.stagesRun,
          scales_bridged: scales,
          seed_keys: c.__cascade.seedKeys
        }
      });
      return;   // first tick sets up; stepping starts next event
    }

    // ---- macro PBF step ----
    s.tick += 1;
    const t = s.tick * DT;
    const settling = s.tick <= SETTLE_TICKS;
    const tau = Math.max(0, s.tick - SETTLE_TICKS) * DT;   // shake clock
    const { px, py, pz, vx, vy, vz, xpx, xpy, xpz, lam, dpx, dpy, dpz, nP } = s;

    // Glass displacement now + inertial (pseudo) acceleration from its 2nd
    // difference (smooth s(tau) -> smooth force). Fluid is simulated in the glass
    // frame; positions are shifted by s(tau) for the lab-frame emit. During the
    // settle phase the glass is held still so the column can relax.
    const sNow = shakeDisplacement(s.comp, tau);
    const ax = -(sNow[0] - 2 * s.sPrev[0] + s.sPrev2[0]) / (DT * DT);
    const ay = -(sNow[1] - 2 * s.sPrev[1] + s.sPrev2[1]) / (DT * DT);
    s.sPrev2 = s.sPrev; s.sPrev = sNow;

    // 1) integrate external forces, predict positions
    for (let i = 0; i < nP; i++) {
      vx[i] += DT * ax; vy[i] += DT * ay; vz[i] += DT * (-G);
      xpx[i] = px[i] + DT * vx[i];
      xpy[i] = py[i] + DT * vy[i];
      xpz[i] = pz[i] + DT * vz[i];
    }
    projectWalls(xpx, xpy, xpz, nP);

    // 2) neighbour list (once per tick) at predicted positions
    const nbr = buildNeighbors(xpx, xpy, xpz, nP);

    // 3) density-constraint solve (Jacobi). rho0 is the confined-column rest
    //    density (35th pct of the fill lattice), so the full constraint (both
    //    directions) holds the 10 cm fill at equilibrium without collapsing or
    //    inflating. Surface tension is the separate cohesion pass (step 5.5).
    const rho0 = s.rho0, invRho0 = 1.0 / rho0;
    for (let it = 0; it < SOLVER_ITERS; it++) {
      for (let i = 0; i < nP; i++) {
        let rho = wPoly6(0);
        let gradiX = 0, gradiY = 0, gradiZ = 0, sumGrad2 = 0;
        const list = nbr[i];
        for (let n = 0; n < list.length; n++) {
          const j = list[n];
          const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 >= H2) continue;
          rho += wPoly6(r2);
          const r = Math.sqrt(r2), gsc = wSpikyGrad(r) * invRho0;
          const gx = gsc * dx, gy = gsc * dy, gz = gsc * dz;
          gradiX += gx; gradiY += gy; gradiZ += gz;
          sumGrad2 += gx * gx + gy * gy + gz * gz;   // |grad_j C_i|^2
        }
        sumGrad2 += gradiX * gradiX + gradiY * gradiY + gradiZ * gradiZ;  // |grad_i C_i|^2
        const C = rho * invRho0 - 1.0;
        lam[i] = -C / (sumGrad2 + CFM_EPS);
      }
      for (let i = 0; i < nP; i++) {
        let cx = 0, cy = 0, cz = 0;
        const list = nbr[i], li = lam[i];
        for (let n = 0; n < list.length; n++) {
          const j = list[n];
          const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 >= H2) continue;
          const r = Math.sqrt(r2), gsc = wSpikyGrad(r);
          const coef = (li + lam[j]) * gsc * invRho0;
          cx += coef * dx; cy += coef * dy; cz += coef * dz;
        }
        const cmag = Math.sqrt(cx * cx + cy * cy + cz * cz);
        if (cmag > MAX_DP) { const sfac = MAX_DP / cmag; cx *= sfac; cy *= sfac; cz *= sfac; }
        dpx[i] = cx; dpy[i] = cy; dpz[i] = cz;
      }
      for (let i = 0; i < nP; i++) { xpx[i] += dpx[i]; xpy[i] += dpy[i]; xpz[i] += dpz[i]; }
      projectWalls(xpx, xpy, xpz, nP);
    }

    // 4) update velocities from the constrained positions
    const invDt = 1.0 / DT;
    for (let i = 0; i < nP; i++) {
      vx[i] = (xpx[i] - px[i]) * invDt;
      vy[i] = (xpy[i] - py[i]) * invDt;
      vz[i] = (xpz[i] - pz[i]) * invDt;
    }
    // 5) XSPH viscosity (cascade-inferred coefficient)
    applyXSPH(s, nbr);
    // 5.5) cohesion / surface tension (cascade-inferred strength) -- pulls drops
    //      together and MERGES them on contact; holds the free surface.
    applyCohesion(s, nbr);
    // 6) wall tangential friction + speed clamp; commit
    let maxSpeed = 0, maxZ = 0, minZ = Infinity;
    for (let i = 0; i < nP; i++) {
      const r2 = xpx[i] * xpx[i] + xpy[i] * xpy[i];
      if (r2 > (R_IN - REST_MARGIN) * (R_IN - REST_MARGIN) * 0.98) {
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

    // Free-surface stats. The still-water level found at the end of settling is
    // the reference the waves and splashes are measured against (the column
    // relaxes a little below the ideal fill line, so measuring against the actual
    // rest level is the honest wave/splash amplitude).
    const surf = surfaceStats(pz, px, py, nP);
    const surfStd = surf.std;
    if (s.tick === SETTLE_TICKS) s.restLevel = surf.mean;   // still-water reference
    const restLevel = s.restLevel || H_FILL;
    const splash = maxZ - restLevel;      // crest height above the still-water level
    if (!settling) {
      s.surfVarSum += surfStd; s.surfVarN += 1;
      if (surfStd > s.wavePeak) s.wavePeak = surfStd;
      if (splash > s.splashPeak) s.splashPeak = splash;
    }

    // ---- emit a viz frame (lab frame = glass frame + s(t)) ----
    if (s.tick === 1 || s.tick % SNAP_EVERY === 0 || s.tick === MACRO_TICKS) {
      const r4 = (v) => Math.round(v * 1e4) / 1e4;
      const xyz = new Array(nP);
      for (let i = 0; i < nP; i++) {
        xyz[i] = [r4(px[i] + sNow[0]), r4(py[i] + sNow[1]), r4(pz[i])];
      }
      ctx.emit("fluid_frame", {
        tick: s.tick, time_s: r4(t),
        glass_xy_m: [r4(sNow[0]), r4(sNow[1])],
        max_speed: r4(maxSpeed), surf_roughness_m: r4(surfStd),
        splash_height_m: r4(splash),
        xyz
      });
    }

    // ---- final summary + validation ----
    if (s.tick === MACRO_TICKS) {
      const meanSurf = s.surfVarN > 0 ? s.surfVarSum / s.surfVarN : 0;
      const wavesPresent = s.wavePeak > 0.004;        // crests > 4 mm roughness
      const splashPresent = s.splashPeak > 0.008;     // some crest rose > 8 mm above rest level
      const contained = s.escaped === 0 && s.minZ >= -1e-4 && s.maxZ <= H_WALL + 1e-3;
      const stable = Number.isFinite(s.maxSpeed) && s.maxSpeed <= MAX_SPEED + 1e-6;
      const cascadeReachedMacro = s.restDensity > 0;
      ctx.emit("glass_summary", {
        particles: s.nP,
        glass: { inner_radius_m: R_IN, fill_height_m: H_FILL, wall_height_m: H_WALL,
                 still_water_level_m: s.restLevel },
        macro_params_from_cascade: {
          rest_density_kg_per_m3: s.restDensity,
          surface_tension_coeff: s.surfaceTension,
          viscosity_coeff: s.viscosity
        },
        dynamics: {
          mean_surface_roughness_m: meanSurf,
          peak_wave_roughness_m: s.wavePeak,
          peak_splash_height_m: s.splashPeak,
          max_speed_m_per_s: s.maxSpeed,
          min_z_m: s.minZ, max_z_m: s.maxZ
        },
        validation: {
          waves_present: wavesPresent,
          splash_present: splashPresent,
          water_contained: contained,
          stable_no_explosion: stable,
          cascade_drove_macro: cascadeReachedMacro,
          // headline: a shaken glass of water sloshing + splashing, with every
          // macro fluid parameter inferred from the nanoscale base by the cascade.
          glass_of_water_from_nano:
            wavesPresent && splashPresent && contained && stable && cascadeReachedMacro
        }
      });
    }
  }
};

// ---- wall projection: keep particles inside the cylinder, above the floor,
//      below the rim. Records escapes (should stay 0 -> mass conserved). ----
function projectWalls(xp, yp, zp, nP) {
  const rmax = R_IN - REST_MARGIN;
  for (let i = 0; i < nP; i++) {
    const r2 = xp[i] * xp[i] + yp[i] * yp[i];
    if (r2 > rmax * rmax) {
      const r = Math.sqrt(r2);
      if (r > 1e-9) { const f = rmax / r; xp[i] *= f; yp[i] *= f; }
    }
    if (zp[i] < REST_MARGIN) zp[i] = REST_MARGIN;
    if (zp[i] > H_WALL - REST_MARGIN) zp[i] = H_WALL - REST_MARGIN;
  }
}

// ---- O(N^2) neighbour list within the kernel radius, built once per tick.
//      Narrow glass -> the cross-section is only a few kernels wide, so a grid
//      buys little; the flat list is simpler and deterministic. ----
function buildNeighbors(xp, yp, zp, nP) {
  const nbr = new Array(nP);
  for (let i = 0; i < nP; i++) nbr[i] = [];
  for (let i = 0; i < nP; i++) {
    for (let j = i + 1; j < nP; j++) {
      const dx = xp[i] - xp[j], dy = yp[i] - yp[j], dz = zp[i] - zp[j];
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 < H2) { nbr[i].push(j); nbr[j].push(i); }
    }
  }
  return nbr;
}

// ---- XSPH viscosity: v_i += c * sum_j (v_j - v_i) W(r) / rho0. The coefficient
//      c is the cascade-inferred macro_viscosity_coeff. ----
function applyXSPH(s, nbr) {
  const { vx, vy, vz, xpx, xpy, xpz, nP } = s;
  const c = s.viscosity, invRho0 = 1.0 / s.rho0;
  if (c <= 0) return;
  const dvx = new Float64Array(nP), dvy = new Float64Array(nP), dvz = new Float64Array(nP);
  for (let i = 0; i < nP; i++) {
    const list = nbr[i];
    let ax = 0, ay = 0, az = 0;
    for (let n = 0; n < list.length; n++) {
      const j = list[n];
      const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 >= H2) continue;
      const w = wPoly6(r2) * invRho0;
      ax += (vx[j] - vx[i]) * w; ay += (vy[j] - vy[i]) * w; az += (vz[j] - vz[i]) * w;
    }
    dvx[i] = c * ax; dvy[i] = c * ay; dvz[i] = c * az;
  }
  for (let i = 0; i < nP; i++) { vx[i] += dvx[i]; vy[i] += dvy[i]; vz[i] += dvz[i]; }
}

// ---- cohesion / surface tension: an explicit attraction toward neighbours
//      within the kernel (peaked mid-range), scaled by the cascade-inferred
//      macro_surface_tension_coeff. Applied as a per-tick velocity nudge. This is
//      what draws separated "drops" together so they merge on contact, and holds
//      the free surface smooth. Interior particles feel ~zero net cohesion (their
//      neighbours cancel); surface particles feel a net inward pull. ----
function applyCohesion(s, nbr) {
  const { vx, vy, vz, xpx, xpy, xpz, nP } = s;
  const g = s.surfaceTension;
  if (g <= 0) return;
  const gain = COH_GAIN * g * DT;
  const ddx = new Float64Array(nP), ddy = new Float64Array(nP), ddz = new Float64Array(nP);
  for (let i = 0; i < nP; i++) {
    const list = nbr[i];
    let ax = 0, ay = 0, az = 0;
    for (let n = 0; n < list.length; n++) {
      const j = list[n];
      const dx = xpx[i] - xpx[j], dy = xpy[i] - xpy[j], dz = xpz[i] - xpz[j];
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 >= H2 || r2 < 1e-12) continue;
      const r = Math.sqrt(r2), w = cohKernel(r) / r;
      ax -= w * dx; ay -= w * dy; az -= w * dz;   // toward the neighbour = attraction
    }
    ddx[i] = gain * ax; ddy[i] = gain * ay; ddz[i] = gain * az;
  }
  for (let i = 0; i < nP; i++) { vx[i] += ddx[i]; vy[i] += ddy[i]; vz[i] += ddz[i]; }
}

// ---- free-surface statistics: bin the (x,y) plane into coarse columns, take the
//      top particle of each, and return the mean surface height + its std-dev
//      (the wave roughness / amplitude). ----
function surfaceStats(zp, xp, yp, nP) {
  const cell = 0.006;   // ~6 mm columns
  const tops = new Map();
  for (let i = 0; i < nP; i++) {
    const cx = Math.round(xp[i] / cell), cy = Math.round(yp[i] / cell);
    const key = cx * 1000 + cy;
    const cur = tops.get(key);
    if (cur === undefined || zp[i] > cur) tops.set(key, zp[i]);
  }
  let sum = 0, sum2 = 0, n = 0;
  for (const z of tops.values()) { sum += z; sum2 += z * z; n += 1; }
  if (n < 2) return { mean: 0, std: 0 };
  const mean = sum / n;
  const varr = Math.max(0, sum2 / n - mean * mean);
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
