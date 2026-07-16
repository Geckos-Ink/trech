// A parameterized lava-lamp thermofluid scenario. Duration is an input, not an identity.
//
// Information discipline:
//   * Geant4 probes the configured carrier and reference wax blend: composition, density,
//     number/electron densities, and the interaction base used by TRECH's derived optics.
//   * ctx.cascade lifts those microscopic/material facts plus heater/geometry context into
//     thermophysical coefficients. It emits no cycle period, scripted phase, or target path.
//   * A deterministic persistent-parcel solver advances temperature, liquid fraction, density,
//     buoyancy, drag, cohesion, heat diffusion, and boundaries. Particle identity is conserved;
//     nothing is regenerated when motion changes direction.
//   * Geant4 does not itself solve phase change or CFD. The macro response surface and parcel
//     discretisation are explicit inferred/hook-layer approximations, not metrology-grade.
//   * The reference wax blend is a simulation material, not a consumer formulation or recipe.
//     Orange/blue/housing colours are labelled representation-only and never feed dynamics.
//
// Run with defaults:
//   build/dev/trech run examples/experiments/lava_lamp.js \
//     --output build/dev/out_lava_lamp
// README full-horizon run (ten physical minutes in ten display seconds):
//   build/dev/trech run examples/experiments/lava_lamp.js \
//     --param duration_s=600 --param playback_duration_s=10 \
//     --param simulation_ticks=100 --output build/dev/out_lava_lamp_readme_10m

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

const CARRIER = "G4_WATER";
const WAX_BASE = "G4_PARAFFIN";
const WAX_DENSIFIER = "G4_TETRACHLOROETHYLENE";
const WAX_BLEND = "lava_wax_blend";
const AIR = "G4_AIR";
const GLASS = "G4_GLASS_PLATE";

// Ideal-volume density matching puts this reference blend just above water when cold. TRECH's
// cascade infers the thermal response that lets the same material cross the carrier density when
// heated. The chlorinated component is a Geant4-visible density-modifier proxy, not a product
// formulation recommendation.
const WAX_DENSIFIER_MASS_FRACTION = 0.185;
const WAX_BLEND_DENSITY_G_CM3 = 1.010;
const waxBlendMaterial = {
  name: WAX_BLEND,
  densityGcm3: WAX_BLEND_DENSITY_G_CM3,
  components: [
    { material: WAX_BASE, fraction: 1.0 - WAX_DENSIFIER_MASS_FRACTION },
    { material: WAX_DENSIFIER, fraction: WAX_DENSIFIER_MASS_FRACTION }
  ]
};

const durationS = TRECH_VALUE.number("duration_s", {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful thermofluid solver advances.",
  default: 600.0, min: 30.0, max: 3600.0, step: 30.0
});
const playbackDurationS = TRECH_VALUE.number("playback_duration_s", {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 10.0, min: 1.0, max: 120.0, step: 1.0
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; internal physics uses bounded finer steps.",
  default: 120, min: 10, max: 2000, step: 10
});
const waxRepresentatives = TRECH_VALUE.integer("wax_representatives", {
  label: "Persistent wax parcels", group: "Precision", unit: "parcels",
  description: "Spatial solver resolution; inventory volume stays fixed as parcel count changes.",
  default: 240, min: 120, max: 480, step: 60
});
const maxPhysicsStepS = TRECH_VALUE.number("max_physics_step_s", {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal solver resolution; smaller steps refine heat, phase, and motion updates.",
  default: 0.4, min: 0.1, max: 1.0, step: 0.1
});
const renderSurfaceGridMm = TRECH_VALUE.number("render_surface_grid_mm", {
  label: "Wax surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated parcel state.",
  default: 1.25, min: 0.75, max: 2.5, step: 0.25
});
const heaterTemperatureK = TRECH_VALUE.number("heater_temperature_k", {
  label: "Heater temperature", group: "Conditions", unit: "K",
  description: "Lower thermal boundary condition; changing it changes the inferred response.",
  default: 333.15, min: 310.0, max: 350.0, step: 1.0
});
const ambientTemperatureK = TRECH_VALUE.number("ambient_temperature_k", {
  label: "Ambient temperature", group: "Conditions", unit: "K",
  description: "Upper/wall thermal boundary and initial carrier temperature.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
});
if (heaterTemperatureK <= ambientTemperatureK) {
  throw new Error("heater_temperature_k must exceed ambient_temperature_k");
}

const APPARATUS = {
  durationS,
  playbackDurationS,
  outputTicks: simulationTicks,
  outputTickIntervalS: durationS / simulationTicks,
  innerRadiusMm: 30.0,
  liquidHeightMm: 180.0,
  glassHeightMm: 190.0,
  heaterTemperatureK,
  ambientTemperatureK,
  representativeWaxParcels: waxRepresentatives,
  initialDroplets: 4,
  carrierThermalCells: 24,
  physicsStepS: maxPhysicsStepS,
  renderSurfaceGridMm
};
APPARATUS.aspectRatio = APPARATUS.liquidHeightMm / (2.0 * APPARATUS.innerRadiusMm);

const REPRESENTATION = {
  policy: "authored display tints; never physics inputs",
  waxTint: [1.0, 0.20, 0.025],
  waxWarmHighlight: [1.0, 0.64, 0.08],
  carrierTint: [0.10, 0.34, 0.58],
  housingColor: [0.055, 0.045, 0.075],
  waxAlpha: 0.82,
  waxSurfaceAlpha: 0.94
};

const Z_MIN_MM = 3.0;
const Z_MAX_MM = APPARATUS.liquidHeightMm - 3.0;
const RADIAL_MAX_MM = APPARATUS.innerRadiusMm - 2.2;
const REFERENCE_WAX_PARCELS = 240;
const REFERENCE_PARCEL_SPACING_MM = 2.7;
const NOMINAL_WAX_VOLUME_MM3 = REFERENCE_WAX_PARCELS *
  REFERENCE_PARCEL_SPACING_MM * REFERENCE_PARCEL_SPACING_MM *
  REFERENCE_PARCEL_SPACING_MM;
const PARCEL_SPACING_MM = Math.cbrt(NOMINAL_WAX_VOLUME_MM3 /
  APPARATUS.representativeWaxParcels);
const PARCEL_LENGTH_SCALE = PARCEL_SPACING_MM / REFERENCE_PARCEL_SPACING_MM;
const PARCEL_REST_MM = 2.5 * PARCEL_LENGTH_SCALE;
const PARCEL_SUPPORT_MM = 6.5 * PARCEL_LENGTH_SCALE;
const PARCEL_SUPPORT2_MM = PARCEL_SUPPORT_MM * PARCEL_SUPPORT_MM;
const TOPOLOGY_LINK_MM = 4.5 * PARCEL_LENGTH_SCALE;
// Retain the earlier parcel-scale topology contract for regression/provenance while rendering
// a wider observer-scale interface suitable for this deliberately coarse parcel discretisation.
const PARCEL_SURFACE_SIGMA_MM = 0.82 * PARCEL_SPACING_MM;
const PARCEL_SURFACE_ISO_LEVEL = 0.52;
const PARCEL_SURFACE_LINK_MM = Math.sqrt(8.0 * PARCEL_SURFACE_SIGMA_MM *
  PARCEL_SURFACE_SIGMA_MM * Math.log(2.0 / PARCEL_SURFACE_ISO_LEVEL));
const RENDER_SURFACE_SIGMA_MM = (4.2 / REFERENCE_PARCEL_SPACING_MM) * PARCEL_SPACING_MM;
const RENDER_SURFACE_ISO_LEVEL = 0.38;
// Pairwise lower bound for two equal Gaussian splats to share the emitted isosurface.
const RENDER_SURFACE_LINK_MM = Math.sqrt(8.0 * RENDER_SURFACE_SIGMA_MM *
  RENDER_SURFACE_SIGMA_MM * Math.log(2.0 / RENDER_SURFACE_ISO_LEVEL));
