// Analytic cross-check scenario: photoelectric process-branching fraction.
//
// The third analytic cross-check, and the photon companion to Beer-Lambert. Both
// fire a monochromatic gamma beam into a water slab, but where Beer-Lambert asks
// "what fraction crosses WITHOUT interacting?" (total attenuation), this one asks
// a different question about the SAME cross sections: "OF the gammas that do
// interact, what fraction interact photoelectrically?" -- the process BRANCHING
// RATIO. It compares two independent answers:
//
//   1. CLASSICAL / Geant4-DERIVED prediction (the expected value):
//        f_photo = sigma_phot / (phot + compt + Rayl + conv)
//      the photoelectric share of the total interaction cross section, summed
//      from Geant4's OWN atomic cross sections via G4EmCalculator -- no
//      externally-tuned constant. Evaluated in C++ right after Initialize.
//
//   2. GEANT4 MONTE-CARLO STATISTICAL result (the measurement):
//        primaries_photoelectric_first / primaries_first_interaction
//      the fraction of primary gammas whose FIRST discrete interaction is a
//      photoelectric absorption, tallied per-primary in SteppingAction (the
//      photoelectric sub-process is read through QBBC's G4GammaGeneralProcess
//      wrapper by EM subtype, so the classification is physics-list robust).
//
// The energy (30 keV) is chosen near water's photoelectric/Compton crossover so
// the fraction sits in the discriminating mid-range (~0.3), well away from 0 or 1
// where both processes are strongly represented. Unlike Beer-Lambert, the
// branching ratio is INDEPENDENT of slab thickness -- given a primary interacts,
// the odds its first interaction is photoelectric are mu_phot/mu_total whatever
// the depth -- so this measures the sampling of the process choice itself.
//
// Both numbers, their delta, the relative error and a within-tolerance flag are
// written to trech_scores.jsonl under `analytic_checks`. They should agree to
// within Poisson statistics -- a self-consistency validation of Geant4's process
// selection against its own tabulated cross sections.
//
// Run:
//   trech run examples/experiments/analytic_photo_fraction.js \
//        --events 20000 --output build/dev/out_analytic_photo_fraction
// Then inspect trech_scores.jsonl -> analytic_checks[0]:
//   classical_predicted vs geant4_measured, relative_error, within_tolerance.

const worldSizeMm = 200.0;    // full side; vacuum world cube
const slabThicknessMm = 50.0; // full side of the centred water cube
const beamEnergyMeV = 0.03;   // 30 keV gamma (near the photo/Compton crossover in water)

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "G4_Galactic", // vacuum: no interactions outside the slab
    mediumBoxMm: slabThicknessMm,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "gamma",
    energyMeV: beamEnergyMeV,
    direction: [0.0, 0.0, 1.0],
    // Start in the vacuum before the slab so the beam enters the water cube head
    // on; the surrounding vacuum contributes no interactions.
    originMm: [0.0, 0.0, -0.4 * worldSizeMm]
  },
  run: { nEvents: 20000, seed: 20260702 },
  // Deterministic transport; no ML inference paths involved.
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "analytic_photo_fraction"
  },
  // The classical cross-check. The engine derives the photoelectric fraction from
  // Geant4's per-process cross sections and compares it to the measured fraction
  // of primaries whose first discrete interaction is photoelectric.
  analytic: {
    enable: true,
    checks: [
      {
        type: "photo_fraction",
        label: "gamma_30keV_photofraction_in_water",
        particle: "gamma",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        toleranceRel: 0.06
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
