// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"energy_mev": function() { return {
  type: "number", default: 10.0, min: 0.1, max: 14.0, unit: "MeV",
  label: "Gamma energy", group: "Beam",
  description: "Monochromatic gamma energy for the pair-production branching check. " +
    "Below 1.022 MeV the predicted and measured fractions must both be exactly zero; " +
    "the 14 MeV ceiling keeps the probe below oxygen's photonuclear giant-dipole region."
}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
