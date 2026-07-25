// The polyurethane foam experiment ("the solid sponge"), observed in an open cup.
//
// Two viscous liquids are poured together:
//   Solution A ... a polyol (multiple -OH groups) carrying a small amount of WATER
//                  plus amine catalyst and silicone surfactant
//   Solution B ... a diisocyanate (two -NCO groups)
// Within seconds the mixture creams, expands up to ~30x its volume, and cures into
// a rigid porous sponge. Two reactions run SIMULTANEOUSLY:
//   polymerization (gel):  R-N=C=O + R'-OH  -> R-NH-CO-O-R'   (urethane linkage)
//   blowing        (blow): R-N=C=O + H2O    -> R-NH2 + CO2^   (gas generation)
// TRECH is told ONLY what is in the cup (the two-solution recipe + the constructed
// Geant4 materials). It is NOT told the expansion ratio, the cream/rise/gel times,
// the exotherm, the colour, or that the result is a rigid solid. All of that must
// EMERGE.
//
// Information discipline (the TRECH thesis, applied to a curing foam):
//   * Geant4 is the physical base. G4-constructed solution/mixture materials supply
//     composition, density, and electron/atom densities (Geant4 literally "sees"
//     the isocyanate nitrogen dissolved in Solution B and the density contrast
//     between the two solutions) plus the cross sections behind TRECH's derived
//     colour for the mixed liquid resin.
//   * ctx.cascade lifts those Geant4 facts + the declared recipe through a nano
//     reagent-descriptor stage and a macro observer-band response surface into the
//     COEFFICIENTS of a reduced dual-reaction foaming model (gel/blow rate
//     constants, Arrhenius activation temperature, per-reaction exotherms, CO2
//     capacity and dissolution threshold, Flory gel-point conversion,
//     Castro-Macosko viscosity exponent, surfactant bubble trapping, expansion
//     mobility). The cascade emits NO expansion ratio, milestone time, colour, or
//     final consistency.
//   * A deterministic hook-layer integrator advances the two coupled conversions,
//     the temperature, the dissolved/trapped/escaped CO2 budget, the viscosity,
//     and the volume. Whether the mixture foams, when it creams, how far it rises,
//     how hot it gets, and whether it ends as a RIGID sponge (motion frozen past
//     the gel point) or collapses all EMERGE from the integration.
//   * Honest scope: Geant4 does not itself solve urethane reaction kinetics or
//     bubble rheology; the reduced foaming model is an explicit "physics for
//     comparison" hook-layer model whose coefficients are inferred from the Geant4
//     base. The compact macro response surface is illustrative (uncertainty sigma
//     emitted). The cream/tan display swatches are labelled representation (the
//     aromatic-urethane chromophore is not a Geant4 cross-section product); the
//     liquid base colour IS Geant4-derived, and the whitening as bubbles nucleate
//     is tied to the emergent gas fraction (light scattering by closed cells) --
//     its TIMING is the emergent, graded result.
//   * PubChem supplies structure identity ONLY (CID + SMILES + formula) for the
//     reagents; those element sets are cross-checked against the declared Geant4
//     composition at run end. No PubChem density/colour/viscosity feeds runtime.
//
// The known polyurethane-foam behaviour used to CHECK the result (never to drive
// it) lives in VALIDATION_ONLY and is read only at run end.
//
// Run (PubChem structure cache first, once):
//   PYTHONPATH=tools/pubchem python -m trech_pubchem fetch --cache-dir build/pubchem_cache \
//     glycerol "toluene 2,4-diisocyanate" water
//   TRECH_PUBCHEM_CACHE_DIR=build/pubchem_cache build/dev/trech run \
//     examples/experiments/polyurethane_foam.js --output build/dev/out_polyurethane_foam

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

const WATER = "G4_WATER";
const AIR = "G4_AIR";
const CUP = "G4_POLYSTYRENE";
const POLYOL_SOLUTION = "polyol_resin_solution";        // Solution A
const ISOCYANATE_SOLUTION = "diisocyanate_solution";    // Solution B
const RESIN_MIX = "polyurethane_resin_mix";             // A + B, freshly mixed

// The prepared two-part recipe (what a demonstrator pours). Declared formulation
// context -- the "known solutions in a cup" -- NOT the reaction result.
const RECIPE = {
  polyolHydroxylNumberMgKohG: 400.0,  // rigid-foam polyether polyol
  waterPartsPerHundredPolyol: 3.5,    // the blowing agent dissolved in Solution A
  isocyanateIndex: 1.10,              // 10% NCO excess over all active hydrogens
  amineCatalystPphp: 1.5,
  surfactantPphp: 1.5,                // silicone cell stabiliser
  pourMassG: 119.0,                   // A + B combined
  mixRatioAtoB: 1.0
};