const FLUID_NECK_MIN_MM = (4.8 / REFERENCE_PARCEL_SPACING_MM) * PARCEL_SPACING_MM;
const FLUID_NECK_SAMPLES = 2;
const FLUID_NECK_WEIGHT = 0.35;
const MAX_SPEED_MM_S = 6.0;
const PAIR_REPULSION_MM_S2 = 22.0;
const PAIR_ACCEL_LIMIT_MM_S2 = 16.0;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
function clamp01(v) { return clamp(v, 0.0, 1.0); }
function bitCount(v) {
  let x = v >>> 0, count = 0;
  while (x !== 0) { count += x & 1; x >>>= 1; }
  return count;
}
function mix(a, b, t) { return a + (b - a) * t; }
function mixRgb(a, b, t) {
  return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];
}
function parcelNoise01(particleId, stream) {
  let x = (((particleId + 1) * 1664525) + ((stream + 1) * 1013904223)) >>> 0;
  x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
  return (x >>> 0) / 4294967296.0;
}
function finite(v, label) {
  const x = Number(v);
  if (!Number.isFinite(x)) throw new Error("non-finite inferred " + label);
  return x;
}
function phaseEquilibrium(temperatureK, meltingTemperatureK) {
  const widthK = 2.4;
  return 1.0 / (1.0 + Math.exp(-(temperatureK - meltingTemperatureK) / widthK));
}
function packedDropletPoints(count) {
  const spacing = PARCEL_SPACING_MM;
  let radius = spacing * (Math.cbrt(3.0 * count / (4.0 * Math.PI)) + 0.9);
  let candidates = [];
  while (candidates.length < count) {
    candidates = [];
    const half = Math.ceil(radius / spacing);
    for (let iz = -half; iz <= half; iz += 1) {
      for (let iy = -half; iy <= half; iy += 1) {
        for (let ix = -half; ix <= half; ix += 1) {
          const x = ix * spacing, y = iy * spacing, z = iz * spacing;
          const r2 = x * x + y * y + z * z;
          if (r2 <= radius * radius) candidates.push([x, y, z, r2]);
        }
      }
    }
    radius += 0.5 * spacing;
  }
  candidates.sort((a, b) => a[3] - b[3] || a[2] - b[2] || a[1] - b[1] || a[0] - b[0]);
  return candidates.slice(0, count);
}

function opticsFor(ctx, material) {
  const item = ctx.optics && ctx.optics[material];
  if (!item || !Array.isArray(item.display_rgb)) {
    throw new Error("ctx.optics missing Geant4-derived colour for " + material);
  }
  return {
    rgb: item.display_rgb.slice(0, 3).map(clamp01),
    refractiveIndex: Number(item.mean_refractive_index),
    absorptionLengthMm: Number(item.mean_absorption_length_mm),
    scatterLengthMm: Number(item.mean_scatter_length_mm)
  };
}

function inferredParameters(cascade) {
  return {
    source: "ctx.cascade(Geant4 material seed -> nano descriptor -> macro thermofluid)",
    meltingTemperatureK: clamp(finite(cascade.macro_melting_temperature_k,
      "melting temperature"), 307.0, 322.0),
    waxThermalExpansionPerK: clamp(finite(cascade.macro_wax_thermal_expansion_per_k,
      "wax thermal expansion"), 0.00055, 0.0016),
    liquidDensityOffsetFraction: clamp(finite(cascade.macro_liquid_density_offset_fraction,
      "liquid density offset"), 0.0, 0.02),
    waxHeatExchangePerS: clamp(finite(cascade.macro_wax_heat_exchange_per_s,
      "wax heat exchange"), 0.01, 0.15),
    phaseRelaxationPerS: clamp(finite(cascade.macro_phase_relaxation_per_s,
      "phase relaxation"), 0.02, 0.25),
    carrierThermalDiffusivityMm2S: clamp(finite(
      cascade.macro_carrier_thermal_diffusivity_mm2_s,
      "carrier thermal diffusivity"), 0.2, 30.0),
    effectiveDynamicViscosityPaS: clamp(finite(
      cascade.macro_effective_dynamic_viscosity_pa_s,
      "effective dynamic viscosity"), 0.08, 1.5),
    effectiveDropletRadiusMm: clamp(finite(cascade.macro_effective_droplet_radius_mm,
      "effective droplet radius"), 1.5, 7.0),
    cohesionAccelMmS2: clamp(finite(cascade.macro_cohesion_accel_mm_s2,
      "cohesion acceleration"), 0.0, 8.0),
    velocityRelaxationPerS: clamp(finite(cascade.macro_velocity_relaxation_per_s,
      "velocity relaxation"), 0.2, 4.0),
    heaterCouplingPerS: clamp(finite(cascade.macro_heater_coupling_per_s,
      "heater coupling"), 0.02, 0.35),
    topCoolingPerS: clamp(finite(cascade.macro_top_cooling_per_s,
      "top cooling"), 0.01, 0.30),
    carrierThermalExpansionPerK: clamp(finite(
      cascade.macro_carrier_thermal_expansion_per_k,
      "carrier thermal expansion"), 0.0001, 0.0007),
    waxToCarrierHeatCapacityRatio: clamp(finite(
      cascade.macro_wax_to_carrier_heat_capacity_ratio,
      "wax/carrier heat capacity ratio"), 0.01, 0.30),
    interfaceVelocityCouplingPerS: clamp(finite(
      cascade.macro_interface_velocity_coupling_per_s,
      "interfacial velocity coupling"), 0.1, 5.0),
    carrierCirculationMmS: clamp(finite(cascade.macro_carrier_circulation_mm_s,
      "carrier circulation"), 0.0, 3.0),
    carrierAdvectionPerS: clamp(finite(cascade.macro_carrier_advection_per_s,
      "carrier advection"), 0.05, 3.0),
    carrierVorticityPerS: clamp(finite(cascade.macro_carrier_vorticity_per_s,
      "carrier vorticity"), 0.0, 0.05),
    lateralPlumeFraction: clamp(finite(cascade.macro_lateral_plume_fraction,
      "lateral plume fraction"), 0.0, 1.0),
    responseSigma: clamp(finite(cascade.macro_response_sigma,
      "response sigma"), 0.0, 1.0)
  };
}

function frameClock(frameIndex) {
  const fraction = frameIndex / APPARATUS.outputTicks;
  return {
    physicalTimeS: fraction * APPARATUS.durationS,
    playbackTimeS: fraction * APPARATUS.playbackDurationS,
    timeScale: APPARATUS.durationS / APPARATUS.playbackDurationS
  };
}

function renderSurfaceHint(state) {
  const n = state.waxOptics.refractiveIndex;
  const fresnelR0 = Math.pow((n - 1.0) / (n + 1.0), 2.0);
  return {
    mode: "metaball",
    kernel: "gaussian",
    grid_spacing_mm: APPARATUS.renderSurfaceGridMm,
    sigma_mm: RENDER_SURFACE_SIGMA_MM,
    iso_level: RENDER_SURFACE_ISO_LEVEL,
    clip_cylinder: {
      axis: "z",
      radius_mm: RADIAL_MAX_MM,
      min_mm: Z_MIN_MM,
      max_mm: Z_MAX_MM
    },
    fluid_necking: {
      mode: "pair_gaussian",
      min_distance_mm: FLUID_NECK_MIN_MM,
      max_distance_mm: RENDER_SURFACE_LINK_MM,
      samples_per_pair: FLUID_NECK_SAMPLES,
      weight: FLUID_NECK_WEIGHT,
      preserves_component_topology: true,
      policy: "distance-weighted neck density fades continuously inside the existing fluid-interface connection radius"
    },
    fresnel_r0: fresnelR0,
    gloss: 0.78,
    opacity: REPRESENTATION.waxSurfaceAlpha,
    positions_unmodified: true,
    policy: "representation only: fluid-interface Gaussian surface from emitted parcel positions; parcel-scale topology retained separately"
  };
}

function carrierCellIndex(zMm) {
  const fraction = clamp01(zMm / APPARATUS.liquidHeightMm);
  return Math.min(APPARATUS.carrierThermalCells - 1,
    Math.floor(fraction * APPARATUS.carrierThermalCells));
}

function waxDensityGcm3(state, particleIndex) {
  const deltaT = state.temperatureK[particleIndex] - APPARATUS.ambientTemperatureK;
  const expansion = 1.0 + state.params.waxThermalExpansionPerK * deltaT;
  return state.waxColdDensityGcm3 / Math.max(0.8, expansion) *
    (1.0 - state.params.liquidDensityOffsetFraction * state.liquidFraction[particleIndex]);
}

function carrierDensityGcm3(state, cellIndex) {
  const deltaT = state.carrierTemperatureK[cellIndex] - APPARATUS.ambientTemperatureK;
  return state.carrierReferenceDensityGcm3 /
    Math.max(0.9, 1.0 + state.params.carrierThermalExpansionPerK * deltaT);
}

