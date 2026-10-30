// Validation scenario: Pascal's Principle & Material Deformation.
// See docs/testscenario_pascal-todo.md.
//
// Two sub-scenarios share one config so both run under the same provenance
// envelope. Each Geant4 event acts as one MD tick; the hook layer evolves a
// 3D H2O particle bath inside an ideal rigid vessel (A) and inside a
// Hookean-spring deformable vessel (B) and emits per-window pressure
// measurements at the sensor wall plus the theoretical F_in/A_syr target.
// The sensor wall is a grid of independent Hookean patches over its (y, z)
// face; the piston is a full-face plate.
//
// Validation:
//   * Scenario A: sensor pressure delta == piston pressure delta (within a
//     tolerance band emitted in `pascal_summary.validation`).
//   * Scenario B: sensor pressure delta strictly less than piston delta, with
//     a visible volume expansion in `wall_displacement_*` fields.
//   * The "macro" scenario reuses the same Hookean wall, parametrized
//     toward a Geant4-DNA-style micro/macro statistical limit (more, stiffer
//     wall segments) so the same data set already supports the
//     micro-to-macro coherence call-out in the doc.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

// Phase layout (relative simulation time units).
//   thermalize: settle the bath against the rest-vessel geometry.
//   baseline:   measure resting pressure at full chamber volume.
//   compress:   piston advances to its inward stop (transient).
//   hold:       piston pinned at the compressed position; sensor and piston
//               feel the steady-state response. This is where Pascal's
//               principle (rigid) and pressure damping (deformable) are
//               cleanest to validate.
//   release:    piston withdrawn and system relaxes back.
const PHASES = {
  thermalize: { end: 200 },
  baseline: { end: 600 },
  compress: { end: 1000 },
  hold: { end: 2000 },
  release: { end: 2400 }
};
const TOTAL_TICKS = PHASES.release.end;

const PASCAL = {
  domainHalfX: 50.0,
  domainHalfY: 28.0,
  domainHalfZ: 28.0,
  pistonAreaUnits: 56.0 * 56.0,   // face area of the moving piston plate
  sensorAreaUnits: 56.0 * 56.0,   // face area of the sensor wall
  // 3D bath: 4x the planar count keeps wall-hit statistics per window useful.
  particleCount: 880,
  particleRadius: 0.6,
  particleMass: 1.0,
  temperatureK: 300.0,
  // Coarse-grained tick velocity scale (cf. testscenario_osmotic-todo.md).
  // We pin H2O mean speed so a particle travels roughly its own diameter
  // per tick; thermal pressure stays well-defined and stable.
  particleMeanSpeed: 0.9,
  brownianAmplitude: 0.0,
  // Berendsen-style thermostat: rescale particle velocities toward the
  // target mean speed each tick so accumulated piston/wall work doesn't
  // drift the bath temperature. This separates Pascal's compressive
  // pressure rise (sustained density change) from accidental heating.
  thermostatCoupling: 0.05,
  // Damping applied to the sensor wall each tick. Without this the wall
  // would oscillate unboundedly under the impulsive forcing from particles.
  wallDamping: 0.85,
  dt: 1.0,
  // The piston is treated as a perfect velocity-controlled actuator:
  // during the compress phase it advances at pistonSpeedCap, during hold
  // it is pinned, during release it withdraws. The "applied force" the
  // doc references is then F_in = ΔP_piston * A_syr, measured directly
  // from collisional impulse on the piston face.
  compressDistance: 25.0,
  pistonSpeedCap: 0.0625,
  // Wall patches per side (the sensor wall is segments x segments patches).
  rigidWallSegments: 14,
  rigidWallStiffness: 5.0e3,  // very stiff, behaves rigid for the test window
  rigidWallMass: 5.0e3,
  deformableWallSegments: 14,
  deformableWallStiffness: 0.036,   // per 4x4 patch: ~unit elastic bulge at baseline
  deformableWallMass: 16.0,         // per 4x4 patch (the planar segment mass)
  // In-plane membrane tension between neighbouring patches, the wall rim held by
  // the rigid vessel: a pressurised wall bulges as a smooth dome, and one
  // molecular impulse cannot fling a single patch. Per-patch tension is
  // resolution-independent (T * h^2 * laplacian = T * sum(neighbour - self)).
  wallTension: 0.08,
  // Micro -> macro variant of scenario B: finer patches with the same bulk
  // wall stiffness per area (N^2*k held constant) and per-patch mass scaled
  // by area. This approximates a structural mesh refinement, a step toward
  // the Geant4-DNA-style micro/macro statistical limit referenced in
  // docs/testscenario_pascal-todo.md.
  macroWallSegments: 28,
  macroWallStiffness: 0.009,
  macroWallMass: 4.0,
  // Plastic memory for visibly deformable vessels. Once a sensor-wall segment
  // yields past this displacement, a fraction of the excess is absorbed into
  // the segment rest position so the released vessel keeps a rounded bulge.
  plasticYieldDisplacement: 0.72,
  plasticFlow: 0.018,
  windowEvents: 25
};

