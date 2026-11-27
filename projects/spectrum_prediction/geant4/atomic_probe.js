// Geant4 atomic-response harvest for the spectrum-prediction atomic rung.
//
// One TRECH run probes the NIST material G4_<symbol> of every element the dataset knows
// (atoms and the elements molecules pool over). Geant4 reports, per element:
//   - the mean excitation energy I of G4IonisParamMat (a log moment of the element's dipole
//     oscillator-strength distribution), and
//   - G4EmCalculator photo-absorption ("phot") cross sections per volume at fixed photon
//     energies, divided by the atom number density into a per-atom cross section.
// `node projects/spectrum_prediction/bin/spectra.cjs geant4 --run <output dir>` converts the run's
// trech_scores.jsonl into catalog/geant4_atomic.json. These are tabulated Geant4 responses, not
// Monte-Carlo tallies, and they are model inputs only: the labels stay measured NIST lines.
TRECH_INCLUDE("../lib/index.js");
const SP = globalThis.TRECH_SPECTRA;
const symbols = SP.features.GEANT4_PROBE.symbols;
globalThis.TRECH_CONFIG = {
  environment: {worldSizeMm: 20, worldMaterial: "G4_Galactic"},
  physics: {list: SP.features.GEANT4_PROBE.physicsList},
  beam: {particle: "gamma", energyMeV: 0.001, direction: [0, 0, 1]},
  run: {nEvents: 1, seed: 20261127, threads: 1},
  determinism: {mode: "strict"},
  materialProbe: {enable: true, materials: symbols.map(s => "G4_" + s),
    interactions: {particle: "gamma", processes: ["phot"],
      energiesMeV: SP.features.GEANT4_PROBE.energiesEv.map(e => e / 1e6)}}
};
