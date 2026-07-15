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
//     examples/experiments/beaker_water_n_pentane.js \
//     --output build/dev/out_beaker_water_n_pentane

TRECH_INCLUDE("trech_helpers.js");
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

const VIZ_INPUT = globalThis.TRECH_BEAKER_VIZ_OVERRIDE || {};
const VIZ_LAYOUTS = ["inferred", "water_above", "pentane_above", "mixed"];
const requestedLayout = String(VIZ_INPUT.layout || "inferred");
if (VIZ_LAYOUTS.indexOf(requestedLayout) < 0) {
  throw new Error("TRECH_BEAKER_VIZ_OVERRIDE.layout must be one of: " + VIZ_LAYOUTS.join(", "));
}
function optionalTint(value) {
  return Array.isArray(value) && value.length >= 3 ?
    [Number(value[0]), Number(value[1]), Number(value[2])] : null;
}
const VIZ = {
  waterTint: optionalTint(VIZ_INPUT.waterTint),
  pentaneTint: optionalTint(VIZ_INPUT.pentaneTint),
  layerGapMm: Number(VIZ_INPUT.layerGapMm || 0.0),
  vaporExaggeration: Math.max(0.25, Number(VIZ_INPUT.vaporExaggeration || 1.0)),
  layout: requestedLayout,
  waterAlpha: Math.max(0.02, Math.min(1.0, Number(VIZ_INPUT.waterAlpha || 0.28))),
  pentaneAlpha: Math.max(0.02, Math.min(1.0, Number(VIZ_INPUT.pentaneAlpha || 0.25))),
  vaporAlpha: Math.max(0.01, Math.min(1.0, Number(VIZ_INPUT.vaporAlpha || 0.08)))
};

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

function clamp01(v) { return Math.max(0.0, Math.min(1.0, Number(v))); }
function tint(rgb, override) {
  if (!override) return rgb.slice(0, 3);
  return [rgb[0] * override[0], rgb[1] * override[1], rgb[2] * override[2]];
}

function opticsFor(ctx, name) {
  const item = ctx.optics && ctx.optics[name];
  if (!item || !Array.isArray(item.display_rgb)) {
    throw new Error("ctx.optics missing Geant4-derived colour for " + name);
  }
  return {
    rgb: item.display_rgb.slice(0, 3).map(clamp01),
    refractiveIndex: Number(item.mean_refractive_index),
    absorptionLengthMm: Number(item.mean_absorption_length_mm),
    scatterLengthMm: Number(item.mean_scatter_length_mm),
    note: item.note
  };
}