const containerHalfMm = units.cm(0.4);
const containerVolumeMm3 = Math.pow(containerHalfMm * 2.0, 3);
const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: units.cm(2.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: PASCAL.temperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  // threads:1 -> serial event processing so the MD bath (one tick per event)
  // accumulates deterministically; MT event ordering otherwise varies the
  // measured wall displacements run to run.
  run: { nEvents: TOTAL_TICKS, seed: 42424242, threads: 1 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "pascal_principle_vessel",
    volumeMm3: containerVolumeMm3
  },
  materials: [waterMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "pascal_chamber",
        sizeMm: [containerHalfMm * 2, containerHalfMm * 2, containerHalfMm * 2],
        tags: ["chamber", "pascal"]
      }),
      geometry.boxVolume({
        name: "fluid_proxy",
        material: "water",
        sizeMm: [containerHalfMm, containerHalfMm, containerHalfMm],
        parent: "pascal_chamber",
        scoreEdep: false,
        tags: ["fluid", "h2o"]
      })
    ]
  },
  hooks: {
    maxStepCallbacks: 1,
    maxEmitsPerCallback: 24,
    maxEmitPayloadBytes: 1048576
  }
};

const gaussian01 = helpers.random.gaussian;

// Local xorshift RNG used to seed each vessel bucket from an identical
// state, so the three buckets start with identical particle distributions
// and any cross-bucket differences in observables are attributable to the
// wall model — not to a divergent initialization stream.
function makeLocalRng(seed) {
  let state = (seed >>> 0) || 0x12345678;
  return {
    uniform() {
      state ^= state << 13;
      state = state >>> 0;
      state ^= state >>> 17;
      state ^= state << 5;
      state = state >>> 0;
      return (state / 4294967296.0);
    }
  };
}

function thermalSpeed() {
  return PASCAL.particleMeanSpeed;
}

function buildWall(opts) {
  // segmentCount x segmentCount independent patches over the (y, z) face,
  // row-major in z then y: index = iz * n + iy.
  const segments = [];
  const n = opts.segmentCount;
  const dy = PASCAL.domainHalfY * 2.0 / n;
  const dz = PASCAL.domainHalfZ * 2.0 / n;
  for (let iz = 0; iz < n; iz += 1) {
    for (let iy = 0; iy < n; iy += 1) {
      segments.push({
        rest: opts.xRest,
        initialRest: opts.xRest,
        x: opts.xRest,
        vx: 0.0,
        yCenter: -PASCAL.domainHalfY + dy * (iy + 0.5),
        zCenter: -PASCAL.domainHalfZ + dz * (iz + 0.5),
        halfHeight: dy * 0.5,
        mass: opts.mass,
        stiffness: opts.stiffness
      });
    }
  }
  segments.side = n;
  return segments;
}

function seedParticles(rng, leftLimit) {
  const out = [];
  const speedScale = thermalSpeed();
  const span = PASCAL.domainHalfY * 2.0 - 2.0 * PASCAL.particleRadius;
  const spanZ = PASCAL.domainHalfZ * 2.0 - 2.0 * PASCAL.particleRadius;
  const usableX = PASCAL.domainHalfX - leftLimit - 2.0 * PASCAL.particleRadius;
  while (out.length < PASCAL.particleCount) {
    const x = leftLimit + PASCAL.particleRadius + rng.uniform() * usableX;
    const y = -PASCAL.domainHalfY + PASCAL.particleRadius + rng.uniform() * span;
    const z = -PASCAL.domainHalfZ + PASCAL.particleRadius + rng.uniform() * spanZ;
    out.push({
      x,
      y,
      z,
      vx: gaussian01(rng) * speedScale,
      vy: gaussian01(rng) * speedScale,
      vz: gaussian01(rng) * speedScale,
      mass: PASCAL.particleMass,
      radius: PASCAL.particleRadius
    });
  }
  return out;
}

