// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"duration_s": function() { return Object.assign({}, {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful foaming + mechanics solver advances.",
  default: 180.0, min: 60.0, max: 900.0, step: 30.0
}, {type: "number"}); },
"playback_duration_s": function() { return Object.assign({}, {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 12.0, min: 1.0, max: 60.0, step: 1.0
}, {type: "number"}); },
"simulation_ticks": function() { return Object.assign({}, {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; physics uses bounded finer steps.",
  default: 216, min: 20, max: 1000, step: 12
}, {type: "integer"}); },
"foam_parcels": function() { return Object.assign({}, {
  label: "Persistent foam parcels", group: "Precision", unit: "parcels",
  description: "Spatial resolution of the bonded network; the poured volume stays fixed.",
  default: 620, min: 200, max: 1400, step: 20
}, {type: "integer"}); },
"max_physics_step_s": function() { return Object.assign({}, {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal resolution of the reaction + mechanics integrator.",
  default: 0.04, min: 0.005, max: 0.2, step: 0.005
}, {type: "number"}); },
"constraint_iterations": function() { return Object.assign({}, {
  label: "Constraint iterations", group: "Precision", unit: "iterations",
  description: "Network stiffness convergence per physics step.",
  default: 3, min: 1, max: 12, step: 1
}, {type: "integer"}); },
"fragment_substeps": function() { return Object.assign({}, {
  label: "Fragment substeps", group: "Precision", unit: "substeps",
  description: "Ballistic resolution for detached pieces inside one network step.",
  default: 6, min: 1, max: 32, step: 1
}, {type: "integer"}); },
"render_surface_grid_mm": function() { return Object.assign({}, {
  label: "Foam surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated state.",
  default: 2.0, min: 1.0, max: 6.0, step: 0.25
}, {type: "number"}); },
"initial_temperature_k": function() { return Object.assign({}, {
  label: "Initial temperature", group: "Conditions", unit: "K",
  description: "Both solutions and the ambient start here.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
}, {type: "number"}); },
"chemistry_source": function() { return Object.assign({}, {
  label: "Chemistry source", group: "Inference",
  description: "reference = the reduced law authored in this scenario; operator = the engine infers the per-parcel chemistry from a trained model (ctx.evolve).",
  choices: ["reference", "operator"], default: "operator"
}, {type: "choice"}); },
"mechanics_source": function() { return Object.assign({}, {
  label: "Constitutive mechanics source", group: "Inference",
  description: "operator = experimental distilled creep/drag/strength (not promoted: observer gates fail); reference = retained reduced-law teacher. Bond/contact laws remain physics for comparison.",
  choices: ["reference", "operator"], default: "reference"
}, {type: "choice"}); },
"emit_operator_samples": function() { return Object.assign({}, {
  label: "Emit operator training samples", group: "Inference",
  description: "Deterministically sample (parcel state -> observed rate) rows from the reference law for harvesting; sideband only, changes no physics.",
  default: false
}, {type: "boolean"}); },
"gravity_scale": function() { return Object.assign({}, {
  label: "Gravity scale", group: "Conditions", unit: "x g",
  description: "Multiplies standard gravity; 0 is the free-fall control that must remove the lean, the sag and every fallen piece.",
  default: 1.0, min: 0.0, max: 2.0, step: 0.1
}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
