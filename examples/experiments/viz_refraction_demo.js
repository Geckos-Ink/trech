// 3D refraction demo: a monochromatic optical-photon beam enters a glass slab
// containing a water cube, then exits back into air.  The point of this
// scenario is to *show* refraction in a 3D viewer where every material's
// optical response (n, absorption, scatter) was derived by TRECH from
// Geant4-level particle interaction cross sections, not from hardcoded
// classical optics.
//
//   - `materials` declares air / glass / water by chemical composition only.
//   - `optics.derive.enable = true` runs the MolecularOptics extractor: for
//     each material it samples Geant4's photoelectric + Compton + Rayleigh
//     cross sections, computes the imaginary part of the refractive index
//     from Beer-Lambert, and applies a Kramers-Kronig transform to obtain the
//     real part at visible wavelengths.  Those derived n / absLength /
//     scatLength tables are then fed to Geant4's optical photon transport
//     (which does the actual statistical refraction sampling at every
//     interface).
//   - `optics.derive.validate.references` lets us record the delta against
//     handbook values.  References never feed back into physics.
//   - `viz.enable = true` makes the engine emit `trech_viz_scene.json`
//     (world + volumes + derived material colors) and
//     `trech_viz_trajectories.jsonl` (sampled photon polylines).
//   - The emitter is a tagged container box so the Python viewer can render
//     it with a forced look ("the light source is white" is a viz choice, not
//     a physics statement).
//
// Run: trech run examples/experiments/viz_refraction_demo.js \
//        --events 200 --output build/dev/out_viz_refraction
// View: python -m trech_viz \
//        --scene build/dev/out_viz_refraction/trech_viz_scene.json \
//        --trajectories build/dev/out_viz_refraction/trech_viz_trajectories.jsonl

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const worldSizeMm = units.cm(20.0);
const glassSizeMm = [units.cm(8.0), units.cm(8.0), units.cm(4.0)];
const waterSizeMm = [units.cm(6.0), units.cm(6.0), units.cm(2.5)];
const emitterSizeMm = [units.cm(2.0), units.cm(2.0), units.cm(0.5)];

const airMaterial = helpers.materialRegistry.fromPreset("air");
const glassMaterial = helpers.materialRegistry.fromPreset("glass");
const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

// Oblique direction so refraction is visually obvious.
const sinTheta = Math.sin(35 * Math.PI / 180);
const cosTheta = Math.cos(35 * Math.PI / 180);

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "air",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "opticalphoton",
    // ~ 2.25 eV ≈ 550 nm (green).  Geant4 takes MeV.
    energyMeV: 2.25e-6,
    direction: [sinTheta, 0.0, cosTheta]
  },
  run: { nEvents: 200, seed: 20260522 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "viz_refraction"
  },
  materials: [airMaterial, glassMaterial, waterMaterial],
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      energyMinEv: 1.6,        // ~ 775 nm (near-IR edge of visible)
      energyMaxEv: 3.2,        // ~ 387 nm (near-UV edge of visible)
      nEnergyBins: 12,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: true,
      validate: {
        enable: true,
        references: [
          { material: "water", energyEv: 2.25, refractiveIndex: 1.333, source: "CRC Handbook" },
          { material: "glass", energyEv: 2.25, refractiveIndex: 1.46, source: "Schott BK7 typical" },
          { material: "air", energyEv: 2.25, refractiveIndex: 1.000293, source: "CRC Handbook" }
        ]
      }
    }
  },
  viz: {
    enable: true,
    maxTrajectories: 192,
    sampleEveryNth: 1,
    maxSegmentsPerTrajectory: 256,
    includeNonOptical: false,
    recordVertices: true
  },
  geometry: {
    volumes: [
      // The light emitter is a thin white slab placed above the world center.
      // It carries a viz tag so the Python viewer renders it as a forced
      // light source (visualization choice, not physics).
      geometry.boxVolume({
        name: "emitter",
        material: "air",
        sizeMm: emitterSizeMm,
        positionMm: [
          -0.5 * worldSizeMm * sinTheta,
          0.0,
          -0.5 * worldSizeMm * cosTheta + units.cm(1.0)
        ],
        tags: ["viz_emitter", "viz_forced_white"]
      }),
      // Glass slab — composition-only (SiO2) so the engine derives n/abs/scat
      // from Geant4 atomic cross sections.
      geometry.boxVolume({
        name: "glass_slab",
        material: "glass",
        sizeMm: glassSizeMm,
        positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true,
        tags: ["dielectric", "glass"]
      }),
      // Water bulk sits inside the glass slab.
      geometry.boxVolume({
        name: "water_bulk",
        material: "water",
        sizeMm: waterSizeMm,
        parent: "glass_slab",
        positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true,
        tags: ["fluid", "water"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
