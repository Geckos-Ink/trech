// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
// Target choices come from the loaded dataset (committed fixture or a Studio training run).
TRECH_PARAMETERS({
"data_dir": function() { return Object.assign({}, {default: "", group: "Spectrum prediction",
  label: "Dataset/model directory",
  description: "Empty uses the committed fixture data/spectrum_prediction. A projects/spectrum_prediction run directory (dataset.json, report.json, models/) selects freshly trained models."}, {type: "string"}); },
"selection": function() { return Object.assign({}, {default: "single", group: "Spectrum prediction",
  label: "Targets", choices: ["single", "test_split", "all_molecules", "all_atoms"],
  description: "single: one molecule or element. test_split: every held-out record of both models (the honest generalisation view). all_*: every record, training members flagged."}, {type: "choice"}); },
"target_kind": function() { return Object.assign({}, {default: "molecule", choices: ["molecule", "atom"],
  group: "Spectrum prediction", label: "Single target kind"}, {type: "choice"}); },
"molecule": function() {
  const names = globalThis.TRECH_SPECTRUM_DATA.dataset.molecules.map(m => m.name);
  return Object.assign({}, {default: names.indexOf("naphthalene") >= 0 ? "naphthalene" : names[0], choices: names,
    group: "Spectrum prediction", label: "Molecule", description: "PubChem compound with a measured UV/Vis maximum record."}, {type: "choice"}); },
"element": function() {
  const symbols = globalThis.TRECH_SPECTRUM_DATA.dataset.atoms.map(a => a.symbol);
  return Object.assign({}, {default: symbols.indexOf("Na") >= 0 ? "Na" : symbols[0], choices: symbols,
    group: "Spectrum prediction", label: "Element", description: "Neutral atom with a NIST ASD line list reached via PubChem."}, {type: "choice"}); },
"mode": function() { return Object.assign({}, {default: "predictive", choices: ["predictive", "strict"],
  group: "Spectrum prediction", description: "Strict mode disables learned inference; measured references are still emitted."}, {type: "choice"}); },
"studio_mode": function() { return Object.assign({}, {default: false, group: "Studio",
  label: "Studio spectrum workspace",
  description: "UI extension mode: declares the spectrum input schema, enables the Spectra dock and emits the architecture leaderboard."}, {type: "boolean"}); },
"proxy_density_gcm3": function() { return Object.assign({}, {default: 1, min: 0.000001, max: 30, unit: "g/cm³",
  group: "Geant4 context", label: "Declared probe density",
  description: "Density of the composition-only Geant4 material probe (single target). Context facts only; not a model input."}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
  // Set by the physics script after resolving the studio_mode parameter (declared once).
  const studio = globalThis.TRECH_SPECTRUM_DATA.studioMode === true;
  globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Spectrum prediction",
    panels: {options: true, scenario: true, emits: true, scale_ladder: true, processes: false, spectra: studio},
    extensions: studio ? ["spectrum_prediction"] : []};
};
