// Shared rigid-SPC/E water molecular-dynamics core for the Sputnik bulk-water
// experiments. Extracted verbatim from h2o_bulk_water.js so the two water
// scenarios (single-state-point structure/diffusion and the D(T) sweep) share
// one physics source instead of each carrying a copy of the force loop and the
// SHAKE/RATTLE constraint solver.
//
// Model: SPC/E (Berendsen, Grigera & Straatsma 1987) charges + geometry, held
// rigid by SHAKE (positions) / RATTLE (velocities); intermolecular LJ(O-O) +
// damped-shifted-force (Fennell-Gezelter) Coulomb in a periodic box with the
// minimum-image convention; velocity-Verlet. Positions are NOT wrapped in the
// integrator (so atom.p is the continuous/unwrapped trajectory, which the
// callers use directly for MSD); only snapshotXyz() wraps for visualization.
//
// Usage:
//   TRECH_INCLUDE("trech_water_md.js");
//   const md = globalThis.TRECH_WATER_MD;
//   const sim = md.create({ nMol, density, rcutMax, alpha, dt, seed,
//                           rdfBins, initialK });
//   sim.step(rdfHist?)         // one constrained velocity-Verlet step;
//                              // accumulates O-O g(r) into rdfHist if provided
//   sim.temperature()          // instantaneous kinetic temperature (rigid dof)
//   sim.thermostat(targetK, a) // velocity rescale lambda=sqrt(1+a*(T0/T-1))
//   sim.snapshotXyz()          // wrapped per-molecule [O,H,H] positions (viz)
//   sim.atoms / sim.mols / sim.boxL / sim.rcut / sim.rdfRmax
//   sim.maxConstraintViol      // max post-SHAKE bond residual seen (rigidity proof)
//   md.lsqSlope(points)        // least-squares slope helper (MSD fits)

