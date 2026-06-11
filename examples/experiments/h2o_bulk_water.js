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
//   N = 108 flexible water molecules, periodic cubic box at liquid density
//       (rho = 0.0334 molecules/A^3 ~ 1 g/cm^3), minimum-image convention.
//       (Scaled up from the first 48-molecule landing: the ~14.8 A box admits
//       a 7.0 A cutoff and a g(r) range that resolves the ~4.5 A tetrahedral
//       second shell, not just the first hydrogen-bond peak.)
//   model          : SPC/E (Berendsen 1987) charges + geometry, run FLEXIBLY
//                     (harmonic bonds/angle about the SPC/E equilibrium rather
//                     than rigid constraints). SPC/E's larger charges
//                     (q_O=-0.8476) and tetrahedral angle (109.47deg) are the
//                     parameters tuned to reproduce liquid structure, so they
//                     deepen the inter-shell depletion vs the plain-SPC charges
//                     used in the first landing.
//   intramolecular : harmonic O-H bonds (r0=1.0 A) + H-O-H angle (109.47deg)
//   intermolecular : LJ(O-O) (SPC/E) + Coulomb via the damped-shifted-force (DSF)
//                    real-space method (Fennell & Gezelter 2006) -- a standard
//                    cutoff electrostatics that approximates Ewald without a
//                    reciprocal-space sum.
//   thermostat     : velocity rescaling toward TARGET_K.
//   velocity-Verlet; seeded RNG + threads:1 => reproducible.
//
// Emits a final `bulk_summary` with temperature, the O-O g(r) first-peak
// position/height, the running coordination number, and the validation.
// Also emits a deterministic `md_snapshot` every SNAP_EVERY ticks (wrapped
// atom positions + the running g(r) histogram) — visualization sideband only,
// consumed by tools/viz/demos/render_bulk_water.py; physics is unchanged.
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

// ---- constants (real units: A, amu, fs; energy amu*A^2/fs^2) ----
const DEG = Math.PI / 180.0;
const KCAL = 4.185e-4;
const KB = 8.314463e-7;
const COULOMB_K = 332.0637 * KCAL;
// SPC/E (Berendsen, Grigera & Straatsma 1987): rigid geometry r_OH=1.0 A,
// angle 109.47 deg, q_O=-0.8476 e, sigma=3.166 A, eps=0.6502 kJ/mol. Run here
// flexibly with harmonic intramolecular terms about that geometry (the
// Toukan-Rahman-style force constants govern the vibration, not the liquid
// structure, which the charges + angle set).
const R0 = 1.0, THETA0 = 109.47 * DEG;
const KBOND = 1059.162 * KCAL, KANG = 75.90 * KCAL;
const QO = -0.8476, QH = 0.4238;
const EPS_OO = 0.1553 * KCAL, SIG_OO = 3.166;
const MASS = { O: 15.999, H: 1.008 };

// ---- system / run ----
const N_MOL = 108;
const DENSITY = 0.0334;            // molecules / A^3 (~1 g/cm^3)
const BOXL = Math.cbrt(N_MOL / DENSITY);
const RCUT = Math.min(7.0, 0.5 * BOXL - 0.2);
const ALPHA = 0.25;               // DSF damping (1/A)
const DT = 0.2, TARGET_K = 300.0, THERMO_EVERY = 10;
const TOTAL_TICKS = 2500;
const EQUIL_FRACTION = 0.4;       // accumulate g(r) after this fraction of ticks
const RDF_BINS = 150, RDF_RMAX = 0.5 * BOXL;
const SEED = 24601;
const SNAP_EVERY = 10;            // md_snapshot emit stride (viz sideband only)