const durationS = TRECH_VALUE.number("duration_s", {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful foaming integrator advances.",
  default: 180.0, min: 60.0, max: 900.0, step: 30.0
});
const playbackDurationS = TRECH_VALUE.number("playback_duration_s", {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 10.0, min: 1.0, max: 60.0, step: 1.0
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; physics uses bounded finer steps.",
  default: 140, min: 20, max: 1000, step: 10
});
const foamParcels = TRECH_VALUE.integer("foam_parcels", {
  label: "Persistent foam parcels", group: "Precision", unit: "parcels",
  description: "Spatial resolution; the represented material volume stays fixed.",
  default: 260, min: 120, max: 520, step: 20
});
const maxPhysicsStepS = TRECH_VALUE.number("max_physics_step_s", {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal resolution of the reaction/expansion integrator.",
  default: 0.05, min: 0.01, max: 0.25, step: 0.01
});
const renderSurfaceGridMm = TRECH_VALUE.number("render_surface_grid_mm", {
  label: "Foam surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated state.",
  default: 3.0, min: 1.5, max: 6.0, step: 0.5
});
const initialTemperatureK = TRECH_VALUE.number("initial_temperature_k", {
  label: "Initial temperature", group: "Conditions", unit: "K",
  description: "Both solutions and the ambient start here.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
});

const APPARATUS = {
  durationS,
  playbackDurationS,
  outputTicks: simulationTicks,
  outputTickIntervalS: durationS / simulationTicks,
  physicsStepS: maxPhysicsStepS,
  cupInnerRadiusMm: 33.0,
  cupHeightMm: 85.0,
  crownRadiusMm: 48.0,        // free-rise mushroom above the cup lip
  crownNeckBlendMm: 14.0,
  initialLiquidHeightMm: 30.0,
  initialTemperatureK,
  parcels: foamParcels,
  renderSurfaceGridMm
};

// ---- representation-only display swatches (labelled; never feed dynamics) ----
// The liquid base colour is replaced at run start by the Geant4-derived colour of
// the mixed resin. Cream/tan foam swatches are representation: their APPEARANCE is
// authored, but WHEN the mixture whitens (bubble scattering) and tans (urethane
// conversion) is emergent chemistry.
const REPRESENTATION = {
  policy: "cream/tan swatches are authored display; liquid base is Geant4-derived; whitening/tanning TIMING is emergent",
  creamTint: [0.95, 0.90, 0.78],
  curedTint: [0.88, 0.77, 0.55],
  liquidAlpha: 0.85,
  foamAlpha: 0.96,
  scatterGain: 2.2
};

const PARCEL_R_MM = APPARATUS.cupInnerRadiusMm - 2.5;   // parcel-space pool radius
const POOL_VOLUME_MM3 = Math.PI * PARCEL_R_MM * PARCEL_R_MM *
  APPARATUS.initialLiquidHeightMm;
const CUP_COLUMN_VOLUME_MM3 = Math.PI * PARCEL_R_MM * PARCEL_R_MM *
  APPARATUS.cupHeightMm;
const CROWN_R_MM = APPARATUS.crownRadiusMm;
const CROWN_AREA_MM2 = Math.PI * CROWN_R_MM * CROWN_R_MM;
const PARCEL_RELAX_PER_S = 1.2;
const MAX_PARCEL_SPEED_MM_S = 25.0;
const RENDER_ISO_LEVEL = 0.42;
// Radius by which a single Gaussian splat's isosurface extends beyond its centre.
const RENDER_BULGE_PER_SIGMA = Math.sqrt(2.0 * Math.log(1.0 / RENDER_ISO_LEVEL));

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
function clamp01(v) { return clamp(v, 0.0, 1.0); }
function mix(a, b, t) { return a + (b - a) * t; }
function mixRgb(a, b, t) { return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)]; }
function round4(v) { return Math.round(v * 1e4) / 1e4; }
function smoothstep(t) { const x = clamp01(t); return x * x * (3.0 - 2.0 * x); }
function finite(v, label) {
  const x = Number(v);
  if (!Number.isFinite(x)) throw new Error("non-finite inferred " + label);
  return x;
}
function parcelNoise01(particleId, stream) {
  let x = (((particleId + 1) * 1664525) + ((stream + 1) * 1013904223)) >>> 0;
  x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
  return (x >>> 0) / 4294967296.0;
}

// ---- Geant4 materials (fail-safe element components; no PubChem properties) ----
// Solution A: polyether polyol (C/H/O backbone) + dissolved water + amine catalyst
// nitrogen. Solution B: aromatic diisocyanate (C9H6N2O2-like mass fractions -- the
// -N=C=O nitrogen is what Geant4 "sees"). Densities are the DECLARED formulation
// facts (like a bottle label), probed back out of the constructed G4 materials.
const polyolMaterial = {
  name: POLYOL_SOLUTION, densityGcm3: 1.08,
  components: [
    { element: "C", fraction: 0.545 },
    { element: "H", fraction: 0.095 },
    { element: "O", fraction: 0.310 },
    { material: WATER, fraction: 0.035 },
    { element: "N", fraction: 0.015 }
  ]
};
const isocyanateMaterial = {
  name: ISOCYANATE_SOLUTION, densityGcm3: 1.22,
  components: [
    { element: "C", fraction: 0.621 },
    { element: "H", fraction: 0.035 },
    { element: "N", fraction: 0.161 },
    { element: "O", fraction: 0.183 }
  ]
};
const resinMixMaterial = {
  name: RESIN_MIX, densityGcm3: 1.15,
  components: [
    { element: "C", fraction: 0.583 },
    { element: "H", fraction: 0.065 },
    { element: "O", fraction: 0.246 },
    { element: "N", fraction: 0.088 },
    { material: WATER, fraction: 0.018 }
  ]
};
const DECLARED_ELEMENTS = ["C", "H", "O", "N"];

