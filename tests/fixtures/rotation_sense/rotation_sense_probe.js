// Rotation-sense probe: where does Geant4 put a volume authored with rotationDeg?
//
// A 100 x 4 x 4 mm water slab at the origin, authored at rotationDeg [25, -35, 40], and a
// 100 MeV proton pencil beam along +z. DetectorConstruction builds R = Rz * Ry * Rx and passes it
// to G4PVPlacement, which reads it as the mother frame's rotation, so the slab is turned by R^T.
// 40 mm along the slab's local +x then lies at (25.10, -30.73, -5.06) mm. Edit BEAM_Y and run:
//
//   trech run tests/fixtures/rotation_sense/rotation_sense_probe.js --output build/rotation_probe
//   grep -o '"total_edep_mev":[0-9.e+-]*' build/rotation_probe/trech_scores.jsonl
//
// Recorded 2026-11-23 (20 events, seed 7), total_edep_mev by beam y at x = 25.10:
//   -30.73 (R^T, what Studio and tools/viz draw)      112.0
//   +21.06 (R, the active rotation drawn before)     7.7e-22
//   +15.87 (Rx * Ry * Rz)                            7.7e-22
//   -21.06 (negated angles, Rz * Ry * Rx order)      7.7e-22
// The same holds for nesting: a pad at local (40, 0, 0) in a frame authored at [0, 0, 30]
// deposited 157 MeV with the beam at (34.64, -20) and 0.27 MeV at (34.64, +20).
const BEAM_Y = -30.73;
globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm: 400.0, worldMaterial: "G4_Galactic" },
  beam: { particle: "proton", energyMeV: 100, direction: [0, 0, 1], originMm: [25.10, BEAM_Y, -150] },
  run: { nEvents: 20, seed: 7, threads: 1 },
  geometry: {
    volumes: [{
      name: "slab", material: "G4_WATER", shape: { type: "box", sizeMm: [100, 4, 4] },
      placement: { parent: "world", positionMm: [0, 0, 0], rotationDeg: [25, -35, 40] }, scoreEdep: true
    }],
    refuseOn: "any"
  }
};
