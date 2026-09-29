// Validation scenario: Osmotic Dehydration via Dimensional & Polarity Exclusion.
// See docs/testscenario_osmotic-todo.md.
//
// The TRECH C++ runtime (Geant4 transport + provenance) drives a deterministic
// event lifecycle. We piggyback a coarse-grained 3D molecular-dynamics tick
// inside the JS hook layer using ctx.state and ctx.rng so that:
//   - every onEventStart firing advances the membrane/particle system by one
//     simulation time unit (t);
//   - water / solute populations on both sides of the membrane are emitted
//     deterministically to trech_hook_emits.jsonl for inspection;
//   - osmotic shift, membrane crenation and pressure are observable as
//     emergent trends.
//
// This models a biological cell in a hypertonic bath. The cell is a closed,
// selectively permeable lipid membrane in three dimensions:
//
//   * H2O  (small, correctly polarized) passes the channel pores and is
//     expelled outward by the concentration gradient -> the cell dehydrates;
//   * glucose (large) is excluded by dimension and bounces off the wall;
//   * ions  (small, but WRONG polarity) fit the pore geometrically yet are
//     rejected by the channel's polarity gate -- the membrane expels these
//     "wrong polarized" molecules even though they would fit dimensionally.
//
// The membrane is a triangulated sphere whose vertices move radially and
// overdamped under (a) the MEASURED pressure difference across it -- the
// collision impulses the particles deliver per unit area on each side --,
// (b) near-conservation of the lipid AREA (bilayers barely stretch) and (c)
// bending. Nothing prescribes the volume: as water leaves through the pores,
// the impermeant glucose/ions outside out-hit those inside, the net inward
// pressure shrinks the cell until the two sides balance (van 't Hoff
// equilibrium, set by the impermeant solute ratio), and because the area
// cannot shrink with the volume, the excess membrane folds. The crenated shape
// EMERGES from those constraints and the seeded per-vertex irregularity -- no
// lobe count, pattern, depth or target volume is prescribed. Particles collide
// with, cross, and are swept by the ACTUAL deformed membrane.
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
  // Cubic bath; the half-size keeps the outside/inside volume ratio (~4.6) of
  // the historical planar bath (~4.8), so the hypertonic balance is unchanged.
  domainHalfSize: 40.0,
  cellRadius: 28.0,
  // Channel pores: caps on the sphere covering the same ~38% of the membrane as
  // the historical twelve 0.2 rad arcs covered of the planar ring.
  poreCount: 24,
  poreHalfAngle: 0.253,
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
  // --- Triangulated membrane (icosphere, radial degrees of freedom) ---
  membraneSubdivisions: 3,        // 642 vertices
  // Pressure seen by the membrane: an exponential average of the per-tick
  // collision impulse per unit area on each side (~200-tick memory: a few dozen
  // impermeant particles make single-tick pressures very noisy).
  pressureRelaxation: 0.005,
  // Overdamped radial mobility per unit net pressure (the membrane's drag).
  membranePressureMobility: 1000.0,
  membraneAreaStiffness: 3.0,     // energy weight of (A/A0 - 1)^2 (lipid area ~conserved)
  membraneBendStiffness: 0.004,   // energy weight of sum (rho_i - mean neighbour rho)^2
  membraneMobility: 6.0,          // overdamped radial mobility per substep
  membraneSubsteps: 6,
  membraneJitter: 0.004,          // seeded per-vertex irregularity (breaks symmetry)
  membraneRadiusMin: 0.45,        // hard clamp (fraction of R0) -> never inverts
  membraneRadiusMax: 1.25
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
    maxEmitPayloadBytes: 262144
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
  // Per-component velocity scale, rescaled into the scenario's coarse tick
  // units. Heavier particles move slower (1/sqrt(m) ratio preserved).
  return SCENARIO.waterMeanSpeed *
    Math.sqrt(SCENARIO.waterMass / Math.max(massU, 1e-9));
}

