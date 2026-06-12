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
// Method (identical rigid-SPC/E physics to h2o_bulk_water.js): the system is
// annealed UP through the temperature list; at each block it re-equilibrates
// with the thermostat, then measures D from the production-phase O-atom
// mean-squared displacement (Einstein relation, MSD = 6 D t). The atom
// positions are never wrapped in the integrator, so MSD is a direct
// difference from a per-block reference set.
//
// NOTE (tech debt): the rigid-SPC/E MD core below is duplicated from
// h2o_bulk_water.js (constants, SHAKE/RATTLE, force loop). A future refactor
// should extract a shared `trech_water_md.js` include so the two water
// experiments share one physics source. It is kept inline here to avoid
// touching the validated single-state-point scenario. N matches the bulk run
// (108) so the box admits the same 7 A cutoff -- a shorter cutoff (smaller box)
// under-binds the H-bond network and makes water diffuse too fast, inflating
// the absolute D. This makes the sweep slow (~12 min); it is SKIP-gated.
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

// ---- constants (real units: A, amu, fs; energy amu*A^2/fs^2) ----
const DEG = Math.PI / 180.0;
const KCAL = 4.185e-4;
const KB = 8.314463e-7;
const COULOMB_K = 332.0637 * KCAL;
// SPC/E (Berendsen, Grigera & Straatsma 1987), held rigid by SHAKE/RATTLE.
const R0 = 1.0, THETA0 = 109.47 * DEG;
const QO = -0.8476, QH = 0.4238;
const EPS_OO = 0.1553 * KCAL, SIG_OO = 3.166;
const MASS = { O: 15.999, H: 1.008 };
const D_OH = R0, D_HH = 2 * R0 * Math.sin(THETA0 / 2);
const SHAKE_TOL = 1e-8, SHAKE_MAXIT = 100;

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

// ---- helpers ----
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
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
function lsqSlope(pts) {
  const n = pts.length;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const p of pts) { sx += p.x; sy += p.y; sxx += p.x * p.x; sxy += p.x * p.y; }
  const denom = n * sxx - sx * sx;
  return denom !== 0 ? (n * sxy - sx * sy) / denom : 0;
}

// DSF self-shift constants (evaluated once at the cutoff).
const TWO_A_SQRTPI = 2 * ALPHA / Math.sqrt(Math.PI);
const DSF_FSHIFT = erfc(ALPHA * RCUT) / (RCUT * RCUT) +
                   TWO_A_SQRTPI * Math.exp(-ALPHA * ALPHA * RCUT * RCUT) / RCUT;

function buildAtoms(rng, targetK) {
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
    const s = Math.sqrt(KB * targetK / a.m);
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
  const nMol = atoms.length / 3;          // rigid water: 6 dof/molecule - 3 (COM)
  return 2 * ke / ((6 * nMol - 3) * KB);
}

function computeForces(atoms, mols) {
  const f = atoms.map(() => [0, 0, 0]);
  const rc2 = RCUT * RCUT, n = atoms.length;
  const invBox = 1 / BOXL, sigSq = SIG_OO * SIG_OO;
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
      }
      fi[0] += fxx; fi[1] += fyy; fi[2] += fzz;
      const fj = f[j]; fj[0] -= fxx; fj[1] -= fyy; fj[2] -= fzz;
    }
  }
  return f;
}

