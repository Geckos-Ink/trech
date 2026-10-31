// Water + n-pentane poured into an open beaker at 30 C, observed for 60 minutes.
//
// Runtime information discipline:
//   * Geant4 is the physical base: G4_WATER / G4_N-PENTANE supply composition,
//     density, electron/atom densities, and the cross sections from which TRECH
//     derives visible colour/optics. No liquid density, colour, vapour pressure,
//     layer order, or evaporation fraction is typed into the runtime path.
//   * PubChem is structure retrieval ONLY: CID + SMILES. The scenario does not
//     read XLogP, molecular weight, boiling point, density, colour, or vapour
//     pressure from PubChem.
//   * ctx.cascade lifts the Geant4 facts + structural atom counts through a
//     held-out n-alkane volatility regression and an observer-band beaker model.
//     The cascade predicts phase separation/layer order and the evaporated
//     fraction for the declared beaker/temperature/duration context.
//   * Physical/chemical reference properties appear only in VALIDATION_ONLY at
//     run end. They grade the prediction gap and cannot feed the state/frames.
//
// Studio receives `material_frame` emits. Positions, material-resolved RGBA,
// layer layout, and vapour count are scenario outputs; Studio does no chemistry.
// The emitted sequence is deliberately observer-readable: water pour, pentane
// pour, transient intermingling/phase separation, then a temperature-aware
// 60-minute evaporation interval mapped onto an explicitly accelerated playback
// clock. Vapour tracers rise, drift, fade, and leave the observed air volume;
// no precomputed fixed vapour targets are revealed over time.
// Default colour is the Geant4-derived neutral transmission colour. To make the
// two colourless phases easier to teach with, a wrapper scenario may set ONLY
// representation overrides before including this file:
//
//   globalThis.TRECH_BEAKER_VIZ_OVERRIDE = {
//     waterTint: [0.78, 0.9, 1.0], pentaneTint: [1.0, 0.86, 0.55],
//     layerGapMm: 3, vaporExaggeration: 2, layout: "pentane_above"
//   };
//   TRECH_INCLUDE("beaker_water_n_pentane.js");
//
// Those values are emitted as authored viz overrides and never alter phase or
// evaporation predictions.
//
// Prepare structure cache + run:
//   PYTHONPATH=tools/pubchem python -m trech_pubchem fetch --cache-dir build/pubchem_cache \
//     --no-png water n-pentane
//   TRECH_PUBCHEM_CACHE_DIR=build/pubchem_cache build/dev/trech run \
//     examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js \
//     --output build/dev/out_beaker_water_n_pentane

TRECH_INCLUDE("../../../js/trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

const WATER = "G4_WATER";
const PENTANE = "G4_N-PENTANE";
const AIR = "G4_AIR";
const GLASS = "G4_GLASS_PLATE";

const APPARATUS = {
  temperatureK: 303.15,
  durationMin: 60,
  beakerInnerRadiusMm: 25.0,
  beakerHeightMm: 105.0,
  waterVolumeMl: 100.0,
  pentaneVolumeMl: 50.0,
  // Geometry/ambient conditions, not substance properties. They are explicit
  // context features consumed by the general macro response surface.
  stillAirBoundaryLayerMm: 20.0
};
const AREA_MM2 = Math.PI * APPARATUS.beakerInnerRadiusMm * APPARATUS.beakerInnerRadiusMm;
const WATER_HEIGHT_MM = APPARATUS.waterVolumeMl * 1000.0 / AREA_MM2;
const PENTANE_HEIGHT_MM = APPARATUS.pentaneVolumeMl * 1000.0 / AREA_MM2;

// Sixty Geant4 events remain the observer clock drive. Their 60 emitted frames
// are allocated across a visible pour/mix prelude and the accelerated 60-minute
// evaporation interval. Both clocks are emitted; Studio never has to guess the
// acceleration or invent intermediate positions.
const TIMELINE = {
  finalFrame: 60,
  waterPourEnd: 8,
  pentanePourEnd: 16,
  separationEnd: 27,
  separationPlaybackEndS: 5.4,
  playbackEndS: 12.0
};
const particleCountFactor = TRECH_PARAMETER("particle_count_factor");
const OBSERVER_PRECISION = helpers.precision.resolve({
  note:"Observer representative count only; unchanged Geant4 events, inventories and learned endpoint",
  axes:[{name:"observer_particles", role:"representation", control:"particle_count_factor", unit:"representatives",
    balanced:440, min:110, max:1760, integer:true,
    override:particleCountFactor === 1 ? 0 : 440*particleCountFactor}]
});
const OBSERVER_PARTICLE_FACTOR = OBSERVER_PRECISION.value("observer_particles") / 440;
OBSERVER_PRECISION.axis("observer_particles").value = Math.round(260*OBSERVER_PARTICLE_FACTOR) + Math.round(180*OBSERVER_PARTICLE_FACTOR);

const VIZ_INPUT = TRECH_VIEWS["beaker_water_n_pentane"]["VIZ_INPUT0"]();
const VIZ_LAYOUTS = TRECH_VIEWS["beaker_water_n_pentane"]["VIZ_LAYOUTS1"]();
const requestedLayout = TRECH_VIEWS["beaker_water_n_pentane"]["requestedLayout2"](VIZ_INPUT);
if (VIZ_LAYOUTS.indexOf(requestedLayout) < 0) {
  throw new Error("TRECH_BEAKER_VIZ_OVERRIDE.layout must be one of: " + VIZ_LAYOUTS.join(", "));
}
function optionalTint(value) {
  return TRECH_VIEWS["beaker_water_n_pentane"]["optionalTint"](value);
}
const VIZ = TRECH_VIEWS["beaker_water_n_pentane"]["VIZ3"](VIZ_INPUT, optionalTint, requestedLayout);

function loadStructure(name) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM unavailable; fetch the build-local structure cache first");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || raw.cid === undefined || typeof raw.smiles !== "string") {
    throw new Error("PubChem structure cache for " + name + " must contain cid + smiles");
  }
  // Deliberately return no physical/chemical property fields.
  return { name, cid: Number(raw.cid), smiles: raw.smiles };
}

