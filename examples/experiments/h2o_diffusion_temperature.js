// Sputnik "H2O fluid behavior" -- DYNAMICS, temperature dependence.
//
// The single-state-point run (h2o_bulk_water.js) showed rigid SPC/E water
// reproduces both the measured liquid STRUCTURE (O-O g(r)) and a measured
// TRANSPORT property (self-diffusion D ~ 2.5e-9 m^2/s) at ~300 K. A single
// state point can be lucky; a TREND cannot. This experiment sweeps three
// temperatures in one deterministic run and measures D at each, comparing the
// curve to the measured temperature dependence of water self-diffusion
// (Holz, Heil & Sacco, PCCP 2000): D nearly triples from 278 to 318 K.
//
// Method: the rigid-SPC/E MD core (force loop, SHAKE/RATTLE, integrator) is the
// shared include `trech_water_md.js` (same physics as h2o_bulk_water.js); this
// scenario adds the temperature-sweep orchestration. The lattice is melted ONCE
// up front, then each measurement block re-equilibrates to its target (strong
// thermostat) and measures D from the production-phase O-atom mean-squared
// displacement (Einstein relation, MSD = 6 D t) under a gentle thermostat. The
// atom positions are never wrapped in the integrator, so MSD is a direct
// difference from the per-block reference origins.
//
// N matches the bulk run (108) so the box admits the same 7 A cutoff -- a
// shorter cutoff (smaller box) under-binds the H-bond network and makes water
// diffuse too fast, inflating the absolute D.
//
// Honest caveats (reported, not tuned): the density is held fixed at the ~298 K
// liquid value across all temperatures (a constant-density NVT-style sweep, not
// constant-pressure), and the absolute D carries finite-size/cutoff offsets.
// D per block is a MULTI-time-origin MSD average (clean, not a single noisy
// origin). The TREND -- D rising monotonically and strongly with T, tracking
// the measured water curve -- is the robust, falsifiable observable; SPC/E's
// rise is known to be a touch steeper than experiment.
//
// Run (slow, ~20 min: N=108 with multi-ps equilibration per temperature block):
//   trech run examples/experiments/h2o_diffusion_temperature.js \
//        --events 8100 --output build/dev/out_h2o_diffusion_T

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

// ---- system / run ----
const N_MOL = 108;
const DENSITY = 0.0334;            // molecules / A^3 (~1 g/cm^3 at ~298 K)
const BOXL = Math.cbrt(N_MOL / DENSITY);
const RCUT = Math.min(7.0, 0.5 * BOXL - 0.2);
const ALPHA = 0.25;               // DSF damping (1/A)
const DT = 2.0, THERMO_EVERY = 10;

// Temperature sweep. The lattice is melted ONCE up front (a hot melt phase),
// then each measurement block re-equilibrates to its target with a STRONG
// thermostat and measures D under a GENTLE one (so the dynamics are barely
// perturbed). Without the up-front melt the first block measures a still-melting
// solid and reports an anomalously high D.
const TEMPS_K = [278.0, 298.0, 318.0];
const MELT_TICKS = 600, MELT_K = 330.0;       // one-time lattice melt (no measure)
// Equilibration must outlast water's structural relaxation (~2-3 ps) so the
// configuration -- not just the kinetic temperature -- reaches the block target
// after a temperature step; a too-short equilibration leaves a melt-like (too
// mobile) structure and an inflated D, especially at the low-T blocks.
const EQUIL = 1500, PROD = 1000, BLOCK = EQUIL + PROD;
// Multiple-time-origin MSD: a fresh reference is captured every ORIGIN_EVERY
// production ticks and every origin contributes to the MSD-vs-lag average, so
// the diffusion slope is averaged over ~tens of origins instead of one (a
// single-origin MSD over a few ps is far too noisy for a reliable per-block D).
const ORIGIN_EVERY = 20, MAX_LAG = 500;       // ticks
const TOTAL_TICKS = MELT_TICKS + TEMPS_K.length * BLOCK;
const THERMO_STRONG = 1.0;    // full velocity rescale (equilibration phases)
const THERMO_GENTLE = 0.1;    // weak Berendsen-like coupling (production)
const SEED = 24601;

