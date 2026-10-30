// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["aerodynamics_reference"] = {
"viz0": function() { return {enable: true}; },
"frame1": function(dx, field, ny, positions, reference, s, scope, values) { return {stream: "aerodynamics_reference", time_s: s.time_s,
    positions_mm: positions.map(p => [1000 * (p[0] - 0.2), 1000 * (p[1] - ny * dx / 2), 0]),
    colors_rgba: values.map(v => {const f = Math.max(0, Math.min(1, (v / reference - 0.5) / 2)); return [f, 0.3, 1 - f, 0.9];})
      .concat(s.solid_positions.map(() => [0.7, 0.72, 0.75, 1])),
    vectors: s.cells.map(c => [c.vx * 0.02, c.vy * 0.02, 0]).concat(s.solid_positions.map(() => [0, 0, 0])),
    up_axis: "y", show_geant4_scene: false,
    phase: "COMPARISON · air " + field,
    clock_text: "t = " + (s.time_s * 1000).toFixed(3) + " ms; CFL step " + s.steps,
    hud_lines: [(field === "temperature" ? "Gas temperature" : field) + ": " + Math.min(...values).toFixed(1) +
      "–" + Math.max(...values).toFixed(1) + (field === "temperature" ? " K" : field === "pressure" ? " Pa" : " kg/m³")],
    legend: [{label: "Blue → red: 0.5–2.5× inlet", color_rgba: [0.5, 0.3, 0.5, 1]},
      {label: "Grey: fixed obstacle", color_rgba: [0.7, 0.72, 0.75, 1]}],
    motion_scope: scope + "; cell centres, display colours and velocity arrows scaled by 0.02 mm/(m/s) are representation"}; }
};
