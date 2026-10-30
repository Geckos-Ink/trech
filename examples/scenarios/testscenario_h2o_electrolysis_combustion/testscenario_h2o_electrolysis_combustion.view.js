// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_h2o_electrolysis_combustion"] = {
"frame0": function(TOTAL_TICKS, apparatus, combustion, counts, helpers, phase, s, view) { return helpers.observer.frame(Object.assign(view, {
    physicalTimeS: s.tick, playbackTimeS: s.tick,
    clockText: "tick " + s.tick + " / " + TOTAL_TICKS + " (" + phase.replace(/_/g, " ") + ")",
    phase: combustion ? "inverse combustion (spark): 2 H2 + O2 -> 2 H2O"
                      : "electrolysis: 2 H2O -> 2 H2 + O2",
    lengthUnit: "sim_unit", upAxis: "y", digits: 2,
    apparatus,
    legend: helpers.observer.legend([["O", helpers.observer.elementRgba.O], ["H", helpers.observer.elementRgba.H],
                                     ["cathodes (H2)", [0.62, 0.64, 0.7, 1]], ["anode (O2)", [0.85, 0.45, 0.35, 1]]]),
    hud: [
      "ctx.react inventory: H2O " + counts.water + "   H2 " + counts.hydrogen + "   O2 " + counts.oxygen,
      "H2 per cathode L/R " + s.hydrogen.left + " / " + s.hydrogen.right +
        "   recombined H2O " + s.recombinedWater
    ],
    // Side charts: the ctx.react inventory itself -- the 2 : 2 : 1 stoichiometry of both legs.
    samples: { h2o: counts.water, h2: counts.hydrogen, o2: counts.oxygen,
               h2_left: s.hydrogen.left, h2_right: s.hydrogen.right },
    charts: s.tick <= 1 ? [
      { id: "inventory", title: "ctx.react inventory (molecule packets)", x: "time",
        x_label: "solver tick", y_label: "packets", cursor: true,
        series: [{ key: "h2o", label: "H₂O", color: "#ff5a4a" },
                 { key: "h2", label: "H₂", color: "#e8ecf4" },
                 { key: "o2", label: "O₂", color: "#ff9a3c" }] },
      { id: "cathodes", title: "H₂ collected at each cathode", x: "time",
        x_label: "solver tick", y_label: "packets", cursor: true,
        series: [{ key: "h2_left", label: "left cathode", color: "#9aa4b8" },
                 { key: "h2_right", label: "right cathode", color: "#c9d3e6", dashed: true }] }
    ] : [],
    motionScope: "packet kinematics are representation (buoyant rise, diffusion); counts are ctx.react output"
  })); }
};

Object.assign(TRECH_VIEWS["testscenario_h2o_electrolysis_combustion"], {
"emitCellFrame": function(ctx, phase, CELL, SCENARIO, TOTAL_TICKS, TRECH_VIEWS, currentCounts, helpers, moleculeFor) {
  const s = ctx.state;
  const counts = currentCounts(s);
  const packets = s.waterPackets.concat(s.visualWater, s.visualH2, s.visualO2);
  const view = helpers.observer.atoms(packets.map(moleculeFor), { radiusScale: 2.4 });
  const h = SCENARIO.chamberHalfSize;
  const rodLength = CELL.electrodeTop - CELL.electrodeBottom;
  const rodY = 0.5 * (CELL.electrodeTop + CELL.electrodeBottom);
  const combustion = phase === "inverse_combustion";
  const apparatus = [
    { shape: "box", center: [0, 0.5 * (CELL.liquidTop - h), 0], size: [2 * h, CELL.liquidTop + h, 2 * h],
      color_rgba: [0.3, 0.55, 0.95, 0.12], label: "electrolyte" },
    { shape: "box", center: [0, CELL.liquidTop, 0], size: [2 * h, 0.15, 2 * h],
      color_rgba: [0.55, 0.78, 1.0, 0.45], label: "liquid surface" },
    { shape: "box", center: [0, 0, 0], size: [2 * h, 2 * h, 2 * h], style: "wire",
      color_rgba: [0.55, 0.65, 0.8, 0.35], label: "cell" },
    { shape: "cylinder", center: [-SCENARIO.cathodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.62, 0.64, 0.7, 1.0], label: "left cathode" },
    { shape: "cylinder", center: [SCENARIO.cathodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.62, 0.64, 0.7, 1.0], label: "right cathode" },
    { shape: "cylinder", center: [CELL.anodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.85, 0.45, 0.35, 1.0], label: "anode" }
  ];
  if (combustion) {
    apparatus.push({ shape: "sphere", center: CELL.spark, radius: 1.6,
                     color_rgba: [1.0, 0.85, 0.3, 1.0], label: "spark" });
  }
  ctx.emit("material_frame", TRECH_VIEWS["testscenario_h2o_electrolysis_combustion"]["frame0"](TOTAL_TICKS, apparatus, combustion, counts, helpers, phase, s, view));
}
});
