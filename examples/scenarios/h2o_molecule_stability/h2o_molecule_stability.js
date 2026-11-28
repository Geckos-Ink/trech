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
//   trech run examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js \
//        --events 2000 --output build/dev/out_h2o_molecule
// Inspect: trech_hook_emits.jsonl carries per-window `molecule_snapshot` and a
// final `molecule_summary` with bond/angle/energy stability metrics.

TRECH_INCLUDE("../../../js/trech_helpers.js");
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
const FRAME_EVERY = 2;          // emit a 3D material_frame every FRAME_EVERY ticks
const observer = helpers.observer;

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

// ---- thermal ensemble and vibrational spectrum -------------------------------------------------
// After the stability run, the same force field is sampled as a thermal ensemble: REPLICAS copies
// start at the equilibrium geometry with Maxwell-Boltzmann velocities at ENSEMBLE_T (ctx.rng), lose
// their centre-of-mass and rigid-rotation parts, and are scaled to the canonical mean vibrational
// energy 3 kT (three harmonic modes, potential energy zero at equilibrium), so equipartition gives a
// kinetic temperature of ENSEMBLE_T. Each replica runs SPECTRUM_STEPS velocity-Verlet steps; the
// power spectra of the symmetric-stretch, antisymmetric-stretch and bend coordinates, summed over
// replicas, locate the molecule's vibrational frequencies. These are this classical force field's
// frequencies (the physics for comparison); the validation companion grades them.
const KB_AMU = 8.31446262e-7;      // Boltzmann constant in amu*A^2/fs^2 per K
const C_CM_PER_FS = 2.99792458e-5; // speed of light, cm/fs (frequency in fs^-1 -> cm^-1)
const ENSEMBLE_T = 300.0;
const REPLICAS = 8;
const SPECTRUM_STEPS = 8192;       // per replica: 1.64 ps at 0.2 fs, 20.4 cm^-1 bins
const BANDS_CM1 = { bend: [1000, 2400], symmetric_stretch: [2800, 4800], antisymmetric_stretch: [2800, 4800] };

const cross = (a, b) => v(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);

// Remove centre-of-mass velocity and rigid rotation (omega = I^-1 L about the centre of mass).
function removeRigidMotion(pos, vel) {
  const atoms = [["O", MASS.O], ["H1", MASS.H], ["H2", MASS.H]];
  const total = MASS.O + 2 * MASS.H;
  let com = v(0, 0, 0), p = v(0, 0, 0);
  for (const [k, m] of atoms) { com = add(com, scale(pos[k], m / total)); p = add(p, scale(vel[k], m)); }
  for (const [k] of atoms) vel[k] = sub(vel[k], scale(p, 1 / total));
  let L = v(0, 0, 0);
  const I = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const [k, m] of atoms) {
    const r = sub(pos[k], com);
    L = add(L, scale(cross(r, vel[k]), m));
    const rr = dot(r, r), c = [r.x, r.y, r.z];
    for (let i = 0; i < 3; i += 1) {
      for (let j = 0; j < 3; j += 1) I[i][j] += m * ((i === j ? rr : 0) - c[i] * c[j]);
    }
  }
  const det = I[0][0] * (I[1][1] * I[2][2] - I[1][2] * I[2][1]) -
              I[0][1] * (I[1][0] * I[2][2] - I[1][2] * I[2][0]) +
              I[0][2] * (I[1][0] * I[2][1] - I[1][1] * I[2][0]);
  const solve = (col) => {  // Cramer: replace column `col` of I with L
    const M = I.map((row) => row.slice());
    const l = [L.x, L.y, L.z];
    for (let i = 0; i < 3; i += 1) M[i][col] = l[i];
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) -
            M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0]) +
            M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0])) / det;
  };
  const omega = v(solve(0), solve(1), solve(2));
  for (const [k] of atoms) vel[k] = sub(vel[k], cross(omega, sub(pos[k], com)));
}

// In-place iterative radix-2 FFT (n a power of two).
function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k += 1) {
        const a = i + k, b = a + len / 2;
        const xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
        const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
      }
    }
  }
}

// Adds the Hann-windowed power spectrum of `series` (mean removed) into `power`.
function accumulatePower(series, power) {
  const n = series.length;
  let mean = 0;
  for (let i = 0; i < n; i += 1) mean += series[i] / n;
  const re = new Float64Array(n), im = new Float64Array(n);
  for (let i = 0; i < n; i += 1) re[i] = (series[i] - mean) * 0.5 * (1 - Math.cos(2 * Math.PI * i / (n - 1)));
  fft(re, im);
  for (let k = 0; k <= n / 2; k += 1) power[k] += re[k] * re[k] + im[k] * im[k];
}

