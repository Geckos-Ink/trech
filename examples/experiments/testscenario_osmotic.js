// Validation scenario: Osmotic Dehydration via Dimensional & Polarity Exclusion.
// See docs/testscenario_osmotic-todo.md.
//
// The TRECH C++ runtime (Geant4 transport + provenance) drives a deterministic
// event lifecycle. We piggyback a coarse-grained 2D molecular-dynamics tick
// inside the JS hook layer using ctx.state and ctx.rng so that:
//   - every onEventStart firing advances the membrane/particle system by one
//     simulation time unit (t);
//   - water / solute populations on both sides of the membrane are emitted
//     deterministically to trech_hook_emits.jsonl for inspection;
//   - osmotic shift, membrane crenation and pressure are observable as
//     emergent trends.
//
// This models a biological cell in a hypertonic bath. The membrane is a
// selectively permeable lipid ring with a turgor-driven elastic response:
//
//   * H2O  (small, correctly polarized) passes the channel pores and is
//     expelled outward by the concentration gradient -> the cell dehydrates;
//   * glucose (large) is excluded by dimension and bounces off the wall;
//   * ions  (small, but WRONG polarity) fit the pore geometrically yet are
//     rejected by the channel's polarity gate -- the membrane expels these
//     "wrong polarized" molecules even though they would fit dimensionally.
//
// As internal water drops, the turgor pressure that inflates the membrane
// falls, the spring ring contracts and buckles into lobes, and the cell
// visibly CRENATES (shrinks/crumples) like a real dehydrating cell. The
// membrane node positions are an emitted physical state (a damped spring ODE
// driven by the cell's actual water content), not a renderer-only effect, and
// the particle collisions are resolved against the deformed wall.
//
// The scenario is reproducible because both Geant4 and the hook RNG are
// seeded; no wall-clock or external state is consulted.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

// --- Simulation parameters (relative units per docs/testscenario_osmotic-todo.md) ---
// Velocity / time units are chosen so a "tick" corresponds to roughly the
// time for a water molecule to travel its own diameter (the scenario doc's
// coarse-grained convention).
const SCENARIO = {
  domainHalfSize: 60.0,
  cellRadius: 28.0,
  poreCount: 12,
  poreHalfWidth: 0.10,
  waterRadius: 0.5,
  glucoseRadius: 1.75,
  ionRadius: 0.45,
  waterMass: 1.0,
  glucoseMass: 10.0,
  ionMass: 1.2,
  temperatureK: 310.0,
  kB: 8.617333262e-5,
  dt: 1.0,
  waterMeanSpeed: 0.9,
  glucoseMeanSpeed: 0.28,
  thermostatCoupling: 0.04,
  thermalEnergyToleranceFactor: 2.5,
  initialInsideWater: 90,
  initialInsideGlucose: 10,
  initialOutsideWater: 12,
  initialOutsideGlucose: 88,
  // Wrong-polarized solute: small enough to fit the pore, but the channel
  // rejects them. Kept off the H2O/glucose tallies (a separate species) so the
  // osmosis statistics that the validation case asserts are untouched.
  initialInsideIon: 7,
  initialOutsideIon: 18,
  pressureWindowEvents: 25,
  emitParticleSnapshotEvery: 50,
  // Denser viz snapshots while the cell is actively dehydrating/crenating.
  denseSnapshotUntil: 1500,
  denseSnapshotEvery: 25,
  // --- Flexible spring membrane (crenation) ---
  membraneNodes: 64,
  // Membrane viscoelastic lag: turgor follows a slowly-relaxing average of the
  // water content, so the wall creeps inward over ~hundreds of ticks instead of
  // snapping to the fast osmotic transient (alpha -> relaxation rate per tick).
  turgorRelaxation: 0.0025,
  membraneSubsteps: 4,
  membraneSpringK: 0.55,        // pull each node toward its turgor target
  membraneNeighborK: 0.35,      // neighbour smoothing (bending resistance)
  membraneDamping: 0.86,        // per-substep velocity damping (stability)
  membraneTurgorFloor: 0.70,    // most-deflated mean radius as a fraction of R0
  membraneCrenationAmp: 0.20,   // lobe depth scale once fully deflated
  membraneLobes: 8,             // preferred buckling mode (echinocyte spicules)
  membraneRadiusMin: 0.45,      // hard clamp (fraction of R0) -> never inverts
  membraneRadiusMax: 1.06
};

