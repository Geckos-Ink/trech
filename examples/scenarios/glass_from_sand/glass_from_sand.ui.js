// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"precision_profile": function() { return Object.assign({}, {
  label: "Precision profile", group: "Precision",
  description: "Moves every declared axis one rung; individual controls still override it.",
  default: "balanced", choices: helpers.precision.names()
}, {type: "choice"}); },
"cells_per_side": function() { return Object.assign({}, {
  label: "Material cells per side (total = N³)", group: "Particles and sampling", unit: "cells",
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
"operator_checkpoints": function() { return {
  type: "string", default: "", group: "Inference", label: "Operator checkpoint directory",
  description: "Optional fitted thermal and chemistry model directory for operator mode."
}; },
"conduction_source": function() { return Object.assign({}, {
  label: "Conduction source", group: "Inference",
  description: "pair = per-pair-material conduction operators (ctx.interact, exactly " +
               "equal-and-opposite; default); set_network = per-cell DeepSets models over the " +
               "face-neighbour set, distilled from the pair path (reports its net heat error).",
  default: "pair", choices: ["pair", "set_network"]
}, {type: "choice"}); },
"grouping": function() { return Object.assign({}, {
  label: "Population grouping", group: "Inference",
  description: "domain (default) = the thermal, chemistry and pair-conduction calls name no " +
               "material: the engine routes every cell (and every neighbour pair) to the operator " +
               "whose measured training domain (inputs + routing_domain) covers it, band by band, " +
               "in unnamed groups; declared = each cell's material, classified in the scenario, " +
               "names the operator (the validation reference the routed grouping is graded " +
               "against). The opt-in set-network conduction still uses the cell materials.",
  default: "domain", choices: ["domain", "declared"]
}, {type: "choice"}); },
"emit_training_rows": function() { return Object.assign({}, {
  label: "Emit training rows", group: "Inference",
  description: "Deterministic harvest sideband: the teacher's exact inputs/outputs for the " +
               "states this run actually visits. Off during ordinary runs.",
  default: false
}, {type: "boolean"}); },
"detect_domains": function() { return Object.assign({}, {
  label: "Detect statistical domains", group: "Inference",
  description: "Record subdivisions of the furnace population from thermal and phase state.",
  default: false
}, {type: "boolean"}); },
"learn_domains": function() { return Object.assign({}, {
  label: "Learn response domains", group: "Inference",
  description: "learn = the engine grows unlabelled response domains of the thermal law online " +
               "(ctx.learnDomains) and grades them prequentially against a pooled model; state " +
               "is unchanged. deploy = a frozen learner (domain_learner_model) drives the thermal " +
               "update in place of the per-material operators, with the declared operator run " +
               "as a shadow to measure its error. evaluate = the frozen learner is graded on the " +
               "declared trajectory without driving it (held-out prequential error).",
  default: "off", choices: ["off", "learn", "evaluate", "deploy"]
}, {type: "choice"}); },
"domain_learner_model": function() { return {
  type: "string", default: "", group: "Inference", label: "Domain learner state",
  description: "trech_domain_learner_v1 state: warm start for learn, the frozen model for deploy. " +
               "Repository-relative unless absolute."
}; },
"engine_field_evolution": function() { return {
  type: "boolean", label: "Validate engine field methods", group: "Inference", default: true,
  description: "Validation only: the validation companion declares the charge temperature to " +
               "ctx.evolveField, and the engine's methods are graded against the run's own " +
               "temperatures (the reference). The scenario declares no field. Never feeds back."
}; },
"hold_seconds": function() { return Object.assign({}, {
  label: "Furnace hold", group: "Time", unit: "s",
  description: "Physical duration of the melt; only the integration horizon.",
  default: 9000.0, min: 600.0, max: 36000.0, step: 600.0
}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