function gridKey(ix, iy, iz) { return ix + "," + iy + "," + iz; }
function buildSpatialGrid(state, cellSizeMm) {
  const grid = new Map();
  const inv = 1.0 / cellSizeMm;
  for (let i = 0; i < state.n; i += 1) {
    const ix = Math.floor((state.px[i] + APPARATUS.innerRadiusMm) * inv);
    const iy = Math.floor((state.py[i] + APPARATUS.innerRadiusMm) * inv);
    const iz = Math.floor(state.pz[i] * inv);
    const key = gridKey(ix, iy, iz);
    let cell = grid.get(key);
    if (!cell) { cell = []; grid.set(key, cell); }
    cell.push(i);
  }
  return grid;
}

function forEachNeighbourPair(state, grid, cellSizeMm, maximumDistance2, callback) {
  const inv = 1.0 / cellSizeMm;
  for (let i = 0; i < state.n; i += 1) {
    const ix = Math.floor((state.px[i] + APPARATUS.innerRadiusMm) * inv);
    const iy = Math.floor((state.py[i] + APPARATUS.innerRadiusMm) * inv);
    const iz = Math.floor(state.pz[i] * inv);
    for (let dxCell = -1; dxCell <= 1; dxCell += 1) {
      for (let dyCell = -1; dyCell <= 1; dyCell += 1) {
        for (let dzCell = -1; dzCell <= 1; dzCell += 1) {
          const cell = grid.get(gridKey(ix + dxCell, iy + dyCell, iz + dzCell));
          if (!cell) continue;
          for (let q = 0; q < cell.length; q += 1) {
            const j = cell[q];
            if (j <= i) continue;
            const dx = state.px[j] - state.px[i];
            const dy = state.py[j] - state.py[i];
            const dz = state.pz[j] - state.pz[i];
            const distance2 = dx * dx + dy * dy + dz * dz;
            if (distance2 < maximumDistance2) callback(i, j, dx, dy, dz, distance2);
          }
        }
      }
    }
  }
}

function advanceCarrierThermalField(state, dt) {
  const cells = APPARATUS.carrierThermalCells;
  const dz = APPARATUS.liquidHeightMm / cells;
  const diffusion = state.params.carrierThermalDiffusivityMm2S * dt / (dz * dz);
  const old = state.carrierTemperatureK;
  const next = state.carrierNextTemperatureK;
  for (let c = 0; c < cells; c += 1) {
    const below = c > 0 ? old[c - 1] : old[c];
    const above = c + 1 < cells ? old[c + 1] : old[c];
    next[c] = old[c] + diffusion * (below - 2.0 * old[c] + above);
  }
  next[0] += state.params.heaterCouplingPerS *
    (APPARATUS.heaterTemperatureK - next[0]) * dt;
  next[cells - 1] += state.params.topCoolingPerS *
    (APPARATUS.ambientTemperatureK - next[cells - 1]) * dt;
  state.carrierTemperatureK = next;
  state.carrierNextTemperatureK = old;
}

function applyThermalAndPhaseState(state, dt) {
  state.carrierHeatDeltaK.fill(0.0);
  const parcelCapacityShare = state.params.waxToCarrierHeatCapacityRatio / state.n;
  for (let i = 0; i < state.n; i += 1) {
    const cell = carrierCellIndex(state.pz[i]);
    const exchange = state.params.waxHeatExchangePerS * state.heatBias[i];
    const dT = exchange * (state.carrierTemperatureK[cell] - state.temperatureK[i]) * dt;
    state.temperatureK[i] += dT;
    state.carrierHeatDeltaK[cell] -= dT * parcelCapacityShare;
    const equilibrium = phaseEquilibrium(state.temperatureK[i],
      state.params.meltingTemperatureK);
    const relax = 1.0 - Math.exp(-state.params.phaseRelaxationPerS * dt);
    state.liquidFraction[i] = clamp01(state.liquidFraction[i] +
      (equilibrium - state.liquidFraction[i]) * relax);
    state.densityGcm3[i] = waxDensityGcm3(state, i);
  }
  for (let c = 0; c < APPARATUS.carrierThermalCells; c += 1) {
    state.carrierTemperatureK[c] += state.carrierHeatDeltaK[c];
  }
}

function applyPairDynamics(state, dt) {
  state.ax.fill(0.0); state.ay.fill(0.0); state.az.fill(0.0);
  state.mixVx.fill(0.0); state.mixVy.fill(0.0); state.mixVz.fill(0.0);
  state.neighbourCount.fill(0);
  const grid = buildSpatialGrid(state, PARCEL_SUPPORT_MM);
  forEachNeighbourPair(state, grid, PARCEL_SUPPORT_MM, PARCEL_SUPPORT2_MM,
    (i, j, dx, dy, dz, distance2) => {
    if (distance2 < 1e-12) return;
    const distance = Math.sqrt(distance2);
    const nx = dx / distance, ny = dy / distance, nz = dz / distance;
    const liquidPair = 0.30 + 0.70 * Math.min(state.liquidFraction[i],
      state.liquidFraction[j]);
    let acceleration = 0.0;
    if (distance < PARCEL_REST_MM) {
      acceleration = -PAIR_REPULSION_MM_S2 *
        (PARCEL_REST_MM - distance) / PARCEL_REST_MM;
    } else {
      const q = (distance - PARCEL_REST_MM) /
        (PARCEL_SUPPORT_MM - PARCEL_REST_MM);
      acceleration = state.params.cohesionAccelMmS2 * liquidPair * q * (1.0 - q);
    }
    acceleration = clamp(acceleration, -PAIR_ACCEL_LIMIT_MM_S2, PAIR_ACCEL_LIMIT_MM_S2);
    const fx = acceleration * nx, fy = acceleration * ny, fz = acceleration * nz;
    state.ax[i] += fx; state.ay[i] += fy; state.az[i] += fz;
    state.ax[j] -= fx; state.ay[j] -= fy; state.az[j] -= fz;
    state.neighbourCount[i] += 1; state.neighbourCount[j] += 1;

    const kernel = (1.0 - distance / PARCEL_SUPPORT_MM) * liquidPair;
    const weight = 1.0 - Math.exp(-state.params.interfaceVelocityCouplingPerS * kernel * dt);
    const dvx = (state.vx[j] - state.vx[i]) * weight;
    const dvy = (state.vy[j] - state.vy[i]) * weight;
    const dvz = (state.vz[j] - state.vz[i]) * weight;
    state.mixVx[i] += dvx; state.mixVy[i] += dvy; state.mixVz[i] += dvz;
    state.mixVx[j] -= dvx; state.mixVy[j] -= dvy; state.mixVz[j] -= dvz;
  });
}

function carrierFlowAt(state, i) {
  const heightFraction = clamp01(state.pz[i] / APPARATUS.liquidHeightMm);
  const radial = Math.sqrt(state.px[i] * state.px[i] + state.py[i] * state.py[i]);
  const radialFraction = clamp01(radial / RADIAL_MAX_MM);
  const circulation = state.params.carrierCirculationMmS;
  const rotation = state.convectionHandedness * state.params.carrierVorticityPerS *
    state.physicsTimeS;
  const cosRotation = Math.cos(rotation), sinRotation = Math.sin(rotation);
  const axisX = state.convectionAxisX * cosRotation -
    state.convectionAxisY * sinRotation;
  const axisY = state.convectionAxisX * sinRotation +
    state.convectionAxisY * cosRotation;
  // A 3-D cylindrical convection basis: radial turnover, a microstate-oriented lateral roll,
  // and azimuthal vorticity. Magnitudes come from the cascade; initial thermal fluctuations set
  // the orientation and handedness. It contains no blob target, cycle timing, or parcel path.
  const radialSpeed = -0.55 * circulation * Math.sin(2.0 * Math.PI * heightFraction) *
    (1.0 - 0.35 * radialFraction);
  const lateralSpeed = state.params.lateralPlumeFraction * circulation *
    Math.cos(Math.PI * heightFraction) * (1.0 - 0.55 * radialFraction * radialFraction);
  const swirlSpeed = state.convectionHandedness * state.params.carrierVorticityPerS * radial *
    Math.sin(Math.PI * heightFraction);
  const plumeProjection = (state.px[i] * axisX + state.py[i] * axisY) / RADIAL_MAX_MM;
  const verticalSpeed = 0.30 * circulation * Math.sin(Math.PI * heightFraction) *
    (1.0 - 2.0 * radialFraction * radialFraction +
      state.params.lateralPlumeFraction * plumeProjection);
  const invRadial = radial > 1e-9 ? 1.0 / radial : 0.0;
  const radialX = state.px[i] * invRadial, radialY = state.py[i] * invRadial;
  return {
    vx: radialSpeed * radialX + lateralSpeed * axisX - swirlSpeed * radialY,
    vy: radialSpeed * radialY + lateralSpeed * axisY + swirlSpeed * radialX,
    vz: verticalSpeed
  };
}