globalThis.TRECH_WATER_MD = (function () {
  "use strict";

  // ---- fixed SPC/E + rigid-geometry constants (real units: A, amu, fs) ----
  const DEG = Math.PI / 180.0;
  const KCAL = 4.185e-4;
  const KB = 8.314463e-7;
  const COULOMB_K = 332.0637 * KCAL;
  const R0 = 1.0, THETA0 = 109.47 * DEG;        // r_OH = 1.0 A, HOH 109.47 deg
  const QO = -0.8476, QH = 0.4238;
  const EPS_OO = 0.1553 * KCAL, SIG_OO = 3.166;
  const MASS = { O: 15.999, H: 1.008 };
  const D_OH = R0, D_HH = 2 * R0 * Math.sin(THETA0 / 2);
  const SHAKE_TOL = 1e-8, SHAKE_MAXIT = 100;

  // ---- pure helpers ----
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  function erfc(x) {                              // Abramowitz & Stegun 7.1.26
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

  // ---- simulator factory (closes over the box-/cutoff-derived constants) ----
  function create(cfg) {
    const nMol = cfg.nMol, density = cfg.density, dt = cfg.dt, alpha = cfg.alpha;
    const rdfBins = cfg.rdfBins || 0;
    const initialK = cfg.initialK;
    const boxL = Math.cbrt(nMol / density);
    const rcut = Math.min(cfg.rcutMax, 0.5 * boxL - 0.2);
    const rdfRmax = 0.5 * boxL;
    // DSF self-shift constants (evaluated once at the cutoff).
    const twoASqrtPi = 2 * alpha / Math.sqrt(Math.PI);
    const dsfFshift = erfc(alpha * rcut) / (rcut * rcut) +
                      twoASqrtPi * Math.exp(-alpha * alpha * rcut * rcut) / rcut;

    function buildAtoms(rng) {
      const atoms = [], mols = [];
      const side = Math.ceil(Math.cbrt(nMol));
      const spacing = boxL / side;
      let placed = 0;
      for (let ix = 0; ix < side && placed < nMol; ix++)
      for (let iy = 0; iy < side && placed < nMol; iy++)
      for (let iz = 0; iz < side && placed < nMol; iz++) {
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
        const s = Math.sqrt(KB * initialK / a.m);
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
      const nM = atoms.length / 3;   // rigid water: 6 dof/molecule - 3 (COM)
      return 2 * ke / ((6 * nM - 3) * KB);
    }

    function computeForces(atoms, mols, rdfHist) {
      const f = atoms.map(() => [0, 0, 0]);
      // No intramolecular force terms: the molecule is held rigid by the
      // SHAKE/RATTLE constraints. Inlined scalar math (no per-pair allocation)
      // -- this is the hot loop and QuickJS pays heavily for allocation/GC.
      const rc2 = rcut * rcut, n = atoms.length;
      const invBox = 1 / boxL, sigSq = SIG_OO * SIG_OO, binScale = rdfBins / rdfRmax;
      for (let i = 0; i < n; i++) {
        const ai = atoms[i], pi = ai.p, qi = ai.q, isOi = ai.type === "O", moli = ai.mol, fi = f[i];
        for (let j = i + 1; j < n; j++) {
          const aj = atoms[j];
          if (aj.mol === moli) continue;
          const pj = aj.p;
          let dx = pi[0] - pj[0], dy = pi[1] - pj[1], dz = pi[2] - pj[2];
          dx -= boxL * Math.round(dx * invBox);
          dy -= boxL * Math.round(dy * invBox);
          dz -= boxL * Math.round(dz * invBox);
          const r2 = dx * dx + dy * dy + dz * dz;
          if (r2 >= rc2) continue;
          const r = Math.sqrt(r2);
          const fc = COULOMB_K * qi * aj.q *
                     (erfc(alpha * r) / r2 + twoASqrtPi * Math.exp(-alpha * alpha * r2) / r - dsfFshift) / r;
          let fxx = dx * fc, fyy = dy * fc, fzz = dz * fc;
          if (isOi && aj.type === "O") {
            const sr2 = sigSq / r2, sr6 = sr2 * sr2 * sr2, sr12 = sr6 * sr6;
            const flj = 24 * EPS_OO * (2 * sr12 - sr6) / r2;
            fxx += dx * flj; fyy += dy * flj; fzz += dz * flj;
            if (rdfHist) {
              const bin = (r * binScale) | 0;
              if (bin < rdfBins) rdfHist[bin] += 2;   // i-j and j-i
            }
          }
          fi[0] += fxx; fi[1] += fyy; fi[2] += fzz;
          const fj = f[j]; fj[0] -= fxx; fj[1] -= fyy; fj[2] -= fzz;
        }
      }
      return f;
    }

    // Per-molecule rigid constraints: O-H1, O-H2 (D_OH) and H1-H2 (D_HH).
    function molConstraints(m) {
      return [[m.O, m.H1, D_OH * D_OH], [m.O, m.H2, D_OH * D_OH], [m.H1, m.H2, D_HH * D_HH]];
    }
    function shake(atoms, mols, pOld) {
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
        for (let c = 0; c < 3; c++) {           // post-correction residual (proof)
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

    // ---- build + assemble the simulator ----
    const rng = makeRng(cfg.seed);
    const { atoms, mols } = buildAtoms(rng);
    // Positions are at the rigid geometry; project the random initial velocities
    // onto the constraint manifold (zero relative velocity along each bond).
    rattle(atoms, mols);
    const pOld = atoms.map(() => [0, 0, 0]);     // reused SHAKE reference buffer

    const sim = {
      atoms, mols, boxL, rcut, rdfRmax, dt, dOH: D_OH, dHH: D_HH,
      maxConstraintViol: 0, force: null,
      temperature() { return temperature(atoms); },
      thermostat(targetK, a) {
        const T = temperature(atoms);
        if (T > 0) {
          const lam = Math.sqrt(1 + a * (targetK / T - 1));
          for (const at of atoms) for (let k = 0; k < 3; k++) at.v[k] *= lam;
        }
      },
      // One constrained velocity-Verlet step. pre-step positions are copied into
      // the reused pOld scratch (QuickJS GC dominates otherwise in this loop).
      step(rdfHist) {
        const f0 = sim.force, hdt = 0.5 * dt;
        for (let i = 0; i < atoms.length; i++) {
          const a = atoms[i], inv = 1 / a.m, fi = f0[i], po = pOld[i], p = a.p, v = a.v;
          po[0] = p[0]; po[1] = p[1]; po[2] = p[2];
          v[0] += hdt * fi[0] * inv; v[1] += hdt * fi[1] * inv; v[2] += hdt * fi[2] * inv;
          p[0] += dt * v[0]; p[1] += dt * v[1]; p[2] += dt * v[2];
        }
        const viol = shake(atoms, mols, pOld);
        const f1 = computeForces(atoms, mols, rdfHist);
        for (let i = 0; i < atoms.length; i++) {
          const a = atoms[i], inv = 1 / a.m, fi = f1[i];
          a.v[0] += hdt * fi[0] * inv; a.v[1] += hdt * fi[1] * inv; a.v[2] += hdt * fi[2] * inv;
        }
        rattle(atoms, mols);
        sim.force = f1;
        if (viol > sim.maxConstraintViol) sim.maxConstraintViol = viol;
      },
      // Wrapped per-molecule [O,H,H] positions for the viz sideband: O wrapped
      // into [0, boxL), each H placed by minimum image relative to its O so
      // display molecules stay whole. 3 decimals (mA) keeps the payload compact.
      snapshotXyz() {
        const r3 = (x) => Math.round(x * 1000) / 1000;
        const wrap = (x) => x - boxL * Math.floor(x / boxL);
        const out = [];
        for (const m of mols) {
          const O = atoms[m.O].p;
          const owx = wrap(O[0]), owy = wrap(O[1]), owz = wrap(O[2]);
          out.push([r3(owx), r3(owy), r3(owz)]);
          for (const Hi of [m.H1, m.H2]) {
            const Hp = atoms[Hi].p;
            let dx = Hp[0] - O[0], dy = Hp[1] - O[1], dz = Hp[2] - O[2];
            dx -= boxL * Math.round(dx / boxL);
            dy -= boxL * Math.round(dy / boxL);
            dz -= boxL * Math.round(dz / boxL);
            out.push([r3(owx + dx), r3(owy + dy), r3(owz + dz)]);
          }
        }
        return out;
      }
    };
    sim.force = computeForces(atoms, mols, null);
    return sim;
  }

  return { create, lsqSlope };
})();