// Strongest bin inside a band, refined by a parabola through the log power of its neighbours.
function peakCm1(power, band, binCm1) {
  let best = -1;
  for (let k = Math.ceil(band[0] / binCm1); k <= Math.floor(band[1] / binCm1) && k < power.length - 1; k += 1) {
    if (best < 0 || power[k] > power[best]) best = k;
  }
  const l = Math.log(power[best - 1]), c = Math.log(power[best]), r = Math.log(power[best + 1]);
  const delta = (l - 2 * c + r) !== 0 ? 0.5 * (l - r) / (l - 2 * c + r) : 0;
  return (best + delta) * binCm1;
}

function thermalSpectrum(rng) {
  const powers = { symmetric_stretch: new Float64Array(SPECTRUM_STEPS / 2 + 1),
                   antisymmetric_stretch: new Float64Array(SPECTRUM_STEPS / 2 + 1),
                   bend: new Float64Array(SPECTRUM_STEPS / 2 + 1) };
  let keSum = 0, keCount = 0, worstDrift = 0;
  for (let rep = 0; rep < REPLICAS; rep += 1) {
    const pos = equilibriumPositions();
    const draw = (m) => { const s = Math.sqrt(KB_AMU * ENSEMBLE_T / m); return v(rng.normal(0, s), rng.normal(0, s), rng.normal(0, s)); };
    const vel = { O: draw(MASS.O), H1: draw(MASS.H), H2: draw(MASS.H) };
    removeRigidMotion(pos, vel);
    const f = Math.sqrt(3 * KB_AMU * ENSEMBLE_T / kineticEnergy(vel));
    for (const k of ["O", "H1", "H2"]) vel[k] = scale(vel[k], f);
    const replica = { pos, vel, force: computeForces(pos) };
    const e0 = kineticEnergy(vel);
    const sym = new Float64Array(SPECTRUM_STEPS), asym = new Float64Array(SPECTRUM_STEPS);
    const bend = new Float64Array(SPECTRUM_STEPS);
    let eMin = Infinity, eMax = -Infinity;
    for (let i = 0; i < SPECTRUM_STEPS; i += 1) {
      const obs = verletStep(replica);
      sym[i] = 0.5 * (obs.bond1 + obs.bond2);
      asym[i] = 0.5 * (obs.bond1 - obs.bond2);
      bend[i] = obs.angle;
      keSum += obs.ke; keCount += 1;
      eMin = Math.min(eMin, obs.etot); eMax = Math.max(eMax, obs.etot);
    }
    worstDrift = Math.max(worstDrift, (eMax - eMin) / e0);
    accumulatePower(sym, powers.symmetric_stretch);
    accumulatePower(asym, powers.antisymmetric_stretch);
    accumulatePower(bend, powers.bend);
  }
  const binCm1 = 1 / (SPECTRUM_STEPS * DT * C_CM_PER_FS);
  const peaks = {};
  for (const mode of Object.keys(BANDS_CM1)) peaks[mode] = peakCm1(powers[mode], BANDS_CM1[mode], binCm1);
  return {
    temperature_target_k: ENSEMBLE_T,
    // Three vibrational degrees of freedom after removing translation and rotation.
    temperature_kinetic_k: 2 * (keSum / keCount) / (3 * KB_AMU),
    replicas: REPLICAS, steps_per_replica: SPECTRUM_STEPS, dt_fs: DT,
    duration_ps_per_replica: SPECTRUM_STEPS * DT / 1000,
    bin_cm1: binCm1,
    worst_energy_drift_fraction: worstDrift,
    peaks_cm1: peaks,
    method: "Hann-windowed FFT power of internal coordinates, summed over replicas; parabolic peak refinement"
  };
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

    // The integrated nuclei themselves, for the classic 3D viewer / Studio. Every 2 ticks
    // (0.4 fs) resolves the ~9 fs O-H stretch; positions are the Verlet state, unmodified.
    if (state.tick % FRAME_EVERY === 0) {
      const at = (el, p) => ({ el, pos: [p.x, p.y, p.z] });
      const molecule = observer.atoms([{
        atoms: [at("O", state.pos.O), at("H", state.pos.H1), at("H", state.pos.H2)],
        bonds: [[0, 1], [0, 2]]
      }]);
      ctx.emit("material_frame", TRECH_VIEWS["h2o_molecule_stability"]["frame0"](DEG, DT, FRAME_EVERY, R0, THETA0, TOTAL_TICKS, molecule, obs, observer, state));
    }

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
        validation: TRECH_CHECKS["h2o_molecule_stability"]["checks0"](bondsStable, energyConserved, exploded)
      });
      const spectrum = thermalSpectrum(ctx.rng);
      spectrum.validation = TRECH_CHECKS["h2o_molecule_stability"]["spectrum0"](
        spectrum, { kb: KB, ka: KA, r0: R0, theta0: THETA0, mass: MASS, cCmPerFs: C_CM_PER_FS });
      ctx.emit("molecule_spectrum", spectrum);
    }
  }
};

// The Geant4 side is just a deterministic per-event clock (geantino, no
// transport). threads:1 keeps the one-tick-per-event MD reproducible.
globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm: units.nm(2.0), worldMaterial: "G4_Galactic" },
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