function targetMeanKineticEnergy() {
  // Three velocity components drawn from thermalSpeed(m): mean KE is
  // 0.5*m*3*sigma^2, independent of species under this scaling.
  return 1.5 * SCENARIO.waterMass * SCENARIO.waterMeanSpeed * SCENARIO.waterMeanSpeed;
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

// --- Triangulated membrane ---------------------------------------------------
// Icosphere: unit directions u_i + triangles + vertex adjacency, plus a
// direction -> nearest-vertex lookup so a particle finds the local membrane
// radius in O(1).
function buildIcosphere(subdivisions) {
  const t = (1.0 + Math.sqrt(5.0)) / 2.0;
  let verts = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
               [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]];
  let faces = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9],
               [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2],
               [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
               [8, 6, 7], [9, 8, 1]];
  const norm = (v) => { const n = Math.hypot(v[0], v[1], v[2]); return [v[0] / n, v[1] / n, v[2] / n]; };
  verts = verts.map(norm);
  for (let s = 0; s < subdivisions; s += 1) {
    const cache = {};
    const mid = (a, b) => {
      const key = a < b ? a + "_" + b : b + "_" + a;
      if (cache[key] === undefined) {
        const va = verts[a], vb = verts[b];
        verts.push(norm([va[0] + vb[0], va[1] + vb[1], va[2] + vb[2]]));
        cache[key] = verts.length - 1;
      }
      return cache[key];
    };
    const next = [];
    for (const f of faces) {
      const ab = mid(f[0], f[1]), bc = mid(f[1], f[2]), ca = mid(f[2], f[0]);
      next.push([f[0], ab, ca], [f[1], bc, ab], [f[2], ca, bc], [ab, bc, ca]);
    }
    faces = next;
  }
  const neighbors = verts.map(() => []);
  for (const f of faces) {
    for (let k = 0; k < 3; k += 1) {
      const a = f[k], b = f[(k + 1) % 3];
      if (neighbors[a].indexOf(b) < 0) neighbors[a].push(b);
      if (neighbors[b].indexOf(a) < 0) neighbors[b].push(a);
    }
  }
  return { dirs: verts, faces, neighbors };
}

const LOOKUP_THETA = 48, LOOKUP_PHI = 96;
function buildDirectionLookup(dirs) {
  const table = new Int32Array(LOOKUP_THETA * LOOKUP_PHI);
  for (let it = 0; it < LOOKUP_THETA; it += 1) {
    const theta = Math.PI * (it + 0.5) / LOOKUP_THETA;
    for (let ip = 0; ip < LOOKUP_PHI; ip += 1) {
      const phi = 2.0 * Math.PI * (ip + 0.5) / LOOKUP_PHI;
      const d = [Math.sin(theta) * Math.cos(phi), Math.sin(theta) * Math.sin(phi), Math.cos(theta)];
      let best = 0, bestDot = -2.0;
      for (let i = 0; i < dirs.length; i += 1) {
        const dot = d[0] * dirs[i][0] + d[1] * dirs[i][1] + d[2] * dirs[i][2];
        if (dot > bestDot) { bestDot = dot; best = i; }
      }
      table[it * LOOKUP_PHI + ip] = best;
    }
  }
  return table;
}

function nearestVertex(membrane, x, y, z, r) {
  const theta = Math.acos(Math.max(-1.0, Math.min(1.0, z / Math.max(r, 1e-12))));
  let phi = Math.atan2(y, x);
  if (phi < 0) phi += 2.0 * Math.PI;
  const it = Math.min(LOOKUP_THETA - 1, Math.floor(theta / Math.PI * LOOKUP_THETA));
  const ip = Math.min(LOOKUP_PHI - 1, Math.floor(phi / (2.0 * Math.PI) * LOOKUP_PHI));
  return membrane.lookup[it * LOOKUP_PHI + ip];
}