// ---- PubChem structure identity (CID + SMILES + formula ONLY) ----
function pubchemStructure(name) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM unavailable; fetch the build-local structure cache first");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || !raw.cid || !raw.smiles) {
    throw new Error("PubChem structure cache for " + name + " must contain cid + smiles");
  }
  // Structure identity only. Physical properties (MW/XLogP/density/...) are
  // deliberately NOT copied out of the cache payload.
  return { cid: Number(raw.cid), smiles: String(raw.smiles),
           formula: String(raw.molecular_formula || "") };
}
function formulaElements(formula) {
  const out = [];
  const re = /([A-Z][a-z]?)(\d*)/g;
  let m;
  while ((m = re.exec(formula)) !== null) {
    if (m[1] && out.indexOf(m[1]) < 0) out.push(m[1]);
  }
  return out;
}
function structureConsistent(structures) {
  return Object.keys(structures).every((key) =>
    formulaElements(structures[key].formula).every(
      (el) => DECLARED_ELEMENTS.indexOf(el) >= 0));
}

function opticsRgb(ctx, name) {
  const item = ctx.optics && ctx.optics[name];
  if (!item || !Array.isArray(item.display_rgb)) {
    throw new Error("ctx.optics missing Geant4-derived colour for " + name);
  }
  return item.display_rgb.slice(0, 3).map(clamp01);
}

// ---- the inferred foaming coefficients (clamped to a physically stable range
// around the cascade prediction) ----
function inferredCoefficients(cascade) {
  return {
    source: "ctx.cascade(Geant4 solution/mixture base + two-part recipe -> nano descriptors -> macro dual-reaction foaming coefficients)",
    gelRatePerS: clamp(finite(cascade.macro_gel_rate_per_s, "gel rate"), 0.001, 0.02),
    blowRatePerS: clamp(finite(cascade.macro_blow_rate_per_s, "blow rate"), 0.002, 0.03),
    activationTemperatureK: clamp(finite(cascade.macro_activation_temperature_k,
      "activation temperature"), 2500.0, 7000.0),
    gelExothermK: clamp(finite(cascade.macro_gel_exotherm_k, "gel exotherm"), 30.0, 90.0),
    blowExothermK: clamp(finite(cascade.macro_blow_exotherm_k, "blow exotherm"), 15.0, 60.0),
    heatLossPerS: clamp(finite(cascade.macro_heat_loss_per_s, "heat loss"), 0.002, 0.03),
    co2ExpansionCapacity: clamp(finite(cascade.macro_co2_expansion_capacity,
      "CO2 expansion capacity"), 15.0, 55.0),
    co2SaturationFraction: clamp(finite(cascade.macro_co2_saturation_fraction,
      "CO2 saturation"), 0.03, 0.30),
    gelPointConversion: clamp(finite(cascade.macro_gel_point_conversion,
      "gel point"), 0.45, 0.75),
    viscosityGrowthExponent: clamp(finite(cascade.macro_viscosity_growth_exponent,
      "viscosity exponent"), 1.0, 4.0),
    bubbleTrapBase: clamp(finite(cascade.macro_bubble_trap_base, "bubble trap"), 0.30, 0.90),
    expansionMobilityPerS: clamp(finite(cascade.macro_expansion_mobility_per_s,
      "expansion mobility"), 0.05, 0.8),
    autocatalysisGain: clamp(finite(cascade.macro_autocatalysis_gain,
      "autocatalysis gain"), 0.0, 3.0),
    solidConversion: clamp(finite(cascade.macro_solid_conversion,
      "solid conversion"), 0.80, 0.98),
    responseSigma: clamp(finite(cascade.macro_response_sigma, "response sigma"), 0.0, 1.0)
  };
}

