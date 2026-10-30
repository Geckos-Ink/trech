// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({

});
globalThis.TRECH_UI_DESCRIPTOR = function() {
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Water + salt process recipe",
  description: "Process libraries own preparation, thermal/phase operators and conservation. Missing models block execution; microscopy morphology is unavailable.",
  processes: experiment.plan.steps.map(s => ({id: s.id, label: s.id, kind: s.role,
    description: "Requires a validated " + s.role + " operator for aqueous_nacl"}))};
};
