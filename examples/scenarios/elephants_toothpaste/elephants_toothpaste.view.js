// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["elephants_toothpaste"] = {
"frame0": function(EVAPORATIVE_CLAMP, POOL_VOLUME_MM3, REPRESENTATION, clock, colors, foamShapeZ, gasFraction, maxDisplacement, phase, positions, renderSurfaceHint, round4, state) { return {
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
  }; },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["cylinder", "viz_shell"]; },
"tags3": function() { return ["tray", "viz_solid", "viz_color=#20242c"]; },
"tags4": function() { return ["viz_hidden"]; },
"tags5": function() { return ["viz_hidden"]; },
"tags6": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["elephants_toothpaste"], {
"REPRESENTATION0": function() { return {
  policy: "white/amber swatches are authored display; clear base is Geant4-derived; whitening/amber TIMING is emergent",
  latherTint: [0.94, 0.95, 0.96],
  iodineAmberTint: [0.86, 0.62, 0.12],
  liquidAlpha: 0.72,
  foamAlpha: 0.95,
  scatterGain: 2.6
}; },
"renderSigmaMm": function(state, POOL_VOLUME_MM3) {
  const totalVolume = POOL_VOLUME_MM3 * (1.0 + state.foamVolumes);
  return 0.9 * Math.cbrt(totalVolume / state.n);
},
"renderSurfaceHint": function(state, APPARATUS, CROWN_R_MM, POOL_VOLUME_MM3, RENDER_BULGE_PER_SIGMA, RENDER_ISO_LEVEL, REPRESENTATION, clamp01, foamShapeZ, mix, renderSigmaMm) {
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
},
"frameClock3": function(APPARATUS, helpers) { return helpers.observer.linearClock(APPARATUS); },
"observedPhase": function(state) {
  if (state.physicsTimeS <= 0.0) return "clear_solutions_combined";
  if (state.foamVolumes < 0.2) return "catalytic_runaway_beginning";
  if (state.eruptTimeS === null) return "foam_filling_cylinder";
  if (state.peroxide > 0.10) return "eruption_fountain";
  if (state.foamVolumes > 0.9 * state.peakFoamVolumes) return "steaming_lather_column";
  return "draining_lather";
},
"emitFrame": function(ctx, state, frameIndex, EVAPORATIVE_CLAMP, Float64Array, POOL_VOLUME_MM3, REPRESENTATION, TRECH_VIEWS, clamp01, foamShapeZ, frameClock, mix, mixRgb, observedPhase, parcelNoise01, renderSurfaceHint, round4) {
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

  ctx.emit("material_frame", TRECH_VIEWS["elephants_toothpaste"]["frame0"](EVAPORATIVE_CLAMP, POOL_VOLUME_MM3, REPRESENTATION, clock, colors, foamShapeZ, gasFraction, maxDisplacement, phase, positions, renderSurfaceHint, round4, state));
}
});
