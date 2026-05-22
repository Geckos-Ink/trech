// Validation scenario: Osmotic Dehydration via Dimensional Exclusion.
// See docs/testscenario_osmotic-todo.md.
//
// The TRECH C++ runtime (Geant4 transport + provenance) drives a deterministic
// event lifecycle. We piggyback a coarse-grained 2D molecular-dynamics tick
// inside the JS hook layer using ctx.state and ctx.rng so that:
//   - every onEventStart firing advances the membrane/particle system by one
//     simulation time unit (t);
//   - water/glucose populations on both sides of the membrane are emitted
//     deterministically to trech_hook_emits.jsonl for inspection;
//   - osmotic shift and membrane pressure are observable as emergent trends.
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
// coarse-grained convention). With these values, an undisturbed water
// particle covers ~0.5 units per tick, so the cell diameter (~56 units)
// takes O(100) ticks to traverse.
const SCENARIO = {
  domainHalfSize: 60.0,
  cellRadius: 28.0,
  poreCount: 12,
  poreHalfWidth: 0.10,
  waterRadius: 0.5,
  glucoseRadius: 1.75,
  waterMass: 1.0,
  glucoseMass: 10.0,
  temperatureK: 310.0,
  kB: 8.617333262e-5,
  dt: 1.0,
  waterMeanSpeed: 0.9,
  glucoseMeanSpeed: 0.28,
  brownianAmplitude: 0.08,
  initialInsideWater: 90,
  initialInsideGlucose: 10,
  initialOutsideWater: 12,
  initialOutsideGlucose: 88,
  pressureWindowEvents: 25,
  emitParticleSnapshotEvery: 100
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
  run: { nEvents: TOTAL_TICKS, seed: 31073101 },
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
    maxEmitPayloadBytes: 65536
  }
};

// --- Coarse-grained MD helpers (closures captured by the hooks) ---
function thermalSpeed(massU) {
  // Maxwell-Boltzmann mean speed in 2D, but rescaled into the scenario's
  // coarse-grained tick velocity units. Heavier particles move slower
  // (1/sqrt(m) ratio preserved). We pin the water mean speed by parameter
  // and derive glucose from the ratio sqrt(m_water / m_glucose).
  const waterMean = SCENARIO.waterMeanSpeed;
  return waterMean * Math.sqrt(SCENARIO.waterMass / Math.max(massU, 1e-9));
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
  const isWater = kind === "h2o";
  const massU = isWater ? SCENARIO.waterMass : SCENARIO.glucoseMass;
  const partRadius = isWater ? SCENARIO.waterRadius : SCENARIO.glucoseRadius;
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
      radius: partRadius
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

function reflectAtRadius(particle, radius) {
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
  // Snap back to just outside the membrane so we don't re-trigger.
  const sign = particle.inside ? -1.0 : 1.0;
  particle.x = nx * (radius + sign * (particle.radius + 0.05));
  particle.y = ny * (radius + sign * (particle.radius + 0.05));
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

function stepParticle(particle, dt, rng, pores) {
  // Brownian impulse keeps kinetic energy near T=310K target.
  const ampl = SCENARIO.brownianAmplitude / Math.sqrt(particle.mass);
  particle.vx += gaussian01(rng) * ampl;
  particle.vy += gaussian01(rng) * ampl;
  particle.x += particle.vx * dt;
  particle.y += particle.vy * dt;
  clampDomain(particle, SCENARIO.domainHalfSize);

  const r2 = particle.x * particle.x + particle.y * particle.y;
  const r = Math.sqrt(r2);
  const radius = SCENARIO.cellRadius;
  let impulse = 0.0;
  let crossed = false;
  if (particle.inside && r >= radius - particle.radius) {
    const theta = Math.atan2(particle.y, particle.x);
    const isWater = particle.kind === "h2o";
    if (isWater && alignsWithPore(theta, pores, SCENARIO.poreHalfWidth)) {
      // Water aligned with a pore: cross outward.
      particle.inside = false;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius);
    }
  } else if (!particle.inside && r <= radius + particle.radius) {
    const theta = Math.atan2(particle.y, particle.x);
    const isWater = particle.kind === "h2o";
    if (isWater && alignsWithPore(theta, pores, SCENARIO.poreHalfWidth)) {
      particle.inside = true;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius);
    }
  }
  return { impulse, crossed, side: particle.inside };
}

