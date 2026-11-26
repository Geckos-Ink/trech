// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"physics_source": function() { return Object.assign({}, {
  label: "Osmotic physics source", group: "Inference",
  description: "operator = learned ctx.evolve particle motion + ctx.react channel passage (normal path); " +
               "reference = retired JS Langevin/passage law for audit only. The membrane response is " +
               "the authored law on both.",
  choices: ["reference", "operator"], default: "operator"
}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
