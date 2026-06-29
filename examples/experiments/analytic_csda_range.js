// Analytic cross-check scenario: charged-particle CSDA range.
//
// The charged-particle companion to analytic_beer_lambert.js, and the second
// fully "derived-from-Geant4" check: behaviour is obtained from Geant4's OWN
// particle-level data, with the classical formula used only as the comparison.
// It fires a proton beam that fully stops inside a water block and compares two
// independent answers to "how far does the proton travel before stopping?":
//
//   1. CLASSICAL / Geant4-DERIVED PREDICTION (the expected value):
//        R_CSDA = integral_0^E dE'/(dE'/dx)
//      the continuous-slowing-down-approximation range -- the path-length
//      integral of the proton slowing from E to rest. The stopping power dE'/dx
//      is Geant4's OWN (G4EmCalculator::GetCSDARange), so no externally-tuned
//      constant enters. The engine evaluates this in C++ right after Initialize.
//
//   2. GEANT4 MONTE-CARLO STATISTICAL RESULT (the measurement):
//        primary_mean_track_length_mm
//      the mean geometric path length of the PRIMARY proton, summed over its
//      steps until it ranges out (a new per-primary tally in SteppingAction).
//
// A proton (not an electron) is used on purpose: it travels almost perfectly
// straight (detour factor ~1) and barely backscatters, so its transported track
// length equals the CSDA range to high accuracy -- the cleanest possible
// "measured == derived" agreement. The two numbers, the gap, the relative error
// and a within-tolerance flag are written to trech_scores.jsonl under
// `analytic_checks`.
//
// Geometry: a vacuum world holding a water cube large enough to CONTAIN the
// proton. The beam starts inside the water near the -x face and fires +x; at
// 20 MeV the proton's CSDA range in water is ~4.3 mm, far short of the +x wall,
// so every primary stops inside (primaries_transmitted = 0) and the mean track
// length maps cleanly onto the CSDA range.
//
// Run:
//   trech run examples/experiments/analytic_csda_range.js \
//        --events 5000 --output build/dev/out_analytic_csda
// Then inspect trech_scores.jsonl -> analytic_checks[0]:
//   classical_predicted (csda_range_mm) vs geant4_measured (mean track length).

const worldSizeMm = 80.0;     // vacuum world cube (full side)
const waterCubeMm = 40.0;     // centred water cube (-20..+20 on each axis)
const beamEnergyMeV = 20.0;   // 20 MeV proton -> CSDA range in water ~4.3 mm
// Start inside the water near the -x face, fire +x: the proton stops ~4.3 mm in,
// well within the +20 mm wall, so it is fully contained.
const beamOriginXmm = -0.45 * waterCubeMm;  // -18 mm

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "G4_Galactic",   // vacuum outside the block
    mediumBoxMm: waterCubeMm,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "proton",
    energyMeV: beamEnergyMeV,
    direction: [1.0, 0.0, 0.0],
    originMm: [beamOriginXmm, 0.0, 0.0]
  },
  // threads:1 makes the measured mean track length (a floating-point sum) byte
  // reproducible -- MT worker-merge ordering would otherwise jitter the last
  // ULPs and the committed report. The mean converges fast (range straggling is
  // ~1-2%), so a single thread over a few thousand protons is plenty.
  run: { nEvents: 5000, seed: 20260630, threads: 1 },
  // Deterministic transport; no ML inference paths involved.
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "analytic_csda_range"
  },
  // The classical cross-check. The engine derives the CSDA range from Geant4's
  // stopping power and compares it to the measured mean primary track length.
  analytic: {
    enable: true,
    checks: [
      {
        type: "csda_range",
        label: "proton_20MeV_csda_range_in_water",
        particle: "proton",
        energyMeV: beamEnergyMeV,
        material: "G4_WATER",
        toleranceRel: 0.05
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