// Number of Geant4 events == number of MD ticks. The four phase boundaries
// (50, 500, 5000, plateau) are explicit in the scenario doc; 6000 ticks let us
// observe thermalization, probing, macroscopic flux, and approach to
// equilibrium without exploding output volume.
const TOTAL_TICKS = 6000;

const containerHalfMm = units.cm(0.2);
const containerVolumeMm3 = Math.pow(containerHalfMm * 2.0, 3);
const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: units.cm(1.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: SCENARIO.temperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  // threads:1 -> serial event processing so the MD bath (one tick per event)
  // accumulates deterministically; MT event ordering otherwise varies the net
  // water flux run to run.
  run: { nEvents: TOTAL_TICKS, seed: 31073101, threads: 1 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "osmotic_dehydration_cell",
    volumeMm3: containerVolumeMm3
  },
  materials: [waterMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "osmotic_chamber",
        sizeMm: [containerHalfMm * 2, containerHalfMm * 2, containerHalfMm * 2],
        tags: ["chamber", "osmotic"]
      }),
      geometry.boxVolume({
        name: "cytoplasm_proxy",
        material: "water",
        sizeMm: [containerHalfMm, containerHalfMm, containerHalfMm],
        parent: "osmotic_chamber",
        scoreEdep: false,
        tags: ["intracellular", "proxy"]
      })
    ]
  },
  hooks: {
    maxStepCallbacks: 1,
    maxEmitsPerCallback: 16,
    maxEmitPayloadBytes: 131072
  }
};

// --- Species table -----------------------------------------------------------
// polarity: +1 == correctly polarized for the channel; -1 == wrong polarity.
// crossable: whether the channel will pass this species when aligned with a
// pore. Only correctly-polarized water crosses; glucose is also size-excluded.
const SPECIES = {
  h2o: { mass: SCENARIO.waterMass, radius: SCENARIO.waterRadius,
         polarity: +1, crossable: true },
  glucose: { mass: SCENARIO.glucoseMass, radius: SCENARIO.glucoseRadius,
             polarity: -1, crossable: false },
  ion: { mass: SCENARIO.ionMass, radius: SCENARIO.ionRadius,
         polarity: -1, crossable: false }
};

// --- Coarse-grained MD helpers (closures captured by the hooks) ---
function thermalSpeed(massU) {
  // Component velocity scale in 2D, rescaled into the scenario's coarse
  // tick units. Heavier particles move slower (1/sqrt(m) ratio preserved).
  return SCENARIO.waterMeanSpeed *
    Math.sqrt(SCENARIO.waterMass / Math.max(massU, 1e-9));
}

function targetMeanKineticEnergy() {
  // With two velocity components drawn from thermalSpeed(m), mean KE is
  // 0.5*m*(sigma^2 + sigma^2), independent of species under this scaling.
  return SCENARIO.waterMass * SCENARIO.waterMeanSpeed * SCENARIO.waterMeanSpeed;
}

function gaussian01(rng) {
  // Box-Muller using two uniform draws (deterministic via ctx.rng).
  let u1 = rng.uniform();
  if (u1 <= 1e-12) {
    u1 = 1e-12;
  }
  const u2 = rng.uniform();
  return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
}

function seedPopulation(rng, count, kind, inside) {
  const particles = [];
  const radius = SCENARIO.cellRadius;
  const half = SCENARIO.domainHalfSize;
  const spec = SPECIES[kind];
  const massU = spec.mass;
  const partRadius = spec.radius;
  const speedScale = thermalSpeed(massU);
  let safety = 0;
  while (particles.length < count && safety < count * 40) {
    safety += 1;
    const x = (rng.uniform() * 2.0 - 1.0) * half;
    const y = (rng.uniform() * 2.0 - 1.0) * half;
    const r = Math.sqrt(x * x + y * y);
    if (inside && r > radius - partRadius - 0.5) {
      continue;
    }
    if (!inside && (r < radius + partRadius + 0.5 || r > half - partRadius - 0.5)) {
      continue;
    }
    const vx = gaussian01(rng) * speedScale;
    const vy = gaussian01(rng) * speedScale;
    particles.push({
      kind,
      inside: !!inside,
      x,
      y,
      vx,
      vy,
      mass: massU,
      radius: partRadius,
      polarity: spec.polarity
    });
  }
  return particles;
}