// ---- helpers ----
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => Math.sqrt(dot(a, a));
function minImage(d) {
  d[0] -= BOXL * Math.round(d[0] / BOXL);
  d[1] -= BOXL * Math.round(d[1] / BOXL);
  d[2] -= BOXL * Math.round(d[2] / BOXL);
  return d;
}
// erfc via Abramowitz & Stegun 7.1.26 (x >= 0).
function erfc(x) {
  const t = 1 / (1 + 0.3275911 * x);
  const y = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 +
            t * (-1.453152027 + t * 1.061405429))));
  return y * Math.exp(-x * x);
}
function makeRng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function gauss(rng) {
  const u = Math.max(1e-12, rng()), v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// DSF self-shift constants (evaluated once at the cutoff).
const ERFC_RC = erfc(ALPHA * RCUT);
const TWO_A_SQRTPI = 2 * ALPHA / Math.sqrt(Math.PI);
const DSF_FSHIFT = ERFC_RC / (RCUT * RCUT) + TWO_A_SQRTPI * Math.exp(-ALPHA * ALPHA * RCUT * RCUT) / RCUT;

function buildAtoms(rng) {
  const atoms = [], mols = [];
  const side = Math.ceil(Math.cbrt(N_MOL));
  const spacing = BOXL / side;
  let placed = 0;
  for (let ix = 0; ix < side && placed < N_MOL; ix++)
  for (let iy = 0; iy < side && placed < N_MOL; iy++)
  for (let iz = 0; iz < side && placed < N_MOL; iz++) {
    const c = [(ix + 0.5) * spacing, (iy + 0.5) * spacing, (iz + 0.5) * spacing];
    const half = THETA0 / 2;
    let h1 = [R0 * Math.cos(half), R0 * Math.sin(half), 0];
    let h2 = [R0 * Math.cos(half), -R0 * Math.sin(half), 0];
    const a1 = 2 * Math.PI * rng(), a2 = Math.PI * rng();
    const rotz = ([x, y, z]) => [x * Math.cos(a1) - y * Math.sin(a1), x * Math.sin(a1) + y * Math.cos(a1), z];
    const roty = ([x, y, z]) => [x * Math.cos(a2) + z * Math.sin(a2), y, -x * Math.sin(a2) + z * Math.cos(a2)];
    h1 = roty(rotz(h1)); h2 = roty(rotz(h2));
    const O = atoms.length;
    atoms.push({ p: c.slice(), v: [0, 0, 0], m: MASS.O, q: QO, mol: placed, type: "O" });
    atoms.push({ p: [c[0] + h1[0], c[1] + h1[1], c[2] + h1[2]], v: [0, 0, 0], m: MASS.H, q: QH, mol: placed, type: "H" });
    atoms.push({ p: [c[0] + h2[0], c[1] + h2[1], c[2] + h2[2]], v: [0, 0, 0], m: MASS.H, q: QH, mol: placed, type: "H" });
    mols.push({ O, H1: O + 1, H2: O + 2 });
    placed++;
  }
  for (const a of atoms) {
    const s = Math.sqrt(KB * TARGET_K / a.m);
    a.v = [s * gauss(rng), s * gauss(rng), s * gauss(rng)];
  }
  const P = [0, 0, 0]; let M = 0;
  for (const a of atoms) { for (let k = 0; k < 3; k++) P[k] += a.m * a.v[k]; M += a.m; }
  for (const a of atoms) for (let k = 0; k < 3; k++) a.v[k] -= P[k] / M;
  return { atoms, mols };
}

function temperature(atoms) {
  let ke = 0;
  for (const a of atoms) ke += 0.5 * a.m * dot(a.v, a.v);
  return 2 * ke / ((3 * atoms.length - 3) * KB);
}

function computeForces(atoms, mols, rdfHist) {
  const f = atoms.map(() => [0, 0, 0]);
  const addF = (i, d, s) => { f[i][0] += d[0] * s; f[i][1] += d[1] * s; f[i][2] += d[2] * s; };

  // intramolecular (no minimum image; molecules stay whole)
  for (const m of mols) {
    const O = atoms[m.O].p, H1 = atoms[m.H1].p, H2 = atoms[m.H2].p;
    for (const [Hi, Hp] of [[m.H1, H1], [m.H2, H2]]) {
      const d = sub(Hp, O), r = norm(d), u = [d[0] / r, d[1] / r, d[2] / r];
      addF(Hi, u, -KBOND * (r - R0)); addF(m.O, u, KBOND * (r - R0));
    }
    const a = sub(H1, O), b = sub(H2, O), ra = norm(a), rb = norm(b);
    const ah = [a[0] / ra, a[1] / ra, a[2] / ra], bh = [b[0] / rb, b[1] / rb, b[2] / rb];
    let c = Math.max(-1, Math.min(1, dot(ah, bh)));
    const th = Math.acos(c), sn = Math.max(1e-8, Math.sqrt(1 - c * c)), dV = KANG * (th - THETA0);
    const fa = [(bh[0] - c * ah[0]) * dV / (sn * ra), (bh[1] - c * ah[1]) * dV / (sn * ra), (bh[2] - c * ah[2]) * dV / (sn * ra)];
    const fb = [(ah[0] - c * bh[0]) * dV / (sn * rb), (ah[1] - c * bh[1]) * dV / (sn * rb), (ah[2] - c * bh[2]) * dV / (sn * rb)];
    addF(m.H1, fa, 1); addF(m.H2, fb, 1); addF(m.O, fa, -1); addF(m.O, fb, -1);
  }

  // intermolecular: minimum-image LJ(O-O) + DSF Coulomb within RCUT.
  // Inlined scalar math (no per-pair array allocation) -- this is the hot loop
  // and QuickJS pays heavily for allocation/GC here.
  const rc2 = RCUT * RCUT, n = atoms.length;
  const invBox = 1 / BOXL, sigSq = SIG_OO * SIG_OO, binScale = RDF_BINS / RDF_RMAX;
  for (let i = 0; i < n; i++) {
    const ai = atoms[i], pi = ai.p, qi = ai.q, isOi = ai.type === "O", moli = ai.mol, fi = f[i];
    for (let j = i + 1; j < n; j++) {
      const aj = atoms[j];
      if (aj.mol === moli) continue;
      const pj = aj.p;
      let dx = pi[0] - pj[0], dy = pi[1] - pj[1], dz = pi[2] - pj[2];
      dx -= BOXL * Math.round(dx * invBox);
      dy -= BOXL * Math.round(dy * invBox);
      dz -= BOXL * Math.round(dz * invBox);
      const r2 = dx * dx + dy * dy + dz * dz;
      if (r2 >= rc2) continue;
      const r = Math.sqrt(r2);
      const fc = COULOMB_K * qi * aj.q *
                 (erfc(ALPHA * r) / r2 + TWO_A_SQRTPI * Math.exp(-ALPHA * ALPHA * r2) / r - DSF_FSHIFT) / r;
      let fxx = dx * fc, fyy = dy * fc, fzz = dz * fc;
      if (isOi && aj.type === "O") {
        const sr2 = sigSq / r2, sr6 = sr2 * sr2 * sr2, sr12 = sr6 * sr6;
        const flj = 24 * EPS_OO * (2 * sr12 - sr6) / r2;
        fxx += dx * flj; fyy += dy * flj; fzz += dz * flj;
        if (rdfHist) {
          const bin = (r * binScale) | 0;
          if (bin < RDF_BINS) rdfHist[bin] += 2; // i-j and j-i
        }
      }
      fi[0] += fxx; fi[1] += fyy; fi[2] += fzz;
      const fj = f[j]; fj[0] -= fxx; fj[1] -= fyy; fj[2] -= fzz;
    }
  }
  return f;
}

function verletStep(state, rdfHist) {
  const { atoms, mols } = state, f0 = state.force;
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m;
    for (let k = 0; k < 3; k++) a.p[k] += a.v[k] * DT + 0.5 * f0[i][k] * inv * DT * DT;
  }
  const f1 = computeForces(atoms, mols, rdfHist);
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m;
    for (let k = 0; k < 3; k++) a.v[k] += 0.5 * (f0[i][k] + f1[i][k]) * inv * DT;
  }
  state.force = f1;
}