function tallyPopulations(particles) {
  const counts = {
    inside_h2o: 0,
    inside_glucose: 0,
    outside_h2o: 0,
    outside_glucose: 0
  };
  for (let i = 0; i < particles.length; i += 1) {
    const p = particles[i];
    if (p.kind === "h2o") {
      counts[p.inside ? "inside_h2o" : "outside_h2o"] += 1;
    } else {
      counts[p.inside ? "inside_glucose" : "outside_glucose"] += 1;
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
    seedPopulation(rng, SCENARIO.initialOutsideWater, "h2o", false).forEach((p) => particles.push(p));
    seedPopulation(rng, SCENARIO.initialOutsideGlucose, "glucose", false).forEach((p) => particles.push(p));
    ctx.state.particles = particles;
    ctx.state.pores = poreAngles();
    ctx.state.tick = 0;
    ctx.state.impulseAccumInternal = 0.0;
    ctx.state.impulseAccumExternal = 0.0;
    ctx.state.windowTicks = 0;
    ctx.state.crossingsOut = 0;
    ctx.state.crossingsIn = 0;
    ctx.state.lastEmittedCounts = null;
    ctx.state.initialized = true;
  }
  return ctx.state;
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
      ratioInside: {
        h2o: SCENARIO.initialInsideWater,
        glucose: SCENARIO.initialInsideGlucose
      },
      ratioOutside: {
        h2o: SCENARIO.initialOutsideWater,
        glucose: SCENARIO.initialOutsideGlucose
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
      if (result.crossed) {
        if (wasInside && !p.inside) {
          crossingsOut += 1;
        } else if (!wasInside && p.inside) {
          crossingsIn += 1;
        }
      }
    }
    state.crossingsOut += crossingsOut;
    state.crossingsIn += crossingsIn;
    state.windowTicks += 1;

    const isMilestone = tick === 1 || tick === 50 || tick === 500 ||
                        tick === 1000 || tick === 2500 || tick === 5000 ||
                        tick === TOTAL_TICKS;
    const isWindowBoundary = state.windowTicks >= SCENARIO.pressureWindowEvents;
    if (isMilestone || isWindowBoundary) {
      const counts = tallyPopulations(particles);
      // Membrane circumference in scenario units acts as "area" for pressure.
      const circumference = 2.0 * Math.PI * SCENARIO.cellRadius;
      const dtWindow = Math.max(state.windowTicks * SCENARIO.dt, 1e-9);
      const internalPressure = state.impulseAccumInternal / (circumference * dtWindow);
      const externalPressure = state.impulseAccumExternal / (circumference * dtWindow);
      ctx.emit("osmotic_snapshot", {
        tick,
        phase: phaseLabel(tick),
        inside_h2o: counts.inside_h2o,
        outside_h2o: counts.outside_h2o,
        inside_glucose: counts.inside_glucose,
        outside_glucose: counts.outside_glucose,
        net_water_flux_out: state.crossingsOut - state.crossingsIn,
        membrane_pressure_internal: internalPressure,
        membrane_pressure_external: externalPressure,
        mean_kinetic_energy: meanKineticEnergy(particles)
      });
      state.impulseAccumInternal = 0.0;
      state.impulseAccumExternal = 0.0;
      state.windowTicks = 0;
      state.lastEmittedCounts = counts;
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) {
      return;
    }
    const counts = tallyPopulations(state.particles);
    ctx.emit("final_summary", {
      tick: state.tick,
      phase: phaseLabel(state.tick),
      counts,
      total_crossings_out: state.crossingsOut,
      total_crossings_in: state.crossingsIn,
      net_water_flux_out: state.crossingsOut - state.crossingsIn,
      validation: {
        osmotic_shift_observed: counts.outside_h2o > SCENARIO.initialOutsideWater,
        dimensional_exclusion_holds:
          counts.inside_glucose === SCENARIO.initialInsideGlucose &&
          counts.outside_glucose === SCENARIO.initialOutsideGlucose
      }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