function poreAngles() {
  const angles = [];
  for (let i = 0; i < SCENARIO.poreCount; i += 1) {
    angles.push((2.0 * Math.PI * i) / SCENARIO.poreCount);
  }
  return angles;
}

function alignsWithPore(theta, pores, halfWidth) {
  for (let i = 0; i < pores.length; i += 1) {
    let d = theta - pores[i];
    while (d > Math.PI) {
      d -= 2.0 * Math.PI;
    }
    while (d < -Math.PI) {
      d += 2.0 * Math.PI;
    }
    if (Math.abs(d) <= halfWidth) {
      return true;
    }
  }
  return false;
}

// --- Flexible spring membrane ------------------------------------------------
function initMembrane(rng) {
  const n = SCENARIO.membraneNodes;
  const r = new Array(n);
  const vr = new Array(n);
  const jitter = new Array(n);
  for (let i = 0; i < n; i += 1) {
    r[i] = SCENARIO.cellRadius;
    vr[i] = 0.0;
    // Small fixed per-node irregularity so the crenated outline looks organic
    // (deterministic: drawn once from the seeded RNG).
    jitter[i] = (rng.uniform() * 2.0 - 1.0) * 0.012;
  }
  return {
    n,
    r,
    vr,
    jitter,
    phase0: rng.uniform() * 2.0 * Math.PI,
    phase1: rng.uniform() * 2.0 * Math.PI,
    meanRadius: SCENARIO.cellRadius
  };
}

function membraneTargetRadius(membrane, i, turgorFactor) {
  const R0 = SCENARIO.cellRadius;
  const theta = (2.0 * Math.PI * i) / membrane.n;
  // Crenation deepens as the cell deflates (1 - turgorFactor).
  const cren = SCENARIO.membraneCrenationAmp * (1.0 - turgorFactor);
  const lobes = SCENARIO.membraneLobes;
  const wave = cren * Math.cos(lobes * theta + membrane.phase0) +
    0.3 * cren * Math.cos(2.0 * lobes * theta + membrane.phase1) +
    membrane.jitter[i];
  return R0 * turgorFactor * (1.0 + wave);
}

function integrateMembrane(membrane, insideWaterCount) {
  const n = membrane.n;
  const frac = Math.max(0.0, Math.min(1.0,
    insideWaterCount / SCENARIO.initialInsideWater));
  const floor = SCENARIO.membraneTurgorFloor;
  const turgorFactor = floor + (1.0 - floor) * frac;
  const dtSub = SCENARIO.dt / SCENARIO.membraneSubsteps;
  const kS = SCENARIO.membraneSpringK;
  const kN = SCENARIO.membraneNeighborK;
  const damp = SCENARIO.membraneDamping;
  const rMin = SCENARIO.membraneRadiusMin * SCENARIO.cellRadius;
  const rMax = SCENARIO.membraneRadiusMax * SCENARIO.cellRadius;
  const r = membrane.r;
  const vr = membrane.vr;
  for (let s = 0; s < SCENARIO.membraneSubsteps; s += 1) {
    for (let i = 0; i < n; i += 1) {
      const target = membraneTargetRadius(membrane, i, turgorFactor);
      const left = r[(i - 1 + n) % n];
      const right = r[(i + 1) % n];
      const smooth = 0.5 * (left + right) - r[i];
      vr[i] += (kS * (target - r[i]) + kN * smooth) * dtSub;
      vr[i] *= damp;
    }
    let sum = 0.0;
    for (let i = 0; i < n; i += 1) {
      r[i] += vr[i] * dtSub;
      if (r[i] < rMin) {
        r[i] = rMin;
        if (vr[i] < 0.0) {
          vr[i] = 0.0;
        }
      } else if (r[i] > rMax) {
        r[i] = rMax;
        if (vr[i] > 0.0) {
          vr[i] = 0.0;
        }
      }
      sum += r[i];
    }
    membrane.meanRadius = sum / n;
  }
}