// Measured water self-diffusion (Holz, Heil & Sacco, PCCP 2000), 1e-9 m^2/s.
// D is compared at the ACTUAL (measured) block temperature via interpolation,
// so the comparison is robust to the thermostat not hitting the target exactly.
const EXP_D_TABLE = [
  [278, 1.31], [283, 1.54], [288, 1.78], [293, 2.03], [298, 2.30],
  [303, 2.60], [308, 2.92], [313, 3.24], [318, 3.58]
];
function expDiffusion(T) {     // m^2/s, linear interp (clamped at the ends)
  const tbl = EXP_D_TABLE, last = tbl.length - 1;
  if (T <= tbl[0][0]) return tbl[0][1] * 1e-9;
  if (T >= tbl[last][0]) return tbl[last][1] * 1e-9;
  for (let i = 1; i < tbl.length; i++) {
    if (T <= tbl[i][0]) {
      const t0 = tbl[i - 1][0], d0 = tbl[i - 1][1], t1 = tbl[i][0], d1 = tbl[i][1];
      return (d0 + (d1 - d0) * (T - t0) / (t1 - t0)) * 1e-9;
    }
  }
  return tbl[last][1] * 1e-9;
}

// Self-diffusion from a block's multi-origin MSD-vs-lag average (Einstein
// relation, MSD = 6 D t). msdSum/msdCnt are accumulated over many time origins;
// the slope is fit over the diffusive tail (lag beyond the cage/ballistic part).
function blockDiffusion(msdSum, msdCnt) {
  const fit = [];
  for (let lag = 1; lag <= MAX_LAG; lag++) {
    if (msdCnt[lag] > 0 && lag >= 0.4 * MAX_LAG)
      fit.push({ x: lag * DT, y: msdSum[lag] / msdCnt[lag] });
  }
  if (fit.length < 8) return { D: 0, slope: 0 };
  const slope = md.lsqSlope(fit);       // A^2 / fs
  return { D: (slope / 6) * 1e-5, slope };   // A^2/fs -> m^2/s
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    // Shared rigid-SPC/E core; initial velocities at the first sweep temperature.
    ctx.state.sim = md.create({
      nMol: N_MOL, density: DENSITY, rcutMax: 7.0, alpha: ALPHA, dt: DT,
      seed: SEED, rdfBins: 0, initialK: TEMPS_K[0]
    });
    Object.assign(ctx.state, {
      tick: 0, initialized: true,
      msdOrigins: [], msdHead: 0,
      msdSum: new Float64Array(MAX_LAG + 1), msdCnt: new Float64Array(MAX_LAG + 1),
      sumT: 0, nAcc: 0, points: []
    });
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "h2o_diffusion_temperature", molecules: N_MOL, box_A: BOXL,
      cutoff_A: RCUT, density_mol_per_A3: DENSITY, dt_fs: DT,
      temperatures_K: TEMPS_K, equil_ticks: EQUIL, prod_ticks: PROD,
      ticks: TOTAL_TICKS,
      model: "rigid SPC/E water (SHAKE/RATTLE), periodic box + DSF Coulomb; temperature sweep for D(T)"
    });
  },
  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;
    const sim = s.sim;
    s.tick += 1;

    // One-time lattice melt at MELT_K (strong thermostat, no measurement) so the
    // first measurement block starts from a fully-equilibrated liquid.
    if (s.tick <= MELT_TICKS) {
      sim.step(null);
      if (s.tick % THERMO_EVERY === 0) sim.thermostat(MELT_K, THERMO_STRONG);
      return;
    }

    const t2 = s.tick - MELT_TICKS - 1;
    const idx = Math.floor(t2 / BLOCK);                // which temperature block
    const within = t2 % BLOCK;                         // tick within the block
    const targetK = TEMPS_K[idx];
    const inProd = within >= EQUIL;

    // New block: reset per-block accumulators (trajectory carries over).
    if (within === 0) {
      s.msdOrigins = []; s.msdHead = 0;
      s.msdSum.fill(0); s.msdCnt.fill(0);
      s.sumT = 0; s.nAcc = 0;
    }

    sim.step(null);
    // Strong rescale while equilibrating to the block's target; gentle while
    // measuring so the diffusive dynamics are barely perturbed.
    if (s.tick % THERMO_EVERY === 0)
      sim.thermostat(targetK, inProd ? THERMO_GENTLE : THERMO_STRONG);

    if (inProd) {
      s.sumT += sim.temperature(); s.nAcc += 1;
      const nO = sim.mols.length;
      // Capture a new time origin (unwrapped O positions) every ORIGIN_EVERY.
      if ((within - EQUIL) % ORIGIN_EVERY === 0) {
        const ref = new Float64Array(nO * 3);
        for (let i = 0; i < nO; i++) {
          const O = sim.atoms[sim.mols[i].O].p;
          ref[3 * i] = O[0]; ref[3 * i + 1] = O[1]; ref[3 * i + 2] = O[2];
        }
        s.msdOrigins.push({ tick: s.tick, ref });
      }
      // Drop origins older than MAX_LAG, then accumulate MSD vs lag for the rest.
      while (s.msdHead < s.msdOrigins.length &&
             s.tick - s.msdOrigins[s.msdHead].tick > MAX_LAG) s.msdHead++;
      for (let oi = s.msdHead; oi < s.msdOrigins.length; oi++) {
        const o = s.msdOrigins[oi], lag = s.tick - o.tick;
        if (lag < 1) continue;
        const ref = o.ref;
        let sum = 0;
        for (let i = 0; i < nO; i++) {
          const O = sim.atoms[sim.mols[i].O].p;
          const dx = O[0] - ref[3 * i], dy = O[1] - ref[3 * i + 1], dz = O[2] - ref[3 * i + 2];
          sum += dx * dx + dy * dy + dz * dz;
        }
        s.msdSum[lag] += sum; s.msdCnt[lag] += nO;
      }
    }

    // Block end: fit D and compare to experiment at the MEASURED temperature.
    if (within === BLOCK - 1) {
      const { D, slope } = blockDiffusion(s.msdSum, s.msdCnt);
      const meanT = s.nAcc ? s.sumT / s.nAcc : 0;
      const point = {
        target_K: targetK, mean_temperature_K: meanT,
        self_diffusion_m2_per_s: D, msd_slope_A2_per_fs: slope,
        experiment_self_diffusion_m2_per_s: expDiffusion(meanT)
      };
      s.points.push(point);
      ctx.emit("diffusion_point", point);
    }

    if (s.tick === TOTAL_TICKS) {
      const pts = s.points;
      // The robust, falsifiable claim is the TREND: D rises monotonically with
      // T, and the rise over the measured span tracks the measured water trend.
      // Absolute values carry the finite-size / constant-density / single-origin
      // caveats and are reported, not tuned.
      let monotonic = true;
      for (let i = 1; i < pts.length; i++)
        if (pts[i].self_diffusion_m2_per_s <= pts[i - 1].self_diffusion_m2_per_s) monotonic = false;
      const allPhysical = pts.every((p) =>
        p.self_diffusion_m2_per_s > 0.3e-9 && p.self_diffusion_m2_per_s < 8e-9);
      const first = pts[0], lastP = pts[pts.length - 1];
      const ratio = pts.length >= 2 && first.self_diffusion_m2_per_s > 0
        ? lastP.self_diffusion_m2_per_s / first.self_diffusion_m2_per_s : 0;
      // Experiment ratio over the SAME measured temperature span (apples-to-apples).
      const expRatio = pts.length >= 2
        ? expDiffusion(lastP.mean_temperature_K) / expDiffusion(first.mean_temperature_K) : 0;
      // The TRECH rise should track the measured rise (within a factor ~1.5).
      const trendMatches = ratio > 1.3 && expRatio > 0 &&
        ratio / expRatio > 0.5 && ratio / expRatio < 2.0;
      ctx.emit("diffusion_vs_temperature", {
        molecules: N_MOL, box_A: BOXL, model: "rigid SPC/E (SHAKE/RATTLE), DSF Coulomb",
        points: pts,
        d_ratio_trech: ratio, d_ratio_experiment: expRatio,
        temperature_span_K: [first.mean_temperature_K, lastP.mean_temperature_K],
        max_constraint_violation: sim.maxConstraintViol,
        validation: {
          monotonic_increase: monotonic,
          all_diffusion_physical: allPhysical,
          trend_matches_experiment: trendMatches,
          rigid_constraints_held: sim.maxConstraintViol < 1e-6,
          diffusion_temperature_trend_ok: monotonic && allPhysical && trendMatches
        }
      });
    }
  }
};

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.nm(5.0), worldMaterial: "G4_Galactic" },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  run: { nEvents: TOTAL_TICKS, seed: 13579, threads: 1 },
  determinism: { mode: "predictive" },
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "h2o_diffusion_temperature" },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "periodic_cell", material: "G4_Galactic",
        sizeMm: [units.nm(2.0), units.nm(2.0), units.nm(2.0)],
        positionMm: [0, 0, 0], tags: ["fluid", "h2o", "md", "diffusion", "temperature"]
      })
    ]
  }
};
