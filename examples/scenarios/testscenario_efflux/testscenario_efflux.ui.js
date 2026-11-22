// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"learn_domains": function() { return Object.assign({}, {
  label: "Learn response domains", group: "Inference",
  description: "learn = the engine grows unlabelled response domains of the transport operator " +
               "(ctx.learnDomains) from its own per-particle outputs, graded prequentially against a " +
               "pooled law; evaluate = a frozen learner (domain_learner_model) is graded on this run; " +
               "both leave the bath unchanged. deploy = the frozen learner drives the particle " +
               "transport in place of the operator, which runs on a copy as a shadow. Operator physics only.",
  default: "off", choices: ["off", "learn", "evaluate", "deploy"]
}, {type: "choice"}); },
"domain_learner_model": function() { return {
  type: "string", default: "", group: "Inference", label: "Domain learner state",
  description: "trech_domain_learner_v1 state: warm start for learn, the frozen model for evaluate and deploy. " +
               "Repository-relative unless absolute."
}; },
"physics_source": function() { return Object.assign({}, {
  label: "Efflux physics source", group: "Inference",
  description: "operator = learned ctx.evolve transport + ctx.react crossing (normal path); reference = retired JS law for audit only.",
  choices: ["reference", "operator"], default: "operator"
}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
