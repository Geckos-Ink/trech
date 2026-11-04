// Predict before transport, then run an independent Geant4 Monte Carlo check.
// Higher-scale fractions come only from the learned observer model.
TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_molecular_particle.js");
const particle = globalThis.TRECH_MOLECULAR_PARTICLE;
const material = TRECH_PARAMETER("material");
const energyKev = TRECH_PARAMETER("energy_kev");
const halfLengthMm = TRECH_PARAMETER("half_length_mm");
const mode = TRECH_PARAMETER("mode");
const events = TRECH_PARAMETER("events");
// Authored composition inventories only: these are not measured material
// densities, molecular geometries, bond laws or response targets.
const authoredCounts = {
  hexane: {C: 6, H: 14}, acetone: {C: 3, H: 6, O: 1}, urea: {C: 1, H: 4, N: 2, O: 1}
};
let inventory;
if (authoredCounts[material]) {
  const counts = authoredCounts[material];
  const elements = [];
  for (const el of Object.keys(counts))
    for (let i = 0; i < counts[el]; ++i) elements.push(el);
  inventory = {counts, elements};
} else {
  // Only the existing authored element inventory is used. Its QM scans,
  // charges, coordinates and PubChem comparisons do not enter inference.
  inventory = TRECH_READ_JSON("../../../data/molecular_series/" + material + ".reference.json");
}
const spec = {elements: inventory.elements.slice(), counts: Object.assign({}, inventory.counts)};
const masses = particle.data.atomic_masses;
const symbols = Object.keys(spec.counts);
const totalMass = symbols.reduce((sum, el) => sum + masses[el] * spec.counts[el], 0);
const scope = "Experimental Geant4-trained particle → atomic → nano composition → meso transport candidate; " +
  "central gamma source in a unit-density homogeneous CHNO cube, QBBC_LIV, 10–30 keV. " +
  "No bound molecular dynamics, isomer response, physical density claim or independent experimental validation.";

globalThis.TRECH_CONFIG = {
  detector: {worldSizeMm: 2 * halfLengthMm, worldMaterial: "molecular_probe", mediumBoxMm: 0},
  beam: {particle: "gamma", energyMeV: energyKev * 0.001, direction: [0, 0, 1], originMm: [0, 0, 0]},
  physics: {list: "QBBC_LIV"},
  run: {nEvents: events, seed: 20261104, threads: 1},
  determinism: {mode},
  materials: [{name: "molecular_probe", densityGcm3: 1,
    components: symbols.map(el => ({element: el, fraction: masses[el] * spec.counts[el] / totalMass}))}],
  materialProbe: {enable: true, materials: ["molecular_probe"]},
  models: particle.models().concat([
    {name: "particle_observer", scale: "meso", path: "data/particle_observer/observer_response.json"}
  ]),
  hooks: {registered: ["onRunStart"], maxEmitsPerCallback: 2, maxEmitPayloadBytes: 65536}
};

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const probe = ctx.materials && ctx.materials.molecular_probe;
    if (!probe || !probe.available || !probe.numberDensityPerCm3)
      throw new Error("Observer inference requires a live Geant4 molecular_probe");
    const representative = symbols[0];
    const moleculeDensity = probe.numberDensityPerCm3[representative] / spec.counts[representative];
    if (!Number.isFinite(moleculeDensity) || moleculeDensity <= 0)
      throw new Error("Missing Geant4 molecular number density");
    // Unit/count conversion only: mm → cm (0.1), barn → cm² (1e-24).
    // No attenuation formula or current-run tally supplies either prediction.
    const arealDensity = moleculeDensity * halfLengthMm * 1e-25;
    const atoms = particle.inferAtoms(ctx, spec, energyKev * 1000);
    let cascade = null;
    if (atoms) {
      const seed = Object.assign({}, atoms.pooled, {
        molecule_areal_density_barn_inv: arealDensity, photon_energy_kev: energyKev
      });
      cascade = ctx.cascade(seed, ["particle_molecular", "particle_observer"]);
      if (!cascade || cascade.__cascade.stagesRun !== 2)
        throw new Error("Missing learned composition/observer response; refusing fabricated outputs");
      for (const key of ["uncollided_fraction", "deposited_energy_fraction"])
        if (!Number.isFinite(cascade[key]) || cascade[key] < 0 || cascade[key] > 1)
          throw new Error("Observer model produced an invalid fraction: " + key);
    } else if (mode === "predictive") {
      throw new Error("Missing learned atomic response; refusing fabricated outputs");
    }
    let heldoutResidual = null;
    if (cascade) {
      const observerTrace = cascade.__cascade.trace.find(stage => stage.model === "particle_observer");
      const accuracy = observerTrace && observerTrace.outputAccuracy;
      if (accuracy) {
        const residual = {};
        for (const key of ["uncollided_fraction", "deposited_energy_fraction"])
          if (accuracy[key] && Number.isFinite(accuracy[key].rmse) && accuracy[key].rmse >= 0)
            residual[key] = accuracy[key].rmse;
        if (Object.keys(residual).length) heldoutResidual = residual;
      }
    }
    const prediction = {
      schema: "trech_particle_observer_prediction_v1", material, mode,
      energy_kev: energyKev, half_length_mm: halfLengthMm, full_length_mm: 2 * halfLengthMm,
      proxy_density_g_per_cm3: probe.density_g_per_cm3,
      molecule_number_density_per_cm3: moleculeDensity,
      molecule_areal_density_barn_inv: arealDensity,
      atom_count: spec.elements.length, counts: spec.counts,
      prediction_available: !!cascade,
      predicted: {
        uncollided_fraction: cascade ? cascade.uncollided_fraction : null,
        deposited_energy_fraction: cascade ? cascade.deposited_energy_fraction : null
      },
      heldout_residual_rmse: heldoutResidual,
      uncertainty_scope: "Global model-held-out residual RMSE in fraction units; not input-conditional confidence or a calibrated interval.",
      molecular_sigma_barn: cascade ? {
        phot: cascade.molecule_phot_barn, compt: cascade.molecule_compt_barn, Rayl: cascade.molecule_Rayl_barn
      } : null,
      atomic_trace: atoms ? atoms.atomic_trace : null,
      cascade_trace: cascade ? cascade.__cascade : null,
      atomic_inference_count: atoms ? atoms.atomic_inference_count : 0,
      cascade_inference_count: cascade ? cascade.__cascade.stagesRun : 0,
      inference_count: atoms ? atoms.atomic_inference_count + cascade.__cascade.stagesRun : 0,
      expected_inference_count: mode === "predictive" ? spec.elements.length + 2 : 0,
      prediction_phase: "onRunStart_before_Monte_Carlo_events",
      fidelity: "geant4_mc_trained_candidate", geant4_trained: true, measured: false, mc_sampled: false,
      label_source: "Lower stages: Geant4 interaction tables; observer stage: independent Geant4 Monte Carlo runs",
      units: {cross_section: "barn", energy: "keV", length: "mm", areal_density: "barn^-1",
        predicted_outputs: "dimensionless fractions of incident photon count / incident energy"},
      scope
    };
    ctx.emit("observer_prediction", prediction);
    ctx.emit("material_frame", TRECH_VIEWS.particle_observer_cascade.frame(
      globalThis.TRECH_HELPERS.observer, prediction));
  }
};