function smoothstep(v) {
  const x = clamp01(v);
  return x * x * (3.0 - 2.0 * x);
}
function lerp(a, b, t) { return a + (b - a) * t; }
function lerpPoint(a, b, t) {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
}
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

  // Inferred disposition drives the default frame. A representation override
  // can make another arrangement legible without feeding it back into physics.
  let renderSeparated = phaseSeparated;
  let renderPentaneOnTop = pentaneOnTop;
  if (VIZ.layout === "mixed") renderSeparated = false;
  if (VIZ.layout === "pentane_above") {
    renderSeparated = true;
    renderPentaneOnTop = true;
  }
  if (VIZ.layout === "water_above") {
    renderSeparated = true;
    renderPentaneOnTop = false;
  }

  const baseZ = 3.0;
  const totalHeight = WATER_HEIGHT_MM + PENTANE_HEIGHT_MM;
  let waterZ0 = baseZ;
  let waterZ1 = baseZ + totalHeight;
  let pentaneZ0 = baseZ;
  let pentaneZ1 = baseZ + totalHeight;
  let renderedLayerOrder = "mixed";
  if (renderSeparated && renderPentaneOnTop) {
    waterZ1 = baseZ + WATER_HEIGHT_MM;
    pentaneZ0 = waterZ1 + VIZ.layerGapMm;
    pentaneZ1 = pentaneZ0 + PENTANE_HEIGHT_MM;
    renderedLayerOrder = "water_below_n_pentane";
  } else if (renderSeparated) {
    pentaneZ1 = baseZ + PENTANE_HEIGHT_MM;
    waterZ0 = pentaneZ1 + VIZ.layerGapMm;
    waterZ1 = waterZ0 + WATER_HEIGHT_MM;
    renderedLayerOrder = "n_pentane_below_water";
  }
  const radius = APPARATUS.beakerInnerRadiusMm - 2.0;
  const waterParticles = makeMaterialParticles(
    ctx.rng, 260, waterZ0, waterZ1, baseZ, baseZ + totalHeight, radius
  );
  const pentaneParticles = makeMaterialParticles(
    ctx.rng, 180, pentaneZ0, pentaneZ1, baseZ, baseZ + totalHeight, radius
  );
  // Removing the highest representatives as evaporation progresses makes the
  // emitted liquid level recede at constant representative density.
  pentaneParticles.sort((a, b) => a.final[2] - b.final[2]);
  const renderedLiquidTop = Math.max(waterZ1, pentaneZ1);
  const plumeSeeds = makePlumeSeeds(
    ctx.rng, Math.ceil(pentaneParticles.length * VIZ.vaporExaggeration) + 12,
    APPARATUS.beakerInnerRadiusMm * 0.9
  );

  ctx.state.beaker = {
    cascade, waterProbe, pentaneProbe, waterOptics, pentaneOptics,
    fraction60, sigma, phaseSeparated, pentaneOnTop, initialPentaneMassG,
    renderedLayerOrder,
    waterParticles, pentaneParticles, plumeSeeds, renderedLiquidTop,
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
  const clock = frameClock(frameIndex);
  // The cascade predicts the 60-minute endpoint. This exponential schedule
  // distributes that endpoint over physical observer time without changing it.
  const progress = clock.evaporationProgress;
  const fraction = state.fraction60 >= 1.0 ? progress :
    1.0 - Math.pow(1.0 - state.fraction60, progress);
  const vaporPhysical = Math.round(state.pentaneParticles.length * fraction);
  const vaporShown = Math.min(state.plumeSeeds.length,
    Math.round(vaporPhysical * VIZ.vaporExaggeration));
  const liquidCount = Math.max(0, state.pentaneParticles.length - vaporPhysical);
  const waterRgb = tint(state.waterOptics.rgb, VIZ.waterTint);
  const pentaneRgb = tint(state.pentaneOptics.rgb, VIZ.pentaneTint);
  const positions = [];
  const colors = [];
  const vaporPositions = [];
  let phase = "empty_beaker";

  function push(point, color) {
    if (!point) return;
    positions.push(point);
    colors.push(color);
  }

  if (frameIndex === 0) {
    phase = "empty_beaker";
  } else if (frameIndex <= TIMELINE.waterPourEnd) {
    phase = "water_pour";
    const p = frameIndex / TIMELINE.waterPourEnd;
    for (let i = 0; i < state.waterParticles.length; i += 1) {
      push(pouredPoint(state.waterParticles[i], p, [-34.0, 3.0, 146.0],
                       state.waterParticles[i].final, frameIndex),
           rgba(waterRgb, VIZ.waterAlpha));
    }
  } else if (frameIndex <= TIMELINE.pentanePourEnd) {
    phase = "pentane_pour_into_water";
    const p = (frameIndex - TIMELINE.waterPourEnd) /
      (TIMELINE.pentanePourEnd - TIMELINE.waterPourEnd);
    for (let i = 0; i < state.waterParticles.length; i += 1) {
      push(agitatedPoint(state.waterParticles[i], state.waterParticles[i].final,
                         state.waterParticles[i].mixed, p, frameIndex, 3.5 * p),
           rgba(waterRgb, VIZ.waterAlpha));
    }
    for (let i = 0; i < state.pentaneParticles.length; i += 1) {
      push(pouredPoint(state.pentaneParticles[i], p, [34.0, -2.0, 142.0],
                       state.pentaneParticles[i].mixed, frameIndex),
           rgba(pentaneRgb, VIZ.pentaneAlpha));
    }
  } else if (frameIndex <= TIMELINE.separationEnd) {
    phase = "intermix_then_phase_separate";
    const p = (frameIndex - TIMELINE.pentanePourEnd) /
      (TIMELINE.separationEnd - TIMELINE.pentanePourEnd);
    const separated = smoothstep((p - 0.18) / 0.82);
    const agitation = 5.0 * (1.0 - separated);
    for (let i = 0; i < state.waterParticles.length; i += 1) {
      push(agitatedPoint(state.waterParticles[i], state.waterParticles[i].mixed,
                         state.waterParticles[i].final, separated, frameIndex, agitation),
           rgba(waterRgb, VIZ.waterAlpha));
    }
    for (let i = 0; i < state.pentaneParticles.length; i += 1) {
      push(agitatedPoint(state.pentaneParticles[i], state.pentaneParticles[i].mixed,
                         state.pentaneParticles[i].final, separated, frameIndex, agitation),
           rgba(pentaneRgb, VIZ.pentaneAlpha));
    }
  } else {
    phase = "accelerated_30c_evaporation";
    for (let i = 0; i < state.waterParticles.length; i += 1) {
      push(agitatedPoint(state.waterParticles[i], state.waterParticles[i].final,
                         state.waterParticles[i].final, 1.0, frameIndex, 0.35),
           rgba(waterRgb, VIZ.waterAlpha));
    }
    for (let i = 0; i < liquidCount; i += 1) {
      push(agitatedPoint(state.pentaneParticles[i], state.pentaneParticles[i].final,
                         state.pentaneParticles[i].final, 1.0, frameIndex, 0.55),
           rgba(pentaneRgb, VIZ.pentaneAlpha));
    }
    const evapFrame = frameIndex - TIMELINE.separationEnd;
    const plumeBottom = state.pentaneParticles[Math.max(0, liquidCount - 1)];
    const liquidTop = plumeBottom ? plumeBottom.final[2] : state.renderedLiquidTop;
    for (let i = 0; i < vaporShown; i += 1) {
      const seed = state.plumeSeeds[i];
      // A continually renewed tracer plume: each representative rises, drifts,
      // fades, leaves the observer volume, and is replaced at the interface.
      const age = fract(seed.age0 + evapFrame * 0.19 * seed.drift);
      const lift = age * (APPARATUS.beakerHeightMm + 62.0 - liquidTop);
      const spread = 4.0 + 24.0 * age;
      const point = [
        seed.x + spread * Math.sin(seed.phase + 0.31 * evapFrame + 1.3 * age),
        seed.y + 0.45 * spread * Math.cos(seed.phase * 0.7 + 0.23 * evapFrame),
        liquidTop + 3.0 + lift
      ];
      vaporPositions.push(point);
      push(point, rgba(pentaneRgb, VIZ.vaporAlpha * Math.pow(1.0 - age, 0.65)));
    }
  }

  if (state.priorVaporPositions.length > 0 && vaporPositions.length > 0) {
    const shared = Math.min(state.priorVaporPositions.length, vaporPositions.length);
    let sumMotion = 0.0;
    for (let i = 0; i < shared; i += 1) {
      const a = state.priorVaporPositions[i];
      const b = vaporPositions[i];
      const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      sumMotion += Math.sqrt(dx * dx + dy * dy + dz * dz);
    }
    state.maxVaporMotionMm = Math.max(state.maxVaporMotionMm, sumMotion / shared);
  }
  state.priorVaporPositions = vaporPositions;
  const phaseKey = phase === "empty_beaker" ? "empty" :
    (phase === "water_pour" ? "water_pour" :
      (phase === "pentane_pour_into_water" ? "pentane_pour" :
        (phase === "intermix_then_phase_separate" ? "intermix_and_separate" :
          "accelerated_evaporation")));
  const phaseOrdinal = phaseKey === "empty" ? 0 : (phaseKey === "water_pour" ? 1 :
    (phaseKey === "pentane_pour" ? 2 : (phaseKey === "intermix_and_separate" ? 3 : 4)));
  if (phaseOrdinal < state.lastPhaseOrdinal) state.phaseOrderValid = false;
  state.lastPhaseOrdinal = phaseOrdinal;
  state.phaseFrames[phaseKey] += 1;
  state.lastFrame = frameIndex;
  state.lastMinute = clock.minute;
  state.lastFraction = fraction;
  ctx.emit("material_frame", {
    time_s: clock.physicalTimeS,
    physical_time_s: clock.physicalTimeS,
    playback_time_s: clock.playbackTimeS,
    time_scale: clock.timeScale,
    minute: clock.minute,
    phase,
    positions_mm: positions,
    colors_rgba: colors,
    counts: { water_inventory_representatives: state.waterParticles.length,
              pentane_liquid_inventory_representatives: liquidCount,
              visible_particles: positions.length,
              pentane_vapor_cumulative_physical: vaporPhysical,
              pentane_vapor_tracers_shown: vaporShown },
    rendered_layer_order: state.renderedLayerOrder,
    clock: {
      source: "scenario-emitted observer clocks",
      evaporation_time_acceleration: clock.timeScale,
      physical_time_retained: true
    },
    motion_scope: "illustrative hook-layer pour/mixing/plume kinematics; cascade drives disposition and evaporation endpoint",
    representation_override: VIZ
  });
}

