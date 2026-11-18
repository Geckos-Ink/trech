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
//   build/dev/trech run examples/scenarios/lava_lamp/lava_lamp.js \
//     --output build/dev/out_lava_lamp
// README full-horizon run (ten physical minutes in ten display seconds):
//   build/dev/trech run examples/scenarios/lava_lamp/lava_lamp.js \
//     --param duration_s=600 --param playback_duration_s=10 \
//     --param simulation_ticks=100 --output build/dev/out_lava_lamp_readme_10m

TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_domain_tracking.js");
TRECH_INCLUDE("../../../js/trech_domain_learning.js");
TRECH_INCLUDE("../../../js/trech_lbm_reference.js");
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

const durationS = TRECH_PARAMETER("duration_s");
const playbackDurationS = TRECH_PARAMETER("playback_duration_s");
// Precision is a named PROFILE mapped onto this scenario's own axes, not a
// global "quality" number: the four knobs below mean four different things
// (parcel discretisation, integration step, output cadence, display grid) and
// the run reports each one separately. `balanced` reproduces the historical
// defaults exactly, so the default run is byte-identical to the pre-profile
// scenario; each control still overrides its axis individually, and any
// override makes the reported profile `custom` rather than a rung only
// half-followed.
const BALANCED_TICKS = 120;
const BALANCED_PARCELS = 240;
const BALANCED_PHYSICS_STEP_S = 0.4;
const BALANCED_SURFACE_GRID_MM = 1.25;

const precisionProfile = TRECH_PARAMETER("precision_profile");
const simulationTicks = TRECH_PARAMETER("simulation_ticks");
const waxRepresentatives = TRECH_PARAMETER("wax_representatives");
const maxPhysicsStepS = TRECH_PARAMETER("max_physics_step_s");
const renderSurfaceGridMm = TRECH_PARAMETER("render_surface_grid_mm");

// A control left at its balanced default follows the profile; a user-changed
// control overrides its axis (and is reported as such).
const overrideOf = (value, balanced) => (value === balanced ? 0 : value);
const PRECISION = helpers.precision.resolve({
  profile: precisionProfile,
  note: "spatial/temporal/output axes refine the solver; the surface grid is display only",
  axes: [
    { name: "parcels", role: "spatial", control: "wax_representatives",
      unit: "parcels", balanced: BALANCED_PARCELS, min: 120, max: 480,
      direction: "higher_is_finer", integer: true,
      override: overrideOf(waxRepresentatives, BALANCED_PARCELS) },
    { name: "physics_step", role: "temporal", control: "max_physics_step_s",
      unit: "s", balanced: BALANCED_PHYSICS_STEP_S, min: 0.1, max: 1.0,
      direction: "lower_is_finer",
      override: overrideOf(maxPhysicsStepS, BALANCED_PHYSICS_STEP_S) },
    { name: "output_ticks", role: "output", control: "simulation_ticks",
      unit: "ticks", balanced: BALANCED_TICKS, min: 10, max: 2000,
      direction: "higher_is_finer", integer: true,
      override: overrideOf(simulationTicks, BALANCED_TICKS) },
    { name: "surface_grid", role: "representation", control: "render_surface_grid_mm",
      unit: "mm", balanced: BALANCED_SURFACE_GRID_MM, min: 0.75, max: 2.5,
      direction: "lower_is_finer",
      override: overrideOf(renderSurfaceGridMm, BALANCED_SURFACE_GRID_MM) }
  ]
});
const heaterTemperatureK = TRECH_PARAMETER("heater_temperature_k");
const ambientTemperatureK = TRECH_PARAMETER("ambient_temperature_k");
const detectDomains = TRECH_PARAMETER("detect_domains");
const domainMethod = TRECH_PARAMETER("domain_method");
// Online response-domain learning of the frame-scale parcel response.
const learnDomains = TRECH_PARAMETER("learn_domains");
// Development dual run (comparison only): a lattice Boltzmann carrier beside the lamp.
const lbmCompanion = TRECH_PARAMETER("lbm_companion");
const lbmCellMm = TRECH_PARAMETER("lbm_cell_mm");
const lbmMachTarget = TRECH_PARAMETER("lbm_mach_target");
const lbmTwinRatio = TRECH_PARAMETER("lbm_twin_ratio");
const lbmScalarMagic = TRECH_PARAMETER("lbm_scalar_magic");
const domainLearnerModel = TRECH_PARAMETER("domain_learner_model");
const LEARNER_STATE = domainLearnerModel
  ? TRECH_READ_JSON(domainLearnerModel.startsWith("/") ? domainLearnerModel : "../../../" + domainLearnerModel)
  : null;
