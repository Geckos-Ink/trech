// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"duration_s": function() { return Object.assign({}, {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful decomposition integrator advances.",
  default: 45.0, min: 15.0, max: 300.0, step: 5.0
}, {type: "number"}); },
"playback_duration_s": function() { return Object.assign({}, {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 9.0, min: 1.0, max: 60.0, step: 1.0
}, {type: "number"}); },
"simulation_ticks": function() { return Object.assign({}, {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; physics uses bounded finer steps.",
  default: 135, min: 20, max: 1000, step: 5
}, {type: "integer"}); },
"foam_parcels": function() { return Object.assign({}, {
  label: "Persistent foam parcels", group: "Precision", unit: "parcels",
  description: "Spatial resolution; the represented material volume stays fixed.",
  default: 280, min: 140, max: 560, step: 20
}, {type: "integer"}); },
"max_physics_step_s": function() { return Object.assign({}, {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal resolution of the decomposition/foam integrator.",
  default: 0.02, min: 0.005, max: 0.1, step: 0.005
}, {type: "number"}); },
"render_surface_grid_mm": function() { return Object.assign({}, {
  label: "Foam surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated state.",
  default: 3.5, min: 2.0, max: 7.0, step: 0.5
}, {type: "number"}); },
"initial_temperature_k": function() { return Object.assign({}, {
  label: "Initial temperature", group: "Conditions", unit: "K",
  description: "Both solutions and the ambient start here.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