// References are deliberately defined after every runtime model/helper. Only
// onRunEnd reads them, and only to grade deltas/flags.
const VALIDATION_ONLY = {
  pentaneDensityGPerCm3: 0.626,
  pentaneVapourPressureKpaAt303K: 81.9789,
  pentaneVapourPressureSource:
    "NIST Chemistry WebBook SRD 69 Antoine parameters; validation only",
  expectedAppearance: "colourless",
  expectedDisposition: "immiscible n-pentane upper layer"
};

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
      representation_override: VIZ
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
      validation: {
        geant4_base_present: densityWater > densityPentane && state.geant4Events === 60 &&
          state.geant4Steps > 0,
        pubchem_structure_only: STRUCTURES.water.smiles.length > 0 &&
          STRUCTURES.nPentane.smiles.length > 0,
        colour_from_geant4: waterChroma < 0.12 && pentaneChroma < 0.12,
        immiscible_layers_inferred: state.phaseSeparated && state.pentaneOnTop,
        volatility_holdout_close: vpRelGap < 0.15,
        evaporation_mass_conserved: Math.abs(state.initialPentaneMassG -
          evaporatedMassG - remainingMassG) < 1e-9,
        sixty_minutes_reached: state.lastMinute === 60,
        pour_mix_evaporate_sequence: state.phaseOrderValid && state.lastPhaseOrdinal === 4 &&
          state.phaseFrames.empty === 1 && state.phaseFrames.water_pour > 0 &&
          state.phaseFrames.pentane_pour > 0 && state.phaseFrames.intermix_and_separate > 0 &&
          state.phaseFrames.accelerated_evaporation > 0,
        vapour_plume_moves: state.maxVaporMotionMm > 1.0,
        accelerated_clock_declared: frameClock(TIMELINE.finalFrame).timeScale > 100.0 &&
          frameClock(TIMELINE.finalFrame).physicalTimeS > 3600.0
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
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
      validate: {
        enable: true,
        references: [
          { material: WATER, energyEv: 2.25, refractiveIndex: 1.333,
            source: "validation-only handbook reference" },
          { material: PENTANE, energyEv: 2.25, refractiveIndex: 1.358,
            source: "validation-only handbook reference" }
        ]
      }
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
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 64, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "beaker_wall", material: GLASS,
        innerRadiusMm: APPARATUS.beakerInnerRadiusMm,
        outerRadiusMm: APPARATUS.beakerInnerRadiusMm + 2.0,
        lengthMm: APPARATUS.beakerHeightMm,
        positionMm: [0, APPARATUS.beakerHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["beaker", "glass", "viz_shell"]
      }),
      geometry.tubeVolume({
        name: "beaker_base", material: GLASS,
        innerRadiusMm: 0.0,
        outerRadiusMm: APPARATUS.beakerInnerRadiusMm + 2.0,
        lengthMm: 3.0,
        positionMm: [0, 1.5, 0], rotationDeg: [90, 0, 0],
        tags: ["beaker", "glass", "viz_shell"]
      }),
      // Hidden probe volumes make both NIST liquids part of the constructed
      // Geant4 geometry/optics panel. Studio draws only emitted dynamic phases.
      geometry.boxVolume({ name: "water_probe", material: WATER,
        sizeMm: [5, 5, 5], positionMm: [-100, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "pentane_probe", material: PENTANE,
        sizeMm: [5, 5, 5], positionMm: [100, 0, 0], tags: ["viz_hidden"] })
    ]
  }
};
