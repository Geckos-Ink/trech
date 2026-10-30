// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["polyurethane_foam"] = {
"frame0": function(REPRESENTATION, bodyMax, bodyMedian, bodyP95, clock, colors, foam, maxDisplacement, metrics, n, phase, positions, renderSurfaceHint, round3, round4, s) { return {
    time_s: round3(clock.physicalTimeS),
    physical_time_s: round3(clock.physicalTimeS),
    playback_time_s: round3(clock.playbackTimeS),
    time_scale: clock.timeScale,
    phase: "polyurethane_foam:" + phase,
    particle_ids: foam.ids,
    positions_mm: positions,
    colors_rgba: colors,
    render_surface: renderSurfaceHint(s, metrics),
    counts: {
      persistent_foam_parcels: n,
      mean_expansion_factor: round3(s.meanExpansion),
      bonds_intact: metrics.bondsTotal - metrics.bondsBroken,
      bonds_broken: metrics.bondsBroken,
      connected_components: metrics.componentCount,
      detached_parcels: metrics.detachedParcels,
      parcels_on_ground: metrics.groundParcels
    },
    physics_state: {
      mean_gel_conversion: round4(s.meanGel),
      mean_blow_conversion: round4(s.meanBlow),
      mean_temperature_k: round3(s.meanTemperatureK),
      core_temperature_k: round3(s.maxTemperatureK),
      skin_temperature_k: round3(s.minTemperatureK),
      mean_rigidity: round4(s.meanRigidity),
      foam_top_mm: round3(metrics.bodyTopZMm),
      debris_top_mm: round3(metrics.maxZMm),
      foam_max_radius_mm: round3(metrics.bodyMaxRadiusMm),
      debris_max_radius_mm: round3(metrics.maxRadiusMm),
      lean_deg: round3(metrics.leanDeg),
      lean_offset_mm: round3(metrics.leanOffsetMm),
      body_median_displacement_since_prior_emit_mm: round4(bodyMedian),
      body_p95_displacement_since_prior_emit_mm: round4(bodyP95),
      body_max_displacement_since_prior_emit_mm: round4(bodyMax),
      max_displacement_since_prior_emit_mm: round4(maxDisplacement)
    },
    geant4_event_id: s.lastGeant4EventId,
    inference: { source: s.coeff.source, response_sigma: s.coeff.responseSigma },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: clock.timeScale
    },
    motion_scope: "persistent foam parcels in a growing viscoelastic bond network under standard gravity; leaning, cracking, detachment and where pieces land are consequences of the stress state, not scheduled events",
    representation_override: REPRESENTATION
  }; },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["cup", "viz_shell", "viz_opacity=0.14"]; },
