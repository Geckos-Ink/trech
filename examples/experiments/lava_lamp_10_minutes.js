// A lava lamp running for ten observer minutes, rendered from one shared TRECH output by
// Studio and the classic trech-viz 3D viewer.
//
// Information discipline:
//   * Geant4 supplies the G4_WATER / G4_PARAFFIN material composition, density, number/electron
//     densities, and the cross sections behind TRECH's derived visible optics. A geantino event
//     is the deterministic clock drive.
//   * ctx.cascade lifts those material facts plus the declared lamp geometry/thermal context
//     through nano -> macro response stages. Its inferred cycle period, vertical excursion,
//     cohesion, and phase heterogeneity drive the observer animation.
//   * Geant4 does NOT solve wax phase change, heat transport, or convection. The moving blobs are
//     an illustrative deterministic hook-layer observer model, labelled in every summary/frame;
//     the compact macro response surface is not yet metrology-grade and emits uncertainty.
//   * The orange wax, blue carrier, dark housing, and warm base highlight are authored rendering
//     choices. They make two otherwise near-colourless Geant4 materials legible and never feed
//     the cascade or motion.
//
// Run:
//   build/dev/trech run examples/experiments/lava_lamp_10_minutes.js \
//     --output build/dev/out_lava_lamp
// README-quality one-minute run (100 real state updates, not a slowed 7-frame excerpt):
//   build/dev/trech run examples/experiments/lava_lamp_10_minutes.js \
//     --param duration_s=60 --param playback_duration_s=10 \
//     --param simulation_ticks=100 --output build/dev/out_lava_lamp_readme_1m

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

const WATER = "G4_WATER";
const WAX = "G4_PARAFFIN";
const AIR = "G4_AIR";
const GLASS = "G4_GLASS_PLATE";

const observerDurationS = TRECH_VALUE.number("duration_s", {
  label: "Physical duration", group: "Observer clock", unit: "s",
  description: "Physical lamp time simulated by the Geant4-driven observer ticks.",
  default: 600.0, min: 60.0, max: 600.0, step: 60.0
});
const playbackDurationS = TRECH_VALUE.number("playback_duration_s", {
  label: "Playback duration", group: "Observer clock", unit: "s",
  description: "Declared display time paired with the retained physical clock.",
  default: 6.0, min: 1.0, max: 60.0, step: 1.0
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Simulation ticks", group: "Run", unit: "ticks",
  description: "Geant4 events and fresh observer-state updates across the configured duration.",
  default: 60, min: 10, max: 2000, step: 10
});

const APPARATUS = {
  durationS: observerDurationS,
  playbackDurationS: playbackDurationS,
  frames: simulationTicks,
  tickIntervalS: observerDurationS / simulationTicks,
  innerRadiusMm: 30.0,
  liquidHeightMm: 180.0,
  glassHeightMm: 190.0,
  bottomTemperatureK: 333.15,
  topTemperatureK: 298.15,
  blobCount: 6,
  representativeWaxPoints: 900
};
APPARATUS.aspectRatio = APPARATUS.liquidHeightMm / (2.0 * APPARATUS.innerRadiusMm);

const REPRESENTATION = {
  policy: "authored display tints; never physics inputs",
  waxTint: [1.0, 0.22, 0.035],
  waxWarmHighlight: [1.0, 0.62, 0.08],
  carrierTint: [0.10, 0.34, 0.58],
  housingColor: [0.055, 0.045, 0.075],
  waxAlpha: 0.78
};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
function clamp01(v) { return clamp(v, 0.0, 1.0); }
function fract(v) { return v - Math.floor(v); }
function smoothstep(v) {
  const x = clamp01(v);
  return x * x * (3.0 - 2.0 * x);
}
function mix(a, b, t) { return a + (b - a) * t; }
function mixRgb(a, b, t) {
  return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];
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

