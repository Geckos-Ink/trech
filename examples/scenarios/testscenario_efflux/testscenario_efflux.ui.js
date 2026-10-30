// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"physics_source": function() { return Object.assign({}, {
  label: "Efflux physics source", group: "Inference",
  description: "operator = learned ctx.evolve transport + ctx.react crossing (normal path); reference = retired JS law for audit only.",
  choices: ["reference", "operator"], default: "operator"
}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
