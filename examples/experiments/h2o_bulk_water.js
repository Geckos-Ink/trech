// Sputnik "H2O fluid behavior", completed toward true BULK: the cluster
// (h2o_cluster_fluid.js) is a finite droplet with a surface; this is bulk
// liquid water in a PERIODIC box, so there is no surface and the structure can
// be compared to the measured liquid. The headline observable is the O-O
// radial distribution function g(r): real liquid water has a sharp first peak
// at ~2.8 A (the hydrogen-bond distance) and tetrahedral coordination ~4-4.5.
//
// Honest scope (unchanged): classical molecular dynamics in the deterministic
// hook layer (Geant4 is the per-tick clock; it does not do molecular bonds).
// The experimental g(r) first-peak position is the "physics for comparison".
//
// Model:
//   N = 108 rigid SPC/E water molecules, periodic cubic box at liquid density
//       (rho = 0.0334 molecules/A^3 ~ 1 g/cm^3), minimum-image convention.
//   model          : SPC/E (Berendsen 1987) charges + geometry, run RIGID via
//                     SHAKE/RATTLE holonomic constraints (the canonical SPC/E is
//                     a rigid model; running it rigid rather than flexible
//                     removes the O-H stretch that smears the intermolecular
//                     structure, sharpening g(r), and -- by killing the stiffest
//                     motion -- lets the timestep go from 0.2 to 2 fs).
//   intermolecular : LJ(O-O) (SPC/E) + Coulomb via the damped-shifted-force
//                    (Fennell & Gezelter 2006), a cutoff method approximating
//                    Ewald without a reciprocal-space sum.
//   velocity-Verlet; seeded RNG + threads:1 => reproducible.
//
// The rigid-SPC/E MD core (force loop, SHAKE/RATTLE, integrator) lives in the
// shared include `trech_water_md.js`; this scenario keeps only the bulk-water
// orchestration (equilibration vs production, the O-O g(r) analysis, and the
// self-diffusion MSD). The D(T) sweep `h2o_diffusion_temperature.js` shares the
// same core.
//
// Emits a final `bulk_summary` with temperature, the O-O g(r) first-peak
// position/height, the coordination number, the inter-shell depletion, the
// self-diffusion coefficient measured two independent ways (Einstein/MSD and
// Green-Kubo/VACF, which agree), and the validation. Also emits a
// deterministic `md_snapshot` every SNAP_EVERY ticks
// (wrapped atom positions + the running g(r) histogram) — visualization
// sideband only, consumed by tools/viz/demos/render_bulk_water.py.
//
// Run:
//   trech run examples/experiments/h2o_bulk_water.js \
//        --events 3000 --output build/dev/out_h2o_bulk

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
const DENSITY = 0.0334;            // molecules / A^3 (~1 g/cm^3)
const BOXL = Math.cbrt(N_MOL / DENSITY);
const RCUT = Math.min(7.0, 0.5 * BOXL - 0.2);
const ALPHA = 0.25;               // DSF damping (1/A)
const DT = 2.0, TARGET_K = 300.0, THERMO_EVERY = 10;  // rigid water -> 2 fs OK
const THERMO_ALPHA = 0.1;         // gentle Berendsen-like coupling
const TOTAL_TICKS = 2500;
const EQUIL_FRACTION = 0.4;       // accumulate g(r) after this fraction of ticks
const RDF_BINS = 150, RDF_RMAX = 0.5 * BOXL;
const SEED = 24601;
const SNAP_EVERY = 10;            // md_snapshot emit stride (viz sideband only)
// Velocity autocorrelation (molecular COM) for the Green-Kubo self-diffusion
// cross-check: D = (1/3) integral_0^inf <v_com(0).v_com(t)> dt. A second,
// independent route to D from the SAME run as the Einstein/MSD estimate; the
// two agreeing is the validation. The window (500 fs) spans the decay + the
// negative cage-backscattering dip after which the VACF (and its integral) has
// converged. Multi-origin averaged (a fresh origin every VACF_ORIGIN_EVERY).
const VACF_WINDOW = 250, VACF_ORIGIN_EVERY = 4;   // ticks

