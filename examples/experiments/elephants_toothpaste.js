// Elephant's toothpaste ("the soapy lather"), observed in a graduated cylinder.
//
// Two clear aqueous solutions are combined:
//   Solution A ... concentrated hydrogen peroxide (H2O2) + liquid dish soap
//   Solution B ... potassium iodide (KI) dissolved in water
// The iodide ion catalyses the decomposition
//   2 H2O2 (aq) --I-->  2 H2O (l) + O2 (g)
// and the sudden oxygen release, trapped by the surfactant, erupts as a massive
// steaming column of lather that never solidifies. TRECH is told ONLY what is in
// the cylinder (the two-solution recipe + the constructed Geant4 materials). It is
// NOT told that the reaction accelerates, how fast it completes, how hot it gets,
// how big the foam grows, its colour, or that the lather stays soft and drains.
// All of that must EMERGE.
//
// Information discipline (the TRECH thesis, applied to a catalytic runaway):
//   * Geant4 is the physical base. G4-constructed solution/mixture materials
//     supply composition, density, and electron/atom densities (Geant4 literally
//     "sees" the dissolved iodine and potassium in Solution B and the oxygen-rich
//     density of the peroxide solution) plus the cross sections behind TRECH's
//     derived colour for the clear mixed solution.
//   * ctx.cascade lifts those Geant4 facts + the declared recipe through a nano
//     reagent-descriptor stage and a macro observer-band response surface into the
//     COEFFICIENTS of a reduced catalytic-decomposition model (catalysed and
//     uncatalysed rate constants, Arrhenius activation temperature, full-conversion
//     exotherm, heat loss, O2 foam capacity, surfactant trapping efficiency, foam
//     drainage rate, iodine-intermediate shunt gain). The cascade emits NO
//     completion time, eruption height, temperature peak, colour, or phase
//     schedule.
//   * A deterministic hook-layer integrator advances the peroxide reservoir, the
//     temperature (with an evaporative clamp near the carrier boiling band -- a
//     labelled comparison-layer constant), the trapped/escaped O2 budget, the foam
//     volume, and the transient iodine intermediate. Whether the decomposition
//     runs away, when the foam erupts over the rim, how tall the fountain grows,
//     the steaming temperature, the yellow iodine tinge, and the slow drainage of
//     a lather that NEVER solidifies all EMERGE from the integration.
//   * Honest scope: Geant4 does not itself solve aqueous redox kinetics or foam
//     drainage; the reduced model is an explicit "physics for comparison"
//     hook-layer model whose coefficients are inferred from the Geant4 base. The
//     compact macro response surface is illustrative (uncertainty sigma emitted).
//     The white-lather/amber display swatches are labelled representation; the
//     clear base colour IS Geant4-derived, and the whitening (bubble scattering)
//     and amber tinge (iodine intermediate) TIMING is the emergent, graded result.
//   * PubChem supplies structure identity ONLY (CID + SMILES + formula); those
//     element sets are cross-checked against the declared Geant4 composition at
//     run end. No PubChem density/colour/rate feeds runtime.
//
// The known elephant's-toothpaste behaviour used to CHECK the result (never to
// drive it) lives in VALIDATION_ONLY and is read only at run end.
//
// Run (PubChem structure cache first, once):
//   PYTHONPATH=tools/pubchem python -m trech_pubchem fetch --cache-dir build/pubchem_cache \
//     "hydrogen peroxide" "potassium iodide" water
//   TRECH_PUBCHEM_CACHE_DIR=build/pubchem_cache build/dev/trech run \
//     examples/experiments/elephants_toothpaste.js --output build/dev/out_elephants_toothpaste

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

const WATER = "G4_WATER";
const AIR = "G4_AIR";
const GLASS = "G4_GLASS_PLATE";
const PEROXIDE_SOAP = "peroxide_soap_solution";       // Solution A
const IODIDE_CATALYST = "iodide_catalyst_solution";   // Solution B
const REACTING_MIX = "toothpaste_reacting_mixture";   // A + B, just combined

// The prepared recipe (what a demonstrator pours). Declared context -- the
// "known solutions in a cylinder" -- NOT the reaction result.
const RECIPE = {
  peroxideMassFraction: 0.30,   // concentrated "30 volume-plus" H2O2
  soapMassFraction: 0.02,       // liquid dish soap surfactant
  kiMolarity: 2.0,              // Solution B potassium iodide
  catalystVolumeFraction: 0.20, // B poured into A
  pourVolumeMl: 250.0
};