if (learnDomains === "evaluate" && !LEARNER_STATE) {
  throw new Error("learn_domains=evaluate needs domain_learner_model");
}
if (heaterTemperatureK <= ambientTemperatureK) {
  throw new Error("heater_temperature_k must exceed ambient_temperature_k");
}

const RESOLVED_TICKS = PRECISION.value("output_ticks");
const APPARATUS = {
  durationS,
  playbackDurationS,
  outputTicks: RESOLVED_TICKS,
  outputTickIntervalS: durationS / RESOLVED_TICKS,
  innerRadiusMm: 30.0,
  liquidHeightMm: 180.0,
  glassHeightMm: 190.0,
  heaterTemperatureK,
  ambientTemperatureK,
  representativeWaxParcels: PRECISION.value("parcels"),
  initialDroplets: 4,
  carrierThermalCells: 24,
  physicsStepS: PRECISION.value("physics_step"),
  renderSurfaceGridMm: PRECISION.value("surface_grid"),
  precisionProfile: PRECISION.profile
};
APPARATUS.aspectRatio = APPARATUS.liquidHeightMm / (2.0 * APPARATUS.innerRadiusMm);

const REPRESENTATION = TRECH_VIEWS["lava_lamp"]["REPRESENTATION0"]();

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

const { clamp, clamp01, mix3: mixRgb, finite } = helpers.math;
function bitCount(v) {
  let x = v >>> 0, count = 0;
  while (x !== 0) { count += x & 1; x >>>= 1; }
  return count;
}
const parcelNoise01 = helpers.random.parcelNoise01;
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

const opticsFor = helpers.materialFacts.optics;

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
      "lateral plume fraction"), 0.0, 1.0)
  };
}

const frameClock = TRECH_VIEWS["lava_lamp"]["frameClock1"](APPARATUS, helpers);

