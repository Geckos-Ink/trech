// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"molecule": function() { return Object.assign({}, {
  label: "Molecule / comparison group", group: "Molecular series",
  default: globalThis.TRECH_MOLECULAR_PRESET || "ethanol",
  choices: ["ethane", "ethanol", "formamide", "butane", "dimethyl_ether", "acetamide"]
}, {type: "choice"}); },
"mode": function() { return Object.assign({}, {
  label: "Inference mode", group: "Molecular series", default: "predictive",
  choices: ["predictive", "strict"]
}, {type: "choice"}); },
"particle_response": function() { return Object.assign({}, {
  label: "Learned particle → atom → molecule response", group: "Molecular series",
  default: ["butane", "dimethyl_ether", "acetamide"].indexOf(molecule) >= 0
}, {type: "boolean"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