// One explicit step of the reduced dual-reaction foaming model.
//   gel  = urethane conversion (R-NCO + R'-OH -> urethane)
//   blow = water conversion    (R-NCO + H2O   -> amine + CO2)
// Both draw on the shared isocyanate budget (ncoShare from the declared index).
function stepReaction(s, c, dt) {
  const arr = Math.exp(c.activationTemperatureK *
    (1.0 / APPARATUS.initialTemperatureK - 1.0 / s.temperatureK));
  const avail = Math.max(0.0, 1.0 - (s.gel + s.blow) * s.ncoShare);
  const dGel = Math.min(c.gelRatePerS * (1.0 - s.gel) * avail * arr *
    (1.0 + c.autocatalysisGain * s.gel) * dt, 1.0 - s.gel);
  const dBlow = Math.min(c.blowRatePerS * (1.0 - s.blow) * avail * arr * dt, 1.0 - s.blow);
  s.gel += dGel;
  s.blow += dBlow;
  s.temperatureK += c.gelExothermK * dGel + c.blowExothermK * dBlow -
    c.heatLossPerS * (s.temperatureK - APPARATUS.initialTemperatureK) * dt;
  s.peakTemperatureK = Math.max(s.peakTemperatureK, s.temperatureK);

  // Castro-Macosko-style viscosity divergence toward the gel point; the rising
  // viscosity is what turns escaping bubbles into trapped ones.
  const gelClamped = Math.min(s.gel, c.gelPointConversion - 1e-3);
  s.relativeViscosity = Math.pow(c.gelPointConversion /
    (c.gelPointConversion - gelClamped), c.viscosityGrowthExponent);
  const trap = Math.min(1.0, c.bubbleTrapBase +
    (1.0 - c.bubbleTrapBase) * (1.0 - 1.0 / s.relativeViscosity));
  s.rigidity = clamp01((s.gel - c.gelPointConversion) /
    (c.solidConversion - c.gelPointConversion));

  // CO2 first dissolves; only past saturation do bubbles nucleate and grow
  // (the induction that delays the visible cream).
  const co2 = c.co2ExpansionCapacity * dBlow;
  s.dissolvedCo2 += co2;
  const saturation = c.co2SaturationFraction * c.co2ExpansionCapacity;
  if (s.dissolvedCo2 > saturation) {
    const excess = s.dissolvedCo2 - saturation;
    s.dissolvedCo2 = saturation;
    s.trappedGas += excess * trap;
    s.escapedGas += excess * (1.0 - trap);
  }
  const target = 1.0 + s.trappedGas * (s.temperatureK / APPARATUS.initialTemperatureK);
  const mobility = c.expansionMobilityPerS * (1.0 - s.rigidity);
  s.expansion += (target - s.expansion) * (1.0 - Math.exp(-mobility * dt));

  s.physicsTimeS += dt;
  s.physicsSteps += 1;
  if (s.creamTimeS === null && s.expansion > 1.15) s.creamTimeS = s.physicsTimeS;
  if (s.gelTimeS === null && s.gel >= c.gelPointConversion) s.gelTimeS = s.physicsTimeS;
  if (s.solidTimeS === null && s.rigidity >= 0.9) s.solidTimeS = s.physicsTimeS;
  s.expansionSeries.push([round4(s.physicsTimeS), round4(s.expansion)]);
}

function advanceTo(s, targetTimeS) {
  const epsilon = 1e-10;
  while (s.physicsTimeS + APPARATUS.physicsStepS <= targetTimeS + epsilon) {
    stepReaction(s, s.coeff, APPARATUS.physicsStepS);
  }
  const remainder = targetTimeS - s.physicsTimeS;
  if (remainder > epsilon) stepReaction(s, s.coeff, remainder);
  s.physicsTimeS = targetTimeS;
}

// ---- persistent parcel continuum: volume-conserving kinematics of the emergent
// foam volume (no authored trajectory or timing; motion mobility dies with the
// emergent rigidity, freezing the sponge shape) ----
function foamShapeZ(volumeFraction, totalVolumeMm3) {
  const volumeBelow = volumeFraction * totalVolumeMm3;
  const columnArea = Math.PI * PARCEL_R_MM * PARCEL_R_MM;
  if (volumeBelow <= CUP_COLUMN_VOLUME_MM3) return volumeBelow / columnArea;
  return APPARATUS.cupHeightMm + (volumeBelow - CUP_COLUMN_VOLUME_MM3) / CROWN_AREA_MM2;
}
function renderSigmaMm(state) {
  const totalVolume = POOL_VOLUME_MM3 * state.expansion;
  return 0.9 * Math.cbrt(totalVolume / state.n);
}
// Parcel CENTRES are pulled inward by the Gaussian-surface bulge so the
// reconstructed representation surface matches the foam body envelope; the
// nominal envelope radii come from the cup/crown geometry.
function foamRadiusAt(zMm, bulgeMm) {
  let nominal;
  if (zMm <= APPARATUS.cupHeightMm) {
    nominal = PARCEL_R_MM;
  } else {
    const blend = smoothstep((zMm - APPARATUS.cupHeightMm) / APPARATUS.crownNeckBlendMm);
    nominal = mix(PARCEL_R_MM, CROWN_R_MM, blend);
  }
  return Math.max(2.0, nominal - bulgeMm);
}

function initParcels(state) {
  const n = state.n;
  const golden = Math.PI * (3.0 - Math.sqrt(5.0));
  const bulge = RENDER_BULGE_PER_SIGMA * renderSigmaMm(state);
  for (let i = 0; i < n; i += 1) {
    state.volumeFraction[i] = clamp((i + 0.5) / n +
      (parcelNoise01(i, 0) - 0.5) * (0.5 / n), 0.002, 0.998);
    state.rhoFraction[i] = clamp(Math.sqrt(parcelNoise01(i, 1)) *
      (1.0 + 0.06 * (parcelNoise01(i, 3) - 0.5)), 0.0, 0.96);
    state.angle[i] = i * golden;
    const z = foamShapeZ(state.volumeFraction[i], POOL_VOLUME_MM3);
    const r = state.rhoFraction[i] * foamRadiusAt(z, bulge);
    state.px[i] = r * Math.cos(state.angle[i]);
    state.py[i] = r * Math.sin(state.angle[i]);
    state.pz[i] = z;
  }
}

