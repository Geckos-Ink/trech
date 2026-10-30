// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"material": function() { return Object.assign({}, {
  label: "Transport material", group: "Conditions",
  description: "Geant4 builds and probes this material; its actual composition feeds the learned model.",
  default: "G4_WATER", choices: ["G4_WATER", "G4_ETHYL_ALCOHOL"]
}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