"tags3": function() { return ["table", "viz_solid", "viz_color=#20242c"]; },
"tags4": function() { return ["viz_hidden"]; },
"tags5": function() { return ["viz_hidden"]; },
"tags6": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["polyurethane_foam"], {
"REPRESENTATION0": function() { return {
  policy: "cream/tan swatches are authored display; liquid base is Geant4-derived; whitening/tanning TIMING is emergent",
  creamTint: [0.95, 0.90, 0.78],
  curedTint: [0.88, 0.77, 0.55],
  liquidAlpha: 0.85,
  foamAlpha: 0.96,
  scatterGain: 2.2
}; },
"frameClock1": function(APPARATUS, helpers) { return helpers.observer.linearClock(APPARATUS); },
"renderSurfaceHint": function(s, metrics, APPARATUS, RENDER_ISO_LEVEL, RENDER_SIGMA_PER_SPACING, REPRESENTATION, clamp01, mix, round3) {
  const sigma = RENDER_SIGMA_PER_SPACING * metrics.spacingMm;
  const bulge = Math.sqrt(2.0 * Math.log(1.0 / RENDER_ISO_LEVEL)) * sigma;
  return {
    mode: "metaball",
    kernel: "gaussian",
    grid_spacing_mm: APPARATUS.renderSurfaceGridMm,
    sigma_mm: round3(sigma),
    iso_level: RENDER_ISO_LEVEL,
    clip_cylinder: {
      axis: "z",
      radius_mm: APPARATUS.tableRadiusMm,
      min_mm: 0.0,
      max_mm: round3(metrics.maxZMm + bulge + 6.0)
    },
    fresnel_r0: 0.04,
    gloss: 0.35,
    opacity: mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
      clamp01(s.meanExpansion - 1.0)),
    positions_unmodified: true,
    policy: "representation only: Gaussian surface over emitted parcel positions; sigma tracks the emergent parcel spacing"
  };
},
"observedPhase": function(s, metrics) {
  if (metrics.detachedParcels > 0 && s.meanRigidity >= 0.9) return "cured_with_fallen_pieces";
  if (metrics.detachedParcels > 0) return "cracking_shedding_pieces";
  if (s.meanRigidity >= 0.9) return "solid_sponge";
  if (s.meanRigidity > 0.05) return "gelling_curing";
  if (s.creamTimeS !== null && s.meanExpansion > 1.5) return "rising";
  if (s.creamTimeS !== null) return "creaming";
  return "mixing_liquids";
},
"emitFrame": function(ctx, s, frameIndex, APPARATUS, Float64Array, REPRESENTATION, TRECH_VIEWS, clamp01, frameClock, mix, mixRgb, observedPhase, renderSurfaceHint, round3, round4) {
  const clock = frameClock(frameIndex);
  const foam = s.foam;
  foam.updateComponents();
  const metrics = foam.metrics();
  const phase = observedPhase(s, metrics);
  const T0 = APPARATUS.initialTemperatureK;
  const n = foam.n;
  const positions = new Array(n);
  const colors = new Array(n);
  let maxDisplacement = 0.0;
  for (let i = 0; i < n; i += 1) {
    positions[i] = [round3(foam.px[i]), round3(foam.py[i]), round3(foam.pz[i])];
    const gasFraction = clamp01((s.localExpansion[i] - 1.0) /
      Math.max(s.localExpansion[i], 1e-9));
    const whiteness = 1.0 - Math.exp(-REPRESENTATION.scatterGain * gasFraction);
    let rgb = mixRgb(s.liquidBaseRgb, REPRESENTATION.creamTint, whiteness);
    rgb = mixRgb(rgb, REPRESENTATION.curedTint, 0.35 * s.gel[i] * whiteness);
    // A detached piece is drawn from the same emitted state; only its colour is
    // slightly darkened so the observer can tell body from fallen debris.
    const shade = foam.freeFlag[i] ? 0.86 : 1.0;
    colors[i] = [round3(clamp01(rgb[0] * shade)), round3(clamp01(rgb[1] * shade)),
                 round3(clamp01(rgb[2] * shade)),
                 round3(mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
                            gasFraction))];
    if (s.lastEmittedPx) {
      const dx = foam.px[i] - s.lastEmittedPx[i];
      const dy = foam.py[i] - s.lastEmittedPy[i];
      const dz = foam.pz[i] - s.lastEmittedPz[i];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (d > maxDisplacement) maxDisplacement = d;
    }
  }
  s.lastEmittedPx = new Float64Array(foam.px);
  s.lastEmittedPy = new Float64Array(foam.py);
  s.lastEmittedPz = new Float64Array(foam.pz);
  // The late-motion probe must not be dominated by falling debris, nor by the one
  // half-cracked flap still hanging by a bond (which really does keep swinging):
  // the cured BULK is what has to be frozen, so report the distribution.
  let bodyMedian = 0.0, bodyP95 = 0.0, bodyMax = 0.0;
  if (s.lastBodyPz) {
    const moved = [];
    for (let i = 0; i < n; i += 1) {
      if (foam.freeFlag[i]) continue;
      const dx = foam.px[i] - s.lastBodyPx[i];
      const dy = foam.py[i] - s.lastBodyPy[i];
      const dz = foam.pz[i] - s.lastBodyPz[i];
      moved.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
    if (moved.length > 0) {
      moved.sort((a, b) => a - b);
      bodyMedian = moved[Math.floor(moved.length * 0.5)];
      bodyP95 = moved[Math.min(moved.length - 1, Math.floor(moved.length * 0.95))];
      bodyMax = moved[moved.length - 1];
    }
  }
  s.lastBodyPx = new Float64Array(foam.px);
  s.lastBodyPy = new Float64Array(foam.py);
  s.lastBodyPz = new Float64Array(foam.pz);
  s.bodyMedianDisplacementsMm.push(round4(bodyMedian));
  s.bodyP95DisplacementsMm.push(round4(bodyP95));

  s.lastFrame = frameIndex;
  s.lastPhysicalTimeS = clock.physicalTimeS;
  if (metrics.leanDeg > s.maxLeanDeg) s.maxLeanDeg = metrics.leanDeg;
  if (metrics.bodyTopZMm > s.maxHeightMm) s.maxHeightMm = metrics.bodyTopZMm;
  if (metrics.detachedParcels > s.maxDetachedParcels) {
    s.maxDetachedParcels = metrics.detachedParcels;
  }
  if (metrics.groundParcels > s.maxGroundParcels) {
    s.maxGroundParcels = metrics.groundParcels;
  }

  ctx.emit("material_frame", TRECH_VIEWS["polyurethane_foam"]["frame0"](REPRESENTATION, bodyMax, bodyMedian, bodyP95, clock, colors, foam, maxDisplacement, metrics, n, phase, positions, renderSurfaceHint, round3, round4, s));
}
});