function atomCountsFromSmiles(smiles) {
  const counts = {};
  for (let i = 0; i < smiles.length; i += 1) {
    const c = smiles[i];
    if (c < "A" || c > "Z") continue;
    let symbol = c;
    if (i + 1 < smiles.length && smiles[i + 1] >= "a" && smiles[i + 1] <= "z") {
      symbol += smiles[i + 1];
      i += 1;
    }
    counts[symbol] = (counts[symbol] || 0) + 1;
  }
  let hetero = 0;
  Object.keys(counts).forEach((symbol) => {
    if (symbol !== "C" && symbol !== "H") hetero += counts[symbol];
  });
  return { carbon: counts.C || 0, hetero, atoms: counts };
}

const STRUCTURES = {
  water: loadStructure("water"),
  nPentane: loadStructure("n-pentane")
};
STRUCTURES.water.counts = atomCountsFromSmiles(STRUCTURES.water.smiles);
STRUCTURES.nPentane.counts = atomCountsFromSmiles(STRUCTURES.nPentane.smiles);

const { clamp01, smoothstep, mix3: lerpPoint } = helpers.math;
function tint(rgb, override) {
  return TRECH_VIEWS["beaker_water_n_pentane"]["tint"](rgb, override);
}

const opticsFor = (ctx, name) => helpers.materialFacts.optics(ctx, name, true);

function fract(v) { return v - Math.floor(v); }

function makeMaterialParticles(rng, count, z0, z1, mixedZ0, mixedZ1, radius) {
  const particles = [];
  for (let i = 0; i < count; i += 1) {
    const angle = 2.0 * Math.PI * rng.uniform();
    const radial = Math.sqrt(rng.uniform()) * radius;
    const mixedAngle = angle + (rng.uniform() - 0.5) * 1.8;
    const mixedRadial = Math.sqrt(rng.uniform()) * radius;
    const zNorm = rng.uniform();
    particles.push({
      final: [radial * Math.cos(angle), radial * Math.sin(angle), z0 + (z1 - z0) * zNorm],
      mixed: [mixedRadial * Math.cos(mixedAngle), mixedRadial * Math.sin(mixedAngle),
              mixedZ0 + (mixedZ1 - mixedZ0) * rng.uniform()],
      zNorm,
      arrival: (i + 0.35 * rng.uniform()) / count,
      phase: 2.0 * Math.PI * rng.uniform()
    });
  }
  return particles;
}

function makePlumeSeeds(rng, count, radius) {
  const seeds = [];
  for (let i = 0; i < count; i += 1) {
    const angle = 2.0 * Math.PI * rng.uniform();
    const radial = Math.sqrt(rng.uniform()) * radius;
    seeds.push({
      x: radial * Math.cos(angle), y: radial * Math.sin(angle),
      age0: rng.uniform(), phase: 2.0 * Math.PI * rng.uniform(),
      drift: 0.65 + 0.7 * rng.uniform()
    });
  }
  return seeds;
}

