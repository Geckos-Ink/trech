// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["lava_lamp"] = {
"frame0": function(APPARATUS, REPRESENTATION, clock, frame, lineage, parcelLineage, phase, renderSurfaceHint, state) { return {
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
  }; },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["lava_carrier", "viz_opacity=0.10", "viz_tint=#1a5794"]; },
"tags3": function() { return ["lava_glass", "viz_shell"]; },
"tags4": function() { return ["housing", "viz_solid", "viz_color=#0e0b14"]; },
"tags5": function() { return ["heater", "viz_emissive", "viz_color=#ff7a18", "viz_opacity=0.62"]; },
"tags6": function() { return ["housing", "viz_solid", "viz_color=#0e0b14"]; },
"tags7": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["lava_lamp"], {
"REPRESENTATION0": function() { return {
  policy: "authored display tints; never physics inputs",
  waxTint: [1.0, 0.20, 0.025],
  waxWarmHighlight: [1.0, 0.64, 0.08],
  carrierTint: [0.10, 0.34, 0.58],
  housingColor: [0.055, 0.045, 0.075],
  waxAlpha: 0.82,
  waxSurfaceAlpha: 0.94
}; },
"frameClock1": function(APPARATUS, helpers) { return helpers.observer.linearClock(APPARATUS); },
"renderSurfaceHint": function(state, APPARATUS, FLUID_NECK_MIN_MM, FLUID_NECK_SAMPLES, FLUID_NECK_WEIGHT, RADIAL_MAX_MM, RENDER_SURFACE_ISO_LEVEL, RENDER_SURFACE_LINK_MM, RENDER_SURFACE_SIGMA_MM, REPRESENTATION, Z_MAX_MM, Z_MIN_MM) {
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
},
"frameState": function(state, APPARATUS, PARCEL_SURFACE_LINK_MM, RENDER_SURFACE_LINK_MM, REPRESENTATION, TOPOLOGY_LINK_MM, clamp01, componentLabels, mixRgb) {
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
},
"observedPhase": function(state, frame) {
  const liquidDelta = frame.meanLiquid - state.lastMeanLiquidFraction;
  if (frame.meanVz > 0.08) return "rising_from_positive_buoyancy";
  if (frame.meanVz < -0.08) return "falling_from_negative_buoyancy";
  if (liquidDelta > 0.002) return "melting";
  if (liquidDelta < -0.002) return "solidifying";
  if (frame.meanLiquid < 0.25) return "heating_solid_wax";
  return "thermally_neutral";
},
"emitFrame": function(ctx, state, frameIndex, APPARATUS, Float64Array, Int32Array, REPRESENTATION, TRECH_VIEWS, frameClock, frameState, lineageTransitions, observedPhase, renderSurfaceHint) {
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

  ctx.emit("material_frame", TRECH_VIEWS["lava_lamp"]["frame0"](APPARATUS, REPRESENTATION, clock, frame, lineage, parcelLineage, phase, renderSurfaceHint, state));
}
});