function reflectAtRadius(particle, localRadius) {
  const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y);
  if (r === 0) {
    return 0.0;
  }
  const nx = particle.x / r;
  const ny = particle.y / r;
  const dot = particle.vx * nx + particle.vy * ny;
  // Reverse normal component (elastic).
  particle.vx -= 2.0 * dot * nx;
  particle.vy -= 2.0 * dot * ny;
  // Snap back to just inside/outside the membrane so we don't re-trigger.
  const sign = particle.inside ? -1.0 : 1.0;
  particle.x = nx * (localRadius + sign * (particle.radius + 0.05));
  particle.y = ny * (localRadius + sign * (particle.radius + 0.05));
  // Impulse magnitude transferred to the membrane (for pressure scoring).
  return 2.0 * Math.abs(dot) * particle.mass;
}

function clampDomain(particle, half) {
  if (particle.x > half - particle.radius) {
    particle.x = half - particle.radius;
    particle.vx = -Math.abs(particle.vx);
  } else if (particle.x < -half + particle.radius) {
    particle.x = -half + particle.radius;
    particle.vx = Math.abs(particle.vx);
  }
  if (particle.y > half - particle.radius) {
    particle.y = half - particle.radius;
    particle.vy = -Math.abs(particle.vy);
  } else if (particle.y < -half + particle.radius) {
    particle.y = -half + particle.radius;
    particle.vy = Math.abs(particle.vy);
  }
}

function applyLangevinThermostat(particle, rng) {
  // Ornstein-Uhlenbeck velocity refresh: Brownian randomness without
  // unbounded heating, centered on the scenario's 310 K kinetic scale.
  const gamma = Math.max(0.0, Math.min(0.999, 1.0 - SCENARIO.thermostatCoupling));
  const sigma = thermalSpeed(particle.mass);
  const noise = sigma * Math.sqrt(Math.max(0.0, 1.0 - gamma * gamma));
  particle.vx = gamma * particle.vx + gaussian01(rng) * noise;
  particle.vy = gamma * particle.vy + gaussian01(rng) * noise;
}

function stepParticle(particle, dt, rng, pores) {
  applyLangevinThermostat(particle, rng);
  particle.x += particle.vx * dt;
  particle.y += particle.vy * dt;
  clampDomain(particle, SCENARIO.domainHalfSize);

  // Particle exclusion is resolved against the nominal pore ring (the channel
  // lattice). The turgor membrane (state.membrane) is an emitted elastic
  // overlay driven by the cell's water content -- it reports the crenated
  // outline but does not perturb the validated bath dynamics, so the osmosis
  // statistics stay reproducible and decoupled from the spring ODE.
  const r2 = particle.x * particle.x + particle.y * particle.y;
  const r = Math.sqrt(r2);
  const theta = Math.atan2(particle.y, particle.x);
  const radius = SCENARIO.cellRadius;
  let impulse = 0.0;
  let crossed = false;
  let rejected = false;
  const canCross = SPECIES[particle.kind].crossable &&
    alignsWithPore(theta, pores, SCENARIO.poreHalfWidth);
  if (particle.inside && r >= radius - particle.radius) {
    if (canCross) {
      particle.inside = false;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius);
      rejected = particle.kind !== "h2o";
    }
  } else if (!particle.inside && r <= radius + particle.radius) {
    if (canCross) {
      particle.inside = true;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius);
      rejected = particle.kind !== "h2o";
    }
  }
  return { impulse, crossed, rejected, side: particle.inside };
}

