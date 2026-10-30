// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_efflux"] = {
"frame0": function(EFFLUX_RGBA, PUBCHEM, SCENARIO, TOTAL_TICKS, colors, helpers, membraneShell, n0, physicsSource, positions, radii, retainedInside, state, tick) { return helpers.observer.frame({
    physicalTimeS: tick,
    playbackTimeS: tick,
    clockText: "tick " + tick + " / " + TOTAL_TICKS + " (solver ticks)",
    phase: "passive efflux (3D coarse-grained cell, " + physicsSource + " transport)",
    lengthUnit: "sim_unit", upAxis: "z", digits: 3,
    positions, colors, radii,
    apparatus: membraneShell(SCENARIO.cellRadius),
    legend: helpers.observer.legend([
      [PUBCHEM.permeant.name + " (XLogP " + PUBCHEM.permeant.xlogp + ")", EFFLUX_RGBA.waste],
      [PUBCHEM.retained.name + " (XLogP " + PUBCHEM.retained.xlogp + ")", EFFLUX_RGBA.retained],
      ["lipid membrane", EFFLUX_RGBA.membrane]
    ]),
    hud: [
      "tick " + tick + "   waste inside " + state.wasteInside + " / " + n0 +
        "   cleared " + state.totalCleared,
      "retained (polar) inside " + retainedInside + " / " + SCENARIO.initialRetained
    ],
    counts: { waste_inside: state.wasteInside, cleared: state.totalCleared,
              retained_inside: retainedInside },
    // Side charts: the counts above over time. A straight line on the log axis is first-order
    // kinetics; nothing here is fitted or typed -- the run-end fit stays in the summary emit.
    samples: { waste_inside: state.wasteInside, retained_inside: retainedInside,
               cleared: state.totalCleared },
    charts: tick === 1 ? [
      { id: "inside", title: "molecules still inside the cell (log scale)", x: "time",
        x_label: "solver tick", y_label: "count", log_y: true, cursor: true,
        y_range: [0.8, Math.max(n0, SCENARIO.initialRetained) * 1.5],
        series: [
          { key: "waste_inside", label: PUBCHEM.permeant.name + " (lipophilic: leaves)",
            color: "#ffb838" },
          { key: "retained_inside", label: PUBCHEM.retained.name + " (polar: stays)",
            color: "#59bfff" }] },
      { id: "cleared", title: "carried away by the bloodstream sink", x: "time",
        x_label: "solver tick", y_label: "cumulative count", cursor: true,
        series: [{ key: "cleared", label: "cleared " + PUBCHEM.permeant.name, color: "#ffb838" }] }
    ] : [],
    motionScope: "3D hook-layer transport state (learned ctx.evolve operator)"
  }); }
};

Object.assign(TRECH_VIEWS["testscenario_efflux"], {
"emitEffluxFrame": function(ctx, state, tick, EFFLUX_RGBA, PUBCHEM, SCENARIO, TOTAL_TICKS, TRECH_VIEWS, helpers, membraneShell, physicsSource) {
  const positions = [], colors = [], radii = [];
  let retainedInside = 0;
  for (let i = 0; i < state.particles.length; i += 1) {
    const q = state.particles[i];
    const base = q.kind === "waste" ? EFFLUX_RGBA.waste : EFFLUX_RGBA.retained;
    // A cleared molecule fades as the bloodstream sink carries it away (its own clearedAge).
    const alpha = q.cleared ? Math.max(0.15, 1.0 - q.clearedAge / SCENARIO.clearedFadeTicks) : 1.0;
    positions.push([q.x, q.y, q.z]);
    colors.push([base[0], base[1], base[2], alpha]);
    radii.push(q.radius);
    if (q.kind === "retained" && q.inside) retainedInside += 1;
  }
  const n0 = SCENARIO.initialWaste;
  ctx.emit("material_frame", TRECH_VIEWS["testscenario_efflux"]["frame0"](EFFLUX_RGBA, PUBCHEM, SCENARIO, TOTAL_TICKS, colors, helpers, membraneShell, n0, physicsSource, positions, radii, retainedInside, state, tick));
}
});
