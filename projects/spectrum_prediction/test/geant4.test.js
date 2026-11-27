'use strict';
// Geant4 atomic inputs: probe rows -> catalogue -> dataset features -> Geant4 architectures and
// ablations. A synthetic probe run stands in for a TRECH run of geant4/atomic_probe.js; the
// committed catalogue is checked against the probe definition it was harvested with.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const S = require('../lib/index.js');
const geant4 = require('../src/geant4.js');
const {train} = require('../src/pipeline.js');

const P = S.features.GEANT4_PROBE;

// A material probe in the ctx.materials / material_probes JSON shape for a pure element.
function probe(symbol, z, options) {
  const o = options || {};
  const atoms = 5e22 + z * 1e21, i = 10 + 12 * z;
  return {name: 'G4_' + symbol, available: true, density_g_per_cm3: 1, mean_excitation_energy_ev: i,
    total_atoms_per_cm3: atoms, elements: [{symbol, z, atoms_per_cm3: atoms, mass_fraction: 1, atomic_mass_amu: 2 * z}],
    interactions: P.energiesEv.filter(e => e !== o.drop).map((e, k) => ({energy_mev: e / 1e6, particle: 'gamma', available: true,
      cross_sections_per_mm: {phot: atoms * 1e-3 * 1e-22 * (1e6 * z) / Math.pow(1 + k, 3)}}))};
}
function syntheticRun(dir, options) {
  const o = options || {};
  const probes = P.symbols.map((s, k) => probe(s, k + 1, {drop: s === o.dropFor ? P.energiesEv[3] : undefined}));
  fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(path.join(dir, 'trech_scores.jsonl'), JSON.stringify({material_probes: probes}) + '\n');
  const prov = {physics_list: o.physicsList || P.physicsList, geant4_version: 'Geant4 version Name: test', config_hash: 'abc', determinism_mode: 'strict', seed: 1};
  fs.writeFileSync(path.join(dir, 'trech_provenance.jsonl'),
    JSON.stringify(Object.assign({phase: 'run_start'}, prov)) + '\n' + JSON.stringify(Object.assign({phase: 'run_end'}, prov)) + '\n');
}

test('a pure-element probe becomes a per-atom row and log features', () => {
  const row = S.features.geant4AtomicRow(probe('C', 6));
  assert.equal(row.symbol, 'C');
  assert.equal(row.mean_excitation_energy_ev, 82);
  // Cross section per volume / atom number density, in barns: the density cancels.
  assert.ok(Math.abs(row.photoabs_barn[0] - 6e6) < 1e-6 * 6e6);
  assert.ok(Math.abs(row.photoabs_barn[2] - 6e6 / 27) < 1e-6 * 6e6);
  const f = S.features.geant4Features(row);
  assert.deepEqual(Object.keys(f), S.features.GEANT4_ATOMIC_FEATURES);
  assert.equal(f.g4_ln_mean_excitation_ev, Math.log(82));
  assert.throws(() => S.features.geant4AtomicRow(probe('C', 6, {drop: P.energiesEv[3]})), /no phot cross section at 50 eV/);
  assert.throws(() => S.features.geant4AtomicRow({name: 'G4_WATER', available: true, elements: [{}, {}]}), /not a pure element/);
  assert.throws(() => S.features.geant4AtomicRow({name: 'G4_X', available: false}), /unavailable/);
});

