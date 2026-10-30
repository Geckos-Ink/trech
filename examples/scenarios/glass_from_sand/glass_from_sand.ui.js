// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"precision_profile": function() { return Object.assign({}, {
  label: "Precision profile", group: "Precision",
  description: "Moves every declared axis one rung; individual controls still override it.",
  default: "balanced", choices: helpers.precision.names()
}, {type: "choice"}); },
"cells_per_side": function() { return Object.assign({}, {
  label: "Crucible cells per side", group: "Precision", unit: "cells",
  description: "Spatial discretisation of the batch; the charge mass per cell scales with it.",
  default: BALANCED_CELLS_PER_SIDE, min: 4, max: 12, step: 1
}, {type: "integer"}); },
"simulation_ticks": function() { return Object.assign({}, {
  label: "Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; the solver takes bounded sub-steps inside each.",
  default: BALANCED_TICKS, min: 20, max: 600, step: 10
}, {type: "integer"}); },
"sub_steps_per_tick": function() { return Object.assign({}, {
  label: "Solver sub-steps per tick", group: "Precision", unit: "steps",
  description: "Temporal resolution of the operator passes inside one Geant4 tick.",
  default: BALANCED_SUBSTEPS, min: 1, max: 16, step: 1
}, {type: "integer"}); },
"furnace_temperature_k": function() { return Object.assign({}, {
  label: "Furnace temperature", group: "Conditions", unit: "K",
  description: "Lower boundary condition; changing it changes the inferred chemistry, not a script.",
  default: 1750.0, min: 1200.0, max: 1900.0, step: 10.0
}, {type: "number"}); },
"ambient_temperature_k": function() { return Object.assign({}, {
  label: "Ambient temperature", group: "Conditions", unit: "K",
  description: "Upper/side boundary and initial charge temperature.",
  default: 300.0, min: 280.0, max: 500.0, step: 5.0
}, {type: "number"}); },
"physics_source": function() { return Object.assign({}, {
  label: "Physics source", group: "Inference",
  description: "operator = trained distilled models (default); reference = the illustrative " +
               "hand-authored teacher they were distilled from.",
  default: "operator", choices: ["operator", "reference"]
}, {type: "choice"}); },
"emit_training_rows": function() { return Object.assign({}, {
  label: "Emit training rows", group: "Inference",
  description: "Deterministic harvest sideband: the teacher's exact inputs/outputs for the " +
               "states this run actually visits. Off during ordinary runs.",
  default: false
}, {type: "boolean"}); },
"hold_seconds": function() { return Object.assign({}, {
  label: "Furnace hold", group: "Time", unit: "s",
  description: "Physical duration of the melt; only the integration horizon.",
  default: 9000.0, min: 600.0, max: 36000.0, step: 600.0
}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
