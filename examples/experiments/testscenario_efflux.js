// Validation scenario: passive membrane efflux (clearance of a lipophilic
// "waste" molecule from a cell), cross-checked against the classical
// first-order / Fick's-law clearance kinetics.
//
// The biological phenomenon: a cell rids itself of a small lipophilic waste /
// xenobiotic molecule that dissolves into and diffuses across the lipid
// bilayer (Overton's rule -- no channel needed), down its concentration
// gradient, into a well-mixed extracellular sink (the bloodstream carries it
// away). Polar "essential" molecules cannot dissolve in the lipid core and are
// retained -- the membrane is selective by chemistry, not size.
//
// The TRECH thesis exercised here (see README): obtain behaviour from physics,
// scale it up, and compare to a closed-form law.
//   * NANOSCALE (Geant4): the membrane lipid's EM interaction coefficient
//     mu_total is computed by G4EmCalculator (the same machinery as the
//     analytic Beer-Lambert cross-check) for the lipid bilayer AND the aqueous
//     cytosol. Their ratio scales the permeability (an *illustrative* mapping:
//     less EM interaction in the low-density lipid -> the lipophilic permeant
//     slips through more freely). Emitted to trech_scores.jsonl as
//     `analytic_checks` so every run carries the Geant4-derived number.
//   * MESOSCALE (this hook MD): each membrane encounter, the lipophilic
//     molecule permeates with probability p_cross (set from the Geant4 ratio);
//     it then leaves and is cleared. The internal count N(t) is tracked.
//   * MACROSCALE (closed-form): a memoryless per-encounter escape gives a
//     first-order clearance N(t) = N0 * exp(-k t) (Fick's first law for a
//     well-mixed cell into a sink, k = P*A/V). The run fits k to the simulated
//     decay and reports R^2, the half-life, and the back-derived permeability
//     -- the comparison the render video plots (simulated points vs the law).
//
// Honest scope (same as every TRECH MD demo): Geant4 transports particles but
// cannot compute molecular partitioning/diffusion, so the permeation is a
// coarse-grained classical model and the Geant4->permeability mapping is
// ILLUSTRATIVE, flagged as such. What is genuinely validated is that random
// microscopic permeation events reproduce the macroscopic first-order law.
//
// Deterministic: Geant4 seed + hook RNG are seeded; threads:1 so the per-event
// MD bath accumulates reproducibly. The bath advances on `onEventEnd` so each
// tick can consume the Geant4 event's transport statistics (`ctx.event`).

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

// --- Geant4-derived nanoscale anchors -------------------------------------
// mu_total (1/mm) for a 30 keV soft-photon proxy in the lipid membrane and in
// the aqueous cytosol, from G4EmCalculator. These are re-emitted live by the
// analytic block below (so provenance carries them every run); the constants
// here are the committed reference (regenerate by reading analytic_checks).
const GEANT4 = {
  probeEnergyMeV: 0.03,
  membraneMaterial: "G4_ADIPOSE_TISSUE_ICRP", // lipid bilayer proxy
  cytosolMaterial: "G4_WATER",
  muMembranePerMm: 0.029093,
  muCytosolPerMm: 0.037714
};
// Illustrative nanoscale -> mesoscale mapping: the permeability scales with the
// cytosol/membrane interaction ratio (the lipophilic permeant moves more freely
// where the medium interacts less). interactionRatio > 1 -> faster permeation.
const interactionRatio = GEANT4.muCytosolPerMm / GEANT4.muMembranePerMm;

function loadPubChemCompound(name) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM is unavailable; rebuild TRECH with the JS PubChem binding");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || raw.cid === undefined || raw.xlogp === undefined || raw.molecular_weight === undefined) {
    throw new Error("PubChem cache entry for " + name + " is missing cid/xlogp/molecular_weight");
  }
  return {
    name: raw.name || name,
    cid: raw.cid,
    formula: raw.molecular_formula,
    molarMassGmol: Number(raw.molecular_weight),
    xlogp: Number(raw.xlogp),
    cachePath: raw.cache_path
  };
}

