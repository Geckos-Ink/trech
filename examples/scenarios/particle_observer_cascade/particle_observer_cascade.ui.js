// Bounded inputs for the experimental homogeneous transport candidate.
TRECH_PARAMETERS({
  material: function() { return {type: "choice", default: "acetone",
    choices: ["butane", "dimethyl_ether", "acetamide", "hexane", "acetone", "urea",
      "propanol_proxy", "formamide_proxy", "propylene_glycol_proxy", "alanine_proxy", "heptane_proxy"], label: "Composition proxy",
    group: "Transport proxy", description: "Unit-density homogeneous composition; not a bound molecule or the substance's measured density."}; },
  energy_kev: function() { return {type: "number", default: 19.3, min: 10, max: 30,
    unit: "keV", label: "Photon energy", group: "Transport proxy"}; },
  half_length_mm: function() { return {type: "number", default: 1, min: 0.25, max: 9,
    unit: "mm", label: "Centre-to-face path", group: "Transport proxy",
    description: "Cube half length. The central +z source travels this far before an uncollided exit."}; },
  mode: function() { return {type: "choice", default: "predictive",
    choices: ["predictive", "strict"], label: "Inference mode", group: "Run"}; },
  observer_model: function() { return {type: "string", default: "",
    label: "Observer checkpoint", group: "Run",
    description: "Optional path to a compatible meso observer checkpoint."}; },
  lift_checkpoint: function() { return {type: "string", default: "",
    label: "Group hierarchy checkpoint", group: "Run",
    description: "Optional directory containing particle_element.json and particle_volume.json."}; },
  events: function() { return {type: "integer", default: 4096, min: 1, max: 1000000,
    label: "Independent Monte Carlo photons", group: "Run"}; }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
  globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Particle → observer cascade",
    description: scope, panels: {options: true, processes: true}, processes: [
      {id: "atomic", label: "Particle → atom", kind: "Geant4-trained table response",
        description: "Shared learned CHNO photon-interaction cross sections; no QM/PubChem target."},
      {id: "molecular", label: "Atom → composition", kind: "Geant4-trained nano response",
        description: "Shared learned independent-atom composition lift."},
      {id: "observer", label: "Composition → meso observer", kind: "Experimental Geant4 Monte Carlo-trained candidate",
        description: "Predicts uncollided-photon and deposited-energy fractions before the independent run; held-out compositions remain a validation gate."}
    ]};
};