function tallyPopulations(particles) {
  const counts = {
    inside_h2o: 0,
    inside_glucose: 0,
    outside_h2o: 0,
    outside_glucose: 0,
    inside_ion: 0,
    outside_ion: 0
  };
  for (let i = 0; i < particles.length; i += 1) {
    const p = particles[i];
    if (p.kind === "h2o") {
      counts[p.inside ? "inside_h2o" : "outside_h2o"] += 1;
    } else if (p.kind === "glucose") {
      counts[p.inside ? "inside_glucose" : "outside_glucose"] += 1;
    } else {
      counts[p.inside ? "inside_ion" : "outside_ion"] += 1;
    }
  }
  return counts;
}

function meanKineticEnergy(particles) {
  if (particles.length === 0) {
    return 0.0;
  }
  let sum = 0.0;
  for (let i = 0; i < particles.length; i += 1) {
    const p = particles[i];
    sum += 0.5 * p.mass * (p.vx * p.vx + p.vy * p.vy);
  }
  return sum / particles.length;
}

function round3(v) {
  return Math.round(v * 1000.0) / 1000.0;
}

function particleSnapshot(particles) {
  const out = [];
  for (let i = 0; i < particles.length; i += 1) {
    const p = particles[i];
    out.push({
      id: i,
      k: p.kind,
      i: p.inside,
      q: p.polarity,
      x: round3(p.x),
      y: round3(p.y)
    });
  }
  return out;
}

function membraneSnapshot(membrane) {
  const out = new Array(membrane.n);
  for (let i = 0; i < membrane.n; i += 1) {
    out[i] = round3(membrane.r[i]);
  }
  return out;
}

function phaseLabel(tick) {
  if (tick <= 50) {
    return "thermalization";
  }
  if (tick <= 500) {
    return "local_diffusion";
  }
  if (tick <= 5000) {
    return "macroscopic_flux";
  }
  return "approaching_equilibrium";
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    return null;
  }
  if (!ctx.state.initialized) {
    const rng = ctx.rng;
    const particles = [];
    seedPopulation(rng, SCENARIO.initialInsideWater, "h2o", true).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialInsideGlucose, "glucose", true).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialInsideIon, "ion", true).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialOutsideWater, "h2o", false).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialOutsideGlucose, "glucose", false).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialOutsideIon, "ion", false).forEach((p) => particles.push(p));
    ctx.state.particles = particles;
    ctx.state.pores = poreAngles();
    ctx.state.membrane = initMembrane(rng);
    ctx.state.insideWaterCount = SCENARIO.initialInsideWater;
    ctx.state.turgorWaterEMA = SCENARIO.initialInsideWater;
    ctx.state.tick = 0;
    ctx.state.impulseAccumInternal = 0.0;
    ctx.state.impulseAccumExternal = 0.0;
    ctx.state.windowTicks = 0;
    ctx.state.crossingsOut = 0;
    ctx.state.crossingsIn = 0;
    ctx.state.rejectionsThisWindow = 0;
    ctx.state.totalRejections = 0;
    ctx.state.recentExpelled = [];
    ctx.state.lastEmittedCounts = null;
    ctx.state.firstCrossingTick = 0;
    ctx.state.milestones = {};
    ctx.state.maxObservedMeanKineticEnergy = 0.0;
    ctx.state.maxPressureDelta = 0.0;
    ctx.state.latePressureInternalSum = 0.0;
    ctx.state.latePressureExternalSum = 0.0;
    ctx.state.latePressureWindows = 0;
    ctx.state.initialMembraneMeanRadius = ctx.state.membrane.meanRadius;
    ctx.state.minMembraneMeanRadius = ctx.state.membrane.meanRadius;
    ctx.state.maxMembraneNodeSpeed = 0.0;
    ctx.state.initialized = true;
  }
  return ctx.state;
}