function makeUnitPoint(rng) {
  const z = 2.0 * rng.uniform() - 1.0;
  const angle = 2.0 * Math.PI * rng.uniform();
  const radial = Math.sqrt(Math.max(0.0, 1.0 - z * z));
  const radius = Math.pow(rng.uniform(), 1.0 / 3.0);
  return {
    x: radius * radial * Math.cos(angle),
    y: radius * radial * Math.sin(angle),
    z: radius * z,
    lobe: rng.uniform() < 0.5 ? -1.0 : 1.0,
    warmthBias: rng.uniform()
  };
}

function makeBlobs(ctx, phaseHeterogeneity) {
  const blobs = [];
  const counts = [175, 165, 155, 145, 135, 125];
  for (let i = 0; i < APPARATUS.blobCount; i += 1) {
    const points = [];
    for (let p = 0; p < counts[i]; p += 1) points.push(makeUnitPoint(ctx.rng));
    blobs.push({
      points,
      phase: fract(i / APPARATUS.blobCount +
        (ctx.rng.uniform() - 0.5) * phaseHeterogeneity / APPARATUS.blobCount),
      radiusMm: 9.5 + 3.8 * ctx.rng.uniform(),
      laneRadiusMm: 2.0 + 7.0 * ctx.rng.uniform(),
      laneAngle: 2.0 * Math.PI * ctx.rng.uniform(),
      orbitDirection: ctx.rng.uniform() < 0.5 ? -1.0 : 1.0
    });
  }
  return blobs;
}

function cycleKinematics(cycle, state) {
  const bottom = 18.0;
  const available = APPARATUS.liquidHeightMm - 2.0 * bottom;
  const travel = available * clamp(state.cascade.macro_vertical_excursion_fraction, 0.65, 0.97);
  const top = bottom + travel;
  const stretch = 1.0 + 2.2 * (1.0 - clamp01(state.cascade.macro_blob_cohesion));
  let stage = "heating_at_base";
  let z = bottom;
  let verticalScale = 0.72;
  let radialScale = 1.16;
  let split = 0.0;
  let warmth = 1.0;

  if (cycle < 0.18) {
    const p = smoothstep(cycle / 0.18);
    z = bottom + 4.0 * p;
    verticalScale = mix(0.68, 1.0, p);
    radialScale = mix(1.20, 1.0, p);
  } else if (cycle < 0.46) {
    stage = "rising_warm_wax";
    const p = smoothstep((cycle - 0.18) / 0.28);
    z = mix(bottom + 4.0, top, p);
    verticalScale = stretch + 0.22 * Math.sin(Math.PI * p);
    radialScale = 1.0 / Math.sqrt(verticalScale);
    split = smoothstep((p - 0.62) / 0.38);
    warmth = 1.0 - 0.42 * p;
  } else if (cycle < 0.62) {
    stage = "cooling_near_top";
    const p = smoothstep((cycle - 0.46) / 0.16);
    z = top - 3.5 * p;
    verticalScale = mix(1.12, 0.78, p);
    radialScale = mix(0.96, 1.16, p);
    split = 1.0 - p;
    warmth = 0.58 - 0.18 * p;
  } else if (cycle < 0.90) {
    stage = "falling_cool_wax";
    const p = smoothstep((cycle - 0.62) / 0.28);
    z = mix(top - 3.5, bottom + 2.0, p);
    verticalScale = stretch + 0.16 * Math.sin(Math.PI * p);
    radialScale = 1.0 / Math.sqrt(verticalScale);
    warmth = 0.40 + 0.30 * p;
  } else {
    stage = "merging_at_base";
    const p = smoothstep((cycle - 0.90) / 0.10);
    z = mix(bottom + 2.0, bottom, p);
    verticalScale = mix(1.0, 0.68, p);
    radialScale = mix(1.0, 1.20, p);
    warmth = mix(0.70, 1.0, p);
  }
  return { stage, z, verticalScale, radialScale, split, warmth };
}

function frameClock(frameIndex) {
  const fraction = frameIndex / APPARATUS.frames;
  return {
    physicalTimeS: fraction * APPARATUS.durationS,
    playbackTimeS: fraction * APPARATUS.playbackDurationS,
    timeScale: APPARATUS.durationS / APPARATUS.playbackDurationS
  };
}