test('a probe run converts into a catalogue that must match the probe definition', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trech-spectra-g4-'));
  syntheticRun(path.join(dir, 'ok'));
  const catalog = geant4.fromRun(path.join(dir, 'ok'));
  assert.equal(catalog.schema, geant4.SCHEMA);
  assert.equal(catalog.elements.length, 56);
  assert.deepEqual(catalog.elements.map(r => r.z), Array.from({length: 56}, (_, k) => k + 1));
  assert.equal(catalog.provenance.physics_list, undefined);
  assert.equal(catalog.probe.physics_list, P.physicsList);
  assert.equal(Object.keys(geant4.index(catalog)).length, 56);
  syntheticRun(path.join(dir, 'gap'), {dropFor: 'Fe'});
  assert.throws(() => geant4.fromRun(path.join(dir, 'gap')), /G4_Fe has no phot cross section/);
  syntheticRun(path.join(dir, 'list'), {physicsList: 'FTFP_BERT'});
  assert.throws(() => geant4.fromRun(path.join(dir, 'list')), /physics list FTFP_BERT/);
  const stale = JSON.parse(JSON.stringify(catalog));
  stale.probe.energies_ev = [10, 20];
  assert.throws(() => geant4.index(stale), /different probe definition/);
});

test('the committed catalogue covers Z 1-56 with the current probe definition', () => {
  const file = path.join(__dirname, '../catalog/geant4_atomic.json');
  const catalog = JSON.parse(fs.readFileSync(file, 'utf8'));
  const rows = geant4.index(catalog);
  assert.deepEqual(Object.keys(rows), P.symbols.slice());
  assert.match(catalog.provenance.geant4_version, /geant4-11/);
  for (const row of catalog.elements) {
    assert.ok(row.mean_excitation_energy_ev > 0, row.symbol);
    assert.ok(row.photoabs_barn.every(v => Number.isFinite(v) && v > 0), row.symbol);
  }
  // Hydrogen's I is the NIST value Geant4 tabulates; heavier atoms absorb more at 10 keV.
  assert.ok(Math.abs(rows.H.mean_excitation_energy_ev - 19.2) < 0.01);
  assert.ok(rows.Ba.photoabs_barn[9] > rows.C.photoabs_barn[9]);
});

// A tiny dataset whose labels depend on the Geant4 response, so the ablation has a signal.
function dataset() {
  const rows = geant4.index(geant4.fromRun((() => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trech-spectra-g4ds-'));
    syntheticRun(dir);
    return dir;
  })()));
  const facts = {}, atoms = [];
  P.symbols.slice(0, 30).forEach((symbol, k) => {
    const z = k + 1, base = {z, atomic_mass: 2 * z, period: 1 + Math.floor(z / 8), valence_s: 2, valence_p: z % 6, valence_d: 0, valence_f: 0,
      ionization_energy_ev: 5 + (z % 7), electronegativity: 1 + (z % 3), electronegativity_missing: 0, electron_affinity_ev: 0,
      electron_affinity_missing: 1, atomic_radius_pm: 100, atomic_radius_missing: 0, ground_multiplicity: 1, ground_L: 0, ground_J: 0,
      ground_odd: 0, ground_missing: 0};
    const features = Object.assign(base, S.features.geant4Features(rows[symbol]));
    facts[symbol] = {z, symbol, features};
    const target = Array.from({length: S.grid.ATOMIC_GRID.bins}, (_, b) => Math.max(0, Math.sin(b / 5 + features.g4_ln_mean_excitation_ev)));
    atoms.push({id: 'Z' + z, z, symbol, group: z % 2 ? 'odd' : 'even', features, target});
  });
  return {schema: 'trech_spectrum_dataset_v1', grids: {atomic: S.grid.ATOMIC_GRID, molecular: S.grid.MOLECULAR_GRID},
    geant4_atomic: {path: 'synthetic'}, element_facts: facts, atoms, molecules: []};
}

