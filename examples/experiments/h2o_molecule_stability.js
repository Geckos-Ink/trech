// Sputnik north-star item: simulate a single H2O molecule and show that its
// bonds are STABLE OVER TIME -- it oscillates around its equilibrium geometry
// without "exploding" (atoms flying apart).
//
// Honest framing: Geant4 transports elementary particles but does NOT form or
// evolve molecular bonds (a bound H2O molecule is a quantum/classical-MD
// object, not a particle-transport one). So the molecule here is evolved by a
// classical molecular-dynamics integrator in the deterministic hook layer (the
// same one-tick-per-Geant4-event pattern as testscenario_pascal/osmotic), with
// the three nuclei (O, H, H) as point masses bound by a flexible-water force
// field. The classical force field is the "physics for comparison"; the test is
// whether the integrated trajectory stays bound and energy-conserving.
//
// Model (flexible water, harmonic):
//   - O-H bonds: V = 1/2 k_b (r - r0)^2,  r0 = 0.9572 A (gas-phase water)
//   - H-O-H angle: V = 1/2 k_a (theta - theta0)^2, theta0 = 104.52 deg
//   - velocity-Verlet integration (NVE: total energy conserved)
//   - masses O = 15.999, H = 1.008 amu; length A, time fs, energy amu*A^2/fs^2
// The molecule starts at equilibrium with a deliberate stretch+bend kick so both
// the symmetric-stretch and bend modes ring; a stable integrator keeps the
// total energy flat and the bonds bounded near r0 forever.
//
// Run:
//   trech run examples/experiments/h2o_molecule_stability.js \
//        --events 2000 --output build/dev/out_h2o_molecule
// Inspect: trech_hook_emits.jsonl carries per-window `molecule_snapshot` and a
// final `molecule_summary` with bond/angle/energy stability metrics.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

// ---- physical constants (real water, classical flexible model) ----
const DEG = Math.PI / 180.0;
const KCAL = 4.185e-4;          // kcal/mol -> amu*A^2/fs^2
const R0 = 0.9572;              // O-H equilibrium length (A)
const THETA0 = 104.52 * DEG;    // H-O-H equilibrium angle (rad)
const KB = 1059.162 * KCAL;     // O-H bond force constant (amu/fs^2)
const KA = 75.90 * KCAL;        // H-O-H angle force constant (amu*A^2/fs^2 /rad^2)
const MASS = { O: 15.999, H: 1.008 };
const DT = 0.2;                 // integration timestep (fs)
const TOTAL_TICKS = 2000;
const WINDOW = 100;             // emit a snapshot every WINDOW ticks

// ---- tiny 3-vector helpers ----
const v = (x, y, z) => ({ x, y, z });
const add = (a, b) => v(a.x + b.x, a.y + b.y, a.z + b.z);
const sub = (a, b) => v(a.x - b.x, a.y - b.y, a.z - b.z);
const scale = (a, s) => v(a.x * s, a.y * s, a.z * s);
const dot = (a, b) => a.x * b.x + a.y * b.y + a.z * b.z;
const norm = (a) => Math.sqrt(dot(a, a));
const unit = (a) => { const n = norm(a); return n > 0 ? scale(a, 1 / n) : v(0, 0, 0); };

// Equilibrium geometry: O at origin, H1/H2 symmetric in the xy-plane.
function equilibriumPositions() {
  const half = THETA0 / 2;
  return {
    O: v(0, 0, 0),
    H1: v(R0 * Math.cos(half), R0 * Math.sin(half), 0),
    H2: v(R0 * Math.cos(half), -R0 * Math.sin(half), 0)
  };
}