function renderSurfaceHint(state) {
  return TRECH_VIEWS["lava_lamp"]["renderSurfaceHint"](state, APPARATUS, FLUID_NECK_MIN_MM, FLUID_NECK_SAMPLES, FLUID_NECK_WEIGHT, RADIAL_MAX_MM, RENDER_SURFACE_ISO_LEVEL, RENDER_SURFACE_LINK_MM, RENDER_SURFACE_SIGMA_MM, REPRESENTATION, Z_MAX_MM, Z_MIN_MM);
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
  // Read-only tap for the lattice companion's one-way wax heat replay.
  if (state.lbmComparison) {
    for (let c = 0; c < APPARATUS.carrierThermalCells; c += 1) {
      state.lbmComparison.waxLoadK[c] += state.carrierHeatDeltaK[c];
    }
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

// --- Lattice Boltzmann dual-run companion (development track) ------------------------------
// Beside the normal path, a thermal lattice Boltzmann carrier (D3Q19 flow + D3Q7 temperature,
// Boussinesq buoyancy) is advanced in the same cylinder with the same cascade properties: carrier
// viscosity, thermal diffusivity and expansion, the heater/top relaxation laws applied to the
// same slabs, and the wax heat load the parcels deposited in each carrier cell (replayed one way).
// It PREDICTS the carrier circulation that the normal path takes from an authored kinematic basis
// (carrierFlowAt) and the temperature field the normal path diffuses in a 1-D column. Each frame
// records the confrontation; nothing here feeds back into the lamp. Contract:
// AGENTS/engine/lattice/AGENTS.md.
const LBM_COMPARISON_SCOPE = "Development dual run: thermal lattice Boltzmann carrier (comparison " +
  "physics) with the lamp's geometry and cascade-inferred properties; one-way wax heat replay, no " +
  "wax momentum coupling; never feeds back into the lamp and is not a Geant4 result";

function lbmComparisonSlabOverlap(z0, z1, a0, a1) {
  return Math.max(0.0, Math.min(z1, a1) - Math.max(z0, a0));
}

// Accuracy the comparison DEMANDS of the lattice (declared, not a stability rule): twin
// discrepancy within 2 % of the heater span and 25 % of the frame's RMS carrier speed, on at least
// 90 % of the cells, on every learned frame after the warm-up.
const LBM_COMPARISON_DEMAND = {temperature_error: 0.02, velocity_error: 0.25};
const LBM_COMPARISON_COVERAGE = 0.9;
const LBM_COMPARISON_WARMUP_CALLS = 3;

// One carrier lattice with cell `dx` mm: same cylinder, properties, heater/top laws and wax load
// slabs. Returns null when no lattice can even be constructed (tau <= 1/2 for this cell).
function buildLbmComparisonLattice(state, dx, props) {
  const LBM = TRECH_LBM_REFERENCE;
  const R = APPARATUS.innerRadiusMm, H = APPARATUS.liquidHeightMm;
  const nxy = Math.ceil(2.0 * R / dx), nz = Math.max(4, Math.round(H / dx));
  // dt keeps the free-fall velocity bound at the declared lattice Mach target.
  const dt = lbmMachTarget * Math.sqrt(1.0 / 3.0) * dx / props.freeFallMmS;
  const tau = 0.5 + 3.0 * props.nuMm2S * dt / (dx * dx);
  const u = LBM.units({dx_m: dx * 1e-3, nu_m2_s: props.nuMm2S * 1e-6, tau,
    kappa_m2_s: props.kappaMm2S * 1e-6});
  const info = {cell_mm: dx, shape: [nxy, nxy, nz], lattice_height_mm: nz * dx, dt_s: u.dt_s,
    tau: u.tau, scalar_tau: u.scalar_tau};
  if (!(u.tau > 0.5) || !(u.scalar_tau > 0.5)) return {info, lbm: null};
  const domain = LBM.createDomain({shape: [nxy, nxy, nz], solid: (x, y) =>
    Math.hypot((x + 0.5) * dx - R, (y + 0.5) * dx - R) > R});
  const F = domain.count, cells = APPARATUS.carrierThermalCells, slab = H / cells;
  // Lattice layer l receives slab c's laws in proportion to the overlap of their heights.
  const overlap = [];
  for (let l = 0; l < nz; l += 1) {
    overlap.push(Array.from({length: cells}, (_, c) =>
      lbmComparisonSlabOverlap(l * dx, (l + 1) * dx, c * slab, (c + 1) * slab) / dx));
  }
  const rate = new Float64Array(F), target = new Float64Array(F), constant = new Float64Array(F);
  for (let i = 0; i < F; i += 1) {
    const w = overlap[domain.z[i]];
    const heat = state.params.heaterCouplingPerS * u.dt_s * w[0];
    const cool = state.params.topCoolingPerS * u.dt_s * w[cells - 1];
    rate[i] = heat + cool;
    target[i] = rate[i] > 0.0 ? heat * props.spanK / rate[i] : 0.0;
  }
  // The lamp's own microstate orientation seeds a 1 mK tilt so the lattice plume and the
  // authored basis share an azimuth; the cylinder staircase alone would also break symmetry.
  const lbm = LBM.createThermalFlow({domain, tau: u.tau, diffusivity: u.kappa_lattice,
    scalarMagic: lbmScalarMagic > 0 ? lbmScalarMagic : undefined,
    initialTemperature: (x, y) => 1e-3 * (((x + 0.5) * dx - R) * state.convectionAxisX +
      ((y + 0.5) * dx - R) * state.convectionAxisY) / R,
    relaxation: {rate, target, constant},
    // Mean reference: the uniformly warming closed column carries no net body force.
    buoyancy: {axis: 2, coefficient: props.gravityMmS2 * props.beta * u.dt_s * u.dt_s / dx, reference: "mean"}});
  return {info, lbm, domain, overlap, constant, dx, dt: u.dt_s, time: 0.0, steps: 0,
    velocityScaleMmS: dx / u.dt_s};
}

function createLbmComparison(state) {
  const LBM = TRECH_LBM_REFERENCE;
  const H = APPARATUS.liquidHeightMm;
  const gravityMmS2 = 9810.0;  // classical constant; comparison physics only
  const rhoKgM3 = 1000.0 * state.carrierReferenceDensityGcm3;
  const nuMm2S = 1e6 * state.params.effectiveDynamicViscosityPaS / rhoKgM3;
  const kappaMm2S = state.params.carrierThermalDiffusivityMm2S;
  const beta = state.params.carrierThermalExpansionPerK;
  const spanK = APPARATUS.heaterTemperatureK - APPARATUS.ambientTemperatureK;
  const freeFallMmS = Math.sqrt(gravityMmS2 * beta * spanK * H);
  const props = {gravityMmS2, nuMm2S, kappaMm2S, beta, spanK, freeFallMmS};
  const main = buildLbmComparisonLattice(state, lbmCellMm, props);
  // The twin exists only to measure the main lattice's local error on the fly.
  const twin = buildLbmComparisonLattice(state, lbmCellMm * lbmTwinRatio, props);
  const context = {
    lattice: Object.assign({flow: "D3Q19", scalar: "D3Q7", collision: "TRT", mach_target: lbmMachTarget,
      scalar_magic: lbmScalarMagic > 0 ? lbmScalarMagic : "default (scalar tau+ = 1)"}, main.info),
    twin: Object.assign({ratio: lbmTwinRatio, role: "on-the-fly error evidence for the main lattice"}, twin.info),
    properties: {kinematic_viscosity_mm2_s: nuMm2S, thermal_diffusivity_mm2_s: kappaMm2S,
      thermal_expansion_per_k: beta, carrier_density_kg_m3: rhoKgM3,
      source: "cascade effective dynamic viscosity / Geant4 carrier density; cascade diffusivity and expansion"},
    dimensionless: {rayleigh: gravityMmS2 * beta * spanK * H * H * H / (nuMm2S * kappaMm2S),
      prandtl: nuMm2S / kappaMm2S, free_fall_velocity_mm_s: freeFallMmS,
      grid_peclet_free_fall: freeFallMmS * lbmCellMm / kappaMm2S},
    accuracy_demand: {errors: LBM_COMPARISON_DEMAND, coverage: LBM_COMPARISON_COVERAGE,
      warmup_calls: LBM_COMPARISON_WARMUP_CALLS}
  };
  const record = {enabled: true, context, frames: [], main, twin, lbm: main.lbm,
    domain: main.domain, overlap: main.overlap, dx: main.dx, velocityScaleMmS: main.velocityScaleMmS,
    ambientK: APPARATUS.ambientTemperatureK, spanK, failure: null,
    scalarRange: [Infinity, -Infinity], staggeredMax: 0.0,
    learning: {calls: 0, rows: 0, learned: [], observed_when_learned: []},
    waxLoadK: new Float64Array(APPARATUS.carrierThermalCells)};
  if (!main.lbm) record.failure = "no lattice: tau <= 1/2 for this cell size and timestep";
  state.lbmComparison = record;
  return record;
}

function advanceLbmComparisonLattice(lattice, targetTimeS, waxLoadK) {
  if (!lattice || !lattice.lbm) return;
  const steps = Math.floor((targetTimeS - lattice.time) / lattice.dt + 1e-9);
  const cells = APPARATUS.carrierThermalCells;
  // Spread the interval's wax heat load evenly over the lattice steps of that interval.
  for (let i = 0; i < lattice.domain.count; i += 1) {
    const w = lattice.overlap[lattice.domain.z[i]];
    let load = 0.0;
    for (let c = 0; c < cells; c += 1) if (w[c] > 0.0) load += w[c] * waxLoadK[c];
    lattice.constant[i] = steps > 0 ? load / steps : 0.0;
  }
  if (steps <= 0) return;
  lattice.lbm.advance(steps);
  lattice.steps += steps;
  lattice.time += steps * lattice.dt;
}

function advanceLbmComparison(state, targetTimeS) {
  const record = state.lbmComparison;
  if (!record) return;
  if (record.lbm && !record.failure) {
    // A diverging lattice is itself evidence: record it and stop, never abort the lamp.
    try {
      advanceLbmComparisonLattice(record.main, targetTimeS, record.waxLoadK);
      advanceLbmComparisonLattice(record.twin, targetTimeS, record.waxLoadK);
    } catch (error) {
      record.failure = "lattice diverged at t = " + record.main.time.toFixed(2) + " s: " + error.message;
    }
  }
  record.waxLoadK.fill(0.0);
}

// Learn, on the fly, where this lattice meets the accuracy demand (see TRECH_LBM_REFERENCE).
function learnLbmComparisonApplicability(ctx, record, time) {
  const LBM = TRECH_LBM_REFERENCE;
  if (!record.twin.lbm) return null;
  const evidence = LBM.twinDiscrepancy(record.main.lbm, record.twin.lbm, {ratio: lbmTwinRatio,
    scalarScale: record.spanK, velocityScale: record.main.velocityScaleMmS,
    twinVelocityScale: record.twin.velocityScaleMmS, velocityFloor: 1e-3});
  const features = LBM.localDescriptors(record.main.lbm, record.spanK);
  return LBM.learnApplicability(ctx, {name: "lbm_applicability", time, features,
    errors: {temperature_error: evidence.temperature, velocity_error: evidence.velocity},
    valid: evidence.valid, demand: LBM_COMPARISON_DEMAND, accumulator: record.learning,
    options: {min_elements: 64}});
}

function lbmComparisonFrame(ctx, state, frameIndex) {
  const record = state.lbmComparison;
  const LBM = TRECH_LBM_REFERENCE;
  if (!record.lbm || record.failure) {
    record.frames.push({frame: frameIndex, time_s: state.physicsTimeS, failed: true});
    return {schema: LBM.SCHEMA, frame: frameIndex, time_s: state.physicsTimeS, ran: false,
      failure: record.failure, applicability: {verdict: "not_applicable", source: "observed failure",
        reasons: [record.failure]}, scope: LBM_COMPARISON_SCOPE};
  }
  const learned = frameIndex > 0 ? learnLbmComparisonApplicability(ctx, record, state.physicsTimeS) : null;
  const cells = APPARATUS.carrierThermalCells, slab = APPARATUS.liquidHeightMm / cells;
  const T = record.lbm.scalar.values(), sums = new Float64Array(cells), weights = new Float64Array(cells);
  for (let i = 0; i < T.length; i += 1) {
    const w = record.overlap[record.domain.z[i]];
    for (let c = 0; c < cells; c += 1) if (w[c] > 0.0) { sums[c] += w[c] * T[i]; weights[c] += w[c]; }
  }
  const lbmProfile = Array.from(sums, (s, c) => record.ambientK + (weights[c] > 0.0 ? s / weights[c] : 0.0));
  const baselineProfile = Array.from(state.carrierTemperatureK);
  const v = record.lbm.flow.velocity(), scale = record.velocityScaleMmS;
  const R = APPARATUS.innerRadiusMm, dx = record.dx;
  const authored = [], lattice = [];
  for (let i = 0; i < state.n; i += 1) {
    const lx = (state.px[i] + R) / dx - 0.5, ly = (state.py[i] + R) / dx - 0.5, lz = state.pz[i] / dx - 0.5;
    const sx = LBM.sample(record.domain, v.ux, lx, ly, lz);
    if (sx === null) continue;
    const flow = carrierFlowAt(state, i);
    authored.push([flow.vx, flow.vy, flow.vz]);
    lattice.push([sx * scale, LBM.sample(record.domain, v.uy, lx, ly, lz) * scale,
      LBM.sample(record.domain, v.uz, lx, ly, lz) * scale]);
  }
  let speed2 = 0.0, peak = 0.0, tMin = Infinity, tMax = -Infinity, tSum = 0.0;
  for (let i = 0; i < T.length; i += 1) { tMin = Math.min(tMin, T[i]); tMax = Math.max(tMax, T[i]); tSum += T[i]; }
  for (let i = 0; i < v.ux.length; i += 1) {
    const s2 = v.ux[i] * v.ux[i] + v.uy[i] * v.uy[i] + v.uz[i] * v.uz[i];
    speed2 += s2; peak = Math.max(peak, s2);
  }
  const staggered = LBM.staggeredFraction(record.domain, v);
  record.staggeredMax = Math.max(record.staggeredMax, staggered);
  const temperature = LBM.compareProfiles(baselineProfile, lbmProfile, record.spanK);
  const flow = authored.length ? LBM.compareVectors(authored, lattice) : null;
  const card = LBM.scoreCard({carrier_temperature: temperature.score,
    flow_speed: flow ? flow.speed_score : 0, flow_direction: flow ? flow.direction_score : 0});
  const status = record.lbm.status();
  const frame = {schema: LBM.SCHEMA, frame: frameIndex, time_s: state.physicsTimeS, ran: true,
    lbm_time_s: record.main.time, lbm_steps: record.main.steps, twin_lbm_time_s: record.twin.lbm ? record.twin.time : null,
    native_kernel: record.lbm.native,
    carrier_temperature: {bin_centres_mm: Array.from({length: cells}, (_, c) => (c + 0.5) * slab),
      baseline_k: baselineProfile, lbm_k: lbmProfile, comparison: temperature},
    carrier_flow: {baseline: "authored kinematic basis (carrierFlowAt) at wax parcels",
      lbm: "lattice velocity trilinearly sampled at the same parcels", comparison: flow},
    lbm_rms_speed_mm_s: Math.sqrt(speed2 / v.ux.length) * scale,
    lbm_max_speed_mm_s: Math.sqrt(peak) * scale,
    lbm_temperature_range_k: [record.ambientK + tMin, record.ambientK + tMax],
    lbm_mean_temperature_k: record.ambientK + tSum / T.length,
    baseline_mean_temperature_k: baselineProfile.reduce((a, b) => a + b, 0) / cells,
    max_mach: status.max_mach, staggered_fraction: staggered, score_card: card,
    // Decision: learned on the fly from twin-lattice evidence. Reference: the textbook envelope.
    applicability: learned ? {source: "learned on the fly (ctx.learnDomains, twin-lattice evidence)",
      learned_share: learned.learned_share, observed_share: learned.observed_share, by_target: learned.by_target,
      meets_coverage: learned.learned_share === null ? null : learned.learned_share >= LBM_COMPARISON_COVERAGE,
      call: learned.call, graded_rows: learned.graded, metrics: learned.metrics, domains: learned.domains} :
      {source: "learned on the fly", learned_share: null, reason: "initial state, nothing to learn yet"},
    reference_assessment: lbmComparisonAssess(record, status.max_mach, [tMin, tMax], staggered),
    scope: LBM_COMPARISON_SCOPE};
  record.scalarRange = [Math.min(record.scalarRange[0], tMin), Math.max(record.scalarRange[1], tMax)];
  record.frames.push({frame: frameIndex, time_s: frame.time_s, overall: card.overall,
    carrier_temperature: temperature.score, flow_speed: card.scores.flow_speed,
    flow_direction: card.scores.flow_direction, lbm_rms_speed_mm_s: frame.lbm_rms_speed_mm_s,
    temperature_rms_k: temperature.norms.l2, max_mach: status.max_mach, staggered_fraction: staggered,
    temperature_range_k: frame.lbm_temperature_range_k,
    learned_share: learned ? learned.learned_share : null, observed_share: learned ? learned.observed_share : null,
    learned_temperature_share: learned ? learned.by_target.temperature_error.learned_share : null,
    learned_velocity_share: learned ? learned.by_target.velocity_error.learned_share : null,
    learned_domains: learned ? learned.domains.length : null,
    reference_verdict: frame.reference_assessment.verdict});
  return frame;
}

// Stability envelope plus the maximum principle: heater/top/wax sources only relax the carrier
// anomaly toward [0, heater span], so a lattice temperature outside it is a transport artefact.
function lbmComparisonAssess(record, mach, range, staggered) {
  return TRECH_LBM_REFERENCE.assess({tau: record.context.lattice.tau,
    scalar_tau: record.context.lattice.scalar_tau, cells_across: record.context.lattice.shape[0],
    mach, scalar_range: range, scalar_bounds: [0.0, record.spanK], scalar_tolerance: 0.01 * record.spanK,
    staggered_fraction: staggered});
}

function emitLbmComparison(ctx, state, frameIndex) {
  if (!state.lbmComparison) return;
  ctx.emit("lbm_comparison", lbmComparisonFrame(ctx, state, frameIndex));
}

function lbmComparisonSummary(state) {
  const record = state.lbmComparison;
  const LBM = TRECH_LBM_REFERENCE;
  const frames = record.frames.filter(f => !f.failed);
  const mean = key => frames.length ? frames.reduce((s, f) => s + f[key], 0) / frames.length : null;
  const status = record.lbm ? record.lbm.status() : null;
  const learned = record.failure ? {verdict: "not_applicable", source: "observed failure", reason: record.failure} :
    Object.assign({source: "learned on the fly (ctx.learnDomains, twin-lattice evidence)"},
      LBM.applicabilityVerdict(record.learning, LBM_COMPARISON_COVERAGE, LBM_COMPARISON_WARMUP_CALLS));
  const reference = record.lbm && !record.failure ? lbmComparisonAssess(record, status.max_mach, record.scalarRange,
    record.staggeredMax) : null;
  const overall = mean("overall");
  const cellSteps = l => l && l.lbm ? l.domain.count * l.steps : 0;
  return {schema: LBM.SCHEMA, scenario: "lava_lamp", ran: frames.length > 0, failure: record.failure,
    track: "development", feeds_back: false, normal_path_unchanged: true,
    context: record.context, applicability: learned, reference_assessment: reference,
    learned_vs_reference: reference && learned.verdict ? {learned: learned.verdict, reference: reference.verdict,
      agree: (learned.verdict === "applicable") === (reference.verdict === "applicable")} : null,
    cost: record.lbm ? {fluid_cells: record.domain.count, lattice_steps: record.main.steps,
      cell_steps: cellSteps(record.main), twin_cell_steps: cellSteps(record.twin),
      learned_rows: record.learning.rows, native_kernel: record.lbm.native} : null,
    mean_scores: {overall, carrier_temperature: mean("carrier_temperature"),
      flow_speed: mean("flow_speed"), flow_direction: mean("flow_direction")},
    final_frame: frames.length ? frames[frames.length - 1] : null,
    agreement: overall === null ? null : overall >= 0.8 ? "agree" : overall >= 0.5 ? "partial" : "diverge",
    trusted: learned.verdict === "applicable",
    series: record.frames, scope: LBM_COMPARISON_SCOPE,
    limitations: "Carrier-only lattice: wax parcels exchange heat one way and exert no momentum on the " +
      "lattice; staircase cylinder wall; carrier viscosity is the cascade's effective viscosity; " +
      "Boussinesq about the instantaneous mean temperature; applicability is learned from twin-lattice " +
      "consistency (numerical evidence), not from an experimental anchor"};
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
  return TRECH_VIEWS["lava_lamp"]["frameState"](state, APPARATUS, PARCEL_SURFACE_LINK_MM, RENDER_SURFACE_LINK_MM, REPRESENTATION, TOPOLOGY_LINK_MM, clamp01, componentLabels, mixRgb);
}

function observedPhase(state, frame) {
  return TRECH_VIEWS["lava_lamp"]["observedPhase"](state, frame);
}

function emitFrame(ctx, state, frameIndex) {
  TRECH_VIEWS["lava_lamp"]["emitFrame"](ctx, state, frameIndex, APPARATUS, Float64Array, Int32Array, REPRESENTATION, TRECH_VIEWS, frameClock, frameState, lineageTransitions, observedPhase, renderSurfaceHint);
  if (detectDomains) {
    const features = { x_mm: state.px, y_mm: state.py, z_mm: state.pz };
    const shared_distance_scale = domainMethod === "density";
    const report = ctx.detectDomains({ features, method: domainMethod, shared_distance_scale });
    if (report) {
      state.statisticalDomains = globalThis.TRECH_TRACK_DOMAINS(report, state.statisticalDomains);
      ctx.emit("domain_discovery", {
        frame: frameIndex, method: domainMethod, shared_distance_scale, report,
        lineage: state.statisticalDomains.groups.map(({id, predecessors}) => ({id, predecessors}))
      });
    }
  }
}

// --- online response-domain learning (ctx.learnDomains) ----------------------
// The learner sees each parcel's state at the start of an output interval --
// height, radius, temperature, molten fraction, the carrier temperature around
// it, its vertical velocity and the heater temperature (run context) -- and the
// interval-averaged heating rate and
// vertical velocity the fine physics steps produced. Domains emerge where one
// frame-scale law stops explaining the parcels; no phase or droplet label is
// read. It is a coarse-grained (meso) lift of the authored step laws and never
// feeds back into the lamp.
function parcelSnapshot(state) {
  const n = state.n;
  const carrier = new Float64Array(n), radius = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    carrier[i] = state.carrierTemperatureK[carrierCellIndex(state.pz[i])];
    radius[i] = Math.sqrt(state.px[i] * state.px[i] + state.py[i] * state.py[i]);
  }
  return {
    time: state.physicsTimeS,
    z_mm: Float64Array.from(state.pz), radius_mm: radius,
    temperature_k: Float64Array.from(state.temperatureK),
    liquid_fraction: Float64Array.from(state.liquidFraction),
    carrier_temperature_k: carrier, vz_mm_s: Float64Array.from(state.vz)
  };
}

function learnParcelResponse(ctx, state, start, target, frameIndex) {
  const dt = target - start.time;
  if (!(dt > 0)) return;
  const n = state.n;
  const heating = new Float64Array(n), rise = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    heating[i] = (state.temperatureK[i] - start.temperature_k[i]) / dt;
    rise[i] = (state.pz[i] - start.z_mm[i]) / dt;
  }
  const finalFrame = frameIndex >= APPARATUS.outputTicks;
  // The heater temperature is run context: constant within a run, it lets
  // domains learned across a campaign condition on the operating point.
  const features = {
    z_mm: start.z_mm, radius_mm: start.radius_mm, temperature_k: start.temperature_k,
    liquid_fraction: start.liquid_fraction, carrier_temperature_k: start.carrier_temperature_k,
    vz_mm_s: start.vz_mm_s,
    heater_temperature_k: new Float64Array(n).fill(APPARATUS.heaterTemperatureK)
  };
  const report = ctx.learnDomains({
    name: "lamp_parcels",
    time: target,
    features,
    targets: { heating_k_per_s: heating, mean_vz_mm_s: rise },
    options: LEARNER_STATE ? { warm_start: LEARNER_STATE, frozen: learnDomains === "evaluate" }
                           : { min_elements: 24, forgetting: 1.0 },
    report: finalFrame ? "full" : "summary",
    export_rows: finalFrame
  });
  if (!report) return;
  const labels = Array.from(start.liquid_fraction, (f) => (f >= 0.5 ? "molten" : "solid"));
  const agreement = TRECH_DOMAIN_LEARNING.agreement(report.elementDomains, labels);
  state.learning = state.learning || TRECH_DOMAIN_LEARNING.accumulator();
  TRECH_DOMAIN_LEARNING.accumulate(state.learning, report, agreement.contingency);
  ctx.emit("domain_learning", TRECH_DOMAIN_LEARNING.summarize(report,
    { scenario: "lava_lamp", frame: frameIndex, mode: learnDomains },
    { labels, allTendencies: finalFrame, samples: { features, count: 48 } }));
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
    if (lbmCompanion === "compare") createLbmComparison(state);
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
    emitLbmComparison(ctx, state, 0);
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
    const start = learnDomains !== "off" ? parcelSnapshot(state) : null;
    advanceTo(state, target);
    if (start) learnParcelResponse(ctx, state, start, target, frameIndex);
    advanceLbmComparison(state, target);
    emitFrame(ctx, state, frameIndex);
    emitLbmComparison(ctx, state, frameIndex);
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
    const validation = TRECH_CHECKS["lava_lamp"]["expectations0"](APPARATUS, MAX_SPEED_MM_S, NOMINAL_WAX_VOLUME_MM3, PARCEL_SPACING_MM, Z_MAX_MM, Z_MIN_MM, bitCount, g4Seeded, idChecksum, state);
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
      domain_learning: learnDomains === "off" ? undefined : {
        mode: learnDomains,
        note: "Frame-scale parcel response domains learned online by ctx.learnDomains from the " +
              "fine physics steps; no phase or droplet label is read. Prequential (predict-then-" +
              "learn) error against a pooled single-domain law fed the same parcels; agreement " +
              "with the molten/solid split is computed afterwards.",
        learner_state: domainLearnerModel || null,
        online: state.learning ? TRECH_DOMAIN_LEARNING.finish(state.learning) : null
      },
      inferred_thermofluid_parameters: state.params,
      precision: {
        profile: PRECISION.profile,
        requested_profile: PRECISION.requested,
        axes: PRECISION.axes,
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
    if (state.lbmComparison) ctx.emit("lbm_comparison_summary", lbmComparisonSummary(state));
  }
};

