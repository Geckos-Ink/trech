'use strict';
// Convert one TRECH run of geant4/atomic_probe.js into catalog/geant4_atomic.json.
//
// The run's trech_scores.jsonl carries `material_probes` (G4_<symbol> for Z 1-56) and its
// trech_provenance.jsonl the Geant4 version, physics list and config hash. Every probed element
// must be available with a photo-absorption cross section at every GEANT4_PROBE energy; anything
// else is an error, so a partial harvest never reaches the dataset.
const fs = require('node:fs');
const path = require('node:path');
const S = require('../lib/index.js');

const SCHEMA = 'trech_spectrum_geant4_atomic_v1';

function jsonLines(file) {
  return fs.readFileSync(file, 'utf8').split('\n').filter(line => line.trim()).map(line => JSON.parse(line));
}

function fromRun(runDir) {
  const scoresFile = path.join(runDir, 'trech_scores.jsonl'), provenanceFile = path.join(runDir, 'trech_provenance.jsonl');
  const scores = jsonLines(scoresFile).find(r => Array.isArray(r.material_probes));
  if (!scores) throw new Error(scoresFile + ' has no material_probes record');
  const provenance = jsonLines(provenanceFile).filter(r => r.phase === 'run_end').pop();
  if (!provenance) throw new Error(provenanceFile + ' has no run_end record');
  const P = S.features.GEANT4_PROBE;
  if (provenance.physics_list !== P.physicsList)
    throw new Error('probe run used physics list ' + provenance.physics_list + ', expected ' + P.physicsList);
  const byName = {};
  for (const probe of scores.material_probes) byName[probe.name] = probe;
  const rows = P.symbols.map((symbol, i) => {
    const probe = byName['G4_' + symbol];
    if (!probe) throw new Error('probe run has no G4_' + symbol);
    const row = S.features.geant4AtomicRow(probe);
    if (row.symbol !== symbol || row.z !== i + 1) throw new Error('G4_' + symbol + ' resolved to ' + row.symbol + ' (Z ' + row.z + ')');
    // Unrounded, so a scenario that recomputes the row from its live probe gets the same doubles.
    return {symbol, z: row.z, mean_excitation_energy_ev: row.mean_excitation_energy_ev, photoabs_barn: row.photoabs_barn};
  });
  return {
    schema: SCHEMA,
    note: 'Geant4 atomic response per element: mean excitation energy I (G4IonisParamMat) and the ' +
      'per-atom photo-absorption cross section (G4EmCalculator "' + P.process + '" per volume / atom number density). ' +
      'Tabulated Geant4 data queried by the engine, not a Monte-Carlo tally; used only as atomic model inputs.',
    probe: {scenario: 'projects/spectrum_prediction/geant4/atomic_probe.js', physics_list: P.physicsList, particle: 'gamma',
      process: P.process, energies_ev: P.energiesEv.slice(), cross_section_unit: 'barn/atom', mean_excitation_unit: 'eV'},
    provenance: {geant4_version: provenance.geant4_version, config_hash: provenance.config_hash,
      determinism_mode: provenance.determinism_mode, seed: provenance.seed},
    elements: rows
  };
}

// Validate a stored catalogue against the current probe definition; returns symbol -> row.
function index(catalog) {
  const P = S.features.GEANT4_PROBE;
  if (!catalog || catalog.schema !== SCHEMA) throw new Error('not a ' + SCHEMA + ' catalogue');
  if (catalog.probe.physics_list !== P.physicsList || catalog.probe.process !== P.process ||
      JSON.stringify(catalog.probe.energies_ev) !== JSON.stringify(P.energiesEv))
    throw new Error('Geant4 atomic catalogue was harvested with a different probe definition; re-run spectra.cjs geant4');
  const out = {};
  for (const row of catalog.elements) out[row.symbol] = row;
  return out;
}

module.exports = {SCHEMA, fromRun, index};
