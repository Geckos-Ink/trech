// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["nacl_dehydration_reference"] = {
"viz0": function() { return {enable: true}; },
"frame1": function(colors, positions, scope, state, step, ticks) { return {stream: "nacl_reference", positions_mm: positions, colors_rgba: colors,
    radii: positions.map(() => 0.42), up_axis: "y", time: step, time_unit: "step", show_geant4_scene: false,
    phase: "COMPARISON · NaCl dehydration",
    clock_text: "Step " + step + "/" + ticks + "; no calibrated physical time",
    hud_lines: ["Solvent " + state.water_liquid + "; salt " + state.salt_crystal + " solid + " + state.salt_dissolved + " dissolved"],
    legend: [{label: "Blue: solvent", color_rgba: [0.2, 0.55, 1, 1]},
      {label: "Gold: dissolved salt", color_rgba: [0.95, 0.7, 0.2, 1]},
      {label: "White: crystal parcels", color_rgba: [0.9, 0.94, 1, 1]}],
    motion_scope: scope + "; parcel positions, radii, colours and tray layout are rendering choices"}; }
};
