// Optics surrogate training panel.
//
// Derives visible-band optical constants (n, absorption, scatter) for a broad
// set of transparent materials via the same MolecularOptics extractor the
// physics demos use (Geant4 atomic cross sections -> Kramers-Kronig + f-sum
// valence oscillator). One run emits a `derived_optics` block per material
// into trech_viz_scene.json; tools/torch/.../train_optics_surrogate.py harvests
// that as composition -> optics training data.
//
// Materials are declared by chemical composition only (G4 NIST component refs)
// with handbook densities so the derived electron density / n are physical. No
// handbook refractive index is fed to the engine -- n is always derived. The
// handbook n values live only in the validation script
// (scripts/validate_optics_surrogate.py) as the held-out comparison target.
//
// Run:
//   trech run examples/experiments/optics_training_panel.js \
//        --events 1 --output build/dev/out_optics_panel

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
const units = helpers.units;
const geometry = helpers.geometry;

// name, G4 NIST component, handbook density (g/cm^3).  Spread of compositions
// (hydrocarbons, oxides, halides, alcohols) and densities (0.001 .. 3.18).
const panel = [
  ["air",          "G4_AIR",              0.001225],
  ["water",        "G4_WATER",            0.998],
  ["ethanol",      "G4_ETHYL_ALCOHOL",    0.789],
  ["glycerol",     "G4_GLYCEROL",         1.261],
  ["pmma",         "G4_PLEXIGLASS",       1.18],
  ["polyethylene", "G4_POLYETHYLENE",     0.94],
  ["polystyrene",  "G4_POLYSTYRENE",      1.06],
  ["pvc",          "G4_POLYVINYL_CHLORIDE", 1.38],
  ["teflon",       "G4_TEFLON",           2.20],
  ["silica",       "G4_SILICON_DIOXIDE",  2.20],
  ["pyrex",        "G4_Pyrex_Glass",      2.23],
  ["nai",          "G4_SODIUM_IODIDE",    3.667],
  ["lif",          "G4_LITHIUM_FLUORIDE", 2.635],
  ["caf2",         "G4_CALCIUM_FLUORIDE", 3.18]
];

const materials = panel.map(([name, ref, densityGcm3]) => ({
  name: name,
  densityGcm3: densityGcm3,
  components: [{ material: ref, fraction: 1.0 }]
}));

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.cm(30.0), worldMaterial: "air" },
  beam: { particle: "opticalphoton", energyMeV: 2.25e-6, direction: [0, 0, 1] },
  run: { nEvents: 1, seed: 20260605 },
  determinism: { mode: "strict" },
  materials: materials,
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      energyMinEv: 1.6,
      energyMaxEv: 3.2,
      nEnergyBins: 16,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: true
    }
  },
  viz: { enable: true, maxTrajectories: 1 },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "sample",
        material: "water",
        sizeMm: [units.cm(5.0), units.cm(5.0), units.cm(5.0)],
        positionMm: [0, 0, 0]
      })
    ]
  }
};