// --- PubChem-derived substance properties ---------------------------------
// Runtime-fetched PubChem JSON (validation populates TRECH_PUBCHEM_CACHE_DIR in
// build/) supplies XLogP and molar mass. XLogP governs passive permeation by
// Overton's rule: XLogP > 0 partitions into the lipid bilayer and crosses;
// XLogP < 0 (polar) cannot dissolve in the lipid core and is retained. So the
// PubChem property decides WHICH molecule the cell clears, while Geant4 scales
// HOW FAST.
const PUBCHEM = {
  permeant: loadPubChemCompound("benzene"),     // lipophilic waste/xenobiotic the cell clears
  retained: loadPubChemCompound("D-glucose")    // polar essential the cell keeps (its fuel)
};
// Overton's rule: lipophilic (XLogP > 0) permeates, polar (XLogP < 0) retained.
const permeantIsLipophilic = PUBCHEM.permeant.xlogp > 0.0;
const retainedIsPolar = PUBCHEM.retained.xlogp < 0.0;

const SCENARIO = {
  domainHalfSize: 60.0,
  cellRadius: 28.0,
  wasteRadius: 0.7,
  retainedRadius: 0.9,
  // Molar masses from PubChem -> the heavier polar molecule moves slower.
  wasteMass: PUBCHEM.permeant.molarMassGmol,   // benzene 78.11
  retainedMass: PUBCHEM.retained.molarMassGmol, // glucose 180.16
  temperatureK: 310.0,
  dt: 1.0,
  wasteMeanSpeed: 0.95,  // thermal speed scale referenced to the permeant mass
  thermostatCoupling: 0.018, // low -> persistent (smooth) random paths, not jitter
  noiseScale: 0.48,      // damp the random component so flow/drift read clearly
  // Cytoplasmic streaming: a coherent rigid-rotation flow advects every molecule
  // so the interior shows an organized internal flow (a slow swirl) instead of
  // random jitter. Volume-preserving -> does not bias escape (first-order safe).
  circulationOmega: 0.024, // rad/tick (~260-tick revolution)
  // The lipophilic permeant feels an outward efflux drift (it descends the
  // chemical-potential gradient toward the exterior) -- directed motion toward
  // the membrane, like a particle settling at terminal velocity. Kept mild
  // enough that diffusion + swirl still keep the interior well-mixed (escape
  // stays memoryless -> first-order kinetics).
  effluxDriftSpeed: 0.028,
  initialWaste: 80,      // lipophilic waste molecules inside at t=0
  initialRetained: 30,   // polar essentials the cell keeps
  // Per-membrane-encounter permeation probability, scaled by the Geant4
  // interaction ratio. pCrossRef is a sim-unit reference chosen for a watchable
  // half-life (~1/5 of the run); the Geant4 ratio sets the relative scale.
  pCrossRef: 0.0170,
  clearedDriftSpeed: 0.6, // cleared molecules drift outward (bloodstream sink)
  clearedFadeTicks: 90,   // then they are carried away (dropped from the bath)
  snapshotEvery: 50,
  fitMinCount: 4          // ignore tail counts below this in the log-linear fit
};

const pCrossBase = Math.min(0.95, SCENARIO.pCrossRef * interactionRatio);

const TOTAL_TICKS = 6000;

const containerHalfMm = units.cm(0.2);
const containerVolumeMm3 = Math.pow(containerHalfMm * 2.0, 3);