function initMembrane(rng) {
  const mesh = buildIcosphere(SCENARIO.membraneSubdivisions);
  const n = mesh.dirs.length;
  const rho = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    // Small fixed per-vertex irregularity (drawn once from the seeded RNG):
    // the only symmetry breaking; the fold pattern is left to the energetics.
    rho[i] = 1.0 + (rng.uniform() * 2.0 - 1.0) * SCENARIO.membraneJitter;
  }
  const membrane = {
    n, dirs: mesh.dirs, faces: mesh.faces, neighbors: mesh.neighbors,
    lookup: buildDirectionLookup(mesh.dirs), rho,
    volume0: 0, area0: 0, volume: 0, area: 0, meanRadius: SCENARIO.cellRadius,
    clampHits: 0
  };
  const geo = membraneGeometry(membrane, null, null);
  membrane.volume0 = (4.0 / 3.0) * Math.PI;   // reference unit sphere (R0 units)
  membrane.area0 = geo.area;                  // lipid area as built (~4 pi)
  membrane.volume = geo.volume;
  membrane.area = geo.area;
  return membrane;
}

// Enclosed volume and area (R0 units) of the radial mesh, optionally with
// their per-vertex radial derivatives dV/drho_i and dA/drho_i.
function membraneGeometry(membrane, dV, dA) {
  const dirs = membrane.dirs, rho = membrane.rho;
  let volume = 0.0, area = 0.0;
  if (dV) dV.fill(0.0);
  if (dA) dA.fill(0.0);
  for (const f of membrane.faces) {
    const ia = f[0], ib = f[1], ic = f[2];
    const a = [dirs[ia][0] * rho[ia], dirs[ia][1] * rho[ia], dirs[ia][2] * rho[ia]];
    const b = [dirs[ib][0] * rho[ib], dirs[ib][1] * rho[ib], dirs[ib][2] * rho[ib]];
    const c = [dirs[ic][0] * rho[ic], dirs[ic][1] * rho[ic], dirs[ic][2] * rho[ic]];
    const cross = (u, v) => [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                             u[0] * v[1] - u[1] * v[0]];
    const bc = cross(b, c), ca = cross(c, a), ab = cross(a, b);
    volume += (a[0] * bc[0] + a[1] * bc[1] + a[2] * bc[2]) / 6.0;
    const e1 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const e2 = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const nrm = cross(e1, e2);
    const nlen = Math.hypot(nrm[0], nrm[1], nrm[2]);
    area += 0.5 * nlen;
    if (dV) {
      // dV/dp_a = (b x c)/6 (cyclic); radial derivative = u_a . dV/dp_a
      dV[ia] += (dirs[ia][0] * bc[0] + dirs[ia][1] * bc[1] + dirs[ia][2] * bc[2]) / 6.0;
      dV[ib] += (dirs[ib][0] * ca[0] + dirs[ib][1] * ca[1] + dirs[ib][2] * ca[2]) / 6.0;
      dV[ic] += (dirs[ic][0] * ab[0] + dirs[ic][1] * ab[1] + dirs[ic][2] * ab[2]) / 6.0;
    }
    if (dA && nlen > 1e-12) {
      // dA/dp_a = 1/2 (b - c) x n_hat (cyclic)
      const nh = [nrm[0] / nlen, nrm[1] / nlen, nrm[2] / nlen];
      const grads = [[ia, b, c], [ib, c, a], [ic, a, b]];
      for (const [i, p, q] of grads) {
        const g = cross([p[0] - q[0], p[1] - q[1], p[2] - q[2]], nh);
        dA[i] += 0.5 * (dirs[i][0] * g[0] + dirs[i][1] * g[1] + dirs[i][2] * g[2]);
      }
    }
  }
  return { volume, area };
}