function advanceParcels(state, dt) {
  const totalVolume = POOL_VOLUME_MM3 * state.expansion;
  const relax = PARCEL_RELAX_PER_S * (1.0 - state.rigidity);
  const blendFactor = 1.0 - Math.exp(-relax * dt);
  const bulge = RENDER_BULGE_PER_SIGMA * renderSigmaMm(state);
  let maxSpeed = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    const zTarget = foamShapeZ(state.volumeFraction[i], totalVolume);
    const rTarget = state.rhoFraction[i] * foamRadiusAt(zTarget, bulge);
    const xTarget = rTarget * Math.cos(state.angle[i]);
    const yTarget = rTarget * Math.sin(state.angle[i]);
    let dx = (xTarget - state.px[i]) * blendFactor;
    let dy = (yTarget - state.py[i]) * blendFactor;
    let dz = (zTarget - state.pz[i]) * blendFactor;
    const speed = Math.sqrt(dx * dx + dy * dy + dz * dz) / Math.max(dt, 1e-9);
    if (speed > MAX_PARCEL_SPEED_MM_S) {
      state.velocityClampCount += 1;
      const scale = MAX_PARCEL_SPEED_MM_S / speed;
      dx *= scale; dy *= scale; dz *= scale;
    }
    state.px[i] += dx; state.py[i] += dy; state.pz[i] += dz;
    maxSpeed = Math.max(maxSpeed, Math.min(speed, MAX_PARCEL_SPEED_MM_S));
  }
  state.maxParcelSpeedMmS = Math.max(state.maxParcelSpeedMmS, maxSpeed);
}

function renderSurfaceHint(state) {
  const totalVolume = POOL_VOLUME_MM3 * state.expansion;
  const topZ = foamShapeZ(1.0, totalVolume);
  const sigma = renderSigmaMm(state);
  return {
    mode: "metaball",
    kernel: "gaussian",
    grid_spacing_mm: APPARATUS.renderSurfaceGridMm,
    sigma_mm: sigma,
    iso_level: RENDER_ISO_LEVEL,
    clip_cylinder: { axis: "z", radius_mm: CROWN_R_MM + 2.0, min_mm: 0.0,
                     max_mm: topZ + RENDER_BULGE_PER_SIGMA * sigma + 8.0 },
    fresnel_r0: 0.04,
    gloss: 0.35,
    opacity: mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
      clamp01(state.expansion - 1.0)),
    positions_unmodified: true,
    policy: "representation only: Gaussian surface over emitted parcel positions; sigma tracks the emergent parcel spacing and centres sit one surface-bulge inside the foam envelope"
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

function observedPhase(state) {
  if (state.rigidity >= 0.9) return "solid_sponge";
  if (state.rigidity > 0.05) return "gelling_curing";
  if (state.creamTimeS !== null && state.expansion > 1.5) return "rising";
  if (state.creamTimeS !== null) return "creaming";
  return "mixing_liquids";
}

function emitFrame(ctx, state, frameIndex) {
  const clock = frameClock(frameIndex);
  const phase = observedPhase(state);
  const gasFraction = clamp01((state.expansion - 1.0) / Math.max(state.expansion, 1e-9));
  const whiteness = 1.0 - Math.exp(-REPRESENTATION.scatterGain * gasFraction);
  const positions = new Array(state.n);
  const colors = new Array(state.n);
  let maxDisplacement = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    positions[i] = [round4(state.px[i]), round4(state.py[i]), round4(state.pz[i])];
    const shade = 1.0 + 0.05 * (parcelNoise01(i, 2) - 0.5);
    let rgb = mixRgb(state.liquidBaseRgb, REPRESENTATION.creamTint, whiteness);
    rgb = mixRgb(rgb, REPRESENTATION.curedTint, 0.35 * state.gel * whiteness);
    colors[i] = [clamp01(rgb[0] * shade), clamp01(rgb[1] * shade),
                 clamp01(rgb[2] * shade),
                 mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha, gasFraction)];
    if (state.lastEmittedPx) {
      const dx = state.px[i] - state.lastEmittedPx[i];
      const dy = state.py[i] - state.lastEmittedPy[i];
      const dz = state.pz[i] - state.lastEmittedPz[i];
      maxDisplacement = Math.max(maxDisplacement, Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
  }
  state.lastEmittedPx = new Float64Array(state.px);
  state.lastEmittedPy = new Float64Array(state.py);
  state.lastEmittedPz = new Float64Array(state.pz);
  state.frameDisplacementsMm.push(round4(maxDisplacement));
  state.lastFrame = frameIndex;
  state.lastPhysicalTimeS = clock.physicalTimeS;

  ctx.emit("material_frame", {
    time_s: round4(clock.physicalTimeS),
    physical_time_s: round4(clock.physicalTimeS),
    playback_time_s: round4(clock.playbackTimeS),
    time_scale: clock.timeScale,
    phase: "polyurethane_foam:" + phase,
    particle_ids: state.ids,
    positions_mm: positions,
    colors_rgba: colors,
    render_surface: renderSurfaceHint(state),
    counts: {
      persistent_foam_parcels: state.n,
      expansion_factor: round4(state.expansion),
      gas_volume_fraction: round4(gasFraction)
    },
    physics_state: {
      gel_conversion: round4(state.gel),
      blow_conversion: round4(state.blow),
      temperature_k: round4(state.temperatureK),
      relative_viscosity: round4(Math.min(state.relativeViscosity, 1e6)),
      rigidity: round4(state.rigidity),
      trapped_gas_volumes: round4(state.trappedGas),
      escaped_gas_volumes: round4(state.escapedGas),
      dissolved_co2_volumes: round4(state.dissolvedCo2),
      foam_top_mm: round4(foamShapeZ(1.0, POOL_VOLUME_MM3 * state.expansion)),
      max_displacement_since_prior_emit_mm: round4(maxDisplacement)
    },
    geant4_event_id: state.lastGeant4EventId,
    inference: { source: state.coeff.source, response_sigma: state.coeff.responseSigma },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: clock.timeScale
    },
    motion_scope: "persistent foam parcels; volume-conserving kinematics of the emergent expansion; mobility dies with the emergent rigidity (no authored trajectory, timing, or endpoint)",
    representation_override: REPRESENTATION
  });
}