function projectBoundary(state, i) {
  const radial2 = state.px[i] * state.px[i] + state.py[i] * state.py[i];
  if (radial2 > RADIAL_MAX_MM * RADIAL_MAX_MM) {
    const radial = Math.sqrt(radial2);
    const nx = state.px[i] / radial, ny = state.py[i] / radial;
    state.px[i] = nx * RADIAL_MAX_MM;
    state.py[i] = ny * RADIAL_MAX_MM;
    const outward = state.vx[i] * nx + state.vy[i] * ny;
    if (outward > 0.0) {
      state.vx[i] -= 1.35 * outward * nx;
      state.vy[i] -= 1.35 * outward * ny;
    }
    state.vx[i] *= 0.72; state.vy[i] *= 0.72;
  }
  if (state.pz[i] < Z_MIN_MM) {
    state.pz[i] = Z_MIN_MM;
    if (state.vz[i] < 0.0) state.vz[i] *= -0.12;
    state.vx[i] *= 0.82; state.vy[i] *= 0.82;
  } else if (state.pz[i] > Z_MAX_MM) {
    state.pz[i] = Z_MAX_MM;
    if (state.vz[i] > 0.0) state.vz[i] *= -0.12;
    state.vx[i] *= 0.82; state.vy[i] *= 0.82;
  }
}

function advanceParcelDynamics(state, dt) {
  applyPairDynamics(state, dt);
  const velocityRelax = 1.0 - Math.exp(-state.params.velocityRelaxationPerS * dt);
  const carrierAdvection = 1.0 - Math.exp(-state.params.carrierAdvectionPerS * dt);
  const radiusM = state.params.effectiveDropletRadiusMm * 1e-3;
  for (let i = 0; i < state.n; i += 1) {
    const cell = carrierCellIndex(state.pz[i]);
    const carrierDensity = carrierDensityGcm3(state, cell);
    const densityDifferenceKgM3 = (carrierDensity - state.densityGcm3[i]) * 1000.0;
    const terminalMps = (2.0 / 9.0) * densityDifferenceKgM3 * 9.80665 *
      radiusM * radiusM / state.params.effectiveDynamicViscosityPaS;
    const carrierFlow = carrierFlowAt(state, i);
    const targetVz = clamp(terminalMps * 1000.0 + carrierFlow.vz,
      -MAX_SPEED_MM_S, MAX_SPEED_MM_S);
    state.vz[i] += (targetVz - state.vz[i]) * velocityRelax;
    state.vx[i] += (carrierFlow.vx - state.vx[i]) * carrierAdvection;
    state.vy[i] += (carrierFlow.vy - state.vy[i]) * carrierAdvection;
    const neighbourScale = 1.0 / Math.max(1, state.neighbourCount[i]);
    state.vx[i] += state.ax[i] * neighbourScale * dt +
      state.mixVx[i] * neighbourScale;
    state.vy[i] += state.ay[i] * neighbourScale * dt +
      state.mixVy[i] * neighbourScale;
    state.vz[i] += state.az[i] * neighbourScale * dt +
      state.mixVz[i] * neighbourScale;
    let speed = Math.sqrt(state.vx[i] * state.vx[i] + state.vy[i] * state.vy[i] +
      state.vz[i] * state.vz[i]);
    if (speed > MAX_SPEED_MM_S) {
      state.velocityClampCount += 1;
      const scale = MAX_SPEED_MM_S / speed;
      state.vx[i] *= scale; state.vy[i] *= scale; state.vz[i] *= scale;
      speed = MAX_SPEED_MM_S;
    }
    state.px[i] += state.vx[i] * dt;
    state.py[i] += state.vy[i] * dt;
    state.pz[i] += state.vz[i] * dt;
    projectBoundary(state, i);
    state.maxSpeedMmS = Math.max(state.maxSpeedMmS, speed);
  }
}

function updateStepMetrics(state) {
  let meanVz = 0.0, meanDensityDifference = 0.0, meanLiquid = 0.0;
  let meanX = 0.0, meanY = 0.0, meanZ = 0.0, meanHorizontalSpeed = 0.0;
  let minZ = Infinity, maxZ = -Infinity;
  for (let i = 0; i < state.n; i += 1) {
    const cell = carrierCellIndex(state.pz[i]);
    meanVz += state.vz[i];
    meanDensityDifference += carrierDensityGcm3(state, cell) - state.densityGcm3[i];
    meanLiquid += state.liquidFraction[i];
    meanX += state.px[i];
    meanY += state.py[i];
    meanZ += state.pz[i];
    meanHorizontalSpeed += Math.sqrt(state.vx[i] * state.vx[i] +
      state.vy[i] * state.vy[i]);
    minZ = Math.min(minZ, state.pz[i]);
    maxZ = Math.max(maxZ, state.pz[i]);
  }
  meanVz /= state.n;
  meanDensityDifference /= state.n;
  meanLiquid /= state.n;
  meanX /= state.n;
  meanY /= state.n;
  meanZ /= state.n;
  meanHorizontalSpeed /= state.n;
  if (meanVz > 0.03) state.upwardPhysicsSteps += 1;
  if (meanVz < -0.03) state.downwardPhysicsSteps += 1;
  if (meanDensityDifference > 0.001) state.lighterThanCarrierSteps += 1;
  if (meanDensityDifference < -0.001) state.heavierThanCarrierSteps += 1;
  const buoyancySign = meanDensityDifference > 0.001 ? 1 :
    (meanDensityDifference < -0.001 ? -1 : 0);
  const motionSign = meanVz > 0.03 ? 1 : (meanVz < -0.03 ? -1 : 0);
  if (buoyancySign !== 0 && state.lastBuoyancySign !== 0 &&
      buoyancySign !== state.lastBuoyancySign) state.buoyancySignChanges += 1;
  if (motionSign !== 0 && state.lastMotionSign !== 0 &&
      motionSign !== state.lastMotionSign) state.motionSignChanges += 1;
  if (buoyancySign !== 0) state.lastBuoyancySign = buoyancySign;
  if (motionSign !== 0) state.lastMotionSign = motionSign;
  if (buoyancySign !== 0 && motionSign !== 0) {
    if (buoyancySign === motionSign) state.buoyancyAlignedSteps += 1;
    else state.buoyancyOpposedSteps += 1;
  }
  state.minMeanLiquidFraction = Math.min(state.minMeanLiquidFraction, meanLiquid);
  state.maxMeanLiquidFraction = Math.max(state.maxMeanLiquidFraction, meanLiquid);
  state.minMeanZMm = Math.min(state.minMeanZMm, meanZ);
  state.maxMeanZMm = Math.max(state.maxMeanZMm, meanZ);
  state.minMeanXMm = Math.min(state.minMeanXMm, meanX);
  state.maxMeanXMm = Math.max(state.maxMeanXMm, meanX);
  state.minMeanYMm = Math.min(state.minMeanYMm, meanY);
  state.maxMeanYMm = Math.max(state.maxMeanYMm, meanY);
  state.maxMeanHorizontalSpeedMmS = Math.max(state.maxMeanHorizontalSpeedMmS,
    meanHorizontalSpeed);
  if (meanHorizontalSpeed > 0.05) state.lateralPhysicsSteps += 1;
  if (state.previousMeanX !== null) {
    state.centroidXyPathMm += Math.sqrt((meanX - state.previousMeanX) *
      (meanX - state.previousMeanX) + (meanY - state.previousMeanY) *
      (meanY - state.previousMeanY));
  }
  state.previousMeanX = meanX;
  state.previousMeanY = meanY;
  const centroidRadius = Math.sqrt(meanX * meanX + meanY * meanY);
  if (centroidRadius > 1.0) {
    const angle01 = (Math.atan2(meanY, meanX) + Math.PI) / (2.0 * Math.PI);
    const bin = Math.min(11, Math.floor(angle01 * 12.0));
    state.centroidAzimuthMask |= (1 << bin);
  }
  state.minParticleZMm = Math.min(state.minParticleZMm, minZ);
  state.maxParticleZMm = Math.max(state.maxParticleZMm, maxZ);
}