function agitatedPoint(particle, from, to, blend, frame, amplitude) {
  const p = lerpPoint(from, to, smoothstep(blend));
  const angle = 0.19 * frame + particle.phase;
  const decay = Math.max(0.0, amplitude);
  return [
    p[0] + decay * Math.cos(angle),
    p[1] + decay * Math.sin(angle),
    p[2] + 0.35 * decay * Math.sin(1.7 * angle)
  ];
}

function pouredPoint(particle, progress, nozzle, target, frame) {
  // Stagger every representative packet so the emitted points form a falling
  // stream, then join the moving liquid instead of teleporting into the beaker.
  const local = (progress - 0.78 * particle.arrival) / 0.22;
  if (local <= 0.0) return null;
  if (local < 0.72) {
    const q = smoothstep(local / 0.72);
    const point = lerpPoint(nozzle, target, q);
    const arc = Math.sin(Math.PI * q);
    point[0] += 5.0 * arc * Math.cos(particle.phase);
    point[1] += 5.0 * arc * Math.sin(particle.phase);
    point[2] += 7.0 * arc;
    return point;
  }
  const settle = smoothstep((local - 0.72) / 0.28);
  return agitatedPoint(particle, target, target, 1.0, frame, 4.0 * (1.0 - settle));
}

function frameClock(frameIndex) {
  if (frameIndex <= TIMELINE.separationEnd) {
    const playback = frameIndex / TIMELINE.separationEnd * TIMELINE.separationPlaybackEndS;
    return {
      playbackTimeS: playback,
      physicalTimeS: playback,
      minute: 0.0,
      evaporationProgress: 0.0,
      timeScale: 1.0
    };
  }
  const progress = (frameIndex - TIMELINE.separationEnd) /
    (TIMELINE.finalFrame - TIMELINE.separationEnd);
  const playbackSpan = TIMELINE.playbackEndS - TIMELINE.separationPlaybackEndS;
  const physicalSpan = APPARATUS.durationMin * 60.0;
  return {
    playbackTimeS: TIMELINE.separationPlaybackEndS + progress * playbackSpan,
    physicalTimeS: TIMELINE.separationPlaybackEndS + progress * physicalSpan,
    minute: progress * APPARATUS.durationMin,
    evaporationProgress: progress,
    timeScale: physicalSpan / playbackSpan
  };
}

function initState(ctx) {
  const waterProbe = ctx.materials && ctx.materials[WATER];
  const pentaneProbe = ctx.materials && ctx.materials[PENTANE];
  if (!waterProbe || !pentaneProbe) throw new Error("Geant4 material probes missing liquids");

  const seed = {};
  seed["structure.water.hetero_atom_count"] = STRUCTURES.water.counts.hetero;
  seed["structure.n_pentane.hetero_atom_count"] = STRUCTURES.nPentane.counts.hetero;
  seed["structure.n_pentane.carbon_count"] = STRUCTURES.nPentane.counts.carbon;
  seed["context.temperature_k"] = APPARATUS.temperatureK;
  seed["context.surface_to_volume_per_mm"] = AREA_MM2 /
    (APPARATUS.pentaneVolumeMl * 1000.0);
  seed["context.duration_min"] = APPARATUS.durationMin;
  seed["context.still_air_boundary_layer_mm"] = APPARATUS.stillAirBoundaryLayerMm;
  const cascade = ctx.cascade(seed);
  if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
    throw new Error("beaker cascade requires predictive mode and two loaded stages");
  }

  const waterOptics = opticsFor(ctx, WATER);
  const pentaneOptics = opticsFor(ctx, PENTANE);
  const fraction60 = clamp01(cascade.macro_evaporation_fraction);
  const sigma = Math.max(0.0, Number(cascade.macro_evaporation_fraction_sigma));
  const phaseSeparated = Number(cascade.macro_phase_separation_score) >= 0.5;
  const pentaneOnTop = Number(cascade.macro_pentane_upper_score) >= 0.5;
  const densityPentane = Number(pentaneProbe.density_g_per_cm3);
  const initialPentaneMassG = densityPentane * APPARATUS.pentaneVolumeMl;

  const presentation = TRECH_VIEWS.beaker_water_n_pentane.initializeLayout(APPARATUS, PENTANE_HEIGHT_MM, VIZ, WATER_HEIGHT_MM, ctx, makeMaterialParticles, makePlumeSeeds, pentaneOnTop, phaseSeparated, OBSERVER_PARTICLE_FACTOR);

  ctx.state.beaker = {
    cascade, waterProbe, pentaneProbe, waterOptics, pentaneOptics,
    fraction60, sigma, phaseSeparated, pentaneOnTop, initialPentaneMassG,
    ...presentation,
    lastMinute: 0, lastFraction: 0.0, lastFrame: 0,
    phaseFrames: { empty: 0, water_pour: 0, pentane_pour: 0,
                   intermix_and_separate: 0, accelerated_evaporation: 0 },
    lastPhaseOrdinal: -1, phaseOrderValid: true,
    priorVaporPositions: [], maxVaporMotionMm: 0.0,
    geant4Events: 0, geant4Steps: 0, geant4TrackLengthMm: 0.0
  };
  return ctx.state.beaker;
}

