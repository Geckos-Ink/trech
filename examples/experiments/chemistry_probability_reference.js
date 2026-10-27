// Joint electronic comparison and Geant4 nuclear initial-state ensembles.
// The approach is a declared parameter scan, not inferred dynamics.
globalThis.TRECH_CHEMISTRY_SCENE_FILE = "../../data/chemistry_probability/water_deuterium.json";
globalThis.TRECH_CHEMISTRY_NUCLEAR_SAMPLES = 8;
TRECH_INCLUDE("chemistry_mode.js");