const durationS = TRECH_VALUE.number("duration_s", {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful decomposition integrator advances.",
  default: 45.0, min: 15.0, max: 300.0, step: 5.0
});
const playbackDurationS = TRECH_VALUE.number("playback_duration_s", {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 9.0, min: 1.0, max: 60.0, step: 1.0
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; physics uses bounded finer steps.",
  default: 135, min: 20, max: 1000, step: 5
});
const foamParcels = TRECH_VALUE.integer("foam_parcels", {
  label: "Persistent foam parcels", group: "Precision", unit: "parcels",
  description: "Spatial resolution; the represented material volume stays fixed.",
  default: 280, min: 140, max: 560, step: 20
});
const maxPhysicsStepS = TRECH_VALUE.number("max_physics_step_s", {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal resolution of the decomposition/foam integrator.",
  default: 0.02, min: 0.005, max: 0.1, step: 0.005
});
const renderSurfaceGridMm = TRECH_VALUE.number("render_surface_grid_mm", {
  label: "Foam surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated state.",
  default: 3.5, min: 2.0, max: 7.0, step: 0.5
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
  cylinderInnerRadiusMm: 25.0,
  cylinderHeightMm: 220.0,
  crownRadiusMm: 52.0,          // billowing lather column above the rim
  crownNeckBlendMm: 18.0,
  initialLiquidHeightMm: 127.0, // 250 mL in the cylinder
  initialTemperatureK,
  parcels: foamParcels,
  renderSurfaceGridMm
};

// ---- representation-only display swatches (labelled; never feed dynamics) ----
// The clear base colour is replaced at run start by the Geant4-derived colour of
// the mixed solution. The white-lather and amber-iodine swatches are
// representation: their APPEARANCE is authored, but WHEN the foam whitens (bubble
// scattering) and takes the yellow iodine tinge (transient intermediate) is
// emergent chemistry.
const REPRESENTATION = {
  policy: "white/amber swatches are authored display; clear base is Geant4-derived; whitening/amber TIMING is emergent",
  latherTint: [0.94, 0.95, 0.96],
  iodineAmberTint: [0.86, 0.62, 0.12],
  liquidAlpha: 0.72,
  foamAlpha: 0.95,
  scatterGain: 2.6
};

// Comparison-layer physical constant (labelled): evaporative heat loss grows
// steeply as the aqueous carrier approaches its boiling band, capping the
// exotherm the way the visible steam does in the demonstration.
const EVAPORATIVE_CLAMP = { onsetK: 368.0, lossPerSPerK: 6.4 };

const PARCEL_R_MM = APPARATUS.cylinderInnerRadiusMm - 1.5;
const POOL_VOLUME_MM3 = Math.PI * PARCEL_R_MM * PARCEL_R_MM *
  APPARATUS.initialLiquidHeightMm;
const CYLINDER_COLUMN_VOLUME_MM3 = Math.PI * PARCEL_R_MM * PARCEL_R_MM *
  APPARATUS.cylinderHeightMm;
const CROWN_R_MM = APPARATUS.crownRadiusMm;
const CROWN_AREA_MM2 = Math.PI * CROWN_R_MM * CROWN_R_MM;
const PARCEL_RELAX_PER_S = 2.6;
const MAX_PARCEL_SPEED_MM_S = 260.0;
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
// Solution A: 30% H2O2 (oxygen-rich water) + dish-soap carbon. Solution B: KI in
// water (Geant4 sees the iodine AND the potassium). The mixture is what reacts.
const peroxideSoapMaterial = {
  name: PEROXIDE_SOAP, densityGcm3: 1.11,
  components: [
    { material: WATER, fraction: 0.68 },
    { element: "O", fraction: 0.28 },
    { element: "H", fraction: 0.02 },
    { element: "C", fraction: 0.02 }
  ]
};
const iodideCatalystMaterial = {
  name: IODIDE_CATALYST, densityGcm3: 1.23,
  components: [
    { material: WATER, fraction: 0.71 },
    { element: "I", fraction: 0.222 },
    { element: "K", fraction: 0.068 }
  ]
};
const reactingMixMaterial = {
  name: REACTING_MIX, densityGcm3: 1.13,
  components: [
    { material: WATER, fraction: 0.686 },
    { element: "O", fraction: 0.224 },
    { element: "H", fraction: 0.016 },
    { element: "C", fraction: 0.016 },
    { element: "I", fraction: 0.044 },
    { element: "K", fraction: 0.014 }
  ]
};
const DECLARED_ELEMENTS = ["H", "O", "C", "I", "K"];

// ---- PubChem structure identity (CID + SMILES + formula ONLY) ----
function pubchemStructure(name) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM unavailable; fetch the build-local structure cache first");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || !raw.cid || !raw.smiles) {
    throw new Error("PubChem structure cache for " + name + " must contain cid + smiles");
  }
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