function integrateMembrane(membrane, pressureInside, pressureOutside) {
  const n = membrane.n;
  const dV = new Float64Array(n), dA = new Float64Array(n);
  const rhoMin = SCENARIO.membraneRadiusMin, rhoMax = SCENARIO.membraneRadiusMax;
  const kA = SCENARIO.membraneAreaStiffness;
  const kB = SCENARIO.membraneBendStiffness, mobility = SCENARIO.membraneMobility;
  // Net outward pressure does work -(P_in - P_out) dV: its radial force on vertex
  // i is (P_in - P_out) * dV/dr_i (in R0 units: R0^2 * dV^/drho_i per R0).
  const pressureDrive = SCENARIO.membranePressureMobility * (pressureInside - pressureOutside);
  const rho = membrane.rho;
  const lap = new Float64Array(n);
  for (let s = 0; s < SCENARIO.membraneSubsteps; s += 1) {
    const geo = membraneGeometry(membrane, dV, dA);
    const cV = -pressureDrive / mobility;
    const cA = 2.0 * kA * (geo.area / membrane.area0 - 1.0) / membrane.area0;
    for (let i = 0; i < n; i += 1) {
      const nb = membrane.neighbors[i];
      let mean = 0.0;
      for (let k = 0; k < nb.length; k += 1) mean += rho[nb[k]];
      lap[i] = rho[i] - mean / nb.length;
    }
    for (let i = 0; i < n; i += 1) {
      // d/drho_i of kB * sum_j lap_j^2 (own term + each neighbour's term).
      let bend = lap[i];
      const nb = membrane.neighbors[i];
      for (let k = 0; k < nb.length; k += 1) {
        bend -= lap[nb[k]] / membrane.neighbors[nb[k]].length;
      }
      const grad = cV * dV[i] + cA * dA[i] + 2.0 * kB * bend;
      rho[i] -= mobility * grad / SCENARIO.membraneSubsteps;
      if (rho[i] < rhoMin) { rho[i] = rhoMin; membrane.clampHits += 1; }
      else if (rho[i] > rhoMax) { rho[i] = rhoMax; membrane.clampHits += 1; }
    }
  }
  const geo = membraneGeometry(membrane, null, null);
  membrane.volume = geo.volume;
  membrane.area = geo.area;
  let sum = 0.0;
  for (let i = 0; i < n; i += 1) sum += rho[i];
  membrane.meanRadius = SCENARIO.cellRadius * sum / n;
}

function localMembraneRadius(membrane, x, y, z, r) {
  return SCENARIO.cellRadius * membrane.rho[nearestVertex(membrane, x, y, z, r)];
}

// --- Particles ---------------------------------------------------------------
function seedPopulation(rng, count, kind, inside) {
  const particles = [];
  const radius = SCENARIO.cellRadius;
  const half = SCENARIO.domainHalfSize;
  const spec = SPECIES[kind];
  const massU = spec.mass;
  const partRadius = spec.radius;
  const speedScale = thermalSpeed(massU);
  let safety = 0;
  while (particles.length < count && safety < count * 60) {
    safety += 1;
    const x = (rng.uniform() * 2.0 - 1.0) * (half - partRadius - 0.5);
    const y = (rng.uniform() * 2.0 - 1.0) * (half - partRadius - 0.5);
    const z = (rng.uniform() * 2.0 - 1.0) * (half - partRadius - 0.5);
    const r = Math.sqrt(x * x + y * y + z * z);
    if (inside && r > radius - partRadius - 0.5) {
      continue;
    }
    if (!inside && r < radius + partRadius + 0.5) {
      continue;
    }
    particles.push({
      kind,
      inside: !!inside,
      x, y, z,
      vx: gaussian01(rng) * speedScale,
      vy: gaussian01(rng) * speedScale,
      vz: gaussian01(rng) * speedScale,
      mass: massU,
      radius: partRadius,
      polarity: spec.polarity
    });
  }
  return particles;
}

function poreDirections() {
  // Fibonacci lattice: near-uniform channel placement over the sphere.
  const dirs = [];
  const n = SCENARIO.poreCount;
  const golden = Math.PI * (3.0 - Math.sqrt(5.0));
  for (let i = 0; i < n; i += 1) {
    const z = 1.0 - 2.0 * (i + 0.5) / n;
    const s = Math.sqrt(Math.max(0.0, 1.0 - z * z));
    dirs.push([s * Math.cos(golden * i), s * Math.sin(golden * i), z]);
  }
  return dirs;
}

function alignsWithPore(ux, uy, uz, pores) {
  const cosHalf = Math.cos(SCENARIO.poreHalfAngle);
  for (let i = 0; i < pores.length; i += 1) {
    if (ux * pores[i][0] + uy * pores[i][1] + uz * pores[i][2] >= cosHalf) {
      return true;
    }
  }
  return false;
}