function physicsStep(state, dt) {
  advanceCarrierThermalField(state, dt);
  applyThermalAndPhaseState(state, dt);
  advanceParcelDynamics(state, dt);
  state.physicsTimeS += dt;
  state.physicsSteps += 1;
  updateStepMetrics(state);
}

function advanceTo(state, targetTimeS) {
  const epsilon = 1e-10;
  while (state.physicsTimeS + APPARATUS.physicsStepS <= targetTimeS + epsilon) {
    physicsStep(state, APPARATUS.physicsStepS);
  }
  const remainder = targetTimeS - state.physicsTimeS;
  if (remainder > epsilon) physicsStep(state, remainder);
  state.physicsTimeS = targetTimeS;
}

function componentLabels(state, linkMm) {
  const parent = new Int32Array(state.n);
  for (let i = 0; i < state.n; i += 1) parent[i] = i;
  function root(a) {
    let x = a;
    while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; }
    return x;
  }
  function unite(a, b) {
    const ra = root(a), rb = root(b);
    if (ra !== rb) parent[rb] = ra;
  }
  const grid = buildSpatialGrid(state, linkMm);
  const link2 = linkMm * linkMm;
  forEachNeighbourPair(state, grid, linkMm, link2, (i, j, dx, dy, dz, distance2) => {
    if (distance2 <= link2) unite(i, j);
  });
  const canonical = new Map();
  const labels = new Int32Array(state.n);
  let next = 0;
  for (let i = 0; i < state.n; i += 1) {
    const r = root(i);
    if (!canonical.has(r)) canonical.set(r, next++);
    labels[i] = canonical.get(r);
  }
  return { labels, count: next };
}

function lineageTransitions(previous, current) {
  if (!previous || previous.length !== current.length) return { merges: 0, splits: 0 };
  const priorByCurrent = new Map();
  const currentByPrior = new Map();
  for (let i = 0; i < current.length; i += 1) {
    if (!priorByCurrent.has(current[i])) priorByCurrent.set(current[i], new Set());
    priorByCurrent.get(current[i]).add(previous[i]);
    if (!currentByPrior.has(previous[i])) currentByPrior.set(previous[i], new Set());
    currentByPrior.get(previous[i]).add(current[i]);
  }
  let merges = 0, splits = 0;
  for (const sources of priorByCurrent.values()) if (sources.size > 1) merges += 1;
  for (const destinations of currentByPrior.values()) if (destinations.size > 1) splits += 1;
  return { merges, splits };
}

function frameState(state) {
  const positions = new Array(state.n);
  const colors = new Array(state.n);
  let meanTemperature = 0.0, meanLiquid = 0.0, meanDensity = 0.0, meanVz = 0.0;
  let meanX = 0.0, meanY = 0.0, meanHorizontalSpeed = 0.0;
  let minTemperature = Infinity, maxTemperature = -Infinity;
  let solidLike = 0, liquidLike = 0;
  let maxDisplacement = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    positions[i] = [state.px[i], state.py[i], state.pz[i]];
    meanTemperature += state.temperatureK[i];
    meanLiquid += state.liquidFraction[i];
    meanDensity += state.densityGcm3[i];
    meanVz += state.vz[i];
    meanX += state.px[i];
    meanY += state.py[i];
    meanHorizontalSpeed += Math.sqrt(state.vx[i] * state.vx[i] +
      state.vy[i] * state.vy[i]);
    minTemperature = Math.min(minTemperature, state.temperatureK[i]);
    maxTemperature = Math.max(maxTemperature, state.temperatureK[i]);
    if (state.liquidFraction[i] < 0.25) solidLike += 1;
    if (state.liquidFraction[i] > 0.75) liquidLike += 1;
    const warmth = clamp01((state.temperatureK[i] - APPARATUS.ambientTemperatureK) /
      (APPARATUS.heaterTemperatureK - APPARATUS.ambientTemperatureK));
    const rgb = mixRgb(REPRESENTATION.waxTint, REPRESENTATION.waxWarmHighlight,
      clamp01(0.15 + 0.75 * warmth));
    colors[i] = [rgb[0], rgb[1], rgb[2], REPRESENTATION.waxAlpha];
    if (state.lastEmittedPx) {
      const dx = state.px[i] - state.lastEmittedPx[i];
      const dy = state.py[i] - state.lastEmittedPy[i];
      const dz = state.pz[i] - state.lastEmittedPz[i];
      maxDisplacement = Math.max(maxDisplacement, Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
  }
  const physicalTopology = componentLabels(state, TOPOLOGY_LINK_MM);
  const parcelSurfaceTopology = componentLabels(state, PARCEL_SURFACE_LINK_MM);
  const renderTopology = componentLabels(state, RENDER_SURFACE_LINK_MM);
  meanTemperature /= state.n; meanLiquid /= state.n; meanDensity /= state.n; meanVz /= state.n;
  meanX /= state.n; meanY /= state.n; meanHorizontalSpeed /= state.n;
  return {
    positions, colors, components: physicalTopology.count,
    parcelSurfaceComponents: parcelSurfaceTopology.count,
    parcelSurfaceLabels: parcelSurfaceTopology.labels,
    renderComponents: renderTopology.count, renderLabels: renderTopology.labels,
    meanTemperature, meanLiquid, meanDensity, meanVz, meanX, meanY, meanHorizontalSpeed,
    minTemperature, maxTemperature, solidLike, liquidLike, maxDisplacement
  };
}

function observedPhase(state, frame) {
  const liquidDelta = frame.meanLiquid - state.lastMeanLiquidFraction;
  if (frame.meanVz > 0.08) return "rising_from_positive_buoyancy";
  if (frame.meanVz < -0.08) return "falling_from_negative_buoyancy";
  if (liquidDelta > 0.002) return "melting";
  if (liquidDelta < -0.002) return "solidifying";
  if (frame.meanLiquid < 0.25) return "heating_solid_wax";
  return "thermally_neutral";
}

function emitFrame(ctx, state, frameIndex) {
  const clock = frameClock(frameIndex);
  const frame = frameState(state);
  const phase = observedPhase(state, frame);
  if (state.previousComponents !== null && frame.components !== state.previousComponents) {
    state.topologyChanges += 1;
  }
  state.previousComponents = frame.components;
  state.minComponents = Math.min(state.minComponents, frame.components);
  state.maxComponents = Math.max(state.maxComponents, frame.components);
  const parcelLineage = lineageTransitions(
    state.previousParcelSurfaceLabels, frame.parcelSurfaceLabels);
  state.parcelSurfaceMergeEvents += parcelLineage.merges;
  state.parcelSurfaceSplitEvents += parcelLineage.splits;
  state.previousParcelSurfaceLabels = new Int32Array(frame.parcelSurfaceLabels);
  state.minParcelSurfaceComponents = Math.min(
    state.minParcelSurfaceComponents, frame.parcelSurfaceComponents);
  state.maxParcelSurfaceComponents = Math.max(
    state.maxParcelSurfaceComponents, frame.parcelSurfaceComponents);
  if (frame.parcelSurfaceComponents <= 2) state.parcelSurfaceMergedFrames += 1;
  const lineage = lineageTransitions(state.previousRenderLabels, frame.renderLabels);
  state.renderMergeEvents += lineage.merges;
  state.renderSplitEvents += lineage.splits;
  state.previousRenderLabels = new Int32Array(frame.renderLabels);
  state.minRenderComponents = Math.min(state.minRenderComponents, frame.renderComponents);
  state.maxRenderComponents = Math.max(state.maxRenderComponents, frame.renderComponents);
  if (frame.renderComponents <= 2) state.renderMergedFrames += 1;
  state.maxFrameDisplacementMm = Math.max(state.maxFrameDisplacementMm, frame.maxDisplacement);
  state.lastMeanLiquidFraction = frame.meanLiquid;
  state.lastFrame = frameIndex;
  state.lastPhysicalTimeS = clock.physicalTimeS;
  state.lastEmittedPx = new Float64Array(state.px);
  state.lastEmittedPy = new Float64Array(state.py);
  state.lastEmittedPz = new Float64Array(state.pz);

  ctx.emit("material_frame", {
    time_s: clock.physicalTimeS,
    physical_time_s: clock.physicalTimeS,
    playback_time_s: clock.playbackTimeS,
    time_scale: clock.timeScale,
    phase: "lava_lamp:" + phase,
    particle_ids: state.ids,
    positions_mm: frame.positions,
    colors_rgba: frame.colors,
    render_surface: renderSurfaceHint(state),
    counts: {
      persistent_wax_parcels: state.n,
      connected_components: frame.components,
      parcel_surface_components: frame.parcelSurfaceComponents,
      rendered_surface_components: frame.renderComponents,
      solid_like: frame.solidLike,
      liquid_like: frame.liquidLike
    },
    topology_events: {
      merges_since_prior_frame: lineage.merges,
      splits_since_prior_frame: lineage.splits,
      parcel_surface_merges_since_prior_frame: parcelLineage.merges,
      parcel_surface_splits_since_prior_frame: parcelLineage.splits,
      basis: "persistent parcel lineage under the emitted fluid-interface connection radius",
      retained_basis: "the earlier parcel-scale Gaussian-surface lineage remains independently reported"
    },
    physics_state: {
      solver_step: state.physicsSteps,
      mean_temperature_k: frame.meanTemperature,
      min_temperature_k: frame.minTemperature,
      max_temperature_k: frame.maxTemperature,
      mean_liquid_fraction: frame.meanLiquid,
      mean_density_g_per_cm3: frame.meanDensity,
      mean_vertical_velocity_mm_per_s: frame.meanVz,
      mean_horizontal_speed_mm_per_s: frame.meanHorizontalSpeed,
      wax_centroid_xy_mm: [frame.meanX, frame.meanY],
      carrier_bottom_temperature_k: state.carrierTemperatureK[0],
      carrier_top_temperature_k:
        state.carrierTemperatureK[APPARATUS.carrierThermalCells - 1],
      max_displacement_since_prior_emit_mm: frame.maxDisplacement
    },
    geant4_event_id: state.lastGeant4EventId,
    inference: { source: state.params.source, response_sigma: state.params.responseSigma },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: clock.timeScale
    },
    motion_scope: "persistent thermo-fluid parcels; Geant4 material base -> ctx.cascade coefficients -> explicit bounded-step integration; no births/deaths or scripted cycle path",
    representation_override: REPRESENTATION
  });
}