// ---- the inferred decomposition coefficients (clamped to a physically stable
// range around the cascade prediction) ----
function inferredCoefficients(cascade) {
  return {
    source: "ctx.cascade(Geant4 solution/mixture base + recipe -> nano descriptors -> macro catalytic-decomposition coefficients)",
    catalysedRatePerS: clamp(finite(cascade.macro_catalysed_rate_per_s,
      "catalysed rate"), 0.005, 0.25),
    uncatalysedRatePerS: clamp(finite(cascade.macro_uncatalysed_rate_per_s,
      "uncatalysed rate"), 1e-8, 1e-4),
    activationTemperatureK: clamp(finite(cascade.macro_activation_temperature_k,
      "activation temperature"), 2000.0, 6500.0),
    exothermKAtFull: clamp(finite(cascade.macro_exotherm_k_at_full,
      "full-conversion exotherm"), 50.0, 220.0),
    heatLossPerS: clamp(finite(cascade.macro_heat_loss_per_s, "heat loss"), 0.01, 0.12),
    o2FoamCapacity: clamp(finite(cascade.macro_o2_foam_capacity,
      "O2 foam capacity"), 30.0, 160.0),
    foamTrapEfficiency: clamp(finite(cascade.macro_foam_trap_efficiency,
      "foam trap efficiency"), 0.05, 0.5),
    foamDrainagePerS: clamp(finite(cascade.macro_foam_drainage_per_s,
      "foam drainage"), 0.001, 0.05),
    iodineShuntGain: clamp(finite(cascade.macro_iodine_shunt_gain,
      "iodine shunt gain"), 0.0, 0.5),
    responseSigma: clamp(finite(cascade.macro_response_sigma, "response sigma"), 0.0, 1.0)
  };
}