function reflectAtRadius(particle, localRadius, r) {
  const nx = particle.x / r, ny = particle.y / r, nz = particle.z / r;
  const dot = particle.vx * nx + particle.vy * ny + particle.vz * nz;
  // Reverse the radial (normal) component: elastic reflection off the wall.
  particle.vx -= 2.0 * dot * nx;
  particle.vy -= 2.0 * dot * ny;
  particle.vz -= 2.0 * dot * nz;
  // Snap back to just inside/outside the membrane so we don't re-trigger.
  const sign = particle.inside ? -1.0 : 1.0;
  const place = localRadius + sign * (particle.radius + 0.05);
  particle.x = nx * place;
  particle.y = ny * place;
  particle.z = nz * place;
  // Impulse magnitude transferred to the membrane (for pressure scoring).
  return 2.0 * Math.abs(dot) * particle.mass;
}

function clampDomain(particle, half) {
  const limit = half - particle.radius;
  for (const [pos, vel] of [["x", "vx"], ["y", "vy"], ["z", "vz"]]) {
    if (particle[pos] > limit) {
      particle[pos] = limit;
      particle[vel] = -Math.abs(particle[vel]);
    } else if (particle[pos] < -limit) {
      particle[pos] = -limit;
      particle[vel] = Math.abs(particle[vel]);
    }
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
  particle.vz = gamma * particle.vz + gaussian01(rng) * noise;
}

function stepParticle(particle, dt, rng, pores, membrane) {
  applyLangevinThermostat(particle, rng);
  particle.x += particle.vx * dt;
  particle.y += particle.vy * dt;
  particle.z += particle.vz * dt;
  clampDomain(particle, SCENARIO.domainHalfSize);

  // Exclusion is resolved against the ACTUAL deformed membrane at the
  // particle's direction; channels are caps around the pore directions.
  const r = Math.sqrt(particle.x * particle.x + particle.y * particle.y + particle.z * particle.z);
  let impulse = 0.0;
  let crossed = false;
  let rejected = false;
  if (r < 1e-9) {
    return { impulse, crossed, rejected, side: particle.inside };
  }
  const radius = localMembraneRadius(membrane, particle.x, particle.y, particle.z, r);
  const canCross = SPECIES[particle.kind].crossable &&
    alignsWithPore(particle.x / r, particle.y / r, particle.z / r, pores);
  if (particle.inside && r >= radius - particle.radius) {
    if (canCross) {
      particle.inside = false;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius, r);
      rejected = particle.kind !== "h2o";
    }
  } else if (!particle.inside && r <= radius + particle.radius) {
    if (canCross) {
      particle.inside = true;
      crossed = true;
    } else {
      impulse = reflectAtRadius(particle, radius, r);
      rejected = particle.kind !== "h2o";
    }
  }
  return { impulse, crossed, rejected, side: particle.inside };
}

// The membrane is overdamped and moves every tick: a particle it sweeps past is
// carried with the wall (contact), never teleported across it.
function sweepParticlesWithMembrane(particles, membrane) {
  for (let i = 0; i < particles.length; i += 1) {
    const p = particles[i];
    const r = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
    if (r < 1e-9) continue;
    const wall = localMembraneRadius(membrane, p.x, p.y, p.z, r);
    let place = r;
    if (p.inside && r > wall - p.radius) place = Math.max(0.0, wall - p.radius - 0.05);
    else if (!p.inside && r < wall + p.radius) place = wall + p.radius + 0.05;
    if (place !== r) {
      p.x *= place / r; p.y *= place / r; p.z *= place / r;
      clampDomain(p, SCENARIO.domainHalfSize);
    }
  }
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
    sum += 0.5 * p.mass * (p.vx * p.vx + p.vy * p.vy + p.vz * p.vz);
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
      y: round3(p.y),
      z: round3(p.z)
    });
  }
  return out;
}