function rgba(rgb, alpha) { return [rgb[0], rgb[1], rgb[2], alpha]; }

function emitFrame(ctx, state, frameIndex) {
  return TRECH_VIEWS["beaker_water_n_pentane"]["emitFrame"](ctx, state, frameIndex, APPARATUS, TIMELINE, TRECH_VIEWS, VIZ, agitatedPoint, fract, frameClock, pouredPoint, rgba, smoothstep, tint);
}

// References are deliberately defined after every runtime model/helper. Only
// onRunEnd reads them, and only to grade deltas/flags.
const VALIDATION_ONLY = TRECH_CHECKS["beaker_water_n_pentane"]["references0"]();

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const state = initState(ctx);
    ctx.emit("beaker_scenario", {
      name: "water_n_pentane_open_beaker",
      apparatus: APPARATUS,
      pubchem_structure_only: {
        water: STRUCTURES.water,
        n_pentane: STRUCTURES.nPentane
      },
      geant4_materials: [WATER, PENTANE, AIR, GLASS],
      cascade_trace: state.cascade.__cascade,
      representation_override: VIZ,
      precision: OBSERVER_PRECISION.config
    });
    emitFrame(ctx, state, 0);
  },
  onEventEnd(ctx) {
    const state = ctx.state && ctx.state.beaker;
    if (!state) return;
    state.geant4Events += 1;
    state.geant4Steps += Number(ctx.event.totalStepCount || 0);
    state.geant4TrackLengthMm += Number(ctx.event.totalTrackLengthMm || 0.0);
    emitFrame(ctx, state, Math.min(TIMELINE.finalFrame, ctx.event.id + 1));
  },
  onRunEnd(ctx) {
    const state = ctx.state && ctx.state.beaker;
    if (!state) return;
    const predictedVp = Math.exp(Number(state.cascade.micro_log_vapour_pressure_kpa));
    const densityPentane = Number(state.pentaneProbe.density_g_per_cm3);
    const densityWater = Number(state.waterProbe.density_g_per_cm3);
    const evaporatedMassG = state.initialPentaneMassG * state.fraction60;
    const remainingMassG = state.initialPentaneMassG - evaporatedMassG;
    const vpRelGap = Math.abs(predictedVp - VALIDATION_ONLY.pentaneVapourPressureKpaAt303K) /
      VALIDATION_ONLY.pentaneVapourPressureKpaAt303K;
    const densityRelGap = Math.abs(densityPentane - VALIDATION_ONLY.pentaneDensityGPerCm3) /
      VALIDATION_ONLY.pentaneDensityGPerCm3;
    const waterChroma = Math.max.apply(null, state.waterOptics.rgb) -
      Math.min.apply(null, state.waterOptics.rgb);
    const pentaneChroma = Math.max.apply(null, state.pentaneOptics.rgb) -
      Math.min.apply(null, state.pentaneOptics.rgb);
    ctx.emit("beaker_summary", {
      minutes: state.lastMinute,
      pubchem_usage: "CID + SMILES structure only; no PubChem physical property read",
      structure: {
        water: STRUCTURES.water,
        n_pentane: STRUCTURES.nPentane
      },
      geant4: {
        water_density_g_per_cm3: densityWater,
        pentane_density_g_per_cm3: densityPentane,
        event_drive: { events: state.geant4Events, steps: state.geant4Steps,
                       track_length_mm: state.geant4TrackLengthMm }
      },
      colour: {
        source: "Geant4 cross sections -> TRECH MolecularOptics -> display_rgb",
        water_rgb: state.waterOptics.rgb,
        n_pentane_rgb: state.pentaneOptics.rgb,
        water_refractive_index: state.waterOptics.refractiveIndex,
        n_pentane_refractive_index: state.pentaneOptics.refractiveIndex,
        authored_tints: { water: VIZ.waterTint, n_pentane: VIZ.pentaneTint }
      },
      disposition: {
        phase_separation_score: state.cascade.macro_phase_separation_score,
        pentane_upper_score: state.cascade.macro_pentane_upper_score,
        phase_separated: state.phaseSeparated,
        n_pentane_on_top: state.pentaneOnTop,
        density_delta_g_per_cm3: state.cascade.micro_density_delta_g_per_cm3,
        rendered_layer_order: state.renderedLayerOrder,
        rendered_layout_source: VIZ.layout === "inferred" ? "cascade" : "authored viz override"
      },
      evaporation: {
        temperature_k: APPARATUS.temperatureK,
        duration_min: APPARATUS.durationMin,
        predicted_vapour_pressure_kpa: predictedVp,
        predicted_air_diffusivity_um2_per_s: state.cascade.micro_air_diffusivity_um2_per_s,
        fraction_evaporated: state.fraction60,
        fraction_sigma: state.sigma,
        initial_mass_g: state.initialPentaneMassG,
        evaporated_mass_g: evaporatedMassG,
        remaining_mass_g: remainingMassG,
        evaporated_volume_equivalent_ml: evaporatedMassG / densityPentane
      },
      observer_dynamics: {
        phase_order: ["empty_beaker", "water_pour", "pentane_pour_into_water",
                      "intermix_then_phase_separate", "accelerated_30c_evaporation"],
        phase_frames: state.phaseFrames,
        playback_duration_s: TIMELINE.playbackEndS,
        physical_evaporation_duration_s: APPARATUS.durationMin * 60.0,
        evaporation_time_acceleration: (APPARATUS.durationMin * 60.0) /
          (TIMELINE.playbackEndS - TIMELINE.separationPlaybackEndS),
        max_mean_vapour_tracer_motion_mm_per_frame: state.maxVaporMotionMm,
        plume_policy: "continually renewed rising/drifting/fading tracers; no fixed targets"
      },
      cascade: state.cascade.__cascade,
      validation_references_only: VALIDATION_ONLY,
      validation_gaps: {
        pentane_density_relative: densityRelGap,
        pentane_vapour_pressure_relative: vpRelGap
      },
      validation: TRECH_CHECKS["beaker_water_n_pentane"]["checks0"](STRUCTURES, TIMELINE, densityPentane, densityWater, evaporatedMassG, frameClock, pentaneChroma, remainingMassG, state, vpRelGap, waterChroma)
    });
  }
};