// One explicit step of the reduced catalytic-decomposition model.
//   peroxide = remaining H2O2 fraction; the iodide catalyst is regenerated each
//   cycle (I- -> IO- -> I-), so the rate stays first-order in peroxide.
function stepReaction(s, c, dt) {
  const arr = Math.exp(c.activationTemperatureK *
    (1.0 / APPARATUS.initialTemperatureK - 1.0 / s.temperatureK));
  const rate = c.catalysedRatePerS * arr;
  const dP = Math.min(rate * s.peroxide * dt, s.peroxide);
  s.peroxide -= dP;
  s.meanArrhenius += arr * dt;
  s.arrheniusTimeS += dt;

  const generated = c.o2FoamCapacity * dP;
  const trapped = generated * c.foamTrapEfficiency;
  s.foamVolumes += trapped - c.foamDrainagePerS * s.foamVolumes * dt;
  s.foamVolumes = Math.max(0.0, s.foamVolumes);
  s.trappedGas += trapped;
  s.escapedGas += generated * (1.0 - c.foamTrapEfficiency);

  s.temperatureK += c.exothermKAtFull * dP -
    c.heatLossPerS * (s.temperatureK - APPARATUS.initialTemperatureK) * dt;
  if (s.temperatureK > EVAPORATIVE_CLAMP.onsetK) {
    const removed = (s.temperatureK - EVAPORATIVE_CLAMP.onsetK) *
      EVAPORATIVE_CLAMP.lossPerSPerK * dt;
    s.temperatureK -= removed;
    s.evaporativeRemovedK += removed;
    s.steamingSteps += 1;
  }
  s.peakTemperatureK = Math.max(s.peakTemperatureK, s.temperatureK);
  // The temperature the same exotherm reaches with the comparison-layer clamp
  // switched off -- so how much of the sub-boiling result is the authored clamp
  // is measurable, not hidden.
  s.unclampedTemperatureK += c.exothermKAtFull * dP -
    c.heatLossPerS * (s.unclampedTemperatureK - APPARATUS.initialTemperatureK) * dt;
  s.peakUnclampedTemperatureK = Math.max(s.peakUnclampedTemperatureK,
    s.unclampedTemperatureK);

  // transient iodine intermediate (I- -> IO-/I2 shunt): quasi-steady with the
  // instantaneous turnover -- rises with the burst, fades as peroxide depletes.
  s.iodineIntermediate = c.iodineShuntGain * rate * s.peroxide /
    Math.max(c.catalysedRatePerS, 1e-9);
  s.peakIodineIntermediate = Math.max(s.peakIodineIntermediate, s.iodineIntermediate);
  if (s.iodineIntermediate === s.peakIodineIntermediate) {
    s.peakIodineTimeS = s.physicsTimeS;
  }

  s.physicsTimeS += dt;
  s.physicsSteps += 1;
  const totalVolume = POOL_VOLUME_MM3 * (1.0 + s.foamVolumes);
  if (s.eruptTimeS === null && totalVolume > CYLINDER_COLUMN_VOLUME_MM3) {
    s.eruptTimeS = s.physicsTimeS;
  }
  if (s.foamVolumes > s.peakFoamVolumes) {
    s.peakFoamVolumes = s.foamVolumes;
    s.peakFoamTimeS = s.physicsTimeS;
  }
  if (s.t90S === null && s.peroxide <= 0.10) s.t90S = s.physicsTimeS;
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
// foam volume (no authored trajectory or timing; the lather never rigidifies, so
// mobility never dies -- late subsidence follows the emergent drainage) ----
function foamShapeZ(volumeFraction, totalVolumeMm3) {
  const volumeBelow = volumeFraction * totalVolumeMm3;
  const columnArea = Math.PI * PARCEL_R_MM * PARCEL_R_MM;
  if (volumeBelow <= CYLINDER_COLUMN_VOLUME_MM3) return volumeBelow / columnArea;
  return APPARATUS.cylinderHeightMm +
    (volumeBelow - CYLINDER_COLUMN_VOLUME_MM3) / CROWN_AREA_MM2;
}
function renderSigmaMm(state) {
  const totalVolume = POOL_VOLUME_MM3 * (1.0 + state.foamVolumes);
  return 0.9 * Math.cbrt(totalVolume / state.n);
}
// Parcel CENTRES are pulled inward by the Gaussian-surface bulge so the
// reconstructed representation surface matches the foam body envelope; the
// nominal envelope radii come from the cylinder/crown geometry.
function foamRadiusAt(zMm, bulgeMm) {
  let nominal;
  if (zMm <= APPARATUS.cylinderHeightMm) {
    nominal = PARCEL_R_MM;
  } else {
    const blend = smoothstep((zMm - APPARATUS.cylinderHeightMm) /
      APPARATUS.crownNeckBlendMm);
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
      (1.0 + 0.12 * (parcelNoise01(i, 3) - 0.5)), 0.0, 0.96);
    state.angle[i] = i * golden;
    const z = foamShapeZ(state.volumeFraction[i], POOL_VOLUME_MM3);
    const r = state.rhoFraction[i] * foamRadiusAt(z, bulge);
    state.px[i] = r * Math.cos(state.angle[i]);
    state.py[i] = r * Math.sin(state.angle[i]);
    state.pz[i] = z;
  }
}

function advanceParcels(state, dt) {
  const totalVolume = POOL_VOLUME_MM3 * (1.0 + state.foamVolumes);
  const blendFactor = 1.0 - Math.exp(-PARCEL_RELAX_PER_S * dt);
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
  const totalVolume = POOL_VOLUME_MM3 * (1.0 + state.foamVolumes);
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
    fresnel_r0: 0.03,
    gloss: 0.5,
    opacity: mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
      clamp01(state.foamVolumes)),
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
  if (state.physicsTimeS <= 0.0) return "clear_solutions_combined";
  if (state.foamVolumes < 0.2) return "catalytic_runaway_beginning";
  if (state.eruptTimeS === null) return "foam_filling_cylinder";
  if (state.peroxide > 0.10) return "eruption_fountain";
  if (state.foamVolumes > 0.9 * state.peakFoamVolumes) return "steaming_lather_column";
  return "draining_lather";
}

