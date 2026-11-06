// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"energy_mev": function() { return {
  type: "number", default: 0.03, min: 0.005, max: 1.0, unit: "MeV",
  label: "Gamma energy", group: "Beam",
  description: "Monochromatic gamma energy for the photoelectric branching check. " +
    "The validation suite sweeps 10-100 keV; 30 keV sits near water's photo/Compton crossover."
}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
