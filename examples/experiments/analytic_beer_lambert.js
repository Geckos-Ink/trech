// Analytic cross-check scenario: Beer-Lambert photon attenuation.
//
// This is a "complex test scenario with comparison to a classical formula vs the
// GEANT4-statistical result" -- the deliverable the ROADMAP calls for. It fires
// a narrow, monochromatic gamma beam through a water slab and lets the engine
// compare two independent answers to the same question, "what fraction of the
// beam crosses the slab without interacting?":
//
//   1. CLASSICAL FORMULA (the expected / truth):
//        T = exp(-mu * x)
//      where mu is the linear attenuation coefficient (summed from Geant4's own
//      atomic cross sections -- photoelectric + Compton + Rayleigh + pair -- via
//      G4EmCalculator) and x is the slab thickness. The engine evaluates this in
//      C++ (sim::computeAnalyticChecks) right after initialization.
//
//   2. GEANT4 MONTE-CARLO STATISTICAL RESULT (the prediction):
//        primaries_uncollided / primaries_emitted
//      measured by transporting N gamma primaries and counting how many reach the
//      world boundary having undergone no discrete interaction.
//
// Both numbers, their delta, the relative error, and a within-tolerance flag are
// written to trech_scores.jsonl under `analytic_checks`. They should agree to
// within Poisson statistics -- a self-consistency validation of the whole
// transport + scoring chain against textbook physics.
//
// Geometry: a vacuum world with a centred water cube. The beam starts in the
// vacuum on the -z side so it traverses exactly the full cube (mediumBoxMm) of
// water; the surrounding vacuum does not attenuate, so the measured uncollided
// fraction maps cleanly onto exp(-mu * mediumBoxMm).
//
// Run:
//   trech run examples/experiments/analytic_beer_lambert.js \
//        --events 20000 --output build/dev/out_analytic_beer_lambert
// Then inspect trech_scores.jsonl -> analytic_checks[0]:
//   classical_predicted vs geant4_measured, relative_error, within_tolerance.

const worldSizeMm = 200.0;   // full side; vacuum world cube
const slabThicknessMm = 50.0; // full side of the centred water cube
const beamEnergyMeV = 0.1;    // 100 keV gamma (Compton-dominated in water)

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "G4_Galactic", // vacuum: no attenuation outside the slab
    mediumBoxMm: slabThicknessMm,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "gamma",
    energyMeV: beamEnergyMeV,
    direction: [0.0, 0.0, 1.0],
    // Start in the vacuum well before the slab so the beam enters the cube head
    // on and traverses the full slab thickness of water.
    originMm: [0.0, 0.0, -0.4 * worldSizeMm]
  },
  run: { nEvents: 20000, seed: 20260619 },
  // Deterministic transport; no ML inference paths involved.
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "analytic_beer_lambert"
  },
  // The classical cross-check. The engine fills in energy/material/path defaults
  // from the beam + medium, but we state them explicitly for clarity.
  analytic: {
    enable: true,
    checks: [
      {
        type: "beer_lambert",
        label: "gamma_100keV_through_50mm_water",
        particle: "gamma",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        pathLengthMm: slabThicknessMm,
        toleranceRel: 0.05
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
