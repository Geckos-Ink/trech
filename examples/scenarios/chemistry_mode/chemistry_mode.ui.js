// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"preset": function() { return Object.assign({}, {default: "ethanol", group: "Chemistry",
  label: "Starting scaffold", choices: Object.keys(globalThis.TRECH_MOLECULAR_SERIES)}, {type: "choice"}); },
"structure_json": function() { return Object.assign({}, {default: JSON.stringify(scaffold), group: "Chemistry",
  label: "Structure JSON", description: "Explicit atoms, positions (angstrom), isotope massNumber and declared bonds; no automatic valence rules."}, {type: "string"}); },
"scene_json": function() { return Object.assign({}, {default: "", group: "Chemistry", label: "Multi-molecule scene JSON"}, {type: "string"}); },
"scene_file": function() { return Object.assign({}, {default: globalThis.TRECH_CHEMISTRY_SCENE_FILE || "", group: "Chemistry", label: "JSON scene file (relative to scenario)"}, {type: "string"}); },
"nuclear_samples": function() { return Object.assign({}, {default: globalThis.TRECH_CHEMISTRY_NUCLEAR_SAMPLES || 0, min: 0, max: 32, group: "Particle probe",
  description: "Independent Geant4 nuclear initial-state configurations for explicit isotopes; not time evolution."}, {type: "integer"}); },
"reaction_json": function() { return Object.assign({}, {default: "", group: "Chemistry",
  label: "Reaction experiment JSON", description: "Optional explicit species structures/counts, conserved channels and learned hazard modelPath. No built-in rates."}, {type: "string"}); },
"mode": function() { return Object.assign({}, {default: "predictive", choices: ["predictive", "strict"], group: "Chemistry"}, {type: "choice"}); },
"photon_energy_ev": function() { return Object.assign({}, {default: 3000, min: 1000, max: 30000, group: "Particle probe", unit: "eV"}, {type: "number"}); },
"proxy_density_gcm3": function() { return Object.assign({}, {default: 1, min: 0.000001, max: 30, group: "Particle probe",
  label: "Declared transport proxy density", unit: "g/cm³"}, {type: "number"}); },
"events": function() { return Object.assign({}, {default: 16, min: 1, max: 10000, group: "Particle probe"}, {type: "integer"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