function initParticles(state) {
  const n = state.n;
  let particle = 0;
  for (let droplet = 0; droplet < APPARATUS.initialDroplets; droplet += 1) {
    const remaining = n - particle;
    const dropletsRemaining = APPARATUS.initialDroplets - droplet;
    const count = Math.ceil(remaining / dropletsRemaining);
    const angle = 2.0 * Math.PI * droplet / APPARATUS.initialDroplets;
    const centerRadius = 14.0;
    const centerX = centerRadius * Math.cos(angle);
    const centerY = centerRadius * Math.sin(angle);
    const packed = packedDropletPoints(count);
    for (let local = 0; local < packed.length; local += 1) {
      const i = particle++;
      const point = packed[local];
      state.px[i] = centerX + point[0];
      state.py[i] = centerY + point[1];
      state.pz[i] = clamp(11.5 + point[2], Z_MIN_MM, 24.0);
      state.temperatureK[i] = APPARATUS.ambientTemperatureK +
        0.3 + 0.7 * parcelNoise01(i, 0);
      state.heatBias[i] = 0.85 + 0.30 * parcelNoise01(i, 1);
      state.liquidFraction[i] = phaseEquilibrium(state.temperatureK[i],
        state.params.meltingTemperatureK);
      state.densityGcm3[i] = waxDensityGcm3(state, i);
    }
  }
}

function initializeConvectionOrientation(state) {
  let meanTemperature = 0.0, meanHeatBias = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    meanTemperature += state.temperatureK[i];
    meanHeatBias += state.heatBias[i];
  }
  meanTemperature /= state.n;
  meanHeatBias /= state.n;
  let thermalX = 0.0, thermalY = 0.0, heatX = 0.0, heatY = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    const thermalDelta = state.temperatureK[i] - meanTemperature;
    const heatDelta = state.heatBias[i] - meanHeatBias;
    thermalX += thermalDelta * state.px[i];
    thermalY += thermalDelta * state.py[i];
    heatX += heatDelta * state.px[i];
    heatY += heatDelta * state.py[i];
  }
  let norm = Math.sqrt(thermalX * thermalX + thermalY * thermalY);
  if (norm < 1e-9) {
    const angle = 2.0 * Math.PI * parcelNoise01(state.n, 7);
    thermalX = Math.cos(angle);
    thermalY = Math.sin(angle);
    norm = 1.0;
  }
  state.convectionAxisX = thermalX / norm;
  state.convectionAxisY = thermalY / norm;
  const cross = thermalX * heatY - thermalY * heatX;
  state.convectionHandedness = Math.abs(cross) > 1e-12 ? (cross > 0.0 ? 1.0 : -1.0) :
    (parcelNoise01(state.n, 8) >= 0.5 ? 1.0 : -1.0);
}