function buildFrame(state, frameIndex) {
  const clock = frameClock(frameIndex);
  const positions = [];
  const colors = [];
  const stageCounts = {
    heating_at_base: 0,
    rising_warm_wax: 0,
    cooling_near_top: 0,
    falling_cool_wax: 0,
    merging_at_base: 0
  };
  let minCenter = Infinity;
  let maxCenter = -Infinity;
  let splitBlobCount = 0;

  for (let i = 0; i < state.blobs.length; i += 1) {
    const blob = state.blobs[i];
    const cycle = fract(clock.physicalTimeS / state.cyclePeriodS + blob.phase);
    const k = cycleKinematics(cycle, state);
    stageCounts[k.stage] += 1;
    minCenter = Math.min(minCenter, k.z);
    maxCenter = Math.max(maxCenter, k.z);
    if (k.split > 0.45) splitBlobCount += 1;
    const orbit = blob.laneAngle + blob.orbitDirection *
      0.42 * clock.physicalTimeS / state.cyclePeriodS;
    const cx = blob.laneRadiusMm * Math.cos(orbit);
    const cy = blob.laneRadiusMm * Math.sin(orbit);
    const pulse = 1.0 + 0.07 * Math.sin(2.0 * Math.PI * cycle + i);

    for (let p = 0; p < blob.points.length; p += 1) {
      const seed = blob.points[p];
      const splitOffset = seed.lobe * k.split * blob.radiusMm * 0.46;
      const splitX = splitOffset * Math.cos(orbit + Math.PI / 2.0);
      const splitY = splitOffset * Math.sin(orbit + Math.PI / 2.0);
      positions.push([
        cx + splitX + seed.x * blob.radiusMm * k.radialScale * pulse,
        cy + splitY + seed.y * blob.radiusMm * k.radialScale * pulse,
        clamp(k.z + seed.z * blob.radiusMm * k.verticalScale * pulse,
              4.0, APPARATUS.liquidHeightMm - 4.0)
      ]);
      const highlight = clamp01(0.22 + 0.58 * k.warmth + 0.20 * seed.warmthBias);
      const rgb = mixRgb(REPRESENTATION.waxTint, REPRESENTATION.waxWarmHighlight, highlight);
      colors.push([rgb[0], rgb[1], rgb[2], REPRESENTATION.waxAlpha]);
    }
  }
  return { clock, positions, colors, stageCounts, minCenter, maxCenter, splitBlobCount };
}

function emitFrame(ctx, state, frameIndex) {
  const frame = buildFrame(state, frameIndex);
  const keys = Object.keys(frame.stageCounts);
  let dominant = keys[0];
  for (let i = 1; i < keys.length; i += 1) {
    if (frame.stageCounts[keys[i]] > frame.stageCounts[dominant]) dominant = keys[i];
  }
  state.lastFrame = frameIndex;
  state.lastPhysicalTimeS = frame.clock.physicalTimeS;
  state.minCenterZ = Math.min(state.minCenterZ, frame.minCenter);
  state.maxCenterZ = Math.max(state.maxCenterZ, frame.maxCenter);
  state.minInventory = Math.min(state.minInventory, frame.positions.length);
  state.maxInventory = Math.max(state.maxInventory, frame.positions.length);
  if (frame.splitBlobCount > 0) state.splitFrames += 1;
  keys.forEach((key) => {
    if (frame.stageCounts[key] > 0) state.stageFrames[key] += 1;
  });

  ctx.emit("material_frame", {
    time_s: frame.clock.physicalTimeS,
    physical_time_s: frame.clock.physicalTimeS,
    playback_time_s: frame.clock.playbackTimeS,
    time_scale: frame.clock.timeScale,
    minute: frame.clock.physicalTimeS / 60.0,
    phase: "lava_convection:" + dominant,
    positions_mm: frame.positions,
    colors_rgba: frame.colors,
    counts: {
      visible_wax_representatives: frame.positions.length,
      blobs: state.blobs.length,
      stages: frame.stageCounts,
      visibly_split_blobs: frame.splitBlobCount
    },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: frame.clock.timeScale
    },
    motion_scope: "illustrative hook-layer thermal/convection replay; cascade outputs drive period, excursion, cohesion, and heterogeneity",
    representation_override: REPRESENTATION
  });
}