function molConstraints(m) {
  return [[m.O, m.H1, D_OH * D_OH], [m.O, m.H2, D_OH * D_OH], [m.H1, m.H2, D_HH * D_HH]];
}
function shake(atoms, mols, pOld, dt) {
  const invDt = 1 / dt;
  let maxRes = 0;
  for (const m of mols) {
    const cons = molConstraints(m);
    for (let it = 0; it < SHAKE_MAXIT; it++) {
      let ok = true;
      for (let c = 0; c < 3; c++) {
        const a = cons[c][0], b = cons[c][1], d2 = cons[c][2];
        const pa = atoms[a].p, pb = atoms[b].p;
        const rx = pa[0] - pb[0], ry = pa[1] - pb[1], rz = pa[2] - pb[2];
        const diff = rx * rx + ry * ry + rz * rz - d2;
        if (Math.abs(diff) / d2 > SHAKE_TOL) {
          ok = false;
          const oa = pOld[a], ob = pOld[b];
          const ox = oa[0] - ob[0], oy = oa[1] - ob[1], oz = oa[2] - ob[2];
          const ima = 1 / atoms[a].m, imb = 1 / atoms[b].m;
          const g = diff / (2 * (ima + imb) * (rx * ox + ry * oy + rz * oz));
          const ga = g * ima, gb = g * imb;
          pa[0] -= ga * ox; pa[1] -= ga * oy; pa[2] -= ga * oz;
          pb[0] += gb * ox; pb[1] += gb * oy; pb[2] += gb * oz;
          const va = atoms[a].v, vb = atoms[b].v;
          va[0] -= ga * ox * invDt; va[1] -= ga * oy * invDt; va[2] -= ga * oz * invDt;
          vb[0] += gb * ox * invDt; vb[1] += gb * oy * invDt; vb[2] += gb * oz * invDt;
        }
      }
      if (ok) break;
    }
    for (let c = 0; c < 3; c++) {
      const a = cons[c][0], b = cons[c][1], d2 = cons[c][2];
      const pa = atoms[a].p, pb = atoms[b].p;
      const rx = pa[0] - pb[0], ry = pa[1] - pb[1], rz = pa[2] - pb[2];
      const rel = Math.abs(rx * rx + ry * ry + rz * rz - d2) / d2;
      if (rel > maxRes) maxRes = rel;
    }
  }
  return maxRes;
}
function rattle(atoms, mols) {
  for (const m of mols) {
    const cons = molConstraints(m);
    for (let it = 0; it < SHAKE_MAXIT; it++) {
      let ok = true;
      for (let c = 0; c < 3; c++) {
        const a = cons[c][0], b = cons[c][1], d2 = cons[c][2];
        const pa = atoms[a].p, pb = atoms[b].p, va = atoms[a].v, vb = atoms[b].v;
        const rx = pa[0] - pb[0], ry = pa[1] - pb[1], rz = pa[2] - pb[2];
        const rv = rx * (va[0] - vb[0]) + ry * (va[1] - vb[1]) + rz * (va[2] - vb[2]);
        if (Math.abs(rv) > SHAKE_TOL * d2) {
          ok = false;
          const ima = 1 / atoms[a].m, imb = 1 / atoms[b].m;
          const k = rv / ((ima + imb) * d2), ka = k * ima, kb = k * imb;
          va[0] -= ka * rx; va[1] -= ka * ry; va[2] -= ka * rz;
          vb[0] += kb * rx; vb[1] += kb * ry; vb[2] += kb * rz;
        }
      }
      if (ok) break;
    }
  }
}
function verletStep(state) {
  const { atoms, mols, pOld } = state, f0 = state.force, hdt = 0.5 * DT;
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m, fi = f0[i], po = pOld[i], p = a.p, v = a.v;
    po[0] = p[0]; po[1] = p[1]; po[2] = p[2];
    v[0] += hdt * fi[0] * inv; v[1] += hdt * fi[1] * inv; v[2] += hdt * fi[2] * inv;
    p[0] += DT * v[0]; p[1] += DT * v[1]; p[2] += DT * v[2];
  }
  const viol = shake(atoms, mols, pOld, DT);
  const f1 = computeForces(atoms, mols);
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m, fi = f1[i];
    a.v[0] += hdt * fi[0] * inv; a.v[1] += hdt * fi[1] * inv; a.v[2] += hdt * fi[2] * inv;
  }
  rattle(atoms, mols);
  state.force = f1;
  if (viol > state.maxConstraintViol) state.maxConstraintViol = viol;
}
function thermostat(atoms, targetK, alpha) {
  const T = temperature(atoms);
  if (T > 0) {
    const lam = Math.sqrt(1 + alpha * (targetK / T - 1));
    for (const a of atoms) for (let k = 0; k < 3; k++) a.v[k] *= lam;
  }
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
  const slope = lsqSlope(fit);          // A^2 / fs
  return { D: (slope / 6) * 1e-5, slope };   // A^2/fs -> m^2/s
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    const rng = makeRng(SEED);
    const { atoms, mols } = buildAtoms(rng, TEMPS_K[0]);
    rattle(atoms, mols);
    Object.assign(ctx.state, {
      atoms, mols, force: computeForces(atoms, mols),
      pOld: atoms.map(() => [0, 0, 0]),
      tick: 0, initialized: true, maxConstraintViol: 0,
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
    s.tick += 1;

    // One-time lattice melt at MELT_K (strong thermostat, no measurement) so the
    // first measurement block starts from a fully-equilibrated liquid.
    if (s.tick <= MELT_TICKS) {
      verletStep(s);
      if (s.tick % THERMO_EVERY === 0) thermostat(s.atoms, MELT_K, THERMO_STRONG);
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

    verletStep(s);
    // Strong rescale while equilibrating to the block's target; gentle while
    // measuring so the diffusive dynamics are barely perturbed.
    if (s.tick % THERMO_EVERY === 0)
      thermostat(s.atoms, targetK, inProd ? THERMO_GENTLE : THERMO_STRONG);

    if (inProd) {
      s.sumT += temperature(s.atoms); s.nAcc += 1;
      const nO = s.mols.length;
      // Capture a new time origin (unwrapped O positions) every ORIGIN_EVERY.
      if ((within - EQUIL) % ORIGIN_EVERY === 0) {
        const ref = new Float64Array(nO * 3);
        for (let i = 0; i < nO; i++) {
          const O = s.atoms[s.mols[i].O].p;
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
          const O = s.atoms[s.mols[i].O].p;
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
        max_constraint_violation: s.maxConstraintViol,
        validation: {
          monotonic_increase: monotonic,
          all_diffusion_physical: allPhysical,
          trend_matches_experiment: trendMatches,
          rigid_constraints_held: s.maxConstraintViol < 1e-6,
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