// g(r) and first peak / coordination from the accumulated O-O histogram.
function analyzeRdf(hist, frames, nO) {
  const dr = RDF_RMAX / RDF_BINS, rho = nO / (BOXL * BOXL * BOXL);
  const g = new Array(RDF_BINS).fill(0);
  for (let b = 0; b < RDF_BINS; b++) {
    const rlo = b * dr, rhi = rlo + dr;
    const shell = (4 / 3) * Math.PI * (rhi * rhi * rhi - rlo * rlo * rlo);
    const ideal = frames * nO * shell * rho;        // pairs counted both ways / nO
    g[b] = ideal > 0 ? hist[b] / ideal : 0;
  }
  // first peak in [2.4, 3.2] A
  let peakR = 0, peakG = 0;
  for (let b = 0; b < RDF_BINS; b++) {
    const r = (b + 0.5) * dr;
    if (r >= 2.4 && r <= 3.2 && g[b] > peakG) { peakG = g[b]; peakR = r; }
  }
  // first minimum: the lowest g(r) in a window past the peak (robust to the
  // post-peak noise of a finite-N RDF; liquid water's first min sits ~3.3 A).
  let minB = Math.floor((peakR + 0.2) / dr), minG = Infinity;
  const hiB = Math.min(RDF_BINS - 1, Math.floor((peakR + 1.4) / dr));
  for (let b = Math.floor((peakR + 0.1) / dr); b <= hiB; b++) {
    if (g[b] < minG) { minG = g[b]; minB = b; }
  }
  let coord = 0;
  for (let b = 0; b <= minB; b++) {
    const r = (b + 0.5) * dr;
    coord += 4 * Math.PI * r * r * rho * g[b] * dr;
  }
  // Fixed-bound coordination at the EXPERIMENTAL first-minimum convention
  // (~3.4 A). This model's inter-shell depletion is shallower and farther out
  // than real water's, so integrating to its OWN first minimum inflates the
  // count; the fixed bound is the cross-model-comparable number. Both are
  // reported.
  let coord34 = 0;
  const b34 = Math.min(RDF_BINS - 1, Math.floor(3.4 / dr));
  for (let b = 0; b <= b34; b++) {
    const r = (b + 0.5) * dr;
    coord34 += 4 * Math.PI * r * r * rho * g[b] * dr;
  }
  // second shell: real water has a tetrahedral second peak at ~4.5 A. Only
  // meaningful when the g(r) range extends well past it (large box).
  let peak2R = 0, peak2G = 0;
  const lo2 = Math.max((minB + 1) * dr, 3.8), hi2 = Math.min(5.4, RDF_RMAX - 0.3);
  for (let b = 0; b < RDF_BINS; b++) {
    const r = (b + 0.5) * dr;
    if (r >= lo2 && r <= hi2 && g[b] > peak2G) { peak2G = g[b]; peak2R = r; }
  }
  return { peakR, peakG, coord, coord34, firstMinR: (minB + 0.5) * dr,
           firstMinG: minG, peak2R, peak2G };
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    // The shared core builds the rigid-SPC/E system, projects the initial
    // velocities onto the constraint manifold, and computes the first force.
    ctx.state.sim = md.create({
      nMol: N_MOL, density: DENSITY, rcutMax: 7.0, alpha: ALPHA, dt: DT,
      seed: SEED, rdfBins: RDF_BINS, initialK: TARGET_K
    });
    Object.assign(ctx.state, {
      tick: 0, initialized: true,
      rdfHist: new Array(RDF_BINS).fill(0), rdfFrames: 0,
      sumT: 0, nAcc: 0,
      msdRef: null, msdT0: 0, msdCurve: [],  // O-position MSD for self-diffusion
      // COM-velocity VACF accumulators (Green-Kubo self-diffusion)
      vacfOrigins: [], vacfHead: 0,
      vacfSum: new Float64Array(VACF_WINDOW + 1),
      vacfCnt: new Float64Array(VACF_WINDOW + 1),
      vcom: new Float64Array(N_MOL * 3)
    });
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "h2o_bulk_water", molecules: N_MOL, box_A: BOXL, cutoff_A: RCUT,
      density_mol_per_A3: DENSITY, target_K: TARGET_K, dt_fs: DT, ticks: TOTAL_TICKS,
      rdf_bins: RDF_BINS, rdf_rmax_A: RDF_RMAX, snap_every: SNAP_EVERY,
      equil_fraction: EQUIL_FRACTION,
      model: "rigid SPC/E water (Berendsen 1987; SHAKE/RATTLE constraints, dt=2 fs), periodic box + DSF Coulomb, classical MD in hook layer"
    });
  },
  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;
    const sim = s.sim;
    s.tick += 1;
    const accumulate = s.tick > EQUIL_FRACTION * TOTAL_TICKS;
    sim.step(accumulate ? s.rdfHist : null);
    if (accumulate) s.rdfFrames += 1;
    if (s.tick % THERMO_EVERY === 0) sim.thermostat(TARGET_K, THERMO_ALPHA);
    // Production-phase mean only: averaging over the lattice-melt transient
    // would misstate the temperature the g(r) was actually sampled at.
    if (accumulate) {
      s.sumT += sim.temperature(); s.nAcc += 1;
      // Mean-squared displacement of the O atoms for the self-diffusion
      // coefficient (Einstein relation). Positions are never wrapped in the
      // integrator (only the viz snapshot wraps), so atom.p is already the
      // continuous/unwrapped trajectory -- MSD is a direct difference from the
      // reference set captured on the first production tick.
      if (!s.msdRef) {
        s.msdRef = sim.mols.map((m) => sim.atoms[m.O].p.slice());
        s.msdT0 = s.tick;
      } else {
        let sum = 0;
        for (let i = 0; i < sim.mols.length; i++) {
          const O = sim.atoms[sim.mols[i].O].p, r0 = s.msdRef[i];
          const dx = O[0] - r0[0], dy = O[1] - r0[1], dz = O[2] - r0[2];
          sum += dx * dx + dy * dy + dz * dz;
        }
        s.msdCurve.push({ t_fs: (s.tick - s.msdT0) * DT, msd_A2: sum / sim.mols.length });
      }
      // Molecular center-of-mass velocity autocorrelation (Green-Kubo route).
      const nMol = sim.mols.length, vcom = s.vcom;
      for (let i = 0; i < nMol; i++) {
        const m = sim.mols[i], O = sim.atoms[m.O], H1 = sim.atoms[m.H1], H2 = sim.atoms[m.H2];
        const M = O.m + H1.m + H2.m;
        vcom[3 * i]     = (O.m * O.v[0] + H1.m * H1.v[0] + H2.m * H2.v[0]) / M;
        vcom[3 * i + 1] = (O.m * O.v[1] + H1.m * H1.v[1] + H2.m * H2.v[1]) / M;
        vcom[3 * i + 2] = (O.m * O.v[2] + H1.m * H1.v[2] + H2.m * H2.v[2]) / M;
      }
      const pidx = s.tick - s.msdT0;   // production index (0 on the first prod tick)
      if (pidx % VACF_ORIGIN_EVERY === 0) {
        s.vacfOrigins.push({ tick: s.tick, v: vcom.slice() });
      }
      while (s.vacfHead < s.vacfOrigins.length &&
             s.tick - s.vacfOrigins[s.vacfHead].tick > VACF_WINDOW) s.vacfHead++;
      for (let oi = s.vacfHead; oi < s.vacfOrigins.length; oi++) {
        const o = s.vacfOrigins[oi], lag = s.tick - o.tick;
        const v0 = o.v;
        let acc = 0;
        for (let k = 0; k < nMol * 3; k++) acc += v0[k] * vcom[k];
        s.vacfSum[lag] += acc; s.vacfCnt[lag] += nMol;
      }
    }

    if (s.tick === 1 || s.tick % SNAP_EVERY === 0) {
      ctx.emit("md_snapshot", {
        tick: s.tick, time_fs: s.tick * DT,
        temperature_K: sim.temperature(),
        xyz: sim.snapshotXyz(),
        rdf: { hist: s.rdfHist.slice(), frames: s.rdfFrames }
      });
    }

    if (s.tick === TOTAL_TICKS) {
      const nO = sim.mols.length;
      const rdf = analyzeRdf(s.rdfHist, s.rdfFrames, nO);
      const meanT = s.sumT / s.nAcc;
      // The robust, experiment-matching observable is the O-O g(r) FIRST PEAK
      // position -- liquid water's hydrogen-bond distance ~2.8 A. Coordination
      // is reported but only loosely gated: with the SPC/E charges both the
      // own-first-minimum integral and the fixed 3.4 A-convention integral now
      // bracket the measured ~4.3-4.7 (the residual is a depletion still a touch
      // shallower than real water under the short-cutoff DSF) -- both bounds are
      // emitted, stated honestly rather than tuned to a target.
      const peakOk = rdf.peakR >= 2.6 && rdf.peakR <= 3.0 && rdf.peakG > 1.5;
      const coordReasonable = rdf.coord >= 3.0 && rdf.coord <= 8.0;
      const tempOk = Math.abs(meanT - TARGET_K) < 120.0;
      // Second shell (experiment ~4.5 A, tetrahedral order): reported and
      // separately flagged, but NOT folded into bulk_water_stable -- at this
      // system size it is a softer feature than the hydrogen-bond peak.
      const shell2Ok = rdf.peak2R >= 4.0 && rdf.peak2R <= 5.2 && rdf.peak2G > 1.0;
      // Rigid-body integrity: the SHAKE/RATTLE constraints must keep every bond
      // at its fixed length to tight tolerance over the whole run. A large
      // residual would mean the constraints are not actually holding the
      // molecule rigid (a silent integrator bug), so it gates bulk_water_stable.
      const rigidOk = sim.maxConstraintViol < 1e-6;
      // Self-diffusion from the production-phase O-atom MSD (Einstein relation,
      // MSD = 6 D t in 3D). Fit the slope over the second half of the MSD curve,
      // where the early ballistic/sub-diffusive part has died out and the motion
      // is diffusive. Honest caveats (reported, not tuned): a single-origin MSD
      // over a few ps with N=108 + a 7 A cutoff is a coarse estimate, and the
      // production temperature (~305 K) sits a little above the 298 K the SPC/E
      // and experimental reference values are quoted at (water's D rises with T).
      let selfD = 0, msdSlope = 0;
      const curve = s.msdCurve;
      if (curve.length > 8) {
        const tmax = curve[curve.length - 1].t_fs;
        const fitPts = [];
        for (const p of curve) if (p.t_fs >= 0.5 * tmax) fitPts.push({ x: p.t_fs, y: p.msd_A2 });
        msdSlope = md.lsqSlope(fitPts);  // A^2 / fs
        selfD = (msdSlope / 6) * 1e-5;   // A^2/fs -> m^2/s  (1 A^2/fs = 1e-5 m^2/s)
      }
      const diffusionPhysical = selfD > 0.5e-9 && selfD < 6e-9;
      // Green-Kubo self-diffusion from the COM-velocity VACF: an INDEPENDENT
      // route to D from the same run -- D = (1/3) integral_0^inf <v(0).v(t)> dt
      // (trapezoid over the converged 500 fs window). The two estimates agreeing
      // (within ~half) is the cross-check; the normalized VACF curve carries the
      // negative cage-backscattering dip characteristic of a dense liquid.
      let greenKuboD = 0;
      const vacf0 = s.vacfCnt[0] > 0 ? s.vacfSum[0] / s.vacfCnt[0] : 0;
      const vacfCurve = [];
      if (vacf0 > 0) {
        let integ = 0;
        for (let lag = 0; lag <= VACF_WINDOW; lag++) {
          const c = s.vacfCnt[lag] > 0 ? s.vacfSum[lag] / s.vacfCnt[lag] : 0;
          const w = (lag === 0 || lag === VACF_WINDOW) ? 0.5 : 1.0;
          integ += w * c * DT;
          if (lag % 2 === 0)
            vacfCurve.push({ t_fs: lag * DT, c_norm: Math.round((c / vacf0) * 1e4) / 1e4 });
        }
        greenKuboD = (integ / 3) * 1e-5;   // A^2/fs -> m^2/s
      }
      const greenKuboConsistent = selfD > 0 && greenKuboD > 0 &&
        Math.abs(greenKuboD - selfD) / selfD < 0.5;
      // Downsample the MSD curve for the emit (the viewer reconstructs the fit).
      const msdStride = Math.max(1, Math.floor(curve.length / 150));
      const msdOut = [];
      for (let i = 0; i < curve.length; i += msdStride)
        msdOut.push({ t_fs: curve[i].t_fs, msd_A2: Math.round(curve[i].msd_A2 * 1e4) / 1e4 });
      ctx.emit("bulk_summary", {
        molecules: N_MOL, box_A: BOXL, ticks: s.tick, time_fs: s.tick * DT,
        mean_temperature_K: meanT,
        gr_first_peak_A: rdf.peakR, gr_first_peak_height: rdf.peakG,
        gr_first_min_A: rdf.firstMinR, gr_first_min_height: rdf.firstMinG,
        coordination_number: rdf.coord,
        coordination_number_to_3p4A: rdf.coord34,
        experiment_first_min_height: 0.75,
        gr_second_peak_A: rdf.peak2R, gr_second_peak_height: rdf.peak2G,
        experiment_first_peak_A: 2.8, experiment_second_peak_A: 4.5,
        max_constraint_violation: sim.maxConstraintViol,
        self_diffusion_m2_per_s: selfD, msd_slope_A2_per_fs: msdSlope,
        msd_fit_window_fs: curve.length ? 0.5 * curve[curve.length - 1].t_fs : 0,
        experiment_self_diffusion_m2_per_s: 2.3e-9,
        spce_literature_self_diffusion_m2_per_s: 2.5e-9,
        msd_curve: msdOut,
        green_kubo_self_diffusion_m2_per_s: greenKuboD,
        vacf_window_fs: VACF_WINDOW * DT, vacf_curve: vacfCurve,
        validation: {
          first_peak_near_experiment: peakOk,
          coordination_reasonable: coordReasonable,
          temperature_controlled: tempOk,
          second_shell_near_tetrahedral: shell2Ok,
          rigid_constraints_held: rigidOk,
          self_diffusion_physical: diffusionPhysical,
          green_kubo_consistent_with_einstein: greenKuboConsistent,
          // The headline claim: a periodic bulk-water structure that reproduces
          // the measured hydrogen-bond peak at a controlled temperature, with
          // the rigid-body constraints provably held.
          bulk_water_stable: peakOk && tempOk && rigidOk
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
            ensemble: "h2o_bulk_water" },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "periodic_cell", material: "G4_Galactic",
        sizeMm: [units.nm(2.0), units.nm(2.0), units.nm(2.0)],
        positionMm: [0, 0, 0], tags: ["fluid", "h2o", "md", "bulk", "periodic"]
      })
    ]
  }
};