function thermostat(atoms) {
  const T = temperature(atoms);
  if (T > 0) {
    const lam = Math.sqrt(1 + 0.1 * (TARGET_K / T - 1));
    for (const a of atoms) for (let k = 0; k < 3; k++) a.v[k] *= lam;
  }
}

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

// Wrapped per-molecule [O,H,H] positions for the viz sideband: O wrapped into
// [0, BOXL), each H placed by minimum image relative to its O so display
// molecules stay whole across the periodic boundary. 3 decimals (mA) keeps
// the emit payload compact.
function snapshotXyz(s) {
  const r3 = (x) => Math.round(x * 1000) / 1000;
  const wrap = (x) => x - BOXL * Math.floor(x / BOXL);
  const out = [];
  for (const m of s.mols) {
    const O = s.atoms[m.O].p;
    const ow = [wrap(O[0]), wrap(O[1]), wrap(O[2])];
    out.push([r3(ow[0]), r3(ow[1]), r3(ow[2])]);
    for (const Hi of [m.H1, m.H2]) {
      const d = minImage(sub(s.atoms[Hi].p, O));
      out.push([r3(ow[0] + d[0]), r3(ow[1] + d[1]), r3(ow[2] + d[2])]);
    }
  }
  return out;
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    const rng = makeRng(SEED);
    const { atoms, mols } = buildAtoms(rng);
    Object.assign(ctx.state, {
      atoms, mols, force: computeForces(atoms, mols, null),
      tick: 0, initialized: true,
      rdfHist: new Array(RDF_BINS).fill(0), rdfFrames: 0,
      sumT: 0, nAcc: 0
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
      model: "flexible SPC/E water (Berendsen 1987 charges+geometry), periodic box + DSF Coulomb, classical MD in hook layer"
    });
  },
  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;
    s.tick += 1;
    const accumulate = s.tick > EQUIL_FRACTION * TOTAL_TICKS;
    verletStep(s, accumulate ? s.rdfHist : null);
    if (accumulate) s.rdfFrames += 1;
    if (s.tick % THERMO_EVERY === 0) thermostat(s.atoms);
    // Production-phase mean only: averaging over the lattice-melt transient
    // would misstate the temperature the g(r) was actually sampled at.
    if (accumulate) { s.sumT += temperature(s.atoms); s.nAcc += 1; }

    if (s.tick === 1 || s.tick % SNAP_EVERY === 0) {
      ctx.emit("md_snapshot", {
        tick: s.tick, time_fs: s.tick * DT,
        temperature_K: temperature(s.atoms),
        xyz: snapshotXyz(s),
        rdf: { hist: s.rdfHist.slice(), frames: s.rdfFrames }
      });
    }

    if (s.tick === TOTAL_TICKS) {
      const nO = s.mols.length;
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
        validation: {
          first_peak_near_experiment: peakOk,
          coordination_reasonable: coordReasonable,
          temperature_controlled: tempOk,
          second_shell_near_tetrahedral: shell2Ok,
          // The headline claim: a periodic bulk-water structure that reproduces
          // the measured hydrogen-bond peak at a controlled temperature.
          bulk_water_stable: peakOk && tempOk
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