test('Geant4 atomic architectures train, ablate and declare particle-derived inputs', async () => {
  const ds = dataset();
  const archs = ['atomic_ridge', 'atomic_ridge_geant4', 'atomic_mlp_tanh_geant4_only'];
  const {report} = await train(ds, {architectures: archs, folds: 3, repeats: 0, jobs: 1});
  assert.deepEqual(report.ranking.atomic.slice().sort(), archs.slice().sort());
  const ab = report.ablation.find(a => a.kind === 'geant4_atomic');
  assert.equal(ab.without, 'atomic_ridge');
  assert.equal(ab.with, 'atomic_ridge_geant4');
  assert.ok(Number.isFinite(ab.cv_rmse_delta) && Number.isFinite(ab.group_cv_rmse_delta));
  assert.ok(ab.cv_rmse_delta < 0, 'labels built from I must favour the Geant4 inputs');
  const only = report.architectures.find(a => a.name === 'atomic_mlp_tanh_geant4_only');
  assert.deepEqual(S.architectures.inputSet(only.spec.inputs), ['z'].concat(S.features.GEANT4_ATOMIC_FEATURES));
  assert.deepEqual(report.skipped, []);
  // Without a Geant4 catalogue the entries are skipped, and naming one is an error.
  const plain = Object.assign({}, ds);
  delete plain.geant4_atomic;
  const skipped = await train(plain, {architectures: ['atomic'], folds: 3, repeats: 0, groupCv: false, jobs: 1});
  assert.ok(skipped.report.skipped.some(x => x.name === 'atomic_ridge_geant4'));
  assert.ok(!skipped.report.ranking.atomic.some(n => n.endsWith('_geant4') || n.endsWith('_geant4_only')));
  await assert.rejects(train(plain, {architectures: ['atomic_ridge_geant4'], folds: 3, jobs: 1}), /needs Geant4 atomic inputs/);
});

test('cascade sources are validated per entry', () => {
  const ok = S.architectures.catalog(['molecular_mlp_cascade_geant4'])[0];
  assert.equal(S.architectures.cascadeOf(ok), 'geant4');
  assert.equal(S.architectures.cascadeOf(S.architectures.catalog(['molecular_mlp_cascade'])[0]), 'pubchem');
  assert.equal(S.architectures.cascadeOf(S.architectures.catalog(['molecular_mlp'])[0]), null);
  assert.ok(S.architectures.usesGeant4(ok));
  assert.throws(() => S.architectures.validate({name: 'x', task: 'molecular', family: 'mlp', inputs: 'descriptors', cascade: 'geant4',
    layers: []}), /bad cascade/);
  assert.throws(() => S.architectures.validate({name: 'y', task: 'atomic', family: 'ridge', inputs: 'atomic', cascadeSource: 'nist'}),
    /unknown cascadeSource/);
});

test('exports can move to the Geant4-fed chain, never to a mismatched one', async () => {
  const ds = dataset();
  const {models} = await train(ds, {architectures: ['atomic_ridge', 'atomic_ridge_geant4'], folds: 3, repeats: 0, groupCv: false, jobs: 1,
    exports: {spectrum_atomic: 'atomic_ridge_geant4'}});
  assert.deepEqual(models.spectrum_atomic.input_features, S.features.ATOMIC_FEATURES.concat(S.features.GEANT4_ATOMIC_FEATURES));
  assert.equal(models.spectrum_atomic.note.particle_derived_inputs, true);
  assert.equal(models.spectrum_atomic.note.geant4_trained, false);
  // The default molecular export pools the Geant4-fed model: exporting the PubChem-fed atomic
  // model beside it would make TRECH pool a model the molecular rung never saw.
  await assert.rejects(train(ds, {exports: {spectrum_atomic: 'atomic_mlp_tanh'}, folds: 3, jobs: 1}), /pools the geant4 atomic model/);
  await assert.rejects(train(ds, {exports: {spectrum_molecular: 'molecular_mlp_cascade'}, folds: 3, jobs: 1}), /pools the pubchem atomic model/);
  await assert.rejects(train(ds, {exports: {spectrum_atomic: 'molecular_mlp'}, folds: 3, jobs: 1}), /is a molecular entry/);
  await assert.rejects(train(ds, {exports: {spectrum_atomic: 'atomic_knn3_geant4'}, folds: 3, jobs: 1}), /only dense families/);
});
