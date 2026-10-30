// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_osmotic"] = {
"frame0": function(OSMO_CHARTS, OSMO_RGBA, SCENARIO, TOTAL_TICKS, colors, counts, helpers, membrane, phaseLabel, pores, positions, radii, state, tick, vertices, volumeFraction) { return helpers.observer.frame({
    physicalTimeS: tick, playbackTimeS: tick,
    clockText: "tick " + tick + " / " + TOTAL_TICKS + " (solver ticks)",
    phase: phaseLabel(tick),
    lengthUnit: "sim_unit", upAxis: "z", digits: 2,
    positions, colors, radii,
    apparatus: [{ shape: "mesh", vertices, faces: membrane.faces, color_rgba: OSMO_RGBA.membrane,
                  label: "lipid membrane" }].concat(pores, [{
      shape: "box", center: [0, 0, 0],
      size: [2 * SCENARIO.domainHalfSize, 2 * SCENARIO.domainHalfSize, 2 * SCENARIO.domainHalfSize],
      style: "wire", color_rgba: [0.55, 0.65, 0.8, 0.35], label: "bath" }]),
    legend: helpers.observer.legend([["water (crosses channels)", OSMO_RGBA.h2o],
                                     ["glucose (size-excluded)", OSMO_RGBA.glucose],
                                     ["ion (polarity-rejected)", OSMO_RGBA.ion],
                                     ["water channel", OSMO_RGBA.pore]]),
    hud: [
      "water inside " + counts.inside_h2o + " / outside " + counts.outside_h2o +
        "   net efflux " + (state.crossingsOut - state.crossingsIn) +
        "   rejections " + state.totalRejections,
      "cell volume " + (100.0 * volumeFraction).toFixed(1) + "% of V0   area " +
        (100.0 * membrane.area / membrane.area0).toFixed(1) + "% of A0   P_out/P_in " +
        (state.pressureInsideEMA > 0 ? (state.pressureOutsideEMA / state.pressureInsideEMA).toFixed(2)
                                     : "-")
    ],
    counts,
    samples: { volume_percent: Math.round(1000.0 * volumeFraction) / 10,
               water_inside: counts.inside_h2o,
               pressure_ratio: state.pressureInsideEMA > 0
                 ? Math.round(1000 * state.pressureOutsideEMA / state.pressureInsideEMA) / 1000 : 1.0 },
    charts: OSMO_CHARTS.declared ? [] : (OSMO_CHARTS.declared = true, [
      { id: "volume", title: "cell volume (membrane solver)", x: "time", x_label: "solver tick",
        y_label: "% of initial volume", cursor: true,
        series: [{ key: "volume_percent", label: "cell volume", color: "#ff9ec7" }] },
      { id: "water", title: "water molecules inside the cell", x: "time", x_label: "solver tick",
        y_label: "count", cursor: true,
        series: [{ key: "water_inside", label: "H₂O inside", color: "#59bfff" }] },
      { id: "pressure", title: "collision pressure outside / inside", x: "time",
        x_label: "solver tick", y_label: "P_out / P_in", cursor: true,
        series: [{ key: "pressure_ratio", label: "measured (EMA)", color: "#ffd24d" }],
        reference: [{ label: "balance (1.0)", color: "#9aa4b8", x: [0, TOTAL_TICKS], y: [1, 1] }] }
    ]),
    motionScope: "3D hook-layer bath + overdamped area-conserving membrane (solver state)"
  }); }
};

Object.assign(TRECH_VIEWS["testscenario_osmotic"], {
"emitOsmoticFrame": function(ctx, state, tick, counts, OSMO_CHARTS, OSMO_RGBA, SCENARIO, TOTAL_TICKS, TRECH_VIEWS, helpers, localMembraneRadius, phaseLabel) {
  const membrane = state.membrane;
  const R0 = SCENARIO.cellRadius;
  const positions = [], colors = [], radii = [];
  for (let i = 0; i < state.particles.length; i += 1) {
    const p = state.particles[i];
    const c = OSMO_RGBA[p.kind];
    positions.push([p.x, p.y, p.z]);
    colors.push(p.inside ? c : [c[0] * 0.8, c[1] * 0.8, c[2] * 0.8, 0.8]);
    radii.push(p.radius);
  }
  const vertices = membrane.dirs.map((d, i) => [d[0] * R0 * membrane.rho[i],
                                                d[1] * R0 * membrane.rho[i],
                                                d[2] * R0 * membrane.rho[i]]);
  const pores = state.pores.map((d) => {
    const rr = localMembraneRadius(membrane, d[0], d[1], d[2], 1.0);
    return { shape: "sphere", center: [d[0] * rr, d[1] * rr, d[2] * rr], radius: 1.1,
             color_rgba: OSMO_RGBA.pore, label: "water channel" };
  });
  const volumeFraction = membrane.volume / membrane.volume0;
  ctx.emit("material_frame", TRECH_VIEWS["testscenario_osmotic"]["frame0"](OSMO_CHARTS, OSMO_RGBA, SCENARIO, TOTAL_TICKS, colors, counts, helpers, membrane, phaseLabel, pores, positions, radii, state, tick, vertices, volumeFraction));
}
});