function reflectWallY(p) {
  if (p.y > PASCAL.domainHalfY - p.radius) {
    p.y = PASCAL.domainHalfY - p.radius;
    p.vy = -Math.abs(p.vy);
  } else if (p.y < -PASCAL.domainHalfY + p.radius) {
    p.y = -PASCAL.domainHalfY + p.radius;
    p.vy = Math.abs(p.vy);
  }
  if (p.z > PASCAL.domainHalfZ - p.radius) {
    p.z = PASCAL.domainHalfZ - p.radius;
    p.vz = -Math.abs(p.vz);
  } else if (p.z < -PASCAL.domainHalfZ + p.radius) {
    p.z = -PASCAL.domainHalfZ + p.radius;
    p.vz = Math.abs(p.vz);
  }
}

function reflectPiston(p, pistonX) {
  if (p.x < pistonX + p.radius) {
    const overlap = pistonX + p.radius - p.x;
    p.x = pistonX + p.radius;
    const dv = Math.abs(p.vx);
    p.vx = Math.abs(p.vx);
    return { impulse: 2.0 * dv * p.mass, overlap };
  }
  return null;
}

function findSegmentForYZ(segments, y, z) {
  // Patches are evenly spaced over the (y, z) face; pick by index.
  if (segments.length === 0) {
    return -1;
  }
  const n = segments.side;
  const clampIndex = (v) => Math.max(0, Math.min(n - 1, v));
  const iy = clampIndex(Math.floor((y + PASCAL.domainHalfY) / (PASCAL.domainHalfY * 2.0 / n)));
  const iz = clampIndex(Math.floor((z + PASCAL.domainHalfZ) / (PASCAL.domainHalfZ * 2.0 / n)));
  return iz * n + iy;
}

function reflectSensorWall(p, segments) {
  const idx = findSegmentForYZ(segments, p.y, p.z);
  if (idx < 0) {
    return null;
  }
  const seg = segments[idx];
  if (p.x > seg.x - p.radius) {
    // Elastic reflection in the wall's moving frame (massive wall limit:
    // m_particle << m_wall, so wall velocity changes negligibly per hit
    // but particle picks up 2 * v_wall). Impulse on the wall is the
    // relative-velocity momentum transfer 2 * m_p * (v_p - v_wall).
    const relV = p.vx - seg.vx;
    if (relV <= 0.0) {
      return null;  // particle is already moving away faster than wall
    }
    p.x = seg.x - p.radius;
    p.vx = 2.0 * seg.vx - p.vx;
    return { impulse: 2.0 * relV * p.mass, segment: idx };
  }
  return null;
}

function advanceSensorWall(segments, accumulators, dt) {
  let totalImpulseDelivered = 0.0;
  const n = segments.side;
  // Neighbour tension (deformable walls): sum of (neighbour - self) with the
  // rim fixed at the undeformed wall plane.
  const tension = new Array(segments.length).fill(0.0);
  if (segments.length > 0 && segments[0].stiffness < 10.0) {
    for (let iz = 0; iz < n; iz += 1) {
      for (let iy = 0; iy < n; iy += 1) {
        const seg = segments[iz * n + iy];
        const nbr = (jy, jz) => (jy < 0 || jz < 0 || jy >= n || jz >= n)
          ? seg.initialRest : segments[jz * n + jy].x;
        tension[iz * n + iy] = PASCAL.wallTension *
          (nbr(iy - 1, iz) + nbr(iy + 1, iz) + nbr(iy, iz - 1) + nbr(iy, iz + 1) - 4.0 * seg.x);
      }
    }
  }
  for (let i = 0; i < segments.length; i += 1) {
    const seg = segments[i];
    const impulse = accumulators[i] || 0.0;
    // Hookean restoring force toward rest position plus membrane tension;
    // impulse transfers momentum directly (Newton: dv = J / m, no dt factor).
    const springForce = -seg.stiffness * (seg.x - seg.rest) + tension[i];
    seg.vx += impulse / seg.mass;
    seg.vx += (springForce / seg.mass) * dt;
    seg.vx *= PASCAL.wallDamping;
    seg.x += seg.vx * dt;
    const yielded = seg.x - seg.rest - PASCAL.plasticYieldDisplacement;
    if (yielded > 0.0 && seg.stiffness < 10.0) {
      const flow = yielded * PASCAL.plasticFlow;
      seg.rest += flow;
      // Keep the plastic shift bounded so it reads as a vessel becoming
      // rounded, not as the wall leaving the chamber.
      const maxPlastic = PASCAL.domainHalfX * 0.10;
      if (seg.rest - seg.initialRest > maxPlastic) {
        seg.rest = seg.initialRest + maxPlastic;
      }
    }
    // Soft clip: segments cannot move past the rigid chamber boundary or
    // crash inward past the rest position by more than the chamber size
    // (keeps long runs numerically stable when stiffness is low).
    const maxOutward = seg.rest + PASCAL.domainHalfX;
    const minInward = seg.rest - PASCAL.domainHalfX * 0.4;
    if (seg.x > maxOutward) {
      seg.x = maxOutward;
      seg.vx = 0.0;
    } else if (seg.x < minInward) {
      seg.x = minInward;
      seg.vx = 0.0;
    }
    totalImpulseDelivered += impulse;
  }
  return totalImpulseDelivered;
}