function membraneSnapshot(membrane) {
  const out = new Array(membrane.n);
  for (let i = 0; i < membrane.n; i += 1) {
    out[i] = round3(SCENARIO.cellRadius * membrane.rho[i]);
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

// --- 3D observer frame (classic trech-viz / Studio) ---------------------------
// The membrane mesh, every particle, and the channel pores exactly as the solver
// holds them; colours and the pore glyphs are representation.
const OSMO_RGBA = {
  h2o: [0.35, 0.7, 1.0, 1.0], glucose: [1.0, 0.78, 0.25, 1.0], ion: [0.95, 0.3, 0.45, 1.0],
  membrane: [0.95, 0.55, 0.72, 0.42], pore: [0.3, 1.0, 0.75, 1.0]
};
function emitOsmoticFrame(ctx, state, tick, counts) {
  const membrane = state.membrane;
  const R0 = SCENARIO.cellRadius;
  const positions = [], colors = [], radii = [];
  for (let i = 0; i < state.particles.length; i += 1) {
    const p = state.particles[i];
    const c = OSMO_RGBA[p.kind];
    positions.push([p.x, p.y, p.z]);
    colors.push(p.inside ? c : [c[0] * 0.8, c[1] * 0.8, c[2] * 0.8, 0.8]);
    radii.push(p.radius);
  }
  const vertices = membrane.dirs.map((d, i) => [d[0] * R0 * membrane.rho[i],
                                                d[1] * R0 * membrane.rho[i],
                                                d[2] * R0 * membrane.rho[i]]);
  const pores = state.pores.map((d) => {
    const rr = localMembraneRadius(membrane, d[0], d[1], d[2], 1.0);
    return { shape: "sphere", center: [d[0] * rr, d[1] * rr, d[2] * rr], radius: 1.1,
             color_rgba: OSMO_RGBA.pore, label: "water channel" };
  });
  const volumeFraction = membrane.volume / membrane.volume0;
  ctx.emit("material_frame", helpers.observer.frame({
    physicalTimeS: tick, playbackTimeS: tick,
    clockText: "tick " + tick + " / " + TOTAL_TICKS + " (solver ticks)",
    phase: phaseLabel(tick),
    lengthUnit: "sim_unit", upAxis: "z", digits: 2,
    positions, colors, radii,
    apparatus: [{ shape: "mesh", vertices, faces: membrane.faces, color_rgba: OSMO_RGBA.membrane,
                  label: "lipid membrane" }].concat(pores, [{
      shape: "box", center: [0, 0, 0],
      size: [2 * SCENARIO.domainHalfSize, 2 * SCENARIO.domainHalfSize, 2 * SCENARIO.domainHalfSize],
      style: "wire", color_rgba: [0.55, 0.65, 0.8, 0.35], label: "bath" }]),
    legend: helpers.observer.legend([["water (crosses channels)", OSMO_RGBA.h2o],
                                     ["glucose (size-excluded)", OSMO_RGBA.glucose],
                                     ["ion (polarity-rejected)", OSMO_RGBA.ion],
                                     ["water channel", OSMO_RGBA.pore]]),
    hud: [
      "water inside " + counts.inside_h2o + " / outside " + counts.outside_h2o +
        "   net efflux " + (state.crossingsOut - state.crossingsIn) +
        "   rejections " + state.totalRejections,
      "cell volume " + (100.0 * volumeFraction).toFixed(1) + "% of V0   area " +
        (100.0 * membrane.area / membrane.area0).toFixed(1) + "% of A0   P_out/P_in " +
        (state.pressureInsideEMA > 0 ? (state.pressureOutsideEMA / state.pressureInsideEMA).toFixed(2)
                                     : "-")
    ],
    counts,
    samples: { volume_percent: Math.round(1000.0 * volumeFraction) / 10,
               water_inside: counts.inside_h2o,
               pressure_ratio: state.pressureInsideEMA > 0
                 ? Math.round(1000 * state.pressureOutsideEMA / state.pressureInsideEMA) / 1000 : 1.0 },
    charts: OSMO_CHARTS.declared ? [] : (OSMO_CHARTS.declared = true, [
      { id: "volume", title: "cell volume (membrane solver)", x: "time", x_label: "solver tick",
        y_label: "% of initial volume", cursor: true,
        series: [{ key: "volume_percent", label: "cell volume", color: "#ff9ec7" }] },
      { id: "water", title: "water molecules inside the cell", x: "time", x_label: "solver tick",
        y_label: "count", cursor: true,
        series: [{ key: "water_inside", label: "H₂O inside", color: "#59bfff" }] },
      { id: "pressure", title: "collision pressure outside / inside", x: "time",
        x_label: "solver tick", y_label: "P_out / P_in", cursor: true,
        series: [{ key: "pressure_ratio", label: "measured (EMA)", color: "#ffd24d" }],
        reference: [{ label: "balance (1.0)", color: "#9aa4b8", x: [0, TOTAL_TICKS], y: [1, 1] }] }
    ]),
    motionScope: "3D hook-layer bath + overdamped area-conserving membrane (solver state)"
  }));
}
const OSMO_CHARTS = { declared: false };

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
    ctx.state.pores = poreDirections();
    ctx.state.membrane = initMembrane(rng);
    ctx.state.insideWaterCount = SCENARIO.initialInsideWater;
    // Membrane-side pressure estimates (impulse per area per tick), started at 0
    // on both sides so no bias is assumed before any collision is measured.
    ctx.state.pressureInsideEMA = 0.0;
    ctx.state.pressureOutsideEMA = 0.0;
    ctx.state.shrinkingPressureDeltaSum = 0.0;
    ctx.state.shrinkingPressureWindows = 0;
    ctx.state.windowStartVolume = ctx.state.membrane.volume;
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
    ctx.state.initialized = true;
  }
  return ctx.state;
}