function emitFrame(ctx, state, frameIndex) {
  const clock = frameClock(frameIndex);
  const phase = observedPhase(state);
  const gasFraction = clamp01(state.foamVolumes / (1.0 + state.foamVolumes));
  const whiteness = 1.0 - Math.exp(-REPRESENTATION.scatterGain * gasFraction);
  const amber = clamp01(state.iodineIntermediate);
  const positions = new Array(state.n);
  const colors = new Array(state.n);
  let maxDisplacement = 0.0;
  for (let i = 0; i < state.n; i += 1) {
    positions[i] = [round4(state.px[i]), round4(state.py[i]), round4(state.pz[i])];
    const shade = 1.0 + 0.06 * (parcelNoise01(i, 2) - 0.5);
    let rgb = mixRgb(state.liquidBaseRgb, REPRESENTATION.latherTint, whiteness);
    rgb = mixRgb(rgb, REPRESENTATION.iodineAmberTint, 0.55 * amber);
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
    phase: "elephants_toothpaste:" + phase,
    particle_ids: state.ids,
    positions_mm: positions,
    colors_rgba: colors,
    render_surface: renderSurfaceHint(state),
    counts: {
      persistent_foam_parcels: state.n,
      foam_volume_factor: round4(1.0 + state.foamVolumes),
      gas_volume_fraction: round4(gasFraction)
    },
    physics_state: {
      peroxide_remaining_fraction: round4(state.peroxide),
      temperature_k: round4(state.temperatureK),
      foam_volumes: round4(state.foamVolumes),
      trapped_gas_volumes: round4(state.trappedGas),
      escaped_gas_volumes: round4(state.escapedGas),
      iodine_intermediate: round4(state.iodineIntermediate),
      steaming: state.temperatureK > EVAPORATIVE_CLAMP.onsetK - 10.0,
      foam_top_mm: round4(foamShapeZ(1.0, POOL_VOLUME_MM3 * (1.0 + state.foamVolumes))),
      max_displacement_since_prior_emit_mm: round4(maxDisplacement)
    },
    geant4_event_id: state.lastGeant4EventId,
    inference: { source: state.coeff.source, response_sigma: state.coeff.responseSigma },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: clock.timeScale
    },
    motion_scope: "persistent lather parcels; volume-conserving kinematics of the emergent foam volume; no rigidity, no authored trajectory, timing, or endpoint",
    representation_override: REPRESENTATION
  });
}