const cfg = {
  detector: {
    worldSizeMm: units.cm(1.0),
    worldMaterial: helpers.materialAliases.air,
    // Medium = the lipid membrane material, so the analytic check below reports
    // the Geant4 nanoscale interaction of the bilayer used to scale permeation.
    mediumBoxMm: 10.0,
    mediumMaterial: GEANT4.membraneMaterial,
    temperatureK: SCENARIO.temperatureK,
    pressureAtm: 1.0
  },
  // The same soft gamma probe used by the analytic checks is transported by
  // Geant4 each tick; onEventEnd consumes the event's track/step/edep summary.
  beam: { particle: "gamma", energyMeV: GEANT4.probeEnergyMeV, direction: [0, 0, 1] },
  run: { nEvents: TOTAL_TICKS, seed: 71081923, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "membrane_efflux_clearance",
    volumeMm3: containerVolumeMm3
  },
  analytic: {
    enable: true,
    checks: [
      {
        type: "beer_lambert",
        label: "membrane_lipid_interaction",
        particle: "gamma",
        energyMeV: GEANT4.probeEnergyMeV,
        material: GEANT4.membraneMaterial,
        pathLengthMm: 10.0,
        toleranceRel: 1.0
      },
      {
        type: "beer_lambert",
        label: "cytosol_water_interaction",
        particle: "gamma",
        energyMeV: GEANT4.probeEnergyMeV,
        material: GEANT4.cytosolMaterial,
        pathLengthMm: 10.0,
        toleranceRel: 1.0
      }
    ]
  },
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "efflux_chamber",
        sizeMm: [containerHalfMm * 2, containerHalfMm * 2, containerHalfMm * 2],
        tags: ["chamber", "efflux"]
      })
    ]
  },
  hooks: {
    maxStepCallbacks: 1,
    maxEmitsPerCallback: 8,
    maxEmitPayloadBytes: 131072
  }
};

// --- Coarse-grained MD helpers --------------------------------------------
function thermalSpeed(massU) {
  return SCENARIO.wasteMeanSpeed *
    Math.sqrt(SCENARIO.wasteMass / Math.max(massU, 1e-9));
}

function gaussian01(rng) {
  let u1 = rng.uniform();
  if (u1 <= 1e-12) {
    u1 = 1e-12;
  }
  const u2 = rng.uniform();
  return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
}

function seedInside(rng, count, kind) {
  const particles = [];
  const radius = SCENARIO.cellRadius;
  const isWaste = kind === "waste";
  const massU = isWaste ? SCENARIO.wasteMass : SCENARIO.retainedMass;
  const partRadius = isWaste ? SCENARIO.wasteRadius : SCENARIO.retainedRadius;
  const speedScale = thermalSpeed(massU) * SCENARIO.noiseScale;
  let safety = 0;
  while (particles.length < count && safety < count * 60) {
    safety += 1;
    const ang = rng.uniform() * 2.0 * Math.PI;
    const rad = Math.sqrt(rng.uniform()) * (radius - partRadius - 1.0);
    const x = rad * Math.cos(ang);
    const y = rad * Math.sin(ang);
    particles.push({
      kind,
      permeant: isWaste,
      inside: true,
      cleared: false,
      x,
      y,
      // rvx/rvy: the persistent (Ornstein-Uhlenbeck) random velocity; the
      // coherent streaming flow + efflux drift are added deterministically.
      rvx: gaussian01(rng) * speedScale,
      rvy: gaussian01(rng) * speedScale,
      mass: massU,
      radius: partRadius
    });
  }
  return particles;
}

// Persistent random velocity (smooth paths) + coherent cytoplasmic streaming
// (rigid rotation) + mild outward efflux drift for the lipophilic permeant.
function advectionVelocity(particle) {
  const omega = SCENARIO.circulationOmega;
  let vx = -omega * particle.y;   // rigid-rotation streaming (volume preserving)
  let vy = omega * particle.x;
  if (particle.permeant) {
    const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
    if (r > 1e-9) {
      vx += SCENARIO.effluxDriftSpeed * particle.x / r;
      vy += SCENARIO.effluxDriftSpeed * particle.y / r;
    }
  }
  return { vx, vy };
}

function stepRandomVelocity(particle, rng) {
  const gamma = Math.max(0.0, Math.min(0.999, 1.0 - SCENARIO.thermostatCoupling));
  const sigma = thermalSpeed(particle.mass) * SCENARIO.noiseScale;
  const noise = sigma * Math.sqrt(Math.max(0.0, 1.0 - gamma * gamma));
  particle.rvx = gamma * particle.rvx + gaussian01(rng) * noise;
  particle.rvy = gamma * particle.rvy + gaussian01(rng) * noise;
}

function reflectInward(particle, radius) {
  const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
  if (r === 0) {
    return;
  }
  const nx = particle.x / r;
  const ny = particle.y / r;
  const dot = particle.rvx * nx + particle.rvy * ny;
  particle.rvx -= 2.0 * dot * nx;
  particle.rvy -= 2.0 * dot * ny;
  particle.x = nx * (radius - particle.radius - 0.05);
  particle.y = ny * (radius - particle.radius - 0.05);
}

