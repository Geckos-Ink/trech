// CTest fixture (trech_ml_registry_quickjs): js/trech_ml.js runs in the QuickJS host, reads a
// registry index with TRECH_READ_JSON relative to this file, refuses a structure conflict, and
// turns the active checkpoint into a models[] entry. No model is loaded by `trech inspect`.
TRECH_INCLUDE("../../../js/trech_ml.js");
const definition = TRECH_ML.defineModel({
  name: "fixture_model", scale: "meso", inputs: ["a", "b"], outputs: ["y"],
  structure: { family: "mlp", width: 4, depth: 1 }
});
const entry = TRECH_ML.modelEntry(definition, { index: "index.json" });
let conflict = "none";
const wide = TRECH_ML.defineModel({ name: "fixture_model_wide", inputs: ["a", "b"], outputs: ["y"],
  structure: { family: "mlp", width: 8, depth: 1 } });
try {
  // A width-8 definition must never receive the stored width-4 weights.
  TRECH_ML.resolve(TRECH_READ_JSON("index.json"), "fixture_model", { version: 1, structure_id: wide.structure_id });
} catch (error) {
  conflict = /structure conflict/.test(error.message) ? "refused" : error.message;
}
if (definition.structure_id !== "s096d90cce414") throw new Error("structure id drifted: " + definition.structure_id);
globalThis.TRECH_CONFIG = {
  detector: { worldSizeMm: 10.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 1, seed: 1 },
  determinism: { mode: "predictive" },
  models: [{ name: entry.name, path: entry.path, scale: entry.scale }],
  ml_fixture: { resolved: entry.registry.checkpoint + ":" + entry.registry.resolved_by, conflict: conflict }
};
