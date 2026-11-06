// Analytic cross-check scenario: Klein-Nishina Compton energy transfer.
//
// The fourth analytic cross-check. Beer-Lambert asks whether a gamma interacts,
// the photo-fraction check asks WHICH process it picks; this one asks what a
// Compton scatter DOES: how much of the photon's energy the struck electron
// carries away. It compares two independent answers:
//
//   1. CLASSICAL prediction (the expected value):
//        <T>/E = sigma_tr / sigma
//      the mean energy-transfer fraction of the free-electron Klein-Nishina
//      cross section, eps = E / m_e c^2 with m_e c^2 taken from Geant4's own
//      CLHEP constant, integrated in C++ (deterministic Simpson quadrature).
//      The Compton edge T_max/E = 2eps/(1+2eps) is recorded alongside it.
//
//   2. GEANT4 MONTE-CARLO STATISTICAL result (the measurement):
//        mean (E - E')/E over primaries whose FIRST discrete interaction is
//        Compton, read from the primary photon's own pre/post-step kinetic
//        energy in SteppingAction (Compton sub-process identified through
//        QBBC's G4GammaGeneralProcess wrapper by EM subtype). The largest
//        sampled transfer should approach, and never exceed, the Compton edge.
//
// 662 keV (the Cs-137 line) puts the scatter firmly in the Compton-dominated,
// strongly non-Thomson regime (<T>/E ~0.38, edge 0.72). The 200 mm water cube
// makes ~80% of primaries interact, so 20000 events give ~16000 Compton
// first interactions and a ~0.4% standard error on the mean.
//
// Honest scope: QBBC's standard EM list uses the free-electron
// G4KleinNishinaCompton model (no binding/Doppler) unless polarisation is on,
// so this is a self-consistency check of Geant4's sampled scattering kinematics
// against the closed form it implements -- not an external calibration and not
// a bound-electron reference.
//
// Run:
//   trech run examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js \
//        --events 20000 --output build/dev/out_analytic_compton
// Then inspect trech_scores.jsonl -> analytic_checks[0]:
//   classical_predicted vs geant4_measured, z_score, measured_max_transfer_fraction
//   vs compton_edge_fraction.

const worldSizeMm = 500.0;     // full side; vacuum world cube
const slabThicknessMm = 200.0; // full side of the centred water cube
const beamEnergyMeV = 0.6617;  // Cs-137 gamma line

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "G4_Galactic", // vacuum: no interactions outside the cube
    mediumBoxMm: slabThicknessMm,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "gamma",
    energyMeV: beamEnergyMeV,
    direction: [0.0, 0.0, 1.0],
    originMm: [0.0, 0.0, -0.4 * worldSizeMm]
  },
  // Serial so strict runs replay byte-for-byte (MT merge order perturbs last ULPs).
  run: { nEvents: 20000, seed: 20261106, threads: 1 },
  // Deterministic transport; no ML inference paths involved.
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "analytic_compton_transfer"
  },
  analytic: {
    enable: true,
    checks: [
      {
        type: "compton_energy_transfer",
        label: "gamma_662keV_klein_nishina_transfer_in_water",
        particle: "gamma",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        toleranceRel: 0.02
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