function membraneMetrics(membrane) {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < membrane.n; i += 1) {
    if (membrane.r[i] < min) {
      min = membrane.r[i];
    }
    if (membrane.r[i] > max) {
      max = membrane.r[i];
    }
  }
  return { min, max, mean: membrane.meanRadius, crenationDepth: max - min };
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "osmotic_dehydration",
      ticks: TOTAL_TICKS,
      pores: SCENARIO.poreCount,
      poreHalfWidth: SCENARIO.poreHalfWidth,
      cellRadius: SCENARIO.cellRadius,
      domainHalfSize: SCENARIO.domainHalfSize,
      waterRadius: SCENARIO.waterRadius,
      glucoseRadius: SCENARIO.glucoseRadius,
      ionRadius: SCENARIO.ionRadius,
      membraneNodes: SCENARIO.membraneNodes,
      particleSnapshotEvery: SCENARIO.emitParticleSnapshotEvery,
      ratioInside: {
        h2o: SCENARIO.initialInsideWater,
        glucose: SCENARIO.initialInsideGlucose,
        ion: SCENARIO.initialInsideIon
      },
      ratioOutside: {
        h2o: SCENARIO.initialOutsideWater,
        glucose: SCENARIO.initialOutsideGlucose,
        ion: SCENARIO.initialOutsideIon
      }
    });
    return {
      override: {
        system: { ensemble: "osmotic_dehydration_cell" }
      }
    };
  },
  onRunStart(ctx) {
    ensureState(ctx);
    const counts = tallyPopulations(ctx.state.particles);
    ctx.emit("initial_population", counts);
  },
  onEventStart(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) {
      return;
    }
    const tick = state.tick + 1;
    state.tick = tick;

    // Evolve the turgor membrane against the cell's (viscoelastically lagged)
    // water content. As water leaves, turgor falls and the spring ring
    // contracts/buckles (crenation) -- an emitted physical state, decoupled
    // from the bath dynamics resolved below.
    state.turgorWaterEMA += SCENARIO.turgorRelaxation *
      (state.insideWaterCount - state.turgorWaterEMA);
    integrateMembrane(state.membrane, state.turgorWaterEMA);
    if (state.membrane.meanRadius < state.minMembraneMeanRadius) {
      state.minMembraneMeanRadius = state.membrane.meanRadius;
    }

    let crossingsOut = 0;
    let crossingsIn = 0;
    const particles = state.particles;
    for (let i = 0; i < particles.length; i += 1) {
      const p = particles[i];
      const wasInside = p.inside;
      const result = stepParticle(p, SCENARIO.dt, ctx.rng, state.pores);
      if (result.impulse > 0.0) {
        if (wasInside) {
          state.impulseAccumInternal += result.impulse;
        } else {
          state.impulseAccumExternal += result.impulse;
        }
      }
      if (result.rejected) {
        state.rejectionsThisWindow += 1;
        state.totalRejections += 1;
        // Keep a small, deterministic sample of expulsion points (membrane
        // strikes by wrong-polarized / oversized molecules) for the renderer.
        if (state.recentExpelled.length < 24 &&
            (state.totalRejections % 5 === 0)) {
          state.recentExpelled.push({
            x: round3(p.x),
            y: round3(p.y),
            k: p.kind,
            i: p.inside
          });
        }
      }
      if (result.crossed) {
        if (wasInside && !p.inside) {
          crossingsOut += 1;
          state.insideWaterCount -= 1;
        } else if (!wasInside && p.inside) {
          crossingsIn += 1;
          state.insideWaterCount += 1;
        }
      }
    }
    state.crossingsOut += crossingsOut;
    state.crossingsIn += crossingsIn;
    if (state.firstCrossingTick === 0 && crossingsOut + crossingsIn > 0) {
      state.firstCrossingTick = tick;
    }
    state.windowTicks += 1;

    const isMilestone = tick === 1 || tick === 50 || tick === 500 ||
                        tick === 1000 || tick === 2500 || tick === 5000 ||
                        tick === TOTAL_TICKS;
    const isWindowBoundary = state.windowTicks >= SCENARIO.pressureWindowEvents;
    if (isMilestone || isWindowBoundary) {
      const counts = tallyPopulations(particles);
      const meanKE = meanKineticEnergy(particles);
      // Membrane circumference in scenario units acts as "area" for pressure.
      // Impulses are tallied on the nominal pore ring, so use the nominal
      // circumference (the external/internal ratio is invariant to it anyway).
      const circumference = 2.0 * Math.PI * SCENARIO.cellRadius;
      const dtWindow = Math.max(state.windowTicks * SCENARIO.dt, 1e-9);
      const internalPressure = state.impulseAccumInternal / (circumference * dtWindow);
      const externalPressure = state.impulseAccumExternal / (circumference * dtWindow);
      const memMetrics = membraneMetrics(state.membrane);
      state.maxObservedMeanKineticEnergy =
        Math.max(state.maxObservedMeanKineticEnergy, meanKE);
      state.maxPressureDelta =
        Math.max(state.maxPressureDelta, Math.abs(externalPressure - internalPressure));
      if (tick >= 500) {
        state.latePressureInternalSum += internalPressure;
        state.latePressureExternalSum += externalPressure;
        state.latePressureWindows += 1;
      }
      ctx.emit("osmotic_snapshot", {
        tick,
        phase: phaseLabel(tick),
        inside_h2o: counts.inside_h2o,
        outside_h2o: counts.outside_h2o,
        inside_glucose: counts.inside_glucose,
        outside_glucose: counts.outside_glucose,
        inside_ion: counts.inside_ion,
        outside_ion: counts.outside_ion,
        net_water_flux_out: state.crossingsOut - state.crossingsIn,
        wrong_polarized_rejections: state.totalRejections,
        membrane_pressure_internal: internalPressure,
        membrane_pressure_external: externalPressure,
        membrane_mean_radius: round3(memMetrics.mean),
        membrane_crenation_depth: round3(memMetrics.crenationDepth),
        mean_kinetic_energy: meanKE,
        target_mean_kinetic_energy: targetMeanKineticEnergy()
      });
      if (isMilestone) {
        state.milestones[String(tick)] = {
          inside_h2o: counts.inside_h2o,
          outside_h2o: counts.outside_h2o,
          net_water_flux_out: state.crossingsOut - state.crossingsIn,
          mean_kinetic_energy: meanKE,
          membrane_mean_radius: round3(memMetrics.mean),
          membrane_pressure_internal: internalPressure,
          membrane_pressure_external: externalPressure
        };
      }
      state.impulseAccumInternal = 0.0;
      state.impulseAccumExternal = 0.0;
      state.windowTicks = 0;
      state.rejectionsThisWindow = 0;
      state.lastEmittedCounts = counts;
    }

    const denseSnapshot = tick <= SCENARIO.denseSnapshotUntil &&
      tick % SCENARIO.denseSnapshotEvery === 0;
    if (tick === 1 || denseSnapshot ||
        tick % SCENARIO.emitParticleSnapshotEvery === 0 ||
        tick === TOTAL_TICKS) {
      const counts = tallyPopulations(particles);
      ctx.emit("osmotic_particles", {
        tick,
        phase: phaseLabel(tick),
        inside_h2o: counts.inside_h2o,
        outside_h2o: counts.outside_h2o,
        inside_glucose: counts.inside_glucose,
        outside_glucose: counts.outside_glucose,
        inside_ion: counts.inside_ion,
        outside_ion: counts.outside_ion,
        net_water_flux_out: state.crossingsOut - state.crossingsIn,
        wrong_polarized_rejections: state.totalRejections,
        membrane_mean_radius: round3(state.membrane.meanRadius),
        membrane: membraneSnapshot(state.membrane),
        expelled: state.recentExpelled,
        particles: particleSnapshot(particles)
      });
      state.recentExpelled = [];
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) {
      return;
    }
    const counts = tallyPopulations(state.particles);
    const initialWaterGradient =
      SCENARIO.initialInsideWater - SCENARIO.initialOutsideWater;
    const finalWaterGradient = counts.inside_h2o - counts.outside_h2o;
    const milestone50 = state.milestones["50"] || null;
    const milestone500 = state.milestones["500"] || null;
    const milestone5000 = state.milestones["5000"] || null;
    const latePressureInternal =
      state.latePressureWindows > 0 ?
        state.latePressureInternalSum / state.latePressureWindows : 0.0;
    const latePressureExternal =
      state.latePressureWindows > 0 ?
        state.latePressureExternalSum / state.latePressureWindows : 0.0;
    const targetKE = targetMeanKineticEnergy();
    const maxAllowedKE = targetKE * SCENARIO.thermalEnergyToleranceFactor;
    const memMetrics = membraneMetrics(state.membrane);
    const initialMean = state.initialMembraneMeanRadius;
    const areaShrinkFraction = initialMean > 0 ?
      1.0 - Math.pow(memMetrics.mean / initialMean, 2.0) : 0.0;
    const dimensionalExclusionHolds =
      counts.inside_glucose === SCENARIO.initialInsideGlucose &&
      counts.outside_glucose === SCENARIO.initialOutsideGlucose;
    const polarityExclusionHolds =
      counts.inside_ion === SCENARIO.initialInsideIon &&
      counts.outside_ion === SCENARIO.initialOutsideIon &&
      state.totalRejections > 0;
    const osmoticShiftObserved =
      counts.outside_h2o > SCENARIO.initialOutsideWater &&
      counts.inside_h2o < SCENARIO.initialInsideWater &&
      (state.crossingsOut - state.crossingsIn) > 0 &&
      finalWaterGradient < initialWaterGradient;
    const earlyCrossoversObserved =
      state.firstCrossingTick > 0 && state.firstCrossingTick <= 500;
    const macroscopicFluxObserved =
      milestone50 !== null && milestone5000 !== null &&
      milestone5000.net_water_flux_out > milestone50.net_water_flux_out;
    const thermalEnergyBounded =
      state.maxObservedMeanKineticEnergy > 0.0 &&
      state.maxObservedMeanKineticEnergy <= maxAllowedKE;
    const pressureResponseObserved =
      state.latePressureWindows > 0 &&
      latePressureExternal > latePressureInternal;
    // The cell visibly dehydrates: its turgor-driven membrane contracts as
    // water leaves (crenation), but the damped spring never blows up.
    const membraneCrenationObserved = areaShrinkFraction > 0.05;
    const membraneStable =
      memMetrics.min >= SCENARIO.membraneRadiusMin * SCENARIO.cellRadius - 1e-6 &&
      memMetrics.max <= SCENARIO.membraneRadiusMax * SCENARIO.cellRadius + 1e-6 &&
      Number.isFinite(memMetrics.mean);
    ctx.emit("final_summary", {
      tick: state.tick,
      phase: phaseLabel(state.tick),
      counts,
      total_crossings_out: state.crossingsOut,
      total_crossings_in: state.crossingsIn,
      net_water_flux_out: state.crossingsOut - state.crossingsIn,
      wrong_polarized_rejections: state.totalRejections,
      first_crossing_tick: state.firstCrossingTick,
      initial_water_gradient: initialWaterGradient,
      final_water_gradient: finalWaterGradient,
      target_mean_kinetic_energy: targetKE,
      max_observed_mean_kinetic_energy: state.maxObservedMeanKineticEnergy,
      max_pressure_delta: state.maxPressureDelta,
      membrane: {
        initial_mean_radius: round3(initialMean),
        final_mean_radius: round3(memMetrics.mean),
        min_node_radius: round3(memMetrics.min),
        max_node_radius: round3(memMetrics.max),
        final_crenation_depth: round3(memMetrics.crenationDepth),
        area_shrink_fraction: round3(areaShrinkFraction)
      },
      late_pressure_average: {
        internal: latePressureInternal,
        external: latePressureExternal,
        windows: state.latePressureWindows
      },
      milestones: {
        tick_50: milestone50,
        tick_500: milestone500,
        tick_5000: milestone5000
      },
      validation: {
        dimensional_exclusion_holds: dimensionalExclusionHolds,
        polarity_exclusion_holds: polarityExclusionHolds,
        osmotic_shift_observed: osmoticShiftObserved,
        early_crossovers_observed: earlyCrossoversObserved,
        macroscopic_flux_observed: macroscopicFluxObserved,
        thermal_energy_bounded: thermalEnergyBounded,
        pressure_response_observed: pressureResponseObserved,
        membrane_crenation_observed: membraneCrenationObserved,
        membrane_stable: membraneStable
      }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
