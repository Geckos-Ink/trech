// Validation scenario (Stage 4): virtual-brain MRI proton densities.
//
// The Geant4 half of the 2D brain-imaging demo. Stages 1-3 discovered the Larmor
// line, produced real-photon tissue contrast, and reconstructed a 1D image line.
// Stage 4 renders an actual 2D image of a virtual brain (a BrainWeb-inspired
// procedural head phantom) whose per-tissue brightness is the Geant4-computed
// proton (1H) number density. This scenario is that Geant4 half: it declares the
// brain-tissue materials, transports a real probe beam through a representative
// slab (real transport + the per-event clock), and -- through the material-probe
// surface -- reports each tissue's proton density (an ignorant material fact,
// never hard-coded). scripts/run_magnetic_resonance_brain.py reads these densities,
// paints them onto the procedural anatomy, and does the 2D k-space acquisition +
// FFT reconstruction that produces the image.
//
// MODELLING NOTE (honest): MRI signal comes from MOBILE (water/lipid) protons, not
// from all bound H. We therefore model each tissue's MRI proton density from its
// mobile-proton fraction relative to water (the biological reference): each tissue
// is water diluted with carbon (an MRI-invisible dry-matter stand-in) so that
// Geant4 reports H density = pd * (pure-water 1H density). The pd values below are
// the literature MRI proton-density fractions; Geant4 turns them into absolute 1H
// number densities that drive the image contrast.
//
// Run (usually via the driver):
//   trech run examples/experiments/testscenario_magnetic_resonance_brain.js \
//        --events 200 --output build/dev/out_mr_brain

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;

// Literature MRI proton-density fractions (mobile 1H relative to pure water).
// tissue -> { pd, materialName }.  csf ~1.0, fat bright, grey > white matter,
// skull near signal-void, air = background.
const BRAIN_TISSUES = [
  { key: "csf",    pd: 1.00, material: "mri_csf" },
  { key: "fat",    pd: 0.90, material: "mri_fat" },
  { key: "grey",   pd: 0.84, material: "mri_grey_matter" },
  { key: "muscle", pd: 0.78, material: "mri_muscle" },
  { key: "white",  pd: 0.72, material: "mri_white_matter" },
  { key: "skull",  pd: 0.12, material: "mri_skull" }
];

// Build a water-content proxy material: water (mass fraction = pd) + carbon
// (the MRI-invisible dry matter). At density 1.0 g/cm^3 Geant4 reports
// H density = pd * pure-water 1H density.
function proxyMaterial(name, pd) {
  const water = Math.max(0.0, Math.min(1.0, pd));
  const dry = 1.0 - water;
  const components = [{ material: "G4_WATER", fraction: water }];
  if (dry > 1e-6) {
    components.push({ element: "C", fraction: dry });
  }
  return { name: name, densityGcm3: 1.0, components: components };
}

const materials = BRAIN_TISSUES.map((t) => proxyMaterial(t.material, t.pd));
const probeMaterials = BRAIN_TISSUES.map((t) => t.material).concat(["G4_AIR"]);

const slabMm = units.cm(2.0);
const worldSizeMm = units.cm(5.0);

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: slabMm,
    mediumMaterial: "mri_grey_matter", // a representative brain slab for the real probe
    temperatureK: 310.15,
    pressureAtm: 1.0
  },
  // Real Geant4 transport through a representative brain slab: the clock + a real
  // edep tally that confirms Geant4 actually built and transported these materials.
  beam: {
    particle: "gamma",
    energyMeV: 0.1,
    originMm: [0, 0, -0.45 * worldSizeMm],
    direction: [0, 0, 1]
  },
  run: { nEvents: 200, seed: 20260705, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "magnetic_resonance_brain"
  },
  materials: materials,
  materialProbe: {
    enable: true,
    materials: probeMaterials
  },
  hooks: { maxEmitsPerCallback: 4, maxEmitPayloadBytes: 131072 }
};

function protonDensityOf(ctx, name) {
  const m = ctx.materials && ctx.materials[name];
  return (m && m.numberDensityPerCm3 && m.numberDensityPerCm3.H) ? m.numberDensityPerCm3.H : 0.0;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", { name: "magnetic_resonance_brain", stage: 4,
      tissues: BRAIN_TISSUES.map((t) => t.key) });
    return { override: { system: { ensemble: "magnetic_resonance_brain" } } };
  },
  onRunStart(ctx) {
    if (ctx.state) { ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0 }; }
  },
  onEventEnd(ctx) {
    if (!ctx.state || !ctx.event) { return; }
    if (!ctx.state.geant4) { ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0 }; }
    ctx.state.geant4.events += 1;
    ctx.state.geant4.totalEdepMeV += ctx.event.edepMeV || 0.0;
  },
  onRunEnd(ctx) {
    const g4 = (ctx.state && ctx.state.geant4) || { events: 0, totalEdepMeV: 0.0 };
    const tissues = {};
    BRAIN_TISSUES.forEach((t) => {
      tissues[t.key] = {
        material: t.material,
        pd_input: t.pd,
        proton_per_cm3: protonDensityOf(ctx, t.material)
      };
    });
    tissues.air = { material: "G4_AIR", pd_input: 0.0, proton_per_cm3: protonDensityOf(ctx, "G4_AIR") };
    ctx.emit("mr_brain_tissues", {
      scenario: "magnetic_resonance_brain",
      note: "per-tissue Geant4 1H number density (mobile-proton model); the driver " +
            "paints these onto a procedural head phantom and reconstructs the 2D image",
      tissues: tissues,
      water_ref_per_cm3: protonDensityOf(ctx, "mri_csf"),
      geant4_drive: { events: g4.events, total_edep_mev: g4.totalEdepMeV }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