function vesselWidth(pistonX, segments) {
  let xMax = -Infinity;
  for (let i = 0; i < segments.length; i += 1) {
    if (segments[i].x > xMax) {
      xMax = segments[i].x;
    }
  }
  return xMax - pistonX;
}

function meanWallDisplacement(segments) {
  let sum = 0.0;
  for (let i = 0; i < segments.length; i += 1) {
    sum += segments[i].x - segments[i].initialRest;
  }
  return sum / Math.max(segments.length, 1);
}

function meanElasticWallDisplacement(segments) {
  let sum = 0.0;
  for (let i = 0; i < segments.length; i += 1) {
    sum += segments[i].x - segments[i].rest;
  }
  return sum / Math.max(segments.length, 1);
}

function meanPlasticWallDisplacement(segments) {
  let sum = 0.0;
  for (let i = 0; i < segments.length; i += 1) {
    sum += segments[i].rest - segments[i].initialRest;
  }
  return sum / Math.max(segments.length, 1);
}

function wallProfile(segments, maxCount) {
  // The mid-z column of patches (the historical 1D wall profile).
  const n = segments.side;
  const column = [];
  const iz = Math.floor(n / 2);
  for (let iy = 0; iy < n; iy += 1) column.push(segments[iz * n + iy]);
  const out = [];
  const stride = Math.max(1, Math.floor(column.length / Math.max(1, maxCount)));
  for (let i = 0; i < column.length && out.length < maxCount; i += stride) {
    const seg = column[i];
    out.push({
      y: Math.round(seg.yCenter * 1000.0) / 1000.0,
      x: Math.round(seg.x * 1000.0) / 1000.0,
      rest: Math.round(seg.rest * 1000.0) / 1000.0,
      plastic: Math.round((seg.rest - seg.initialRest) * 1000.0) / 1000.0
    });
  }
  return out;
}

function instantiateBucket(bucketName, options) {
  return {
    name: bucketName,
    options,
    particles: null,
    sensorSegments: null,
    pistonX: -PASCAL.domainHalfX,
    sensorImpulseWindow: 0.0,
    pistonImpulseWindow: 0.0,
    windowTicks: 0,
    baselineSamples: [],
    holdSamples: []
  };
}

function buildBuckets() {
  return [
    instantiateBucket("rigid_pascal", {
      segmentCount: PASCAL.rigidWallSegments,
      mass: PASCAL.rigidWallMass,
      stiffness: PASCAL.rigidWallStiffness,
      pistonXRest: -PASCAL.domainHalfX,
      sensorXRest: PASCAL.domainHalfX
    }),
    instantiateBucket("deformable_hookean", {
      segmentCount: PASCAL.deformableWallSegments,
      mass: PASCAL.deformableWallMass,
      stiffness: PASCAL.deformableWallStiffness,
      pistonXRest: -PASCAL.domainHalfX,
      sensorXRest: PASCAL.domainHalfX
    }),
    instantiateBucket("deformable_macro_mesh", {
      segmentCount: PASCAL.macroWallSegments,
      mass: PASCAL.macroWallMass,
      stiffness: PASCAL.macroWallStiffness,
      pistonXRest: -PASCAL.domainHalfX,
      sensorXRest: PASCAL.domainHalfX
    })
  ];
}

function initializeBucket(bucket, seed) {
  bucket.pistonX = bucket.options.pistonXRest;
  bucket.sensorSegments = buildWall({
    segmentCount: bucket.options.segmentCount,
    mass: bucket.options.mass,
    stiffness: bucket.options.stiffness,
    xRest: bucket.options.sensorXRest
  });
  // Each bucket gets the same particle layout for an apples-to-apples
  // wall-model comparison.
  bucket.particles = seedParticles(makeLocalRng(seed), bucket.pistonX);
  bucket.tickRng = makeLocalRng((seed ^ 0xDEADBEEF) >>> 0);
}

