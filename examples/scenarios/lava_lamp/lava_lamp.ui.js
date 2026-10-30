// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"duration_s": function() { return Object.assign({}, {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful thermofluid solver advances.",
  default: 600.0, min: 30.0, max: 3600.0, step: 30.0
}, {type: "number"}); },
"playback_duration_s": function() { return Object.assign({}, {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 10.0, min: 1.0, max: 120.0, step: 1.0
}, {type: "number"}); },
"precision_profile": function() { return Object.assign({}, {
  label: "Precision profile", group: "Precision",
  description: "Moves every declared axis one rung; individual controls below still override it.",
  default: "balanced", choices: helpers.precision.names()
}, {type: "choice"}); },
"simulation_ticks": function() { return Object.assign({}, {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; internal physics uses bounded finer steps.",
  default: BALANCED_TICKS, min: 10, max: 2000, step: 10
}, {type: "integer"}); },
"wax_representatives": function() { return Object.assign({}, {
  label: "Persistent wax parcels", group: "Precision", unit: "parcels",
  description: "Spatial solver resolution; inventory volume stays fixed as parcel count changes.",
  default: BALANCED_PARCELS, min: 120, max: 480, step: 60
}, {type: "integer"}); },
"max_physics_step_s": function() { return Object.assign({}, {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal solver resolution; smaller steps refine heat, phase, and motion updates.",
  default: BALANCED_PHYSICS_STEP_S, min: 0.1, max: 1.0, step: 0.1
}, {type: "number"}); },
"render_surface_grid_mm": function() { return Object.assign({}, {
  label: "Wax surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated parcel state.",
  default: BALANCED_SURFACE_GRID_MM, min: 0.75, max: 2.5, step: 0.25
}, {type: "number"}); },
"heater_temperature_k": function() { return Object.assign({}, {
  label: "Heater temperature", group: "Conditions", unit: "K",
  description: "Lower thermal boundary condition; changing it changes the inferred response.",
  default: 333.15, min: 310.0, max: 350.0, step: 1.0
}, {type: "number"}); },
"ambient_temperature_k": function() { return Object.assign({}, {
  label: "Ambient temperature", group: "Conditions", unit: "K",
  description: "Upper/wall thermal boundary and initial carrier temperature.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