// Known elephant's-toothpaste behaviour, read ONLY at run end to grade the
// emergent result. None of this feeds the state or the frames.
const VALIDATION_ONLY = {
  expectedBehaviour: "sudden catalytic O2 release erupting as a steaming lather column that never solidifies, then slowly drains",
  minimumCatalyticAcceleration: 1000.0,
  plausibleCompletionTimeS: [3.0, 40.0],
  plausibleFoamVolumeFactorRange: [8.0, 40.0],
  plausiblePeakTemperatureK: [330.0, 373.5],
  expectedFinalConsistency: "soft draining lather (no rigidity; motion continues)",
  source: "Shakhashiri demonstration; iodide-catalysed H2O2 decomposition kinetics (Ea ~ 56 kJ/mol uncatalysed, lowered by I-); validation only"
};

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const waterProbe = ctx.materials && ctx.materials[WATER];
    const peroxideProbe = ctx.materials && ctx.materials[PEROXIDE_SOAP];
    const catalystProbe = ctx.materials && ctx.materials[IODIDE_CATALYST];
    const mixProbe = ctx.materials && ctx.materials[REACTING_MIX];
    if (!waterProbe || !peroxideProbe || !catalystProbe || !mixProbe) {
      throw new Error("Geant4 material probes missing toothpaste media");
    }
    const structures = {
      oxidizer: pubchemStructure("hydrogen peroxide"),
      catalyst_salt: pubchemStructure("potassium iodide"),
      carrier: pubchemStructure("water")
    };
    const seed = {};
    seed["context.peroxide_mass_fraction"] = RECIPE.peroxideMassFraction;
    seed["context.soap_mass_fraction"] = RECIPE.soapMassFraction;
    seed["context.ki_molarity"] = RECIPE.kiMolarity;
    seed["context.catalyst_volume_fraction"] = RECIPE.catalystVolumeFraction;
    seed["context.initial_temperature_k"] = APPARATUS.initialTemperatureK;
    const cascade = ctx.cascade(seed);
    if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
      throw new Error("elephant's-toothpaste cascade requires predictive mode and two loaded stages");
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
      liquidBaseRgb: opticsRgb(ctx, REACTING_MIX),
      waterDensity: Number(waterProbe.density_g_per_cm3),
      peroxideDensity: Number(peroxideProbe.density_g_per_cm3),
      catalystDensity: Number(catalystProbe.density_g_per_cm3),
      mixDensity: Number(mixProbe.density_g_per_cm3),
      mixElectronDensity: Number(mixProbe.electron_density_per_cm3),
      catalystIodinePerCm3: Number((catalystProbe.numberDensityPerCm3 || {}).I || 0),
      catalystPotassiumPerCm3: Number((catalystProbe.numberDensityPerCm3 || {}).K || 0),
      // reaction state
      peroxide: 1.0,
      temperatureK: APPARATUS.initialTemperatureK,
      peakTemperatureK: APPARATUS.initialTemperatureK,
      unclampedTemperatureK: APPARATUS.initialTemperatureK,
      peakUnclampedTemperatureK: APPARATUS.initialTemperatureK,
      evaporativeRemovedK: 0.0,
      foamVolumes: 0.0, peakFoamVolumes: 0.0, peakFoamTimeS: 0.0,
      trappedGas: 0.0, escapedGas: 0.0,
      iodineIntermediate: 0.0, peakIodineIntermediate: 0.0, peakIodineTimeS: 0.0,
      steamingSteps: 0,
      meanArrhenius: 0.0, arrheniusTimeS: 0.0,
      physicsTimeS: 0.0, physicsSteps: 0,
      eruptTimeS: null, t90S: null,
      // parcel/frame bookkeeping
      lastEmittedPx: null, lastEmittedPy: null, lastEmittedPz: null,
      frameDisplacementsMm: [],
      velocityClampCount: 0, maxParcelSpeedMmS: 0.0,
      lastFrame: 0, lastPhysicalTimeS: 0.0,
      geant4Events: 0, geant4Edep: 0.0, geant4Steps: 0, lastGeant4EventId: -1
    };
    initParcels(state);
    ctx.state.toothpaste = state;
    ctx.emit("elephants_toothpaste_scenario", {
      name: "elephants_toothpaste",
      recipe: RECIPE,
      apparatus: APPARATUS,
      reaction: "2 H2O2 (aq) --I-catalysed--> 2 H2O (l) + O2 (g); surfactant traps the O2 as lather",
      geant4_materials: [PEROXIDE_SOAP, IODIDE_CATALYST, REACTING_MIX, WATER],
      geant4_sees: {
        peroxide_solution_density_g_per_cm3: state.peroxideDensity,
        catalyst_solution_density_g_per_cm3: state.catalystDensity,
        reacting_mix_density_g_per_cm3: state.mixDensity,
        water_density_g_per_cm3: state.waterDensity,
        catalyst_iodine_atoms_per_cm3: state.catalystIodinePerCm3,
        catalyst_potassium_atoms_per_cm3: state.catalystPotassiumPerCm3,
        mix_electron_density_per_cm3: state.mixElectronDensity
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures
      },
      inferred_coefficients: coeff,
      cascade_trace: cascade.__cascade,
      comparison_layer_constants: { evaporative_clamp: EVAPORATIVE_CLAMP },
      representation_override: REPRESENTATION
    });
    emitFrame(ctx, state, 0);
  },
  onEventEnd(ctx) {
    const state = ctx.state && ctx.state.toothpaste;
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
    const state = ctx.state && ctx.state.toothpaste;
    if (!state) return;
    const coeff = state.coeff;
    const meanArr = state.arrheniusTimeS > 0 ?
      state.meanArrhenius / state.arrheniusTimeS : 1.0;
    const accelerationFactor = coeff.catalysedRatePerS * meanArr /
      Math.max(coeff.uncatalysedRatePerS, 1e-12);
    const trappedFraction = state.trappedGas /
      Math.max(1e-9, state.trappedGas + state.escapedGas);
    const lateWindow = state.frameDisplacementsMm.slice(-10);
    const lateMaxDisplacement = lateWindow.length ? Math.max.apply(null, lateWindow) : 0.0;
    const retention = state.peakFoamVolumes > 0 ?
      state.foamVolumes / state.peakFoamVolumes : 0.0;
    const peakFoamFactor = 1.0 + state.peakFoamVolumes;
    const seedKeys = state.cascade.__cascade.seedKeys || [];
    const g4Seeded =
      seedKeys.indexOf("material." + REACTING_MIX + ".density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material." + IODIDE_CATALYST + ".density_g_per_cm3") >= 0;
    const crownTopMm = foamShapeZ(1.0, POOL_VOLUME_MM3 * (1.0 + state.peakFoamVolumes)) -
      APPARATUS.cylinderHeightMm;

    ctx.emit("elephants_toothpaste_summary", {
      recipe: RECIPE,
      geant4: {
        peroxide_solution_density_g_per_cm3: state.peroxideDensity,
        catalyst_solution_density_g_per_cm3: state.catalystDensity,
        reacting_mix_density_g_per_cm3: state.mixDensity,
        water_density_g_per_cm3: state.waterDensity,
        catalyst_iodine_atoms_per_cm3: state.catalystIodinePerCm3,
        catalyst_potassium_atoms_per_cm3: state.catalystPotassiumPerCm3,
        clear_base_rgb: state.liquidBaseRgb,
        event_drive: { events: state.geant4Events, edep_mev: round4(state.geant4Edep),
                       steps: state.geant4Steps }
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures: state.structures
      },
      inferred_coefficients: coeff,
      cascade: state.cascade.__cascade,
      comparison_layer_constants: { evaporative_clamp: EVAPORATIVE_CLAMP },
      emergent: {
        frames: state.lastFrame + 1,
        catalytic_acceleration_factor: round4(accelerationFactor),
        completion_90pct_time_s: state.t90S === null ? null : round4(state.t90S),
        eruption_time_s: state.eruptTimeS === null ? null : round4(state.eruptTimeS),
        peak_foam_volume_factor: round4(peakFoamFactor),
        peak_foam_time_s: round4(state.peakFoamTimeS),
        final_foam_volume_factor: round4(1.0 + state.foamVolumes),
        foam_retention_vs_peak: round4(retention),
        crown_height_above_rim_mm: round4(crownTopMm),
        peak_temperature_k: round4(state.peakTemperatureK),
        peak_temperature_k_without_evaporative_clamp:
          round4(state.peakUnclampedTemperatureK),
        evaporative_cooling_removed_k: round4(state.evaporativeRemovedK),
        steaming_physics_steps: state.steamingSteps,
        peroxide_remaining_fraction: round4(state.peroxide),
        trapped_gas_fraction: round4(trappedFraction),
        peak_iodine_intermediate: round4(state.peakIodineIntermediate),
        peak_iodine_time_s: round4(state.peakIodineTimeS),
        late_window_max_displacement_mm: round4(lateMaxDisplacement),
        velocity_clamp_count: state.velocityClampCount,
        max_parcel_speed_mm_per_s: round4(state.maxParcelSpeedMmS)
      },
      validation_references_only: VALIDATION_ONLY,
      validation: {
        geant4_base_present: state.catalystDensity > state.peroxideDensity &&
          state.peroxideDensity > state.waterDensity &&
          state.catalystIodinePerCm3 > 0 && state.catalystPotassiumPerCm3 > 0 &&
          state.geant4Events === APPARATUS.outputTicks && state.geant4Edep > 0.0,
        cascade_supplies_coefficients: state.cascade.__cascade.stagesRun === 2 &&
          g4Seeded && coeff.catalysedRatePerS > 0 && coeff.o2FoamCapacity > 0,
        no_engine_reaction_rule: true,
        catalysis_accelerates_decomposition:
          accelerationFactor >= VALIDATION_ONLY.minimumCatalyticAcceleration,
        sudden_completion: state.t90S !== null &&
          state.t90S >= VALIDATION_ONLY.plausibleCompletionTimeS[0] &&
          state.t90S <= VALIDATION_ONLY.plausibleCompletionTimeS[1],
        eruption_emerged: state.eruptTimeS !== null && crownTopMm > 100.0,
        foam_expansion_plausible:
          peakFoamFactor >= VALIDATION_ONLY.plausibleFoamVolumeFactorRange[0] &&
          peakFoamFactor <= VALIDATION_ONLY.plausibleFoamVolumeFactorRange[1],
        // The lower bound and the steaming requirement are the emergent content:
        // the inferred exotherm must actually drive the mixture into the steaming
        // band. The upper bound is partly held by the LABELLED evaporative clamp,
        // so the unclamped peak and the kelvin the clamp removed are emitted
        // beside it rather than hidden.
        exothermic_steaming:
          state.peakTemperatureK >= VALIDATION_ONLY.plausiblePeakTemperatureK[0] &&
          state.peakTemperatureK <= VALIDATION_ONLY.plausiblePeakTemperatureK[1] &&
          state.steamingSteps > 0,
        evaporative_clamp_contribution_disclosed:
          state.evaporativeRemovedK >= 0.0 &&
          state.peakUnclampedTemperatureK >= state.peakTemperatureK,
        surfactant_traps_gas: state.trappedGas > 0.0 && state.escapedGas > 0.0 &&
          trappedFraction < 0.5,
        never_solidifies_then_drains: retention > 0.4 && retention < 0.999 &&
          lateMaxDisplacement > 0.05,
        iodine_intermediate_transient: state.peakIodineIntermediate > 0.0 &&
          state.t90S !== null && state.peakIodineTimeS < state.t90S &&
          state.iodineIntermediate < 0.5 * state.peakIodineIntermediate,
        pubchem_structure_consistent_with_geant4: structureConsistent(state.structures),
        velocity_cap_not_driving_motion: state.velocityClampCount === 0,
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 1600.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.initialTemperatureK,
    pressureAtm: 1.0
  },
  // A low-energy gamma transported through the actual reacting solution each tick:
  // it exercises Geant4 transport/scoring (the per-frame clock + event drive)
  // while the hook layer advances the inferred decomposition. It does not carry
  // the chemistry.
  beam: {
    particle: "gamma",
    energyMeV: 0.06,
    originMm: [0, 60.0, -60.0],
    direction: [0, 0, 1],
    spread: helpers.beamProfiles.spread("ledLamp", { energySpreadFractional: 0.04 })
  },
  run: { nEvents: APPARATUS.outputTicks, seed: 20260725, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: {
    enable: true,
    materials: [WATER, PEROXIDE_SOAP, IODIDE_CATALYST, REACTING_MIX]
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
    { name: "macro_eruption_response", scale: "macro",
      path: "data/elephants_toothpaste_cascade/macro_eruption_response.json" },
    { name: "nano_reagent_descriptors", scale: "nano",
      path: "data/elephants_toothpaste_cascade/nano_reagent_descriptors.json" }
  ],
  system: {
    enable: true, mode: "transient", frame: "observer",
    ensemble: "elephants_toothpaste",
    volumeMm3: POOL_VOLUME_MM3
  },
  materials: [peroxideSoapMaterial, iodideCatalystMaterial, reactingMixMaterial],
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 524288 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "cylinder_wall", material: GLASS,
        innerRadiusMm: APPARATUS.cylinderInnerRadiusMm,
        outerRadiusMm: APPARATUS.cylinderInnerRadiusMm + 2.5,
        lengthMm: APPARATUS.cylinderHeightMm,
        positionMm: [0, APPARATUS.cylinderHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["cylinder", "viz_shell"]
      }),
      geometry.tubeVolume({
        name: "spill_tray", material: GLASS,
        innerRadiusMm: 0.0, outerRadiusMm: 110.0, lengthMm: 6.0,
        positionMm: [0, -3.5, 0], rotationDeg: [90, 0, 0],
        tags: ["tray", "viz_solid", "viz_color=#20242c"]
      }),
      // The freshly combined reacting solution: the beam medium + optics/
      // composition base. Hidden in viz -- the parcels represent the material.
      geometry.tubeVolume({
        name: "reacting_pool", material: REACTING_MIX,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.cylinderInnerRadiusMm,
        lengthMm: APPARATUS.initialLiquidHeightMm,
        positionMm: [0, APPARATUS.initialLiquidHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["viz_hidden"]
      }),
      // Hidden probe volumes make each prepared solution part of the constructed
      // Geant4 geometry (composition/optics panel).
      geometry.boxVolume({ name: "peroxide_probe", material: PEROXIDE_SOAP,
        sizeMm: [4, 4, 4], positionMm: [-200, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "catalyst_probe", material: IODIDE_CATALYST,
        sizeMm: [4, 4, 4], positionMm: [200, 0, 0], tags: ["viz_hidden"] })
    ]
  }
};