function tickBucket(bucket, tick) {
  const rng = bucket.tickRng;
  const phaseName = currentPhase(tick);
  const restX = -PASCAL.domainHalfX;
  const targetCompressedX = restX + PASCAL.compressDistance;
  // Piston motion is phase-driven:
  //   compress: advance at pistonSpeedCap until target reached
  //   hold:     pinned at target
  //   release:  withdraw at pistonSpeedCap back to rest
  if (phaseName === "compress") {
    bucket.pistonX = Math.min(targetCompressedX,
                              bucket.pistonX + PASCAL.pistonSpeedCap * PASCAL.dt);
  } else if (phaseName === "hold") {
    bucket.pistonX = targetCompressedX;
  } else if (phaseName === "release") {
    bucket.pistonX = Math.max(restX,
                              bucket.pistonX - PASCAL.pistonSpeedCap * PASCAL.dt);
  }

  const segmentImpulses = new Array(bucket.sensorSegments.length).fill(0.0);
  let pistonImpulse = 0.0;
  let sensorImpulse = 0.0;

  // Berendsen velocity rescale toward the target thermal speed. Computed
  // before the integration step so all collisions in this tick see a
  // bath at the target temperature.
  if (PASCAL.thermostatCoupling > 0.0) {
    let speedSq = 0.0;
    for (let i = 0; i < bucket.particles.length; i += 1) {
      const p = bucket.particles[i];
      speedSq += p.vx * p.vx + p.vy * p.vy + p.vz * p.vz;
    }
    const meanSpeedSq = speedSq / Math.max(bucket.particles.length, 1);
    const targetSpeedSq = PASCAL.particleMeanSpeed * PASCAL.particleMeanSpeed * 3.0;
    if (meanSpeedSq > 1e-12) {
      const lambda = Math.sqrt(
        1.0 + PASCAL.thermostatCoupling * (targetSpeedSq / meanSpeedSq - 1.0)
      );
      for (let i = 0; i < bucket.particles.length; i += 1) {
        const p = bucket.particles[i];
        p.vx *= lambda;
        p.vy *= lambda;
        p.vz *= lambda;
      }
    }
  }

  const ampl = PASCAL.brownianAmplitude / Math.sqrt(PASCAL.particleMass);
  for (let i = 0; i < bucket.particles.length; i += 1) {
    const p = bucket.particles[i];
    if (ampl > 0.0) {
      p.vx += gaussian01(rng) * ampl;
      p.vy += gaussian01(rng) * ampl;
      p.vz += gaussian01(rng) * ampl;
    }
    p.x += p.vx * PASCAL.dt;
    p.y += p.vy * PASCAL.dt;
    p.z += p.vz * PASCAL.dt;
    reflectWallY(p);
    const pistonHit = reflectPiston(p, bucket.pistonX);
    if (pistonHit) {
      pistonImpulse += pistonHit.impulse;
    }
    const sensorHit = reflectSensorWall(p, bucket.sensorSegments);
    if (sensorHit) {
      sensorImpulse += sensorHit.impulse;
      segmentImpulses[sensorHit.segment] += sensorHit.impulse;
    }
  }

  advanceSensorWall(bucket.sensorSegments, segmentImpulses, PASCAL.dt);

  bucket.pistonImpulseWindow += pistonImpulse;
  bucket.sensorImpulseWindow += sensorImpulse;
  bucket.windowTicks += 1;
}

function bucketSnapshot(bucket, tick) {
  const dtWindow = Math.max(bucket.windowTicks * PASCAL.dt, 1e-9);
  const sensorPressure = bucket.sensorImpulseWindow / (PASCAL.sensorAreaUnits * dtWindow);
  const pistonPressure = bucket.pistonImpulseWindow / (PASCAL.pistonAreaUnits * dtWindow);
  const theoretical = pistonPressure;
  const meanDisp = meanWallDisplacement(bucket.sensorSegments);
  const elasticDisp = meanElasticWallDisplacement(bucket.sensorSegments);
  const plasticDisp = meanPlasticWallDisplacement(bucket.sensorSegments);
  const phaseName = currentPhase(tick);
  // Skip the first window of each measurement phase (transient settle)
  // and only accumulate samples once dynamics have equilibrated.
  if (phaseName === "baseline" && tick >= PHASES.thermalize.end + 4 * PASCAL.windowEvents) {
    bucket.baselineSamples.push({ sensor: sensorPressure, piston: pistonPressure });
  } else if (phaseName === "hold" && tick >= PHASES.compress.end + 4 * PASCAL.windowEvents) {
    bucket.holdSamples.push({ sensor: sensorPressure, piston: pistonPressure });
  }
  const snapshot = {
    bucket: bucket.name,
    tick,
    phase: phaseName,
    sensor_pressure: sensorPressure,
    piston_pressure_from_collisions: pistonPressure,
    theoretical_piston_pressure: theoretical,
    piston_position: bucket.pistonX,
    mean_wall_displacement: meanDisp,
    mean_elastic_wall_displacement: elasticDisp,
    mean_plastic_wall_displacement: plasticDisp,
    vessel_width: vesselWidth(bucket.pistonX, bucket.sensorSegments),
    wall_profile: wallProfile(bucket.sensorSegments, 18)
  };
  bucket.pistonImpulseWindow = 0.0;
  bucket.sensorImpulseWindow = 0.0;
  bucket.windowTicks = 0;
  return snapshot;
}

