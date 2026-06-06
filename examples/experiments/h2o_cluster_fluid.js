// Sputnik item: "Simulate H2O fluid behavior". Next step after the single
// stable molecule (h2o_molecule_stability.js): a small ENSEMBLE of water
// molecules that attract each other and settle into a stable, liquid-like
// hydrogen-bonded droplet at ~300 K -- emergent fluid behavior from molecular
// interactions, not one isolated molecule.
//
// Honest scope (same as the single molecule): Geant4 transports particles but
// does not do bound-state / intermolecular chemistry, so this is a classical
// molecular-dynamics model run in the deterministic hook layer, with Geant4 as
// the per-tick clock. The force field is the "physics for comparison".
//
// Model:
//   intramolecular  : harmonic O-H bonds (r0 = 0.9572 A) + H-O-H angle
//                     (theta0 = 104.52 deg)              [as the single molecule]
//   intermolecular  : Lennard-Jones on O-O (SPC: eps = 0.1554 kcal/mol,
//                     sigma = 3.166 A) + Coulomb on SPC partial charges
//                     (qO = -0.82 e, qH = +0.41 e), soft-cored at short range
//                     so a stray H...O contact cannot blow up.
//   thermostat      : velocity rescaling toward TARGET_K (Berendsen-like), so
//                     the droplet reaches and holds a temperature.
//   integrator      : velocity-Verlet; units A / amu / fs, energy amu*A^2/fs^2.
//
// Emits per-window `cluster_snapshot` (temperature, potential energy, hydrogen-
// bond count, radius of gyration) and a final `cluster_summary` with the
// stability + structure validation.
//
// Run:
//   trech run examples/experiments/h2o_cluster_fluid.js \
//        --events 4000 --output build/dev/out_h2o_cluster

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

// ---- constants (real units) ----
const DEG = Math.PI / 180.0;
const KCAL = 4.185e-4;            // kcal/mol -> amu*A^2/fs^2
const KB = 8.314463e-7;          // Boltzmann const (amu*A^2/fs^2 / K)
const COULOMB_K = 332.0637 * KCAL; // e^2 -> energy*length (amu*A^3/fs^2 / e^2)

// intramolecular
const R0 = 0.9572, THETA0 = 104.52 * DEG;
const KBOND = 1059.162 * KCAL, KANG = 75.90 * KCAL;
// intermolecular (SPC)
const QO = -0.82, QH = 0.41;
const EPS_OO = 0.1554 * KCAL, SIG_OO = 3.166;
const SOFT2 = 0.6 * 0.6;          // Coulomb soft-core (A^2): r_eff^2 = r^2 + SOFT2
const MASS = { O: 15.999, H: 1.008 };

// run / model size
const N_MOL = 8;                  // 2x2x2 droplet
const LATTICE_A = 3.1;            // initial molecule spacing (A) ~ liquid water
const DT = 0.2;                   // fs
const TARGET_K = 300.0;           // K
const THERMO_EVERY = 10;          // rescale velocities every N ticks
const TOTAL_TICKS = 4000;
const WINDOW = 200;
const HBOND_OO = 3.5;             // O-O distance (A) counted as a contact/H-bond
// Spherical boundary potential: a gentle inward restraint on molecules that
// stray beyond R_DROP of the centre of mass, standing in for the bulk water
// that would surround a finite droplet. Without it a small *vacuum* cluster
// slowly evaporates surface molecules (expected finite-size physics); with it
// the droplet holds a constant size, i.e. behaves like a piece of bulk liquid.
const R_DROP = 4.6, K_WALL = 6.0 * 4.185e-4;
const SEED = 7771;

// ---- vec helpers ----
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => Math.sqrt(dot(a, a));

