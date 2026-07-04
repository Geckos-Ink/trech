// Validation scenario (Stage 2): virtual-tissue magnetic-resonance contrast.
//
// This is the parameterized, DETECTION-focused half of the magnetic-resonance
// track. Stage 1 (testscenario_magnetic_resonance.js) discovered the Larmor line
// and computed a signal from the Geant4-derived proton density. Stage 2 makes the
// "output photons" REAL: driven by scripts/run_magnetic_resonance_tissues.py, the
// same scenario is run once per tissue, and the number of excitation events for
// each tissue is set proportional to that tissue's Geant4-computed proton (1H)
// number density -- so the emission count "starts from a Geant4 ignorant
// prediction" (a material fact Geant4 computes with no knowledge of NMR). Every
// consequent photon is then produced and transported by Geant4, and a surrounding
// scintillator detector shell scores the REAL deposited energy of all of it. The
// per-tissue detected signal is therefore a genuine Monte-Carlo tally.
//
// Parameters come from globals a tiny wrapper sets before TRECH_INCLUDE-ing this
// file (the driver generates the wrappers):
//   globalThis.MR_TISSUE  -- NIST material name for the phantom (default G4_WATER)
//   globalThis.MR_LABEL   -- human label (default derived from MR_TISSUE)
// The per-tissue event count is passed via the CLI --events override.
//
// Honest scope: Geant4 cannot make nuclear spins radiate RF. The one excitation
// primary per "proton packet" is a proxy for "more protons -> more RF signal";
// what is REAL is that (a) the emission count = Geant4's own proton-density
// prediction and (b) every detected photon's energy is a real Geant4 transport
// tally. The driver reports the measured contrast with its gap to a pure
// proton-density weighting.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

const TISSUE = (typeof globalThis.MR_TISSUE === "string" && globalThis.MR_TISSUE)
  ? globalThis.MR_TISSUE : "G4_WATER";
const LABEL = (typeof globalThis.MR_LABEL === "string" && globalThis.MR_LABEL)
  ? globalThis.MR_LABEL
  : TISSUE.replace(/^G4_/, "").replace(/_ICRP$/, "").replace(/_/g, " ").toLowerCase();

// Reference tissues probed in every run so material_probes always carries the
// full proton-density panel (the driver reads N_H from the probe run; listing
// them here keeps the panel visible in each tissue run too).
const REFERENCE_TISSUES = [
  "G4_WATER",
  "G4_ADIPOSE_TISSUE_ICRP",
  "G4_MUSCLE_SKELETAL_ICRP",
  "G4_BRAIN_ICRP",
  "G4_LUNG_ICRP",
  "G4_BONE_CORTICAL_ICRP"
];

