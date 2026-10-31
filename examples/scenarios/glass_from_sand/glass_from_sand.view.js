// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["glass_from_sand"] = {
"frame0": function(CELL_PITCH_MM, CHARGE_HEIGHT_MM, CRUCIBLE_WIDTH_MM, KIND_BATCH, KIND_COLOR, KIND_GLASS, KIND_MELT, SIDE, cells, colors, positions, state, summary) { return {
      tag: "glass_furnace",
      time_s: state.timeS,
      physical_time_s: state.timeS,
      time_scale: 1.0,
      phase: summary.kinds[KIND_GLASS] > 0 ? "glass_forming"
             : (summary.kinds[KIND_MELT] > 0 ? "melting" : "heating"),
      particle_ids: cells.ids,
      positions_mm: positions,
      colors_rgba: colors,
      // Cells live in the Geant4 frame (y-up) of the crucible; each is drawn at its pitch.
      up_axis: "y",
      radii: positions.map(() => 0.45 * CELL_PITCH_MM),
      legend: [{ label: "batch (sand + soda + lime)", color_rgba: KIND_COLOR[KIND_BATCH].slice(0, 3) },
               { label: "melt", color_rgba: KIND_COLOR[KIND_MELT].slice(0, 3) },
               { label: "soda-lime glass", color_rgba: KIND_COLOR[KIND_GLASS].slice(0, 3) }],
      hud_lines: [
        "glass units " + summary.glass_units + "   mean T " +
          Math.round(summary.mean_temperature_k) + " K   remaining carbonates " +
          summary.remaining_carbonates,
        SIDE + "^3 cells; operators: ctx.evolve / ctx.react / ctx.interact (6-neighbour pairs)"
      ],
      // The same cells as a continuum in both viewers: one smooth surface per material
      // class (the solver's class of every cell; smoothing only shapes the drawn boundary).
      grid: {
        origin: [0.5 * CELL_PITCH_MM - 0.5 * CRUCIBLE_WIDTH_MM, 0.5 * (CHARGE_HEIGHT_MM / SIDE),
                 0.5 * CELL_PITCH_MM - 0.5 * CRUCIBLE_WIDTH_MM],
        spacing: [CELL_PITCH_MM, CHARGE_HEIGHT_MM / SIDE, CELL_PITCH_MM],
        shape: [SIDE, SIDE, SIDE],
        values: cells.kind.map((k) => (k === KIND_BATCH ? 0 : (k === KIND_MELT ? 1 : 2))),
        classes: [
          { id: 0, label: "batch", color_rgba: KIND_COLOR[KIND_BATCH], style: "solid" },
          { id: 1, label: "melt", color_rgba: [1.0, 0.42, 0.08, 0.48], style: "liquid" },
          { id: 2, label: "glass", color_rgba: [0.55, 0.88, 0.92, 0.55], style: "solid" }
        ],
        replaces_points: true
      },
      samples: {
        batch: summary.kinds[KIND_BATCH] || 0, melt: summary.kinds[KIND_MELT] || 0,
        glass: summary.kinds[KIND_GLASS] || 0,
        mean_temperature_k: Math.round(summary.mean_temperature_k),
        remaining_carbonates: summary.remaining_carbonates
      },
      charts: state.tick === 1 ? [
        { id: "phases", title: "cells in each material class", x: "time", x_scale: 1 / 60,
          x_label: "time (min)", y_label: "cells", cursor: true,
          series: [{ key: "batch", label: "batch (sand + soda + lime)", color: "#d4bd85" },
                   { key: "melt", label: "melt", color: "#ff6b14" },
                   { key: "glass", label: "soda-lime glass", color: "#8ce0eb" }] },
        { id: "temp", title: "mean charge temperature", x: "time", x_scale: 1 / 60,
          x_label: "time (min)", y_label: "K", cursor: true,
          series: [{ key: "mean_temperature_k", label: "mean T", color: "#ff8a5c" }] },
        { id: "co2", title: "carbonates left (CO₂ still to release)", x: "time", x_scale: 1 / 60,
          x_label: "time (min)", y_label: "formula units", cursor: true,
          series: [{ key: "remaining_carbonates", label: "Na₂CO₃ + CaCO₃", color: "#c9d3e6" }] }
      ] : [],
      representation_override: "continuous class boundaries; sand/melt/glass transparency is for visibility, not measured optical transmission",
      counts: summary.kinds,
      physics_state: {
        glass_units: summary.glass_units,
        mean_temperature_k: summary.mean_temperature_k,
        remaining_carbonates: summary.remaining_carbonates
      }
    }; },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["viz_shell"]; },
"tags3": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["glass_from_sand"], {
"KIND_COLOR0": function(KIND_BATCH, KIND_GLASS, KIND_MELT) {return {
  [KIND_BATCH]: [0.83, 0.74, 0.52, 0.38],
  [KIND_MELT]: [1.0, 0.45, 0.10, 0.48],
  [KIND_GLASS]: [0.55, 0.85, 0.90, 0.55]
};}
});