// Forces + potential energy + geometry observables for a configuration.
function computeForces(pos) {
  let fO = v(0, 0, 0), fH1 = v(0, 0, 0), fH2 = v(0, 0, 0);
  let pe = 0.0;

  // Two O-H bonds.
  const bond = (Hpos) => {
    const d = sub(Hpos, pos.O);
    const r = norm(d);
    const dir = scale(d, 1 / r);
    const stretch = r - R0;
    pe += 0.5 * KB * stretch * stretch;
    const fH = scale(dir, -KB * stretch);   // pulls H back toward r0
    return { fH, fO: scale(fH, -1), r };
  };
  const b1 = bond(pos.H1);
  const b2 = bond(pos.H2);
  fH1 = add(fH1, b1.fH); fO = add(fO, b1.fO);
  fH2 = add(fH2, b2.fH); fO = add(fO, b2.fO);

  // H-O-H angle (standard harmonic-angle force).
  const a = sub(pos.H1, pos.O), b = sub(pos.H2, pos.O);
  const ra = norm(a), rb = norm(b);
  const aHat = scale(a, 1 / ra), bHat = scale(b, 1 / rb);
  let cosT = dot(aHat, bHat);
  cosT = Math.max(-1, Math.min(1, cosT));
  const theta = Math.acos(cosT);
  const sinT = Math.max(1e-8, Math.sqrt(1 - cosT * cosT));
  const dV = KA * (theta - THETA0);
  pe += 0.5 * KA * (theta - THETA0) * (theta - THETA0);
  const fa = scale(sub(bHat, scale(aHat, cosT)), dV / (sinT * ra));
  const fb = scale(sub(aHat, scale(bHat, cosT)), dV / (sinT * rb));
  fH1 = add(fH1, fa);
  fH2 = add(fH2, fb);
  fO = sub(fO, add(fa, fb));

  return { fO, fH1, fH2, pe, bond1: b1.r, bond2: b2.r, angle: theta };
}

function kineticEnergy(vel) {
  return 0.5 * (MASS.O * dot(vel.O, vel.O) +
                MASS.H * dot(vel.H1, vel.H1) +
                MASS.H * dot(vel.H2, vel.H2));
}

// Velocity-Verlet step (NVE). Mutates pos/vel in state, returns observables.
function verletStep(state) {
  const { pos, vel } = state;
  const f0 = state.force;
  const accel = (f, m) => scale(f, 1 / m);
  // r(t+dt) = r + v dt + 1/2 a dt^2
  const aO = accel(f0.fO, MASS.O), aH1 = accel(f0.fH1, MASS.H), aH2 = accel(f0.fH2, MASS.H);
  pos.O = add(pos.O, add(scale(vel.O, DT), scale(aO, 0.5 * DT * DT)));
  pos.H1 = add(pos.H1, add(scale(vel.H1, DT), scale(aH1, 0.5 * DT * DT)));
  pos.H2 = add(pos.H2, add(scale(vel.H2, DT), scale(aH2, 0.5 * DT * DT)));
  const f1 = computeForces(pos);
  // v(t+dt) = v + 1/2 (a(t) + a(t+dt)) dt
  const aO1 = accel(f1.fO, MASS.O), aH11 = accel(f1.fH1, MASS.H), aH21 = accel(f1.fH2, MASS.H);
  vel.O = add(vel.O, scale(add(aO, aO1), 0.5 * DT));
  vel.H1 = add(vel.H1, scale(add(aH1, aH11), 0.5 * DT));
  vel.H2 = add(vel.H2, scale(add(aH2, aH21), 0.5 * DT));
  state.force = f1;
  const ke = kineticEnergy(vel);
  return { bond1: f1.bond1, bond2: f1.bond2, angle: f1.angle, pe: f1.pe, ke, etot: f1.pe + ke };
}