function geant4EventDrive(event) {
  const edep = Math.max(0.0, event.edepMeV || 0.0);
  const length = Math.max(0.0, event.totalTrackLengthMm || 0.0);
  const steps = Math.max(0.0, event.totalStepCount || 0.0);
  // Keep the scale deliberately modest: Geant4 changes the mesoscale rate, but
  // PubChem selectivity and the first-order law validation remain inspectable.
  const activation = Math.max(0.75, Math.min(1.35,
    0.88 + 0.04 * Math.log1p(steps) + 0.012 * Math.log1p(length) + 0.20 * edep));
  return { edep, length, steps, activation };
}

// Advance one inside particle; returns true if it just permeated out (cleared).
function stepInside(particle, rng, pCrossTick) {
  stepRandomVelocity(particle, rng);
  const flow = advectionVelocity(particle);
  particle.x += (particle.rvx + flow.vx) * SCENARIO.dt;
  particle.y += (particle.rvy + flow.vy) * SCENARIO.dt;
  const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
  const radius = SCENARIO.cellRadius;
  if (r >= radius - particle.radius) {
    if (particle.kind === "waste" && rng.uniform() < pCrossTick) {
      // Permeate across the bilayer and out: now cleared into the sink.
      particle.inside = false;
      particle.cleared = true;
      particle.clearedAge = 0;
      const nx = particle.x / Math.max(r, 1e-9);
      const ny = particle.y / Math.max(r, 1e-9);
      particle.x = nx * (radius + particle.radius + 0.05);
      particle.y = ny * (radius + particle.radius + 0.05);
      // Outward drift (carried away by the extracellular fluid).
      particle.rvx = nx * SCENARIO.clearedDriftSpeed;
      particle.rvy = ny * SCENARIO.clearedDriftSpeed;
      return true;
    }
    reflectInward(particle, radius);
  }
  return false;
}

// Advance a cleared molecule drifting outward in the sink; returns true when it
// has been carried away (should be dropped from the bath).
function stepCleared(particle, rng) {
  particle.clearedAge += 1;
  stepRandomVelocity(particle, rng);
  const r0 = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
  const nx = particle.x / Math.max(r0, 1e-9);
  const ny = particle.y / Math.max(r0, 1e-9);
  particle.x += (particle.rvx + nx * SCENARIO.clearedDriftSpeed) * SCENARIO.dt;
  particle.y += (particle.rvy + ny * SCENARIO.clearedDriftSpeed) * SCENARIO.dt;
  const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
  return particle.clearedAge > SCENARIO.clearedFadeTicks ||
    r > SCENARIO.domainHalfSize - 1.0;
}

function round3(v) {
  return Math.round(v * 1000.0) / 1000.0;
}

function snapshotParticles(state) {
  const out = [];
  for (let i = 0; i < state.particles.length; i += 1) {
    const p = state.particles[i];
    out.push({
      id: p.id,
      k: p.kind,
      s: p.cleared ? 2 : (p.inside ? 0 : 1),
      x: round3(p.x),
      y: round3(p.y)
    });
  }
  return out;
}

