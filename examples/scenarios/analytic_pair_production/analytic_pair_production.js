// Analytic cross-check scenario: pair-production branching and threshold.
//
// The fifth analytic cross-check, and the high-energy companion to the
// photofraction. Both ask "OF the gammas that interact, what fraction pick
// process X first?" from the SAME Geant4 cross sections Beer-Lambert sums; here
// X is gamma conversion (e+e- pair production). It compares:
//
//   1. CLASSICAL / Geant4-DERIVED prediction (the expected value):
//        f_pair = sigma_conv / (phot + compt + Rayl + conv)
//      from Geant4's OWN per-process cross sections (G4EmCalculator), with the
//      threshold 2 m_e c^2 = 1.022 MeV taken from CLHEP. Below threshold the
//      prediction is exactly zero.
//
//   2. GEANT4 MONTE-CARLO STATISTICAL result (the measurement):
//        primaries_pair_first / primaries_first_interaction
//      the fraction of primaries whose FIRST discrete interaction is a
//      conversion (fGammaConversion, read through QBBC's G4GammaGeneralProcess
//      wrapper by EM subtype). Below threshold the run must tally none at all;
//      an exact-zero prediction is satisfied only by an exact-zero measurement.
//
// A second check grades the photonuclear branch the same way:
//
//   f_pn = sigma_pn / (phot + compt + Rayl + conv + sigma_pn)
//
// with sigma_pn the registered gamma inelastic (photonuclear) cross section from
// G4HadronicProcessStore -- the evaluated photonuclear table QBBC's
// G4GammaGeneralProcess samples -- against the fraction of primaries whose
// first interaction is photonuclear absorption (fHadronInelastic). sigma_pn is
// part of mu_total for BOTH checks, so energies through and above oxygen's
// giant-dipole resonance (peak ~23 MeV, f_pn ~ 5% in water) stay honest. Below
// oxygen's photonuclear threshold (the default 10 MeV included) sigma_pn is
// exactly zero and the run must tally no photonuclear first interaction.
//
// Default 10 MeV: pair production is ~1/5 of interactions in water. The
// branching ratios are slab-thickness independent; a 200 mm cube makes ~36% of
// primaries interact, so 50000 events give ~18000 first interactions (~1.4%
// relative error on f_pair at 10 MeV).
//
// Honest scope: self-consistency checks of Geant4's process selection against
// its own tabulated conversion (G4PairProductionRelModel, triplet folded in) and
// photonuclear cross sections, not an external XCOM / IAEA calibration.
//
// Run:
//   trech run examples/scenarios/analytic_pair_production/analytic_pair_production.js \
//        --events 50000 --output build/dev/out_analytic_pair
// Threshold / sweep points:
//   trech run .../analytic_pair_production.js --param energy_mev=1.0 ...

const worldSizeMm = 600.0;     // full side; vacuum world cube
const slabThicknessMm = 200.0; // full side of the centred water cube
// The validation suite reruns this with --param energy_mev=... to grade the
// threshold and the rise of the branching ratio (analytic_pair_fraction_energy_sweep)
// and the photonuclear giant-dipole resonance (analytic_photonuclear_fraction_*).
const beamEnergyMeV = TRECH_PARAMETER("energy_mev");

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
  run: { nEvents: 50000, seed: 20261107, threads: 1 },
  // Deterministic transport; no ML inference paths involved.
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "analytic_pair_production"
  },
  analytic: {
    enable: true,
    checks: [
      {
        type: "pair_fraction",
        label: "gamma_pair_fraction_in_water",
        particle: "gamma",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        toleranceRel: 0.06
      },
      {
        // Exactly zero below threshold (the default 10 MeV); ~5% at the 23 MeV
        // giant-dipole peak, where 50000 events give ~760 absorptions (~3.6%).
        type: "photonuclear_fraction",
        label: "gamma_photonuclear_fraction_in_water",
        particle: "gamma",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        toleranceRel: 0.25
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
