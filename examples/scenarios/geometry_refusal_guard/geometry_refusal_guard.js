// Geometry refusal guard: a small water target and a polystyrene dosimeter
// beside it, authored with `geometry.refuseOn: "any"`. Geant4 places
// overlapping volumes silently and DetectorConstruction substitutes unknown
// materials and parents, so without the guard a mistyped geometry still runs
// and produces numbers for a different apparatus. With the guard the engine
// checks its own post-construction report and, on any substitution or sampled
// overlap, writes one `geometry_refused` provenance record, runs no events,
// writes no scores and exits 1.
//
// The default geometry is clean, so the guard passes and the run proceeds.
// `--param inject_defects=true` adds two deliberate authoring errors -- a probe
// box overlapping the target and a volume naming a material Geant4 does not
// know -- which the guard must refuse. The validation suite runs both and
// grades them with `geometry_refusal_guard_refuses_defects`.
//
// Run:
//   trech run examples/scenarios/geometry_refusal_guard/geometry_refusal_guard.js \
//        --output build/dev/out_geometry_refusal_clean
//   trech run .../geometry_refusal_guard.js --param inject_defects=true \
//        --output build/dev/out_geometry_refusal_injected   # exits 1 by design
//
// Honest scope: a configuration/provenance guard over Geant4 transport. The
// overlap check samples solid surfaces, so a clean report is a bound, not a proof.

const injectDefects = TRECH_PARAMETER("inject_defects");

const volumes = [
  {
    name: "target",
    material: "G4_WATER",
    shape: { type: "box", sizeMm: [60.0, 60.0, 60.0] },
    placement: { parent: "world", positionMm: [0, 0, 0] },
    scoreEdep: true
  },
  {
    name: "dosimeter",
    material: "G4_POLYSTYRENE",
    shape: { type: "box", sizeMm: [20.0, 20.0, 10.0] },
    placement: { parent: "world", positionMm: [0, 0, 60.0] },
    scoreEdep: true
  }
];

if (injectDefects) {
  // Overlaps the target's +x face by 5 mm (the target spans x in [-30, 30]).
  volumes.push({
    name: "probe",
    material: "G4_Al",
    shape: { type: "box", sizeMm: [10.0, 10.0, 10.0] },
    placement: { parent: "world", positionMm: [30.0, 0, 0] }
  });
  // A material name Geant4 does not know: DetectorConstruction would fall back.
  volumes.push({
    name: "shield",
    material: "G4_UNOBTAINIUM",
    shape: { type: "box", sizeMm: [40.0, 40.0, 4.0] },
    placement: { parent: "world", positionMm: [0, 0, -60.0] }
  });
}

globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm: 300.0, worldMaterial: "G4_AIR" },
  beam: { particle: "gamma", energyMeV: 0.662, direction: [0, 0, 1], originMm: [0, 0, -120] },
  run: { nEvents: 200, seed: 20261114, threads: 1 },
  geometry: { volumes, refuseOn: "any" }
};