function initState() {
  const pos = equilibriumPositions();
  // Deliberate kick: stretch the H1 bond +0.20 A and bend H2 by +6 deg so both
  // the stretch and bend modes are excited (a clean, reproducible perturbation;
  // no RNG, so the run is exactly reproducible).
  pos.H1 = scale(unit(pos.H1), R0 + 0.20);
  const bendBy = 6.0 * DEG;
  const half = THETA0 / 2 + bendBy;
  pos.H2 = v(R0 * Math.cos(-half), R0 * Math.sin(-half), 0);
  const vel = { O: v(0, 0, 0), H1: v(0, 0, 0), H2: v(0, 0, 0) };
  const force = computeForces(pos);
  return {
    pos, vel, force, tick: 0, initialized: true,
    e0: force.pe,                 // initial (all-potential) total energy
    maxBond: Math.max(force.bond1, force.bond2),
    minBond: Math.min(force.bond1, force.bond2),
    sumBond: 0, sumAngle: 0, nAcc: 0,
    etotMin: Infinity, etotMax: -Infinity
  };
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    throw new Error("hook ctx.state unavailable");
  }
  if (!ctx.state.initialized) {
    Object.assign(ctx.state, initState());
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "h2o_molecule_stability",
      model: "flexible harmonic water (classical MD in hook layer)",
      r0_A: R0, theta0_deg: THETA0 / DEG, dt_fs: DT, ticks: TOTAL_TICKS
    });
  },

  onEventStart(ctx) {
    const state = ensureState(ctx);
    if (!ctx.event) return;
    state.tick += 1;
    const obs = verletStep(state);

    state.maxBond = Math.max(state.maxBond, obs.bond1, obs.bond2);
    state.minBond = Math.min(state.minBond, obs.bond1, obs.bond2);
    state.sumBond += 0.5 * (obs.bond1 + obs.bond2);
    state.sumAngle += obs.angle;
    state.nAcc += 1;
    state.etotMin = Math.min(state.etotMin, obs.etot);
    state.etotMax = Math.max(state.etotMax, obs.etot);

    if (state.tick % WINDOW === 0) {
      ctx.emit("molecule_snapshot", {
        tick: state.tick, time_fs: state.tick * DT,
        bond1_A: obs.bond1, bond2_A: obs.bond2, angle_deg: obs.angle / DEG,
        pe: obs.pe, ke: obs.ke, etot: obs.etot
      });
    }

    if (state.tick === TOTAL_TICKS) {
      const meanBond = state.sumBond / state.nAcc;
      const meanAngle = state.sumAngle / state.nAcc / DEG;
      // Energy drift relative to the initial energy (NVE => should be ~0).
      const energyDrift = Math.abs(state.etotMax - state.etotMin) / Math.abs(state.e0);
      // "Exploded" if any bond ever exceeded 1.6x its equilibrium length.
      const exploded = state.maxBond > 1.6 * R0;
      const bondsStable = !exploded &&
                          Math.abs(meanBond - R0) < 0.15 &&
                          Math.abs(meanAngle - THETA0 / DEG) < 8.0;
      const energyConserved = energyDrift < 0.02;   // <2% over the whole run
      ctx.emit("molecule_summary", {
        ticks: state.tick, time_fs: state.tick * DT,
        mean_bond_A: meanBond, max_bond_A: state.maxBond, min_bond_A: state.minBond,
        mean_angle_deg: meanAngle,
        energy_drift_fraction: energyDrift,
        validation: {
          stable_without_exploding: bondsStable && energyConserved,
          bonds_stable: bondsStable,
          energy_conserved: energyConserved,
          exploded: exploded
        }
      });
    }
  }
};

// The Geant4 side is just a deterministic per-event clock (geantino, no
// transport). threads:1 keeps the one-tick-per-event MD reproducible.
globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.nm(2.0), worldMaterial: "G4_Galactic" },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  run: { nEvents: TOTAL_TICKS, seed: 18181818, threads: 1 },
  determinism: { mode: "predictive" },
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "h2o_molecule_stability" },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "molecule_cell",
        material: "G4_Galactic",
        sizeMm: [units.nm(1.0), units.nm(1.0), units.nm(1.0)],
        positionMm: [0, 0, 0],
        tags: ["molecule", "h2o", "md"]
      })
    ]
  }
};
