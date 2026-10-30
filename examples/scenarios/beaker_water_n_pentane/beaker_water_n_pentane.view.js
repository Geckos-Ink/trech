// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["beaker_water_n_pentane"] = {
"frame0": function(APPARATUS, VIZ, clock, colors, fraction, frameIndex, liquidCount, pentaneRgb, phase, positions, state, vaporPhysical, vaporShown, waterRgb) { return {
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
    representation_override: VIZ,
    legend: [{ label: "water (Geant4 optics" + (VIZ.waterTint ? ", display tint)" : ")"),
               color_rgba: waterRgb },
             { label: "n-pentane (Geant4 optics" + (VIZ.pentaneTint ? ", display tint)" : ")"),
               color_rgba: pentaneRgb },
             { label: "pentane vapour tracers", color_rgba: pentaneRgb }],
    hud_lines: [
      "cascade: " + (state.phaseSeparated ? "immiscible" : "miscible") + ", pentane " +
        (state.pentaneOnTop ? "floats on top" : "sinks") + " (Geant4 densities " +
        Number(state.pentaneProbe.density_g_per_cm3).toFixed(3) + " vs " +
        Number(state.waterProbe.density_g_per_cm3).toFixed(3) + " g/cm3)",
      "evaporated so far " + (100.0 * fraction).toFixed(1) + "% of the pentane (cascade 60-min endpoint " +
        (100.0 * state.fraction60).toFixed(1) + "%)",
      "pour / mixing / plume paths: illustrative motion, not a fluid solve"
    ],
    samples: { minute: Math.round(clock.minute * 100) / 100,
               evaporated_percent: Math.round(1000.0 * fraction) / 10,
               pentane_liquid: liquidCount },
    charts: frameIndex === 0 ? [
      { id: "evap", title: "n-pentane evaporated (cascade-predicted)", x: "minute",
        x_label: "minutes at 30 °C", y_label: "% of poured pentane", x_range: [0, APPARATUS.durationMin],
        y_range: [0, Math.max(10.0, 130.0 * state.fraction60)],
        series: [{ key: "evaporated_percent", label: "evaporated", color: "#ffcf66" }],
        reference: [{ label: "cascade 60-min endpoint", color: "#9ad0ff",
                      x: [0, APPARATUS.durationMin],
                      y: [100.0 * state.fraction60, 100.0 * state.fraction60] }] }
    ] : []
  }; },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 64, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["beaker", "glass", "viz_shell"]; },
"tags3": function() { return ["beaker", "glass", "viz_shell"]; },
"tags4": function() { return ["viz_hidden"]; },
"tags5": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["beaker_water_n_pentane"], {
"optionalTint": function(value) {
  return Array.isArray(value) && value.length >= 3 ?
    [Number(value[0]), Number(value[1]), Number(value[2])] : null;
},
"tint": function(rgb, override) {
  if (!override) return rgb.slice(0, 3);
  return [rgb[0] * override[0], rgb[1] * override[1], rgb[2] * override[2]];
},
"emitFrame": function(ctx, state, frameIndex, APPARATUS, TIMELINE, TRECH_VIEWS, VIZ, agitatedPoint, fract, frameClock, pouredPoint, rgba, smoothstep, tint) {
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
  ctx.emit("material_frame", TRECH_VIEWS["beaker_water_n_pentane"]["frame0"](APPARATUS, VIZ, clock, colors, fraction, frameIndex, liquidCount, pentaneRgb, phase, positions, state, vaporPhysical, vaporShown, waterRgb));
}
});

Object.assign(TRECH_VIEWS["beaker_water_n_pentane"], {
"VIZ_INPUT0": function() {return globalThis.TRECH_BEAKER_VIZ_OVERRIDE || {};},
"VIZ_LAYOUTS1": function() {return ["inferred", "water_above", "pentane_above", "mixed"];},
"requestedLayout2": function(VIZ_INPUT) {return String(VIZ_INPUT.layout || "inferred");},
"VIZ3": function(VIZ_INPUT, optionalTint, requestedLayout) {return {
  waterTint: optionalTint(VIZ_INPUT.waterTint),
  pentaneTint: optionalTint(VIZ_INPUT.pentaneTint),
  layerGapMm: Number(VIZ_INPUT.layerGapMm || 0.0),
  vaporExaggeration: Math.max(0.25, Number(VIZ_INPUT.vaporExaggeration || 1.0)),
  layout: requestedLayout,
  waterAlpha: Math.max(0.02, Math.min(1.0, Number(VIZ_INPUT.waterAlpha || 0.28))),
  pentaneAlpha: Math.max(0.02, Math.min(1.0, Number(VIZ_INPUT.pentaneAlpha || 0.25))),
  vaporAlpha: Math.max(0.01, Math.min(1.0, Number(VIZ_INPUT.vaporAlpha || 0.08)))
};}
});

TRECH_VIEWS.beaker_water_n_pentane.initializeLayout = function(APPARATUS, PENTANE_HEIGHT_MM, VIZ, WATER_HEIGHT_MM, ctx, makeMaterialParticles, makePlumeSeeds, pentaneOnTop, phaseSeparated) {
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

return {renderedLayerOrder, waterParticles, pentaneParticles, plumeSeeds, renderedLiquidTop};
};
