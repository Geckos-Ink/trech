TRECH_INCLUDE("../../../js/trech_solution_processes.js");

// Preparation and intent only. The libraries own the process details.
const experiment = TRECH_SOLUTION_PROCESSES.solution({
  water: {parcels: 256}, salt: {formula: "NaCl", parcels: 64},
  parcelAmountMol: 1e-6, temperatureK: 293.15
}).mix().heat({bathTemperatureK: 373.15})
  .evaporate({remainingFraction: 0.05}).crystallize({solidFraction: 0.95}).compile();
const process = experiment.create();

globalThis.TRECH_CONFIG = {
  run: {nEvents: 8, seed: 424242, threads: 1}, determinism: {mode: "predictive"},
  detector: {worldSizeMm: 100, worldMaterial: "G4_WATER"},
  beam: {particle: "gamma", energyMeV: 0.1, direction: [0, 0, 1]},
  materials: [{name: "salt", densityGcm3: 2.16,
    components: [{element: "Na", atoms: 1}, {element: "Cl", atoms: 1}]}],
  materialProbe: {enable: true, materials: ["G4_WATER", "salt"]},
  hooks: {enable: true, inputs: {recipe: experiment.plan}}
  // Attach validated scale-tagged models with matching operator_role / element_kind.
};

globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  ctx.emit("process_recipe_state", process.step(ctx, 0.1));
}};