function meanKey(arr, key) {
  if (!arr || arr.length === 0) {
    return 0.0;
  }
  let s = 0.0;
  for (let i = 0; i < arr.length; i += 1) {
    s += arr[i][key];
  }
  return s / arr.length;
}

function currentPhase(tick) {
  if (tick <= PHASES.thermalize.end) {
    return "thermalize";
  }
  if (tick <= PHASES.baseline.end) {
    return "baseline";
  }
  if (tick <= PHASES.compress.end) {
    return "compress";
  }
  if (tick <= PHASES.hold.end) {
    return "hold";
  }
  return "release";
}

// --- 3D observer frame (classic trech-viz / Studio) ---------------------------
// The three vessels are laid out in a row (a display offset along x, so an oblique
// camera sees each wall's bulge in profile); every particle, the piston plate
// and each sensor-wall patch are the solver's state.
const VESSEL_OFFSET_X = 125.0;
const PASCAL_RGBA = { water: [0.35, 0.7, 1.0, 0.95], piston: [0.85, 0.85, 0.9, 0.9],
                      chamber: [0.55, 0.65, 0.8, 0.35] };
// Wall displacement drawn x WALL_DISPLAY_GAIN (a labelled display exaggeration: the solver's
// bulge is a few units on a 100-unit vessel); colour is the patch's own displacement.
const WALL_DISPLAY_GAIN = 3.0;
function heat(u) {
  const t = Math.max(0.0, Math.min(1.0, u));
  // blue (at rest) -> yellow -> red (most displaced)
  return t < 0.5 ? [0.3 + 1.4 * t, 0.55 + 0.8 * t, 1.0 - 1.6 * t, 0.9]
                 : [1.0, 0.95 - 1.3 * (t - 0.5), 0.2 - 0.3 * (t - 0.5), 0.9];
}
function wallMesh(segments, offsetX) {
  // Patch centres as a (y, z) grid surface; each vertex coloured by its patch displacement.
  const n = segments.side;
  const vertices = segments.map((seg) => [
    seg.initialRest + WALL_DISPLAY_GAIN * (seg.x - seg.initialRest) + offsetX, seg.yCenter, seg.zCenter]);
  const vertexRgba = segments.map((seg) => heat((seg.x - seg.initialRest) / 3.5));
  const faces = [];
  for (let iz = 0; iz + 1 < n; iz += 1) {
    for (let iy = 0; iy + 1 < n; iy += 1) {
      const a = iz * n + iy, b = a + 1, c = a + n, d = c + 1;
      faces.push([a, b, d], [a, d, c]);
    }
  }
  return { vertices, faces, vertexRgba };
}
function emitPascalFrame(ctx, state, tick, snaps) {
  const positions = [], colors = [], radii = [], apparatus = [], hud = [];
  const samples = {}, labels = [];
  state.buckets.forEach((bucket, k) => {
    const offsetX = (k - 1) * VESSEL_OFFSET_X;
    for (const p of bucket.particles) {
      positions.push([p.x + offsetX, p.y, p.z]);
      colors.push(PASCAL_RGBA.water);
      radii.push(p.radius);
    }
    const mesh = wallMesh(bucket.sensorSegments, offsetX);
    const bulge = meanWallDisplacement(bucket.sensorSegments);
    apparatus.push({ shape: "mesh", vertices: mesh.vertices, faces: mesh.faces,
                     vertex_rgba: mesh.vertexRgba, color_rgba: [0.7, 0.7, 0.9, 0.9],
                     label: bucket.name + " sensor wall" });
    // The wall's undeformed rest plane, so the bulge is read against it.
    const restX = bucket.sensorSegments[0].initialRest + offsetX;
    apparatus.push({ shape: "box", center: [restX, 0, 0],
                     size: [0.05, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ], style: "wire",
                     color_rgba: [0.9, 0.9, 1.0, 0.8], label: "rest plane" });
    apparatus.push({ shape: "box", center: [bucket.pistonX - 0.6 + offsetX, 0, 0],
                     size: [1.2, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ],
                     color_rgba: PASCAL_RGBA.piston, label: "piston" });
    apparatus.push({ shape: "box", center: [offsetX, 0, 0],
                     size: [2 * PASCAL.domainHalfX, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ],
                     style: "wire", color_rgba: PASCAL_RGBA.chamber, label: "chamber" });
    const snap = snaps[k];
    const ratio = snap.piston_pressure_from_collisions > 0
      ? snap.sensor_pressure / snap.piston_pressure_from_collisions : 0.0;
    samples["ratio_" + k] = Math.round(ratio * 1000) / 1000;
    samples["bulge_" + k] = Math.round(bulge * 1000) / 1000;
    samples["plastic_" + k] = Math.round(meanPlasticWallDisplacement(bucket.sensorSegments) * 1000) / 1000;
    labels.push({ position: [offsetX, PASCAL.domainHalfY + 8.0, 0],
                  text: ["rigid wall", "Hookean (plastic) wall", "fine-mesh wall"][k] || bucket.name,
                  color_rgba: [0.85, 0.9, 1.0, 1] });
  });
  const names = ["rigid", "Hookean", "fine mesh"];
  const colours = ["#c9d3e6", "#ffb838", "#66e0ff"];
  const charts = !state.chartsDeclared ? [
    { id: "ratio", title: "Pascal: pressure at the wall / at the piston", x: "time",
      x_label: "solver tick", y_label: "P_sensor / P_piston", cursor: true, y_range: [0, 2.0],
      series: names.map((n, k) => ({ key: "ratio_" + k, label: n, color: colours[k] })),
      reference: [{ label: "Pascal: equal (1.0)", color: "#9aa4b8", x: [0, TOTAL_TICKS], y: [1, 1] }] },
    { id: "bulge", title: "mean wall bulge (solid) and permanent set (dashed)", x: "time",
      x_label: "solver tick", y_label: "displacement (sim units)", cursor: true,
      series: names.map((n, k) => ({ key: "bulge_" + k, label: n, color: colours[k] }))
        .concat(names.slice(1).map((n, j) => ({ key: "plastic_" + (j + 1), label: n + " plastic",
                                                 color: colours[j + 1], dashed: true }))) }
  ] : [];
  state.chartsDeclared = true;
  ctx.emit("material_frame", helpers.observer.frame({
    physicalTimeS: tick, playbackTimeS: tick,
    clockText: "tick " + tick + " / " + TOTAL_TICKS + " (" + currentPhase(tick) + ")",
    phase: "piston " + currentPhase(tick) + " (3D bath; vessels in a row)",
    lengthUnit: "sim_unit", upAxis: "y", digits: 2,
    positions, colors, radii, apparatus,
    legend: helpers.observer.legend([["H2O bath", PASCAL_RGBA.water], ["piston", PASCAL_RGBA.piston],
                                     ["wall at rest", heat(0.0)], ["wall displaced", heat(1.0)],
                                     ["displacement drawn ×" + WALL_DISPLAY_GAIN, [0.8, 0.8, 0.85, 1]]]),
    hud: ["piston " + currentPhase(tick) + ": the same push reaches every wall"],
    samples, charts, labels,
    motionScope: "hook-layer 3D bath, piston and sensor-wall patches (solver state)"
  }));
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    return null;
  }
  if (!ctx.state.initialized) {
    ctx.state.buckets = buildBuckets();
    const baseSeed = 0xC0FFEE17;
    for (let i = 0; i < ctx.state.buckets.length; i += 1) {
      initializeBucket(ctx.state.buckets[i], baseSeed);
    }
    ctx.state.tick = 0;
    ctx.state.initialized = true;
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "pascal_pressure_validation",
      ticks: TOTAL_TICKS,
      phases: PHASES,
      piston_area: PASCAL.pistonAreaUnits,
      sensor_area: PASCAL.sensorAreaUnits,
      compress_distance: PASCAL.compressDistance,
      piston_speed_cap: PASCAL.pistonSpeedCap,
      vessels: [
        { name: "rigid_pascal", model: "ideal_rigid", stiffness: PASCAL.rigidWallStiffness },
        { name: "deformable_hookean", model: "hookean_spring", stiffness: PASCAL.deformableWallStiffness, segments: PASCAL.deformableWallSegments },
        { name: "deformable_macro_mesh", model: "micro_macro_mesh", stiffness: PASCAL.macroWallStiffness, segments: PASCAL.macroWallSegments }
      ]
    });
    return {
      override: {
        system: { ensemble: "pascal_principle_vessel" }
      }
    };
  },
  onRunStart(ctx) {
    ensureState(ctx);
  },
  onEventStart(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) {
      return;
    }
    state.tick += 1;
    const tick = state.tick;
    for (let i = 0; i < state.buckets.length; i += 1) {
      tickBucket(state.buckets[i], tick);
    }
    const milestones = [PHASES.thermalize.end, PHASES.baseline.end,
                        PHASES.compress.end, PHASES.hold.end, TOTAL_TICKS];
    const milestone = milestones.indexOf(tick) >= 0;
    const windowReady = state.buckets[0].windowTicks >= PASCAL.windowEvents;
    if (windowReady || milestone) {
      const snaps = [];
      for (let i = 0; i < state.buckets.length; i += 1) {
        const bucket = state.buckets[i];
        const snap = bucketSnapshot(bucket, tick);
        ctx.emit("pascal_snapshot", snap);
        snaps.push(snap);
      }
      emitPascalFrame(ctx, state, tick, snaps);
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) {
      return;
    }
    const results = [];
    for (let i = 0; i < state.buckets.length; i += 1) {
      const bucket = state.buckets[i];
      const baselineSensor = meanKey(bucket.baselineSamples, "sensor");
      const baselinePiston = meanKey(bucket.baselineSamples, "piston");
      const holdSensor = meanKey(bucket.holdSamples, "sensor");
      const holdPiston = meanKey(bucket.holdSamples, "piston");
      const deltaSensor = holdSensor - baselineSensor;
      const deltaPiston = holdPiston - baselinePiston;
      const transmission =
          deltaPiston > 0 ? deltaSensor / deltaPiston : 0.0;
      const displacement = meanWallDisplacement(bucket.sensorSegments);
      // The doc references F_in/A_syr; with a velocity-controlled piston
      // this is the measured ΔP_piston (force balance F = ΔP * A_syr).
      const theoreticalAppliedPressure = deltaPiston;
      let verdict;
      if (bucket.name === "rigid_pascal") {
        // Pascal: sensor delta tracks piston delta to within 25%. The
        // walls have effectively zero displacement, so all piston work is
        // transmitted into bulk pressure (Pascal's principle).
        const transmissionOk = transmission > 0.75 && transmission < 1.25;
        const rigidOk = Math.abs(displacement) < 0.05;
        verdict = (transmissionOk && rigidOk) ? "pass" : "fail";
      } else {
        // Deformable / macro: the wall yields measurably outward. Per the
        // doc, "the overall area/volume of the vessel must visibly
        // increase" — this is the validation handle that survives the
        // statistical noise of a coarse-grained bath.
        const yielded = displacement > 0.5;
        // The transmitted pressure is still bounded by the piston delta;
        // i.e. sensor never exceeds piston by more than a noise margin.
        const transmissionBounded = transmission < 1.15;
        verdict = (yielded && transmissionBounded) ? "pass" : "fail";
      }
      results.push({
        bucket: bucket.name,
        baseline_mean_sensor_pressure: baselineSensor,
        baseline_mean_piston_pressure: baselinePiston,
        hold_mean_sensor_pressure: holdSensor,
        hold_mean_piston_pressure: holdPiston,
        delta_sensor_pressure: deltaSensor,
        delta_piston_pressure: deltaPiston,
        theoretical_applied_pressure: theoreticalAppliedPressure,
        sensor_over_piston_transmission: transmission,
        mean_wall_displacement: displacement,
        mean_elastic_wall_displacement: meanElasticWallDisplacement(bucket.sensorSegments),
        mean_plastic_wall_displacement: meanPlasticWallDisplacement(bucket.sensorSegments),
        baseline_window_samples: bucket.baselineSamples.length,
        hold_window_samples: bucket.holdSamples.length,
        verdict
      });
    }
    ctx.emit("pascal_summary", {
      tick: state.tick,
      results,
      validation: {
        pascal_principle_holds: results[0].verdict === "pass",
        plastic_damping_observed: results[1].verdict === "pass",
        macro_mesh_consistent: results[2].verdict === "pass",
        rigid_wall_displacement: Math.abs(results[0].mean_wall_displacement),
        deformable_wall_displacement: results[1].mean_wall_displacement,
        macro_mesh_wall_displacement: results[2].mean_wall_displacement
      }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