const B0_TESLA = 1.5;               // machine field (carried for provenance/labels)
const voxelSideMm = units.cm(1.0);  // 1 cm tissue voxel
const worldSizeMm = units.cm(6.0);
const shellInnerMm = voxelSideMm * 0.5 + 2.0; // detector shell just outside the voxel
const shellOuterMm = shellInnerMm + 6.0;

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: voxelSideMm,
    mediumMaterial: TISSUE,          // the tissue phantom
    temperatureK: 310.15,
    pressureAtm: 1.0
  },
  // Real excitation primary fired into the voxel. A gamma is only the CARRIER of
  // the excitation -- Geant4 then produces every consequent photon (Compton
  // scatter, fluorescence, secondary bremsstrahlung, ...) which the shell detects.
  // The physics of interest is the Geant4-computed consequence, not the carrier.
  beam: {
    particle: "gamma",
    energyMeV: 0.2,
    originMm: [0, 0, -0.45 * worldSizeMm],
    direction: [0, 0, 1]
  },
  run: { nEvents: 2000, seed: 20260705, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "magnetic_resonance_tissue_" + LABEL.replace(/\s+/g, "_"),
    volumeMm3: Math.pow(voxelSideMm, 3)
  },
  materialProbe: {
    enable: true,
    materials: REFERENCE_TISSUES
  },
  geometry: {
    volumes: [
      // Scintillator detector shell around the voxel: a hollow NaI box catching
      // escaping radiation in ~4pi. Its volume_edep_mev is the REAL detected
      // "output photon" signal (energy of every consequent photon Geant4
      // transported to it). Built as six plates so the beam enters/exits freely
      // while the sides + back + front frame the voxel.
      geometry.boxVolume({
        name: "receiver_coil",
        material: "G4_SODIUM_IODIDE",
        sizeMm: [shellOuterMm * 2, shellOuterMm * 2, 3.0],
        positionMm: [0, 0, shellInnerMm + 1.5],
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      }),
      geometry.boxVolume({
        name: "receiver_coil_side_px",
        material: "G4_SODIUM_IODIDE",
        sizeMm: [3.0, shellOuterMm * 2, shellOuterMm * 2],
        positionMm: [shellInnerMm + 1.5, 0, 0],
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      }),
      geometry.boxVolume({
        name: "receiver_coil_side_nx",
        material: "G4_SODIUM_IODIDE",
        sizeMm: [3.0, shellOuterMm * 2, shellOuterMm * 2],
        positionMm: [-(shellInnerMm + 1.5), 0, 0],
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      }),
      geometry.boxVolume({
        name: "receiver_coil_side_py",
        material: "G4_SODIUM_IODIDE",
        sizeMm: [shellOuterMm * 2, 3.0, shellOuterMm * 2],
        positionMm: [0, shellInnerMm + 1.5, 0],
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      }),
      geometry.boxVolume({
        name: "receiver_coil_side_ny",
        material: "G4_SODIUM_IODIDE",
        sizeMm: [shellOuterMm * 2, 3.0, shellOuterMm * 2],
        positionMm: [0, -(shellInnerMm + 1.5), 0],
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      })
    ]
  },
  hooks: {
    maxEmitsPerCallback: 4,
    maxEmitPayloadBytes: 131072
  }
};

function protonDensityOf(ctx, name) {
  const m = ctx.materials && ctx.materials[name];
  if (m && m.numberDensityPerCm3 && m.numberDensityPerCm3.H) {
    return m.numberDensityPerCm3.H;
  }
  return 0.0;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "magnetic_resonance_tissue",
      stage: 2,
      tissue: TISSUE,
      label: LABEL,
      b0_tesla: B0_TESLA
    });
    return { override: { system: { ensemble: "magnetic_resonance_tissue_" + LABEL.replace(/\s+/g, "_") } } };
  },
  onRunStart(ctx) {
    if (ctx.state) {
      ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0, totalStepCount: 0 };
    }
  },
  onEventEnd(ctx) {
    if (!ctx.state || !ctx.event) { return; }
    if (!ctx.state.geant4) {
      ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0, totalStepCount: 0 };
    }
    ctx.state.geant4.events += 1;
    ctx.state.geant4.totalEdepMeV += ctx.event.edepMeV || 0.0;
    ctx.state.geant4.totalStepCount += ctx.event.totalStepCount || 0;
  },
  onRunEnd(ctx) {
    const g4 = (ctx.state && ctx.state.geant4) || { events: 0, totalEdepMeV: 0.0, totalStepCount: 0 };
    // Geant4-derived proton densities for the whole reference panel (so the
    // driver can read them from any run, not only the probe run).
    const protonPanel = {};
    REFERENCE_TISSUES.forEach((name) => { protonPanel[name] = protonDensityOf(ctx, name); });
    ctx.emit("mr_tissue_point", {
      tissue: TISSUE,
      label: LABEL,
      b0_tesla: B0_TESLA,
      proton_per_cm3: protonDensityOf(ctx, TISSUE),
      proton_panel_per_cm3: protonPanel,
      events: g4.events,
      geant4_drive: {
        events: g4.events,
        total_edep_mev: g4.totalEdepMeV,
        total_step_count: g4.totalStepCount
      },
      // The REAL detected "output photon" signal (receiver_coil volume_edep_mev)
      // lives in trech_scores.jsonl; the driver reads it from there and pairs it
      // with proton_per_cm3 to build the tissue-contrast table.
      note: "detected signal = sum of receiver_coil volume_edep_mev in trech_scores.jsonl"
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
