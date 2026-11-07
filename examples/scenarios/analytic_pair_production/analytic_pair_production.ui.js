// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"energy_mev": function() { return {
  type: "number", default: 10.0, min: 0.1, max: 50.0, unit: "MeV",
  label: "Gamma energy", group: "Beam",
  description: "Monochromatic gamma energy for the pair-production and photonuclear " +
    "branching checks. Below 1.022 MeV the predicted and measured pair fractions must both " +
    "be exactly zero, and below oxygen's photonuclear threshold so must the photonuclear " +
    "fractions. Photonuclear absorption is part of mu_total, so energies through and above " +
    "the giant-dipole resonance (~22-24 MeV) stay honest; the 50 MeV ceiling bounds the probe."
}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
