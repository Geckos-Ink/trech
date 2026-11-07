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
}; },
"gamma_nuclear_le_limit_mev": function() { return {
  type: "number", default: -1.0, min: -1.0, max: 1000.0, unit: "MeV",
  label: "Photonuclear low-energy model edge", group: "Physics",
  description: "Upper edge of Geant4's low-energy photonuclear model (G4LowEGammaNuclearModel, " +
    "GammaNPreco). -1 keeps the Geant4 default (200 MeV) and serializes no physics block; 0 removes " +
    "the low-energy model so the Bertini cascade samples every photonuclear final state. Used to " +
    "compare the 16O giant-dipole channel mix between the two models; branching is unaffected."
}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