globalThis.TRECH_CONFIG = {
  environment: {
    worldSizeMm: 500.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.ambientTemperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 1, 0] },
  run: { nEvents: APPARATUS.outputTicks, seed: 20260716, threads: 1 },
  determinism: { mode: "predictive" },
  precision: PRECISION.config,
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
  hooks: { maxStepCallbacks: 1,
           maxEmitsPerCallback: (learnDomains === "off" ? 4 : 6) + (lbmCompanion === "compare" ? 1 : 0),
           // The final learner state carries its reservoir rows.
           maxEmitPayloadBytes: learnDomains === "off" ? 524288 : 268435456 },
  viz: TRECH_VIEWS["lava_lamp"]["viz1"](),
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "carrier_liquid", material: CARRIER,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.innerRadiusMm,
        lengthMm: APPARATUS.liquidHeightMm,
        positionMm: [0, APPARATUS.liquidHeightMm / 2.0, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["lava_lamp"]["tags2"]()
      }),
      geometry.tubeVolume({
        name: "glass_envelope", material: GLASS,
        innerRadiusMm: APPARATUS.innerRadiusMm,
        outerRadiusMm: APPARATUS.innerRadiusMm + 3.0,
        lengthMm: APPARATUS.glassHeightMm,
        positionMm: [0, APPARATUS.glassHeightMm / 2.0, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["lava_lamp"]["tags3"]()
      }),
      geometry.tubeVolume({
        name: "lamp_base", material: GLASS,
        innerRadiusMm: 29.0, outerRadiusMm: 41.0, lengthMm: 34.0,
        positionMm: [0, -17.0, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["lava_lamp"]["tags4"]()
      }),
      geometry.tubeVolume({
        name: "heater_light", material: GLASS,
        innerRadiusMm: 0.0, outerRadiusMm: 29.0, lengthMm: 34.0,
        positionMm: [0, -17.0, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["lava_lamp"]["tags5"]()
      }),
      geometry.tubeVolume({
        name: "lamp_cap", material: GLASS,
        innerRadiusMm: 0.0, outerRadiusMm: 37.0, lengthMm: 26.0,
        positionMm: [0, APPARATUS.glassHeightMm + 13.0, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["lava_lamp"]["tags6"]()
      }),
      geometry.boxVolume({
        name: "wax_material_probe", material: WAX_BLEND,
        sizeMm: [4, 4, 4], positionMm: [120, 0, 0], tags: TRECH_VIEWS["lava_lamp"]["tags7"]()
      })
    ]
  }
};
