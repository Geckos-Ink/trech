// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"reaction_source": function() { return Object.assign({}, {
  label: "Reaction source", group: "Inference",
  description: "operator = learned ctx.react hazards (normal path); reference = retired JS probability law for audit/validation only.",
  choices: ["reference", "operator"], default: "operator"
}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