// Known polyurethane-foam behaviour, read ONLY at run end to grade the emergent
// result. None of this feeds the state or the frames.
const VALIDATION_ONLY = {
  expectedBehaviour: "cream within seconds-to-tens-of-seconds, expand up to ~30x, exotherm, cure into a rigid porous sponge",
  plausibleExpansionRange: [10.0, 40.0],
  plausibleCreamTimeRangeS: [5.0, 40.0],
  plausibleExothermRiseK: [30.0, 120.0],
  expectedFinalConsistency: "rigid (motion frozen past the gel point), porous (mostly gas)",
  source: "rigid PU foam demonstration kits; Flory gelation + Castro-Macosko rheology; urethane/water-isocyanate reaction chemistry (validation only)"
};

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const waterProbe = ctx.materials && ctx.materials[WATER];
    const polyolProbe = ctx.materials && ctx.materials[POLYOL_SOLUTION];
    const isoProbe = ctx.materials && ctx.materials[ISOCYANATE_SOLUTION];
    const mixProbe = ctx.materials && ctx.materials[RESIN_MIX];
    if (!waterProbe || !polyolProbe || !isoProbe || !mixProbe) {
      throw new Error("Geant4 material probes missing foam media");
    }
    const structures = {
      polyol_initiator: pubchemStructure("glycerol"),
      diisocyanate: pubchemStructure("toluene 2,4-diisocyanate"),
      blowing_agent: pubchemStructure("water")
    };
    const seed = {};
    seed["context.polyol_hydroxyl_number"] = RECIPE.polyolHydroxylNumberMgKohG;
    seed["context.water_pphp"] = RECIPE.waterPartsPerHundredPolyol;
    seed["context.isocyanate_index"] = RECIPE.isocyanateIndex;
    seed["context.amine_catalyst_pphp"] = RECIPE.amineCatalystPphp;
    seed["context.surfactant_pphp"] = RECIPE.surfactantPphp;
    seed["context.initial_temperature_k"] = APPARATUS.initialTemperatureK;
    const cascade = ctx.cascade(seed);
    if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
      throw new Error("polyurethane cascade requires predictive mode and two loaded stages");
    }
    const coeff = inferredCoefficients(cascade);
    const n = APPARATUS.parcels;
    const state = {
      cascade, coeff, structures,
      n,
      ids: Array.from({ length: n }, (_, i) => i),
      px: new Float64Array(n), py: new Float64Array(n), pz: new Float64Array(n),
      volumeFraction: new Float64Array(n),
      rhoFraction: new Float64Array(n),
      angle: new Float64Array(n),
      liquidBaseRgb: opticsRgb(ctx, RESIN_MIX),
      waterDensity: Number(waterProbe.density_g_per_cm3),
      polyolDensity: Number(polyolProbe.density_g_per_cm3),
      isoDensity: Number(isoProbe.density_g_per_cm3),
      mixDensity: Number(mixProbe.density_g_per_cm3),
      mixElectronDensity: Number(mixProbe.electron_density_per_cm3),
      isoNitrogenPerCm3: Number((isoProbe.numberDensityPerCm3 || {}).N || 0),
      mixNumberDensity: mixProbe.numberDensityPerCm3 || {},
      // shared isocyanate budget from the declared index (two consumer channels)
      ncoShare: 1.0 / (2.0 * RECIPE.isocyanateIndex),
      // reaction state
      gel: 0.0, blow: 0.0,
      temperatureK: APPARATUS.initialTemperatureK,
      peakTemperatureK: APPARATUS.initialTemperatureK,
      dissolvedCo2: 0.0, trappedGas: 0.0, escapedGas: 0.0,
      relativeViscosity: 1.0, rigidity: 0.0, expansion: 1.0,
      physicsTimeS: 0.0, physicsSteps: 0,
      creamTimeS: null, gelTimeS: null, solidTimeS: null,
      expansionSeries: [],
      // parcel/frame bookkeeping
      lastEmittedPx: null, lastEmittedPy: null, lastEmittedPz: null,
      frameDisplacementsMm: [],
      velocityClampCount: 0, maxParcelSpeedMmS: 0.0,
      lastFrame: 0, lastPhysicalTimeS: 0.0,
      geant4Events: 0, geant4Edep: 0.0, geant4Steps: 0, lastGeant4EventId: -1
    };
    initParcels(state);
    ctx.state.puFoam = state;
    ctx.emit("polyurethane_foam_scenario", {
      name: "polyurethane_foam",
      recipe: RECIPE,
      apparatus: APPARATUS,
      reactions: {
        polymerization: "R-N=C=O + R'-OH -> R-NH-CO-O-R' (urethane linkage; builds the cross-linked matrix)",
        blowing: "R-N=C=O + H2O -> R-NH2 + CO2^ (gas generation; inflates the curing matrix)"
      },
      geant4_materials: [POLYOL_SOLUTION, ISOCYANATE_SOLUTION, RESIN_MIX, WATER],
      geant4_sees: {
        polyol_solution_density_g_per_cm3: state.polyolDensity,
        diisocyanate_solution_density_g_per_cm3: state.isoDensity,
        resin_mix_density_g_per_cm3: state.mixDensity,
        water_density_g_per_cm3: state.waterDensity,
        isocyanate_nitrogen_atoms_per_cm3: state.isoNitrogenPerCm3,
        mix_electron_density_per_cm3: state.mixElectronDensity
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures
      },
      inferred_coefficients: coeff,
      cascade_trace: cascade.__cascade,
      representation_override: REPRESENTATION
    });
    emitFrame(ctx, state, 0);
  },
  onEventEnd(ctx) {
    const state = ctx.state && ctx.state.puFoam;
    if (!state) return;
    state.geant4Events += 1;
    state.geant4Edep += Number(ctx.event.edepMeV || 0.0);
    state.geant4Steps += Number(ctx.event.totalStepCount || 0);
    state.lastGeant4EventId = Number(ctx.event.id);
    const frameIndex = Math.min(APPARATUS.outputTicks, Number(ctx.event.id) + 1);
    const previousTimeS = state.physicsTimeS;
    const target = frameClock(frameIndex).physicalTimeS;
    advanceTo(state, target);
    advanceParcels(state, Math.max(target - previousTimeS, 1e-9));
    emitFrame(ctx, state, frameIndex);
  },
  onRunEnd(ctx) {
    const state = ctx.state && ctx.state.puFoam;
    if (!state) return;
    const coeff = state.coeff;
    const finalExpansion = state.expansion;
    let riseTimeS = null;
    for (let i = 0; i < state.expansionSeries.length; i += 1) {
      if (state.expansionSeries[i][1] >= 0.95 * finalExpansion) {
        riseTimeS = state.expansionSeries[i][0];
        break;
      }
    }
    const lateWindow = state.frameDisplacementsMm.slice(-10);
    const lateMaxDisplacement = lateWindow.length ? Math.max.apply(null, lateWindow) : Infinity;
    const gasFraction = clamp01((finalExpansion - 1.0) / Math.max(finalExpansion, 1e-9));
    const trappedFraction = state.trappedGas /
      Math.max(1e-9, state.trappedGas + state.escapedGas);
    const seedKeys = state.cascade.__cascade.seedKeys || [];
    const g4Seeded = seedKeys.indexOf("material." + RESIN_MIX + ".density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material." + ISOCYANATE_SOLUTION + ".density_g_per_cm3") >= 0;
    const exothermRiseK = state.peakTemperatureK - APPARATUS.initialTemperatureK;
    const ordering = state.creamTimeS !== null && state.gelTimeS !== null &&
      state.solidTimeS !== null && riseTimeS !== null &&
      state.creamTimeS < state.gelTimeS && state.gelTimeS < state.solidTimeS &&
      state.creamTimeS < riseTimeS;

    ctx.emit("polyurethane_foam_summary", {
      recipe: RECIPE,
      geant4: {
        polyol_solution_density_g_per_cm3: state.polyolDensity,
        diisocyanate_solution_density_g_per_cm3: state.isoDensity,
        resin_mix_density_g_per_cm3: state.mixDensity,
        water_density_g_per_cm3: state.waterDensity,
        isocyanate_nitrogen_atoms_per_cm3: state.isoNitrogenPerCm3,
        mix_electron_density_per_cm3: state.mixElectronDensity,
        liquid_base_rgb: state.liquidBaseRgb,
        event_drive: { events: state.geant4Events, edep_mev: round4(state.geant4Edep),
                       steps: state.geant4Steps }
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures: state.structures
      },
      inferred_coefficients: coeff,
      cascade: state.cascade.__cascade,
      emergent: {
        frames: state.lastFrame + 1,
        final_expansion_factor: round4(finalExpansion),
        final_gas_volume_fraction: round4(gasFraction),
        cream_time_s: state.creamTimeS === null ? null : round4(state.creamTimeS),
        rise_time_s: riseTimeS === null ? null : round4(riseTimeS),
        gel_time_s: state.gelTimeS === null ? null : round4(state.gelTimeS),
        solid_time_s: state.solidTimeS === null ? null : round4(state.solidTimeS),
        peak_temperature_k: round4(state.peakTemperatureK),
        exotherm_rise_k: round4(exothermRiseK),
        final_gel_conversion: round4(state.gel),
        final_blow_conversion: round4(state.blow),
        final_rigidity: round4(state.rigidity),
        trapped_gas_fraction: round4(trappedFraction),
        escaped_gas_volumes: round4(state.escapedGas),
        foam_top_mm: round4(foamShapeZ(1.0, POOL_VOLUME_MM3 * finalExpansion)),
        late_window_max_displacement_mm: round4(lateMaxDisplacement),
        velocity_clamp_count: state.velocityClampCount,
        max_parcel_speed_mm_per_s: round4(state.maxParcelSpeedMmS)
      },
      validation_references_only: VALIDATION_ONLY,
      validation: {
        geant4_base_present: state.isoDensity > state.polyolDensity &&
          state.mixDensity > state.waterDensity && state.isoNitrogenPerCm3 > 0 &&
          state.geant4Events === APPARATUS.outputTicks && state.geant4Edep > 0.0,
        cascade_supplies_coefficients: state.cascade.__cascade.stagesRun === 2 &&
          g4Seeded && coeff.gelRatePerS > 0 && coeff.blowRatePerS > 0 &&
          coeff.co2ExpansionCapacity > 0,
        no_engine_reaction_rule: true,
        two_simultaneous_reactions: state.gel > 0.8 && state.blow > 0.8,
        induction_then_cream: state.creamTimeS !== null &&
          state.creamTimeS >= VALIDATION_ONLY.plausibleCreamTimeRangeS[0] &&
          state.creamTimeS <= VALIDATION_ONLY.plausibleCreamTimeRangeS[1],
        expansion_emerged_plausible:
          finalExpansion >= VALIDATION_ONLY.plausibleExpansionRange[0] &&
          finalExpansion <= VALIDATION_ONLY.plausibleExpansionRange[1],
        milestone_ordering_cream_gel_solid: ordering,
        exotherm_plausible: exothermRiseK >= VALIDATION_ONLY.plausibleExothermRiseK[0] &&
          exothermRiseK <= VALIDATION_ONLY.plausibleExothermRiseK[1],
        gas_trapped_by_curing_matrix: trappedFraction >= 0.7 && state.escapedGas > 0.0,
        solidifies_rigid: state.rigidity >= 0.9 && lateMaxDisplacement < 0.5,
        porous_sponge_structure: gasFraction > 0.9,
        pubchem_structure_consistent_with_geant4: structureConsistent(state.structures),
        velocity_cap_not_driving_motion: state.velocityClampCount === 0,
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 1200.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.initialTemperatureK,
    pressureAtm: 1.0
  },
  // A low-energy gamma transported through the actual liquid resin pool each tick:
  // it exercises Geant4 transport/scoring (the per-frame clock + event drive) while
  // the hook layer advances the inferred foaming model. It does not carry the
  // chemistry.
  beam: {
    particle: "gamma",
    energyMeV: 0.06,
    originMm: [0, 15.0, -70.0],
    direction: [0, 0, 1],
    spread: helpers.beamProfiles.spread("ledLamp", { energySpreadFractional: 0.04 })
  },
  run: { nEvents: APPARATUS.outputTicks, seed: 20260725, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: {
    enable: true,
    materials: [WATER, POLYOL_SOLUTION, ISOCYANATE_SOLUTION, RESIN_MIX]
  },
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
      writeSpectrum: false
    }
  },
  models: [
    { name: "macro_foam_response", scale: "macro",
      path: "data/polyurethane_cascade/macro_foam_response.json" },
    { name: "nano_reagent_descriptors", scale: "nano",
      path: "data/polyurethane_cascade/nano_reagent_descriptors.json" }
  ],
  system: {
    enable: true, mode: "transient", frame: "observer",
    ensemble: "polyurethane_foam",
    volumeMm3: POOL_VOLUME_MM3
  },
  materials: [polyolMaterial, isocyanateMaterial, resinMixMaterial],
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 524288 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "cup_wall", material: CUP,
        innerRadiusMm: APPARATUS.cupInnerRadiusMm,
        outerRadiusMm: APPARATUS.cupInnerRadiusMm + 2.5,
        lengthMm: APPARATUS.cupHeightMm,
        positionMm: [0, APPARATUS.cupHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["cup", "viz_shell", "viz_opacity=0.14"]
      }),
      // The freshly mixed liquid resin pool: the beam medium + optics/composition
      // base. Hidden in viz -- the persistent parcels represent the material.
      geometry.tubeVolume({
        name: "resin_pool", material: RESIN_MIX,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.cupInnerRadiusMm,
        lengthMm: APPARATUS.initialLiquidHeightMm,
        positionMm: [0, APPARATUS.initialLiquidHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["viz_hidden"]
      }),
      // Hidden probe volumes make each prepared solution part of the constructed
      // Geant4 geometry (composition/optics panel).
      geometry.boxVolume({ name: "polyol_probe", material: POLYOL_SOLUTION,
        sizeMm: [4, 4, 4], positionMm: [-160, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "isocyanate_probe", material: ISOCYANATE_SOLUTION,
        sizeMm: [4, 4, 4], positionMm: [160, 0, 0], tags: ["viz_hidden"] })
    ]
  }
};
