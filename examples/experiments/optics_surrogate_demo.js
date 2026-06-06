// Optics surrogate demo: show the LibTorch-free ridge surrogate correcting a
// material the pure f-sum physics extractor cannot reach.
//
// The MolecularOptics extractor derives n from Geant4 cross sections + the
// f-sum valence oscillator with NO handbook input. That works well for light-
// element dielectrics (water, silica), but it cannot capture the high-Z
// valence response of sodium iodide (NaI) -- it derives n ~ 1.33 where the
// handbook is ~1.775. The optics surrogate is an opt-in ML layer trained on the
// material panel (composition -> handbook n); leave-one-out validated for
// generalisation. When `optics.derive.surrogateModelPath` points at the
// exported ridge model, the engine shifts each material's derived dispersion
// curve to the surrogate's level, so transport (RINDEX) uses the learned n.
//
// This scenario opts IN (unlike the headline glass-of-water demos, which stay
// pure physics). Compare the derived_optics block here against a run without
// the surrogate to see the correction.
//
// Run (export the model first if needed):
//   trech run examples/experiments/optics_training_panel.js --events 1 \
//        --output build/dev/out_optics_panel
//   python3 scripts/validate_optics_surrogate.py --run build/dev/out_optics_panel \
//        --no-write --export data/optics_surrogate_ridge.json
//   trech run examples/experiments/optics_surrogate_demo.js --events 1 \
//        --output build/dev/out_optics_surrogate

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

// name, G4 NIST component, handbook density (g/cm^3). NaI is the headline case;
// water and silica are light-element controls the f-sum already gets right.
const panel = [
  ["water",  "G4_WATER",           0.998],
  ["silica", "G4_SILICON_DIOXIDE", 2.20],
  ["nai",    "G4_SODIUM_IODIDE",   3.667]
];

const materials = panel.map(([name, ref, densityGcm3]) => ({
  name: name,
  densityGcm3: densityGcm3,
  components: [{ material: ref, fraction: 1.0 }]
}));

globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: units.cm(30.0), worldMaterial: "air" },
  beam: { particle: "opticalphoton", energyMeV: 2.25e-6, direction: [0, 0, 1] },
  run: { nEvents: 1, seed: 20260606 },
  determinism: { mode: "predictive" },
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
      writeSpectrum: true,
      // Opt in to the anchor-trained ridge surrogate (LibTorch-free). Off in
      // the headline physics demos; here it corrects the NaI residual.
      surrogateModelPath: "data/optics_surrogate_ridge.json"
    }
  },
  viz: { enable: true, maxTrajectories: 1 },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "sample",
        material: "nai",
        sizeMm: [units.cm(5.0), units.cm(5.0), units.cm(5.0)],
        positionMm: [0, 0, 0]
      })
    ]
  }
};