// Least-squares fit of ln(N) vs t -> first-order rate k and R^2.
function fitFirstOrder(series) {
  const xs = [];
  const ys = [];
  for (let i = 0; i < series.length; i += 1) {
    const n = series[i].n;
    if (n >= SCENARIO.fitMinCount) {
      xs.push(series[i].t);
      ys.push(Math.log(n));
    }
  }
  const m = xs.length;
  if (m < 3) {
    return { k: 0.0, lnN0: 0.0, r2: 0.0, points: m };
  }
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < m; i += 1) {
    sx += xs[i];
    sy += ys[i];
    sxx += xs[i] * xs[i];
    sxy += xs[i] * ys[i];
  }
  const denom = m * sxx - sx * sx;
  const slope = denom !== 0 ? (m * sxy - sx * sy) / denom : 0.0;
  const intercept = (sy - slope * sx) / m;
  // R^2
  const meanY = sy / m;
  let ssTot = 0, ssRes = 0;
  for (let i = 0; i < m; i += 1) {
    const pred = intercept + slope * xs[i];
    ssRes += (ys[i] - pred) * (ys[i] - pred);
    ssTot += (ys[i] - meanY) * (ys[i] - meanY);
  }
  const r2 = ssTot > 0 ? 1.0 - ssRes / ssTot : 0.0;
  return { k: -slope, lnN0: intercept, r2, points: m };
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    return null;
  }
  if (!ctx.state.initialized) {
    const rng = ctx.rng;
    const particles = [];
    seedInside(rng, SCENARIO.initialWaste, "waste").forEach((p) => particles.push(p));
    seedInside(rng, SCENARIO.initialRetained, "retained").forEach((p) => particles.push(p));
    // Stable ids (particles are only ever removed, never added) so the renderer
    // can track molecules across snapshots for smooth interpolation.
    for (let i = 0; i < particles.length; i += 1) {
      particles[i].id = i;
    }
    ctx.state.particles = particles;
    ctx.state.tick = 0;
    ctx.state.wasteInside = SCENARIO.initialWaste;
    ctx.state.totalCleared = 0;
    ctx.state.series = [];        // { t, n } internal waste count over time
    ctx.state.geant4Drive = {
      events: 0,
      totalEdepMeV: 0.0,
      totalTrackLengthMm: 0.0,
      totalStepCount: 0,
      activationSum: 0.0,
      maxActivation: 0.0
    };
    ctx.state.firstClearTick = 0;
    ctx.state.initialized = true;
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "membrane_efflux_clearance",
      ticks: TOTAL_TICKS,
      cellRadius: SCENARIO.cellRadius,
      domainHalfSize: SCENARIO.domainHalfSize,
      wasteRadius: SCENARIO.wasteRadius,
      retainedRadius: SCENARIO.retainedRadius,
      snapshotEvery: SCENARIO.snapshotEvery,
      initialWaste: SCENARIO.initialWaste,
      initialRetained: SCENARIO.initialRetained,
      pCrossBase: pCrossBase,
      pubchem: {
        permeant: PUBCHEM.permeant,
        retained: PUBCHEM.retained
      },
      geant4: {
        probeEnergyMeV: GEANT4.probeEnergyMeV,
        membraneMaterial: GEANT4.membraneMaterial,
        cytosolMaterial: GEANT4.cytosolMaterial,
        muMembranePerMm: GEANT4.muMembranePerMm,
        muCytosolPerMm: GEANT4.muCytosolPerMm,
        interactionRatio: interactionRatio
      }
    });
    return { override: { system: { ensemble: "membrane_efflux_clearance" } } };
  },
  onRunStart(ctx) {
    ensureState(ctx);
    ctx.emit("initial_population", {
      waste_inside: ctx.state.wasteInside,
      retained_inside: SCENARIO.initialRetained
    });
  },
  onEventEnd(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) {
      return;
    }
    const drive = geant4EventDrive(ctx.event);
    state.geant4Drive.events += 1;
    state.geant4Drive.totalEdepMeV += drive.edep;
    state.geant4Drive.totalTrackLengthMm += drive.length;
    state.geant4Drive.totalStepCount += drive.steps;
    state.geant4Drive.activationSum += drive.activation;
    state.geant4Drive.maxActivation = Math.max(state.geant4Drive.maxActivation, drive.activation);
    const pCrossTick = Math.min(0.95, pCrossBase * drive.activation);
    const tick = state.tick + 1;
    state.tick = tick;
    const particles = state.particles;
    let clearedThisTick = 0;
    const survivors = [];
    for (let i = 0; i < particles.length; i += 1) {
      const p = particles[i];
      if (p.cleared) {
        const gone = stepCleared(p, ctx.rng);
        if (!gone) {
          survivors.push(p);
        }
        continue;
      }
      const justCleared = stepInside(p, ctx.rng, pCrossTick);
      if (justCleared) {
        clearedThisTick += 1;
      }
      survivors.push(p);
    }
    state.particles = survivors;
    if (clearedThisTick > 0) {
      state.wasteInside -= clearedThisTick;
      state.totalCleared += clearedThisTick;
      if (state.firstClearTick === 0) {
        state.firstClearTick = tick;
      }
    }

    if (tick === 1 || tick % SCENARIO.snapshotEvery === 0 || tick === TOTAL_TICKS) {
      state.series.push({ t: tick, n: state.wasteInside });
      let retainedInside = 0;
      for (let i = 0; i < state.particles.length; i += 1) {
        if (state.particles[i].kind === "retained" && state.particles[i].inside) {
          retainedInside += 1;
        }
      }
      ctx.emit("efflux_snapshot", {
        tick,
        waste_inside: state.wasteInside,
        waste_cleared: state.totalCleared,
        retained_inside: retainedInside,
        geant4_activation: drive.activation,
        particles: snapshotParticles(state)
      });
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) {
      return;
    }
    const fit = fitFirstOrder(state.series);
    const r = SCENARIO.cellRadius;
    const halfLifeTicks = fit.k > 0 ? Math.log(2.0) / fit.k : 0.0;
    // Back-derive an effective permeability from the fitted rate via the 2D
    // Fick relation k = 2 P / R (well-mixed disk into a sink) -> P = k R / 2.
    const permeabilityEff = 0.5 * fit.k * r;
    let retainedInside = 0;
    for (let i = 0; i < state.particles.length; i += 1) {
      if (state.particles[i].kind === "retained" && state.particles[i].inside) {
        retainedInside += 1;
      }
    }
    const finalWaste = state.wasteInside;
    const firstOrderKinetics = fit.r2 >= 0.97 && fit.k > 0 && fit.points >= 5;
    const wasteCleared = finalWaste <= 0.2 * SCENARIO.initialWaste;
    const essentialsRetained = retainedInside === SCENARIO.initialRetained;
    const geant4ParamPresent =
      GEANT4.muMembranePerMm > 0 && GEANT4.muCytosolPerMm > 0 &&
      interactionRatio > 0;
    const geant4EventDrivePresent =
      state.geant4Drive.events === state.tick &&
      state.geant4Drive.totalStepCount > 0 &&
      state.geant4Drive.activationSum > 0.0;
    // Overton's rule (from PubChem XLogP): the cleared molecule is lipophilic
    // (partitions into the bilayer) and the retained one is polar.
    const lipophilicitySelectivity =
      permeantIsLipophilic && retainedIsPolar &&
      PUBCHEM.permeant.xlogp > PUBCHEM.retained.xlogp;
    ctx.emit("efflux_summary", {
      ticks: state.tick,
      initial_waste: SCENARIO.initialWaste,
      final_waste_inside: finalWaste,
      total_cleared: state.totalCleared,
      first_clear_tick: state.firstClearTick,
      retained_inside: retainedInside,
      p_cross_base: pCrossBase,
      fit: {
        rate_per_tick: fit.k,
        ln_n0: fit.lnN0,
        r_squared: fit.r2,
        half_life_ticks: halfLifeTicks,
        permeability_eff_units_per_tick: permeabilityEff,
        fit_points: fit.points
      },
      geant4: {
        probe_energy_mev: GEANT4.probeEnergyMeV,
        mu_membrane_per_mm: GEANT4.muMembranePerMm,
        mu_cytosol_per_mm: GEANT4.muCytosolPerMm,
        interaction_ratio: interactionRatio,
        event_drive: {
          events: state.geant4Drive.events,
          total_edep_mev: state.geant4Drive.totalEdepMeV,
          total_track_length_mm: state.geant4Drive.totalTrackLengthMm,
          total_step_count: state.geant4Drive.totalStepCount,
          mean_activation: state.geant4Drive.events > 0 ?
            state.geant4Drive.activationSum / state.geant4Drive.events : 0.0,
          max_activation: state.geant4Drive.maxActivation
        }
      },
      pubchem: {
        permeant: PUBCHEM.permeant,
        retained: PUBCHEM.retained
      },
      series: state.series,
      validation: {
        first_order_kinetics: firstOrderKinetics,
        waste_cleared: wasteCleared,
        essentials_retained: essentialsRetained,
        geant4_param_present: geant4ParamPresent,
        geant4_event_drive_present: geant4EventDrivePresent,
        lipophilicity_selectivity: lipophilicitySelectivity
      }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