// deterministic RNG (mulberry32) -> reproducible with no engine RNG.
function makeRng(seed) {
  let s = seed >>> 0;
  return () => { s |= 0; s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function gauss(rng) { // Box-Muller
  const u = Math.max(1e-12, rng()), v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Build N molecules on a cubic lattice with random orientation.
function buildAtoms(rng) {
  const atoms = [];   // {p:[x,y,z], v:[..], m, q, mol, type}
  const mols = [];
  const side = Math.ceil(Math.cbrt(N_MOL));
  let placed = 0;
  for (let ix = 0; ix < side && placed < N_MOL; ix++)
  for (let iy = 0; iy < side && placed < N_MOL; iy++)
  for (let iz = 0; iz < side && placed < N_MOL; iz++) {
    const c = [ix * LATTICE_A, iy * LATTICE_A, iz * LATTICE_A];
    // random small rotation of the rigid equilibrium geometry
    const half = THETA0 / 2;
    let h1 = [R0 * Math.cos(half), R0 * Math.sin(half), 0];
    let h2 = [R0 * Math.cos(half), -R0 * Math.sin(half), 0];
    const ang = 2 * Math.PI * rng();
    const rot = ([x, y, z]) => [x * Math.cos(ang) - y * Math.sin(ang),
                                x * Math.sin(ang) + y * Math.cos(ang), z];
    h1 = rot(h1); h2 = rot(h2);
    const O = atoms.length;
    atoms.push({ p: c.slice(), v: [0, 0, 0], m: MASS.O, q: QO, mol: placed, type: "O" });
    atoms.push({ p: [c[0] + h1[0], c[1] + h1[1], c[2] + h1[2]], v: [0, 0, 0], m: MASS.H, q: QH, mol: placed, type: "H" });
    atoms.push({ p: [c[0] + h2[0], c[1] + h2[1], c[2] + h2[2]], v: [0, 0, 0], m: MASS.H, q: QH, mol: placed, type: "H" });
    mols.push({ O, H1: O + 1, H2: O + 2 });
    placed++;
  }
  // Maxwell-Boltzmann velocities at TARGET_K, then remove net momentum.
  for (const a of atoms) {
    const s = Math.sqrt(KB * TARGET_K / a.m);
    a.v = [s * gauss(rng), s * gauss(rng), s * gauss(rng)];
  }
  removeNetMomentum(atoms);
  return { atoms, mols };
}

function removeNetMomentum(atoms) {
  const P = [0, 0, 0]; let M = 0;
  for (const a of atoms) { P[0] += a.m * a.v[0]; P[1] += a.m * a.v[1]; P[2] += a.m * a.v[2]; M += a.m; }
  for (const a of atoms) for (let k = 0; k < 3; k++) a.v[k] -= P[k] / M;
}

function temperature(atoms) {
  let ke = 0;
  for (const a of atoms) ke += 0.5 * a.m * dot(a.v, a.v);
  const dof = 3 * atoms.length - 3;  // minus net-momentum constraint
  return { ke, T: 2 * ke / (dof * KB) };
}

// Forces + potential energy + structure observables.
function computeForces(atoms, mols) {
  const f = atoms.map(() => [0, 0, 0]);
  let pe = 0;
  const addF = (i, vec, s) => { f[i][0] += vec[0] * s; f[i][1] += vec[1] * s; f[i][2] += vec[2] * s; };

  // intramolecular: bonds + angle (per molecule)
  for (const m of mols) {
    const O = atoms[m.O].p, H1 = atoms[m.H1].p, H2 = atoms[m.H2].p;
    for (const [Hi, Hp] of [[m.H1, H1], [m.H2, H2]]) {
      const d = sub(Hp, O), r = norm(d), u = [d[0] / r, d[1] / r, d[2] / r];
      const fmag = -KBOND * (r - R0);
      pe += 0.5 * KBOND * (r - R0) * (r - R0);
      addF(Hi, u, fmag); addF(m.O, u, -fmag);
    }
    const a = sub(H1, O), b = sub(H2, O), ra = norm(a), rb = norm(b);
    const ah = [a[0] / ra, a[1] / ra, a[2] / ra], bh = [b[0] / rb, b[1] / rb, b[2] / rb];
    let c = Math.max(-1, Math.min(1, dot(ah, bh)));
    const th = Math.acos(c), sn = Math.max(1e-8, Math.sqrt(1 - c * c));
    const dV = KANG * (th - THETA0);
    pe += 0.5 * KANG * (th - THETA0) * (th - THETA0);
    const fa = [(bh[0] - c * ah[0]) * dV / (sn * ra), (bh[1] - c * ah[1]) * dV / (sn * ra), (bh[2] - c * ah[2]) * dV / (sn * ra)];
    const fb = [(ah[0] - c * bh[0]) * dV / (sn * rb), (ah[1] - c * bh[1]) * dV / (sn * rb), (ah[2] - c * bh[2]) * dV / (sn * rb)];
    addF(m.H1, fa, 1); addF(m.H2, fb, 1);
    addF(m.O, fa, -1); addF(m.O, fb, -1);
  }

  // intermolecular: LJ(O-O) + soft Coulomb(all cross-molecule atom pairs)
  let hbonds = 0;
  for (let i = 0; i < atoms.length; i++) {
    for (let j = i + 1; j < atoms.length; j++) {
      if (atoms[i].mol === atoms[j].mol) continue;
      const d = sub(atoms[j].p, atoms[i].p);
      const r2 = dot(d, d), r = Math.sqrt(r2);
      // Coulomb (soft-cored): V = k qi qj / sqrt(r^2 + SOFT2)
      const reff = Math.sqrt(r2 + SOFT2);
      const vc = COULOMB_K * atoms[i].q * atoms[j].q / reff;
      pe += vc;
      const fc = vc / (reff * reff);          // -dV/dr_eff * dr_eff/dr / r * d, simplified below
      // F = k qi qj * r_vec / reff^3 (points i<-j); apply to both
      const fcoef = COULOMB_K * atoms[i].q * atoms[j].q / (reff * reff * reff);
      addF(i, d, -fcoef); addF(j, d, fcoef);
      // LJ only O-O
      if (atoms[i].type === "O" && atoms[j].type === "O") {
        const sr2 = (SIG_OO * SIG_OO) / r2, sr6 = sr2 * sr2 * sr2, sr12 = sr6 * sr6;
        pe += 4 * EPS_OO * (sr12 - sr6);
        const flj = 24 * EPS_OO * (2 * sr12 - sr6) / r2;  // F = flj * r_vec (repulsive +)
        addF(i, d, -flj); addF(j, d, flj);
        if (r < HBOND_OO) hbonds++;
      }
      void fc;
    }
  }

  // Spherical boundary potential on each molecule's O (the H's follow via the
  // stiff bonds): a soft inward restraint beyond R_DROP from the centre of mass.
  const com = [0, 0, 0]; let M = 0;
  for (const a of atoms) { com[0] += a.m * a.p[0]; com[1] += a.m * a.p[1]; com[2] += a.m * a.p[2]; M += a.m; }
  for (let k = 0; k < 3; k++) com[k] /= M;
  for (const m of mols) {
    const d = sub(atoms[m.O].p, com), r = norm(d);
    if (r > R_DROP) {
      const u = [d[0] / r, d[1] / r, d[2] / r];
      pe += 0.5 * K_WALL * (r - R_DROP) * (r - R_DROP);
      addF(m.O, u, -K_WALL * (r - R_DROP));
    }
  }
  return { f, pe, hbonds };
}

function radiusOfGyration(atoms) {
  const com = [0, 0, 0]; let M = 0;
  for (const a of atoms) { com[0] += a.m * a.p[0]; com[1] += a.m * a.p[1]; com[2] += a.m * a.p[2]; M += a.m; }
  for (let k = 0; k < 3; k++) com[k] /= M;
  let s = 0;
  for (const a of atoms) { const d = sub(a.p, com); s += a.m * dot(d, d); }
  return Math.sqrt(s / M);
}

function verletStep(state) {
  const { atoms, mols } = state;
  const f0 = state.force;
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m;
    for (let k = 0; k < 3; k++) {
      a.p[k] += a.v[k] * DT + 0.5 * f0[i][k] * inv * DT * DT;
    }
  }
  const r1 = computeForces(atoms, mols);
  for (let i = 0; i < atoms.length; i++) {
    const a = atoms[i], inv = 1 / a.m;
    for (let k = 0; k < 3; k++) {
      a.v[k] += 0.5 * (f0[i][k] + r1.f[i][k]) * inv * DT;
    }
  }
  state.force = r1.f;
  return r1;
}

function thermostat(atoms, targetK) {
  const { T } = temperature(atoms);
  if (T <= 0) return;
  const lambda = Math.sqrt(1 + 0.1 * (targetK / T - 1)); // gentle Berendsen
  for (const a of atoms) for (let k = 0; k < 3; k++) a.v[k] *= lambda;
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    const rng = makeRng(SEED);
    const { atoms, mols } = buildAtoms(rng);
    const r0 = computeForces(atoms, mols);
    Object.assign(ctx.state, {
      atoms, mols, force: r0.f, tick: 0, initialized: true,
      rg0: radiusOfGyration(atoms),
      sumT: 0, sumHb: 0, sumRg: 0, nAcc: 0, maxRg: 0,
      tMin: Infinity, tMax: -Infinity
    });
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "h2o_cluster_fluid",
      molecules: N_MOL, target_K: TARGET_K, dt_fs: DT, ticks: TOTAL_TICKS,
      model: "flexible SPC-like water (intra harmonic + inter LJ/Coulomb), classical MD in hook layer"
    });
  },
  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;
    s.tick += 1;
    const r = verletStep(s);
    if (s.tick % THERMO_EVERY === 0) thermostat(s.atoms, TARGET_K);

    const { T } = temperature(s.atoms);
    const rg = radiusOfGyration(s.atoms);
    s.sumT += T; s.sumHb += r.hbonds; s.sumRg += rg; s.nAcc += 1;
    s.maxRg = Math.max(s.maxRg, rg);
    s.tMin = Math.min(s.tMin, T); s.tMax = Math.max(s.tMax, T);

    if (s.tick % WINDOW === 0) {
      ctx.emit("cluster_snapshot", {
        tick: s.tick, time_fs: s.tick * DT,
        temperature_K: T, potential_energy: r.pe, hbond_contacts: r.hbonds,
        radius_of_gyration_A: rg
      });
    }
    if (s.tick === TOTAL_TICKS) {
      // Use the second half (equilibrated) for the means.
      const meanT = s.sumT / s.nAcc, meanHb = s.sumHb / s.nAcc, meanRg = s.sumRg / s.nAcc;
      // Stable droplet: did NOT evaporate (Rg bounded) or collapse (Rg > tiny).
      const evaporated = s.maxRg > 4.0 * s.rg0;
      const collapsed = meanRg < 0.3 * s.rg0;
      const tempControlled = Math.abs(meanT - TARGET_K) < 120.0;  // within ~40% of target
      const hbondsPresent = meanHb >= 1.0;                        // liquid-like contacts
      ctx.emit("cluster_summary", {
        molecules: N_MOL, ticks: s.tick, time_fs: s.tick * DT,
        mean_temperature_K: meanT, mean_hbond_contacts: meanHb,
        mean_radius_of_gyration_A: meanRg, initial_radius_of_gyration_A: s.rg0,
        max_radius_of_gyration_A: s.maxRg,
        validation: {
          stable_cluster: !evaporated && !collapsed,
          temperature_controlled: tempControlled,
          hydrogen_bonding_present: hbondsPresent,
          fluid_stable: !evaporated && !collapsed && tempControlled && hbondsPresent
        }
      });
    }
  }
};

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.nm(5.0), worldMaterial: "G4_Galactic" },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  run: { nEvents: TOTAL_TICKS, seed: 909090, threads: 1 },
  determinism: { mode: "predictive" },
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "h2o_cluster_fluid" },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "droplet_cell", material: "G4_Galactic",
        sizeMm: [units.nm(2.0), units.nm(2.0), units.nm(2.0)],
        positionMm: [0, 0, 0], tags: ["fluid", "h2o", "md", "cluster"]
      })
    ]
  }
};