function initState(ctx) {
  const carrierProbe = ctx.materials && ctx.materials[CARRIER];
  const waxProbe = ctx.materials && ctx.materials[WAX_BLEND];
  if (!carrierProbe || !waxProbe) throw new Error("Geant4 material probes missing lamp media");
  const cascade = ctx.cascade({
    "context.temperature_span_k": APPARATUS.heaterTemperatureK - APPARATUS.ambientTemperatureK,
    "context.lamp_aspect_ratio": APPARATUS.aspectRatio
  });
  if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
    throw new Error("lava-lamp cascade requires predictive mode and two loaded stages");
  }
  const params = inferredParameters(cascade);
  const n = APPARATUS.representativeWaxParcels;
  const cells = APPARATUS.carrierThermalCells;
  const state = {
    carrierProbe,
    waxProbe,
    carrierOptics: opticsFor(ctx, CARRIER),
    waxOptics: opticsFor(ctx, WAX_BLEND),
    cascade,
    params,
    n,
    ids: Array.from({ length: n }, (_, i) => i),
    identityChecksum: n * (n - 1) / 2,
    carrierReferenceDensityGcm3: Number(carrierProbe.density_g_per_cm3),
    waxColdDensityGcm3: Number(waxProbe.density_g_per_cm3),
    px: new Float64Array(n), py: new Float64Array(n), pz: new Float64Array(n),
    vx: new Float64Array(n), vy: new Float64Array(n), vz: new Float64Array(n),
    ax: new Float64Array(n), ay: new Float64Array(n), az: new Float64Array(n),
    mixVx: new Float64Array(n), mixVy: new Float64Array(n), mixVz: new Float64Array(n),
    neighbourCount: new Int32Array(n),
    temperatureK: new Float64Array(n), liquidFraction: new Float64Array(n),
    densityGcm3: new Float64Array(n), heatBias: new Float64Array(n),
    carrierTemperatureK: new Float64Array(cells),
    carrierNextTemperatureK: new Float64Array(cells),
    carrierHeatDeltaK: new Float64Array(cells),
    physicsTimeS: 0.0,
    physicsSteps: 0,
    geant4Events: 0,
    geant4Steps: 0,
    geant4TrackLengthMm: 0.0,
    lastGeant4EventId: -1,
    lastFrame: 0,
    lastPhysicalTimeS: 0.0,
    lastMeanLiquidFraction: 0.0,
    lastEmittedPx: null,
    lastEmittedPy: null,
    lastEmittedPz: null,
    previousComponents: null,
    minComponents: Infinity,
    maxComponents: -Infinity,
    topologyChanges: 0,
    previousRenderLabels: null,
    minRenderComponents: Infinity,
    maxRenderComponents: -Infinity,
    renderMergeEvents: 0,
    renderSplitEvents: 0,
    renderMergedFrames: 0,
    previousParcelSurfaceLabels: null,
    minParcelSurfaceComponents: Infinity,
    maxParcelSurfaceComponents: -Infinity,
    parcelSurfaceMergeEvents: 0,
    parcelSurfaceSplitEvents: 0,
    parcelSurfaceMergedFrames: 0,
    convectionAxisX: 1.0,
    convectionAxisY: 0.0,
    convectionHandedness: 1.0,
    previousMeanX: null,
    previousMeanY: null,
    minMeanXMm: Infinity,
    maxMeanXMm: -Infinity,
    minMeanYMm: Infinity,
    maxMeanYMm: -Infinity,
    centroidXyPathMm: 0.0,
    centroidAzimuthMask: 0,
    maxMeanHorizontalSpeedMmS: 0.0,
    lateralPhysicsSteps: 0,
    maxFrameDisplacementMm: 0.0,
    maxSpeedMmS: 0.0,
    velocityClampCount: 0,
    upwardPhysicsSteps: 0,
    downwardPhysicsSteps: 0,
    lighterThanCarrierSteps: 0,
    lastBuoyancySign: 0,
    lastMotionSign: 0,
    buoyancySignChanges: 0,
    motionSignChanges: 0,
    buoyancyAlignedSteps: 0,
    buoyancyOpposedSteps: 0,
    heavierThanCarrierSteps: 0,
    minMeanLiquidFraction: Infinity,
    maxMeanLiquidFraction: -Infinity,
    minMeanZMm: Infinity,
    maxMeanZMm: -Infinity,
    minParticleZMm: Infinity,
    maxParticleZMm: -Infinity
  };
  state.carrierTemperatureK.fill(APPARATUS.ambientTemperatureK);
  state.carrierNextTemperatureK.fill(APPARATUS.ambientTemperatureK);
  initParticles(state);
  initializeConvectionOrientation(state);
  ctx.state.lavaLamp = state;
  return state;
}

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const state = initState(ctx);
    ctx.emit("lava_lamp_scenario", {
      name: "lava_lamp",
      apparatus: APPARATUS,
      configured_materials: {
        carrier: CARRIER,
        wax_blend: WAX_BLEND,
        wax_base: WAX_BASE,
        density_modifier_proxy: WAX_DENSIFIER,
        density_modifier_mass_fraction: WAX_DENSIFIER_MASS_FRACTION,
        formulation_scope: "simulation reference blend; not a product recipe"
      },
      geant4_materials: [CARRIER, WAX_BLEND, AIR, GLASS],
      geant4_optics: { carrier: state.carrierOptics, wax_blend: state.waxOptics },
      cascade_trace: state.cascade.__cascade,
      inferred_thermofluid_parameters: state.params,
      solver: {
        kind: "persistent thermofluid material parcels",
        physics_step_s: APPARATUS.physicsStepS,
        nominal_wax_volume_mm3: NOMINAL_WAX_VOLUME_MM3,
        parcel_spacing_mm: PARCEL_SPACING_MM,
        particle_identity_conserved: true,
        scheduled_cycle_or_trajectory: false
      },
      representation: renderSurfaceHint(state),
      honest_scope: "Geant4 material/optics base -> TRECH cascade thermophysical coefficients -> persistent hook-layer phase/heat/buoyancy/cohesion solver; macro model is illustrative, not metrology-grade",
      representation_override: REPRESENTATION
    });
    emitFrame(ctx, state, 0);
  },
  onEventEnd(ctx) {
    const state = ctx.state && ctx.state.lavaLamp;
    if (!state) return;
    state.geant4Events += 1;
    state.geant4Steps += Number(ctx.event.totalStepCount || 0);
    state.geant4TrackLengthMm += Number(ctx.event.totalTrackLengthMm || 0.0);
    state.lastGeant4EventId = Number(ctx.event.id);
    const frameIndex = Math.min(APPARATUS.outputTicks, Number(ctx.event.id) + 1);
    const target = frameClock(frameIndex).physicalTimeS;
    advanceTo(state, target);
    emitFrame(ctx, state, frameIndex);
  },
  onRunEnd(ctx) {
    const state = ctx.state && ctx.state.lavaLamp;
    if (!state) return;
    const seedKeys = state.cascade.__cascade.seedKeys || [];
    const g4Seeded = seedKeys.indexOf("material.G4_WATER.density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material.lava_wax_blend.density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material.lava_wax_blend.electron_density_per_cm3") >= 0;
    const frameEnd = frameClock(APPARATUS.outputTicks);
    const idChecksum = state.ids.reduce((sum, id) => sum + id, 0);
    const validation = {
      geant4_material_and_composition_base_present:
        state.carrierReferenceDensityGcm3 > 0.0 && state.waxColdDensityGcm3 > 0.0 &&
        Number(state.waxProbe.electron_density_per_cm3) > 0.0 &&
        state.geant4Events === APPARATUS.outputTicks && state.geant4Steps > 0,
      cascade_supplies_integrator_coefficients:
        state.cascade.__cascade.stagesRun === 2 && g4Seeded &&
        state.params.meltingTemperatureK > APPARATUS.ambientTemperatureK &&
        state.params.waxThermalExpansionPerK > 0.0 &&
        state.params.waxHeatExchangePerS > 0.0 && state.params.cohesionAccelMmS2 >= 0.0 &&
        state.params.interfaceVelocityCouplingPerS > 0.0 &&
        state.params.carrierCirculationMmS > 0.0 && state.params.carrierAdvectionPerS > 0.0 &&
        state.params.carrierVorticityPerS > 0.0 && state.params.lateralPlumeFraction > 0.0,
      persistent_particle_identity:
        state.ids.length === state.n && idChecksum === state.identityChecksum,
      configured_duration_reached:
        Math.abs(state.lastPhysicalTimeS - APPARATUS.durationS) < 1e-8 &&
        state.lastFrame === APPARATUS.outputTicks,
      one_frame_per_geant4_tick:
        state.geant4Events === APPARATUS.outputTicks && state.lastFrame === state.geant4Events,
      bounded_step_state_integration:
        state.physicsSteps >= Math.floor(APPARATUS.durationS / APPARATUS.physicsStepS) &&
        Math.abs(state.physicsTimeS - APPARATUS.durationS) < 1e-8,
      precision_controls_are_independent:
        Math.abs(state.n * PARCEL_SPACING_MM * PARCEL_SPACING_MM * PARCEL_SPACING_MM -
          NOMINAL_WAX_VOLUME_MM3) < 1e-8 &&
        APPARATUS.physicsStepS > 0.0 && APPARATUS.outputTickIntervalS > 0.0 &&
        APPARATUS.renderSurfaceGridMm > 0.0,
      thermodynamic_phase_response:
        state.maxMeanLiquidFraction - state.minMeanLiquidFraction > 0.10,
      density_crossing_drives_buoyancy:
        state.heavierThanCarrierSteps > 0 && state.lighterThanCarrierSteps > 0,
      bidirectional_motion_emerged:
        state.upwardPhysicsSteps > 0 && state.downwardPhysicsSteps > 0,
      thermally_caused_reversal:
        state.buoyancySignChanges > 0 && state.motionSignChanges > 0 &&
        state.buoyancyAlignedSteps > state.buoyancyOpposedSteps,
      substantial_vertical_transport:
        state.maxParticleZMm > 0.55 * APPARATUS.liquidHeightMm &&
        state.maxMeanZMm - state.minMeanZMm > 0.45 * APPARATUS.liquidHeightMm,
      volumetric_convection_not_axis_locked:
        state.maxMeanXMm - state.minMeanXMm > 0.12 * APPARATUS.innerRadiusMm &&
        state.maxMeanYMm - state.minMeanYMm > 0.12 * APPARATUS.innerRadiusMm &&
        state.centroidXyPathMm > APPARATUS.innerRadiusMm &&
        bitCount(state.centroidAzimuthMask) >= 6 &&
        state.lateralPhysicsSteps > 0.5 * state.physicsSteps,
      velocity_cap_not_driving_motion: state.velocityClampCount === 0,
      bounded_continuous_motion:
        state.minParticleZMm >= Z_MIN_MM - 1e-8 &&
        state.maxParticleZMm <= Z_MAX_MM + 1e-8 &&
        state.maxSpeedMmS <= MAX_SPEED_MM_S + 1e-8 &&
        state.maxFrameDisplacementMm <=
          MAX_SPEED_MM_S * APPARATUS.outputTickIntervalS * 1.05 + 1e-6,
      topology_computed_from_neighbours:
        Number.isFinite(state.minComponents) && Number.isFinite(state.maxComponents) &&
        state.minComponents > 0 && state.maxComponents > 0,
      visible_surface_coalescence_and_fission:
        state.renderMergeEvents > 0 && state.renderSplitEvents > 0 &&
        state.minRenderComponents === 1 && state.maxRenderComponents >= 3 &&
        state.renderMergedFrames >= Math.max(6, Math.floor((state.lastFrame + 1) * 0.15)),
      parcel_surface_lineage_retained:
        state.parcelSurfaceMergeEvents > 0 && state.parcelSurfaceSplitEvents > 0 &&
        state.minParcelSurfaceComponents === 1 && state.maxParcelSurfaceComponents >= 4 &&
        state.parcelSurfaceMergedFrames >= Math.max(6, Math.floor((state.lastFrame + 1) * 0.15)),
      blob_topology_temporally_coherent:
        state.topologyChanges <= Math.ceil(APPARATUS.outputTicks * 0.45) &&
        state.maxRenderComponents <= 10
    };
    ctx.emit("lava_lamp_summary", {
      scenario: "lava_lamp",
      configured_duration_s: APPARATUS.durationS,
      frames: state.lastFrame + 1,
      conditions: {
        heater_temperature_k: APPARATUS.heaterTemperatureK,
        ambient_temperature_k: APPARATUS.ambientTemperatureK,
        wax_representatives: APPARATUS.representativeWaxParcels,
        max_physics_step_s: APPARATUS.physicsStepS,
        render_surface_grid_mm: APPARATUS.renderSurfaceGridMm
      },
      geant4: {
        carrier_density_g_per_cm3: state.carrierReferenceDensityGcm3,
        wax_blend_density_g_per_cm3: state.waxColdDensityGcm3,
        wax_blend_electron_density_per_cm3: state.waxProbe.electron_density_per_cm3,
        events: state.geant4Events,
        steps: state.geant4Steps,
        track_length_mm: state.geant4TrackLengthMm
      },
      cascade: state.cascade.__cascade,
      inferred_thermofluid_parameters: state.params,
      precision: {
        spatial: {
          persistent_parcels: state.n,
          parcel_spacing_mm: PARCEL_SPACING_MM,
          nominal_wax_volume_mm3: NOMINAL_WAX_VOLUME_MM3,
          invariant: "parcel_count * parcel_spacing_mm^3 is constant"
        },
        temporal: { max_physics_step_s: APPARATUS.physicsStepS },
        output: {
          geant4_ticks: APPARATUS.outputTicks,
          interval_s: APPARATUS.outputTickIntervalS
        },
        representation_only: renderSurfaceHint(state)
      },
      dynamics: {
        persistent_parcels: state.n,
        identity_checksum: idChecksum,
        physics_steps: state.physicsSteps,
        max_speed_mm_per_s: state.maxSpeedMmS,
        velocity_clamp_count: state.velocityClampCount,
        max_frame_displacement_mm: state.maxFrameDisplacementMm,
        upward_physics_steps: state.upwardPhysicsSteps,
        downward_physics_steps: state.downwardPhysicsSteps,
        heavier_than_carrier_steps: state.heavierThanCarrierSteps,
        lighter_than_carrier_steps: state.lighterThanCarrierSteps,
        buoyancy_sign_changes: state.buoyancySignChanges,
        motion_sign_changes: state.motionSignChanges,
        buoyancy_aligned_steps: state.buoyancyAlignedSteps,
        buoyancy_opposed_steps: state.buoyancyOpposedSteps,
        mean_liquid_fraction_range: [state.minMeanLiquidFraction,
          state.maxMeanLiquidFraction],
        mean_z_range_mm: [state.minMeanZMm, state.maxMeanZMm],
        particle_z_range_mm: [state.minParticleZMm, state.maxParticleZMm],
        connected_component_range: [state.minComponents, state.maxComponents],
        topology_changes: state.topologyChanges,
        rendered_surface_component_range: [state.minRenderComponents,
          state.maxRenderComponents],
        rendered_surface_merge_events: state.renderMergeEvents,
        rendered_surface_split_events: state.renderSplitEvents,
        rendered_surface_merged_frames: state.renderMergedFrames,
        parcel_surface_component_range: [state.minParcelSurfaceComponents,
          state.maxParcelSurfaceComponents],
        parcel_surface_merge_events: state.parcelSurfaceMergeEvents,
        parcel_surface_split_events: state.parcelSurfaceSplitEvents,
        parcel_surface_merged_frames: state.parcelSurfaceMergedFrames,
        centroid_x_range_mm: [state.minMeanXMm, state.maxMeanXMm],
        centroid_y_range_mm: [state.minMeanYMm, state.maxMeanYMm],
        centroid_xy_path_mm: state.centroidXyPathMm,
        centroid_azimuth_bins_occupied: bitCount(state.centroidAzimuthMask),
        max_mean_horizontal_speed_mm_per_s: state.maxMeanHorizontalSpeedMmS,
        lateral_physics_steps: state.lateralPhysicsSteps,
        convection_initial_axis_xy: [state.convectionAxisX, state.convectionAxisY],
        convection_handedness: state.convectionHandedness
      },
      observer_clock: {
        physical_duration_s: APPARATUS.durationS,
        playback_duration_s: APPARATUS.playbackDurationS,
        acceleration: frameEnd.timeScale,
        geant4_ticks: APPARATUS.outputTicks,
        emitted_frames: state.lastFrame + 1,
        output_tick_interval_s: APPARATUS.outputTickIntervalS,
        physics_step_s: APPARATUS.physicsStepS
      },
      honest_scope: "Geant4 does not solve phase change or CFD; its probed material base feeds a TRECH-inferred thermofluid response whose coefficients drive every step of a persistent parcel solver",
      representation_override: REPRESENTATION,
      validation
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 500.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.ambientTemperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 1, 0] },
  run: { nEvents: APPARATUS.outputTicks, seed: 20260716, threads: 1 },
  determinism: { mode: "predictive" },
  materials: [waxBlendMaterial],
  materialProbe: { enable: true, materials: [CARRIER, WAX_BLEND, AIR, GLASS] },
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      energyMinEv: 1.6,
      energyMaxEv: 3.2,
      nEnergyBins: 16,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: true
    }
  },
  models: [
    { name: "macro_thermofluid_response", scale: "macro",
      path: "data/lava_lamp_cascade/macro_thermofluid_response.json" },
    { name: "nano_material_response", scale: "nano",
      path: "data/lava_lamp_cascade/nano_material_response.json" }
  ],
  system: { enable: true, mode: "transient", frame: "observer", ensemble: "lava_lamp" },
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 524288 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "carrier_liquid", material: CARRIER,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.innerRadiusMm,
        lengthMm: APPARATUS.liquidHeightMm,
        positionMm: [0, APPARATUS.liquidHeightMm / 2.0, 0], rotationDeg: [90, 0, 0],
        tags: ["lava_carrier", "viz_opacity=0.10", "viz_tint=#1a5794"]
      }),
      geometry.tubeVolume({
        name: "glass_envelope", material: GLASS,
        innerRadiusMm: APPARATUS.innerRadiusMm,
        outerRadiusMm: APPARATUS.innerRadiusMm + 3.0,
        lengthMm: APPARATUS.glassHeightMm,
        positionMm: [0, APPARATUS.glassHeightMm / 2.0, 0], rotationDeg: [90, 0, 0],
        tags: ["lava_glass", "viz_shell"]
      }),
      geometry.tubeVolume({
        name: "lamp_base", material: GLASS,
        innerRadiusMm: 29.0, outerRadiusMm: 41.0, lengthMm: 34.0,
        positionMm: [0, -17.0, 0], rotationDeg: [90, 0, 0],
        tags: ["housing", "viz_solid", "viz_color=#0e0b14"]
      }),
      geometry.tubeVolume({
        name: "heater_light", material: GLASS,
        innerRadiusMm: 0.0, outerRadiusMm: 29.0, lengthMm: 34.0,
        positionMm: [0, -17.0, 0], rotationDeg: [90, 0, 0],
        tags: ["heater", "viz_emissive", "viz_color=#ff7a18", "viz_opacity=0.62"]
      }),
      geometry.tubeVolume({
        name: "lamp_cap", material: GLASS,
        innerRadiusMm: 0.0, outerRadiusMm: 37.0, lengthMm: 26.0,
        positionMm: [0, APPARATUS.glassHeightMm + 13.0, 0], rotationDeg: [90, 0, 0],
        tags: ["housing", "viz_solid", "viz_color=#0e0b14"]
      }),
      geometry.boxVolume({
        name: "wax_material_probe", material: WAX_BLEND,
        sizeMm: [4, 4, 4], positionMm: [120, 0, 0], tags: ["viz_hidden"]
      })
    ]
  }
};