function initState(ctx) {
  const waterProbe = ctx.materials && ctx.materials[WATER];
  const waxProbe = ctx.materials && ctx.materials[WAX];
  if (!waterProbe || !waxProbe) throw new Error("Geant4 material probes missing lamp media");
  const seed = {
    "context.temperature_span_k": APPARATUS.bottomTemperatureK - APPARATUS.topTemperatureK,
    "context.lamp_aspect_ratio": APPARATUS.aspectRatio
  };
  const cascade = ctx.cascade(seed);
  if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
    throw new Error("lava-lamp cascade requires predictive mode and two loaded stages");
  }
  const cyclePeriodS = clamp(cascade.macro_cycle_period_s, 70.0, 160.0);
  const phaseHeterogeneity = clamp01(cascade.macro_phase_heterogeneity);
  const blobs = makeBlobs(ctx, phaseHeterogeneity);
  const waxOptics = opticsFor(ctx, WAX);
  const waterOptics = opticsFor(ctx, WATER);
  ctx.state.lavaLamp = {
    waterProbe, waxProbe, waterOptics, waxOptics, cascade, cyclePeriodS, phaseHeterogeneity,
    blobs, geant4Events: 0, geant4Steps: 0, geant4TrackLengthMm: 0.0,
    lastFrame: 0, lastPhysicalTimeS: 0.0,
    minCenterZ: Infinity, maxCenterZ: -Infinity,
    minInventory: Infinity, maxInventory: -Infinity, splitFrames: 0,
    stageFrames: {
      heating_at_base: 0, rising_warm_wax: 0, cooling_near_top: 0,
      falling_cool_wax: 0, merging_at_base: 0
    }
  };
  return ctx.state.lavaLamp;
}

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const state = initState(ctx);
    ctx.emit("lava_lamp_scenario", {
      name: "lava_lamp_10_minutes",
      apparatus: APPARATUS,
      geant4_materials: [WATER, WAX, AIR, GLASS],
      geant4_optics: { water: state.waterOptics, paraffin: state.waxOptics },
      cascade_trace: state.cascade.__cascade,
      macro_response: {
        cycle_period_s: state.cyclePeriodS,
        vertical_excursion_fraction: state.cascade.macro_vertical_excursion_fraction,
        blob_cohesion: state.cascade.macro_blob_cohesion,
        phase_heterogeneity: state.phaseHeterogeneity,
        response_sigma: state.cascade.macro_response_sigma
      },
      honest_scope: "Geant4 material/optics base + geantino clock; cascade-driven illustrative hook-layer thermal/convection replay",
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
    emitFrame(ctx, state, Math.min(APPARATUS.frames, ctx.event.id + 1));
  },
  onRunEnd(ctx) {
    const state = ctx.state && ctx.state.lavaLamp;
    if (!state) return;
    const seedKeys = state.cascade.__cascade.seedKeys || [];
    const g4Seeded = seedKeys.indexOf("material.G4_WATER.density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material.G4_PARAFFIN.density_g_per_cm3") >= 0;
    const frameEnd = frameClock(APPARATUS.frames);
    const validation = {
      geant4_material_base_present: Number(state.waterProbe.density_g_per_cm3) > 0.0 &&
        Number(state.waxProbe.density_g_per_cm3) > 0.0 && state.geant4Events === APPARATUS.frames &&
        state.geant4Steps > 0,
      cascade_drives_observer_cycle: state.cascade.__cascade.stagesRun === 2 && g4Seeded &&
        state.cyclePeriodS > 0.0,
      ten_minutes_reached: Math.abs(state.lastPhysicalTimeS - 600.0) < 1e-9 &&
        state.lastFrame === APPARATUS.frames,
      accelerated_clock_declared: frameEnd.timeScale > 1.0 &&
        Math.abs(frameEnd.timeScale -
          APPARATUS.durationS / APPARATUS.playbackDurationS) < 1e-9 &&
        frameEnd.physicalTimeS === APPARATUS.durationS &&
        frameEnd.playbackTimeS === APPARATUS.playbackDurationS,
      configured_duration_reached:
        Math.abs(state.lastPhysicalTimeS - APPARATUS.durationS) < 1e-9 &&
        state.lastFrame === APPARATUS.frames,
      one_frame_per_geant4_tick: state.geant4Events === APPARATUS.frames &&
        state.lastFrame === state.geant4Events,
      wax_visits_bottom_and_top: state.minCenterZ < 25.0 && state.maxCenterZ > 140.0,
      bidirectional_convection_visible: state.stageFrames.rising_warm_wax > 0 &&
        state.stageFrames.falling_cool_wax > 0,
      split_and_merge_visible: state.splitFrames > 0 && state.stageFrames.merging_at_base > 0,
      representative_inventory_conserved: state.minInventory === APPARATUS.representativeWaxPoints &&
        state.maxInventory === APPARATUS.representativeWaxPoints
    };
    ctx.emit("lava_lamp_summary", {
      duration_s: state.lastPhysicalTimeS,
      duration_min: state.lastPhysicalTimeS / 60.0,
      frames: state.lastFrame + 1,
      geant4: {
        water_density_g_per_cm3: state.waterProbe.density_g_per_cm3,
        paraffin_density_g_per_cm3: state.waxProbe.density_g_per_cm3,
        events: state.geant4Events,
        steps: state.geant4Steps,
        track_length_mm: state.geant4TrackLengthMm
      },
      cascade: state.cascade.__cascade,
      macro_response: {
        cycle_period_s: state.cyclePeriodS,
        cycles_observed_per_blob: APPARATUS.durationS / state.cyclePeriodS,
        vertical_excursion_fraction: state.cascade.macro_vertical_excursion_fraction,
        blob_cohesion: state.cascade.macro_blob_cohesion,
        phase_heterogeneity: state.phaseHeterogeneity,
        response_sigma: state.cascade.macro_response_sigma
      },
      dynamics: {
        min_blob_center_z_mm: state.minCenterZ,
        max_blob_center_z_mm: state.maxCenterZ,
        vertical_travel_mm: state.maxCenterZ - state.minCenterZ,
        split_frames: state.splitFrames,
        stage_frames: state.stageFrames,
        representative_inventory_range: [state.minInventory, state.maxInventory]
      },
      observer_clock: {
        physical_duration_s: APPARATUS.durationS,
        playback_duration_s: APPARATUS.playbackDurationS,
        acceleration: frameEnd.timeScale,
        geant4_ticks: APPARATUS.frames,
        emitted_frames: state.lastFrame + 1,
        tick_interval_s: APPARATUS.tickIntervalS
      },
      honest_scope: "Geant4 does not solve lamp heat flow or wax convection; macro response and blob kinematics are illustrative cascade/hook-layer observer models",
      representation_override: REPRESENTATION,
      validation
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 500.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.topTemperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 1, 0] },
  run: { nEvents: APPARATUS.frames, seed: 20260716, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: { enable: true, materials: [WATER, WAX, AIR, GLASS] },
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
    { name: "macro_convection_response", scale: "macro",
      path: "data/lava_lamp_cascade/macro_convection_response.json" },
    { name: "nano_material_response", scale: "nano",
      path: "data/lava_lamp_cascade/nano_material_response.json" }
  ],
  system: { enable: true, mode: "transient", frame: "observer",
            ensemble: "lava_lamp_10_minutes" },
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 524288 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "carrier_liquid", material: WATER,
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
        name: "wax_material_probe", material: WAX,
        sizeMm: [4, 4, 4], positionMm: [120, 0, 0], tags: ["viz_hidden"]
      })
    ]
  }
};