globalThis.TRECH_CONFIG = {
  precision: OBSERVER_PRECISION.config,
  detector: {
    worldSizeMm: 300.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.temperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 1, 0] },
  run: { nEvents: 60, seed: 20260715, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: { enable: true, materials: [WATER, PENTANE, AIR, GLASS] },
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
      writeSpectrum: true,
      validate: TRECH_CHECKS["beaker_water_n_pentane"]["opticsReferences1"](PENTANE, WATER)
    }
  },
  models: [
    { name: "macro_beaker_behavior", scale: "macro",
      path: "data/beaker_cascade/macro_beaker_behavior.json" },
    { name: "nano_pair_descriptors", scale: "nano",
      path: "data/beaker_cascade/nano_pair_descriptors.json" }
  ],
  system: { enable: true, mode: "transient", frame: "observer",
            ensemble: "water_n_pentane_open_beaker" },
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 524288 },
  viz: TRECH_VIEWS["beaker_water_n_pentane"]["viz1"](),
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "beaker_wall", material: GLASS,
        innerRadiusMm: APPARATUS.beakerInnerRadiusMm,
        outerRadiusMm: APPARATUS.beakerInnerRadiusMm + 2.0,
        lengthMm: APPARATUS.beakerHeightMm,
        positionMm: [0, APPARATUS.beakerHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["beaker_water_n_pentane"]["tags2"]()
      }),
      geometry.tubeVolume({
        name: "beaker_base", material: GLASS,
        innerRadiusMm: 0.0,
        outerRadiusMm: APPARATUS.beakerInnerRadiusMm + 2.0,
        lengthMm: 3.0,
        positionMm: [0, 1.5, 0], rotationDeg: [90, 0, 0],
        tags: TRECH_VIEWS["beaker_water_n_pentane"]["tags3"]()
      }),
      // Hidden probe volumes make both NIST liquids part of the constructed
      // Geant4 geometry/optics panel. Studio draws only emitted dynamic phases.
      geometry.boxVolume({ name: "water_probe", material: WATER,
        sizeMm: [5, 5, 5], positionMm: [-100, 0, 0], tags: TRECH_VIEWS["beaker_water_n_pentane"]["tags4"]() }),
      geometry.boxVolume({ name: "pentane_probe", material: PENTANE,
        sizeMm: [5, 5, 5], positionMm: [100, 0, 0], tags: TRECH_VIEWS["beaker_water_n_pentane"]["tags5"]() })
    ]
  }
};