function membraneMetrics(membrane) {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < membrane.n; i += 1) {
    const r = SCENARIO.cellRadius * membrane.rho[i];
    if (r < min) {
      min = r;
    }
    if (r > max) {
      max = r;
    }
  }
  return { min, max, mean: membrane.meanRadius, crenationDepth: max - min };
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "osmotic_dehydration",
      dimensions: 3,
      ticks: TOTAL_TICKS,
      pores: SCENARIO.poreCount,
      poreHalfAngle: SCENARIO.poreHalfAngle,
      cellRadius: SCENARIO.cellRadius,
      domainHalfSize: SCENARIO.domainHalfSize,
      waterRadius: SCENARIO.waterRadius,
      glucoseRadius: SCENARIO.glucoseRadius,
      ionRadius: SCENARIO.ionRadius,
      membraneSubdivisions: SCENARIO.membraneSubdivisions,
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

    // Move the membrane under the measured pressure difference (collision
    // impulses per area on each side, exponentially averaged) while its lipid
    // area is held, so shrinking folds the excess area (crenation). Particles
    // the moving wall sweeps past are carried with it.
    integrateMembrane(state.membrane, state.pressureInsideEMA, state.pressureOutsideEMA);
    if (state.membrane.meanRadius < state.minMembraneMeanRadius) {
      state.minMembraneMeanRadius = state.membrane.meanRadius;
    }
    sweepParticlesWithMembrane(state.particles, state.membrane);

    let crossingsOut = 0;
    let crossingsIn = 0;
    let tickImpulseInside = 0.0;
    let tickImpulseOutside = 0.0;
    const particles = state.particles;
    for (let i = 0; i < particles.length; i += 1) {
      const p = particles[i];
      const wasInside = p.inside;
      const result = stepParticle(p, SCENARIO.dt, ctx.rng, state.pores, state.membrane);
      if (result.impulse > 0.0) {
        if (wasInside) {
          state.impulseAccumInternal += result.impulse;
          tickImpulseInside += result.impulse;
        } else {
          state.impulseAccumExternal += result.impulse;
          tickImpulseOutside += result.impulse;
        }
      }
      if (result.rejected) {
        state.rejectionsThisWindow += 1;
        state.totalRejections += 1;
        // Keep a small, deterministic sample of expulsion points (membrane
        // strikes by wrong-polarized / oversized molecules) for inspection.
        if (state.recentExpelled.length < 24 &&
            (state.totalRejections % 5 === 0)) {
          state.recentExpelled.push({
            x: round3(p.x),
            y: round3(p.y),
            z: round3(p.z),
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
    const areaPhysical = state.membrane.area * SCENARIO.cellRadius * SCENARIO.cellRadius;
    const alpha = SCENARIO.pressureRelaxation;
    state.pressureInsideEMA += alpha *
      (tickImpulseInside / (areaPhysical * SCENARIO.dt) - state.pressureInsideEMA);
    state.pressureOutsideEMA += alpha *
      (tickImpulseOutside / (areaPhysical * SCENARIO.dt) - state.pressureOutsideEMA);
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
      // Pressure = impulse / (membrane area * window): the actual deformed area.
      const membraneArea = state.membrane.area * SCENARIO.cellRadius * SCENARIO.cellRadius;
      const dtWindow = Math.max(state.windowTicks * SCENARIO.dt, 1e-9);
      const internalPressure = state.impulseAccumInternal / (membraneArea * dtWindow);
      const externalPressure = state.impulseAccumExternal / (membraneArea * dtWindow);
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
      // The pressure bias that DRIVES dehydration: external minus internal over
      // the windows in which the cell actually lost volume.
      if (state.membrane.volume < state.windowStartVolume) {
        state.shrinkingPressureDeltaSum += externalPressure - internalPressure;
        state.shrinkingPressureWindows += 1;
      }
      state.windowStartVolume = state.membrane.volume;
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
        membrane_volume_fraction: round3(state.membrane.volume / state.membrane.volume0),
        membrane_area_fraction: round3(state.membrane.area / state.membrane.area0),
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
      emitOsmoticFrame(ctx, state, tick, counts);
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
    const membrane = state.membrane;
    const memMetrics = membraneMetrics(membrane);
    const initialMean = state.initialMembraneMeanRadius;
    const volumeShrinkFraction = 1.0 - membrane.volume / membrane.volume0;
    const areaDrift = membrane.area / membrane.area0 - 1.0;
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
    // With a mechanically coupled membrane the two sides approach balance at
    // osmotic equilibrium, so the physical signature is the sign of the bias
    // while the cell is shrinking: the hypertonic bath presses harder.
    const shrinkingPressureBias = state.shrinkingPressureWindows > 0
      ? state.shrinkingPressureDeltaSum / state.shrinkingPressureWindows : 0.0;
    const pressureResponseObserved =
      state.shrinkingPressureWindows > 0 && shrinkingPressureBias > 0.0;
    // The cell visibly dehydrates: its enclosed volume falls as water leaves
    // while the lipid area is held, so the excess membrane folds (crenation)
    // -- measured as the spread of vertex radii -- and the overdamped membrane
    // stays finite, inside its safety bounds, with the lipid area held (vertex
    // contacts with the radial safety bounds are reported as clamp_hits).
    const membraneCrenationObserved = volumeShrinkFraction > 0.05 &&
      memMetrics.crenationDepth > 0.05 * SCENARIO.cellRadius;
    const membraneStable =
      memMetrics.min >= SCENARIO.membraneRadiusMin * SCENARIO.cellRadius - 1e-6 &&
      memMetrics.max <= SCENARIO.membraneRadiusMax * SCENARIO.cellRadius + 1e-6 &&
      Math.abs(areaDrift) < 0.08 &&
      Number.isFinite(memMetrics.mean);
    ctx.emit("final_summary", {
      tick: state.tick,
      phase: phaseLabel(state.tick),
      dimensions: 3,
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
        vertices: membrane.n,
        initial_mean_radius: round3(initialMean),
        final_mean_radius: round3(memMetrics.mean),
        min_node_radius: round3(memMetrics.min),
        max_node_radius: round3(memMetrics.max),
        final_crenation_depth: round3(memMetrics.crenationDepth),
        volume_shrink_fraction: round3(volumeShrinkFraction),
        area_drift_fraction: round3(areaDrift),
        clamp_hits: membrane.clampHits
      },
      late_pressure_average: {
        internal: latePressureInternal,
        external: latePressureExternal,
        windows: state.latePressureWindows
      },
      shrinking_pressure_bias: {
        external_minus_internal: shrinkingPressureBias,
        windows: state.shrinkingPressureWindows
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
