'use strict';
// Offline end-to-end: synthetic raw cache -> dataset -> train/export -> CLI (incl. --studio mode).
// The fixture exercises plumbing and contracts only; real spectra come from `spectra.cjs collect`.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const S = require('../lib/index.js');
const {build} = require('../src/dataset.js');
const {train, markdown} = require('../src/pipeline.js');
const {slug} = require('../src/collect.js');

const CLI = path.join(__dirname, '../bin/spectra.cjs');
const ELEMENTS = [
  ['1', 'H', 'Hydrogen', '1.008', '1s1', '2.2', '13.598', '0.754', '2S1/2'],
  ['5', 'B', 'Boron', '10.81', '[He]2s2 2p1', '2.04', '8.298', '0.277', '2P°1/2'],
  ['6', 'C', 'Carbon', '12.011', '[He]2s2 2p2', '2.55', '11.260', '1.263', '3P0'],
  ['7', 'N', 'Nitrogen', '14.007', '[He] 2s2 2p3', '3.04', '14.534', '', '4S°3/2'],
  ['8', 'O', 'Oxygen', '15.999', '[He]2s2 2p4', '3.44', '13.618', '1.461', '3P2'],
  ['10', 'Ne', 'Neon', '20.18', '[He]2s2 2p6', '', '21.565', '', '1S0'],
  ['11', 'Na', 'Sodium', '22.99', '[Ne]3s1', '0.93', '5.139', '0.548', '2S1/2'],
  ['12', 'Mg', 'Magnesium', '24.305', '[Ne]3s2', '1.31', '7.646', '', '1S0']
];
const MOLECULES = {
  families: {
    aromatic: ['benzene', 'toluene', 'phenol', 'aniline', 'nitrobenzene'],
    carbonyl: ['acetone', 'acrolein', 'benzaldehyde', 'crotonaldehyde'],
    other: ['hexatriene', 'pyridine', 'missing compound']
  },
  smiles: {benzene: 'C1=CC=CC=C1', toluene: 'CC1=CC=CC=C1', phenol: 'C1=CC=C(C=C1)O', aniline: 'C1=CC=C(C=C1)N',
    nitrobenzene: 'C1=CC=C(C=C1)[N+](=O)[O-]', acetone: 'CC(=O)C', acrolein: 'C=CC=O', benzaldehyde: 'C1=CC=C(C=C1)C=O',
    crotonaldehyde: 'CC=CC=O', hexatriene: 'C=CC=CC=C', pyridine: 'C1=CC=NC=C1'}
};

function sha(text) { return crypto.createHash('sha256').update(text).digest('hex'); }
function writeCache(dir) {
  const entries = {};
  const put = (key, url, value, status) => {
    const text = typeof value === 'string' ? value : JSON.stringify(value);
    fs.writeFileSync(path.join(dir, 'raw', key), text);
    entries[key] = {url, status: status || 200, fetched_utc: '2026-11-07T00:00:00.000Z', sha256: sha(text), bytes: text.length};
  };
  fs.mkdirSync(path.join(dir, 'raw'), {recursive: true});
  const cols = ['AtomicNumber', 'Symbol', 'Name', 'AtomicMass', 'CPKHexColor', 'ElectronConfiguration', 'Electronegativity',
    'AtomicRadius', 'IonizationEnergy', 'ElectronAffinity', 'OxidationStates', 'StandardState', 'MeltingPoint', 'BoilingPoint',
    'Density', 'GroupBlock', 'YearDiscovered'];
  put('pubchem_periodictable.json', 'https://pubchem/periodictable', {Table: {Columns: {Column: cols},
    Row: ELEMENTS.map(e => ({Cell: [e[0], e[1], e[2], e[3], '', e[4], e[5], '120', e[6], e[7], '', 'Gas', '', '', '',
      Number(e[0]) % 2 ? 'Nonmetal' : 'Metal', '']}))}});  // two group blocks for group CV
  for (const e of ELEMENTS) {
    const z = Number(e[0]);
    put(`pubchem_element_${z}_atomic_spectra.json`, 'u', {Record: {Section: [{TOCHeading: 'Properties', Section: [{TOCHeading: 'Atomic Spectra',
      Information: [{ReferenceNumber: 7, URL: `https://physics.nist.gov/cgi-bin/ASD/lines_hold.pl?el=${e[1]}`, Value: {StringWithMarkup: [{String: 'Lines Holdings'}]}}]}]}],
      Reference: [{ReferenceNumber: 7, SourceName: 'NIST Physical Measurement Laboratory'}]}});
    put(`pubchem_element_${z}_ground_level.json`, 'u', {Record: {Section: [{Information: [{Value: {StringWithMarkup: [{String: e[8]}]}}]}]}});
    if (e[1] === 'Mg') continue;  // no line list cached -> rejection, facts still available
    const rows = ['obs_wl_air(nm),ritz_wl_air(nm),intens,Aki(s^-1),Acc,Ei(cm-1),Ek(cm-1),conf_i,term_i,J_i,conf_k,term_k,J_k,g_i,g_k,Type,'];
    const n = e[1] === 'B' ? 3 : 12;  // boron: too few weighted lines -> rejection
    for (let i = 0; i < n; i++) {
      const wl = 210 + ((z * 37 + i * 61) % 780);
      rows.push(`"=""${wl}""","=""""","=""10""","=""${(1 + (i % 4)) * z}e+06""",B,"=""0""","=""1""",,,,,,,2,${1 + (i % 3)},,`);
    }
    put(`nist_asd_${e[1]}_I_200_1000.csv`, S.nist.linesUrl(e[1], 200, 1000), rows.join('\n'));
  }
  let cid = 100;
  for (const name of Object.values(MOLECULES.families).flat()) {
    if (!MOLECULES.smiles[name]) { put(`pubchem_name_${slug(name)}.json`, 'u', {Fault: {Message: 'not found'}}, 404); continue; }
    cid++;
    put(`pubchem_name_${slug(name)}.json`, 'u', {IdentifierList: {CID: [cid]}});
    put(`pubchem_cid_${cid}_properties.json`, 'u', {PropertyTable: {Properties: [{CID: cid, MolecularFormula: 'X', MolecularWeight: '1', SMILES: MOLECULES.smiles[name]}]}});
    if (name === 'pyridine') { put(`pubchem_cid_${cid}_uv.json`, 'u', {Fault: {Code: 'PUGVIEW.NotFound'}}, 404); continue; }
    const wl = 200 + (cid * 23) % 180, le = 2 + (cid % 7) / 3;
    put(`pubchem_cid_${cid}_uv.json`, 'u', {Record: {Section: [{Information: [
      {ReferenceNumber: 1, Value: {StringWithMarkup: [{String: `MAX ABSORPTION (ALCOHOL): ${wl} NM (LOG E= ${le.toFixed(2)}); ${wl + 40} NM (LOG E= ${(le - 0.8).toFixed(2)})`}]}},
      {Value: {StringWithMarkup: [{String: 'UV: 12 (Sadtler Research Laboratories Spectral Collection)'}]}}]}],
      Reference: [{ReferenceNumber: 1, SourceName: 'Hazardous Substances Data Bank (HSDB)'}]}});
  }
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({schema: 'trech_spectrum_cache_v1', entries}));
}

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trech-spectra-'));
  writeCache(path.join(dir, 'cache'));
  const catalog = path.join(dir, 'catalog.json');
  fs.writeFileSync(catalog, JSON.stringify({schema: 'trech_spectrum_catalog_v1', families: MOLECULES.families}));
  return {dir, cache: path.join(dir, 'cache'), catalog};
}

test('dataset build is offline, deterministic and records every rejection', () => {
  const f = fixture();
  const a = build({cacheDir: f.cache, catalog: f.catalog, elements: [1, 20], root: f.dir});
  const b = build({cacheDir: f.cache, catalog: f.catalog, elements: [1, 20], root: f.dir});
  assert.equal(JSON.stringify(a), JSON.stringify(b));
  assert.equal(a.schema, 'trech_spectrum_dataset_v1');
  assert.deepEqual(a.atoms.map(x => x.symbol), ['H', 'C', 'N', 'O', 'Ne', 'Na']);
  assert.equal(Object.keys(a.element_facts).length, 8);
  const reasons = Object.fromEntries(a.rejected.map(r => [r.id, r.reason]));
  assert.match(reasons.Z005_B, /fewer than 5 lines/);
  assert.match(reasons.Z012_Mg, /not cached/);
  assert.match(reasons.pyridine, /no PubChem UV Spectra section/);
  assert.match(reasons['missing compound'], /name lookup failed/);
  assert.equal(a.molecules.length, 10);
  const benzene = a.molecules.find(m => m.name === 'benzene');
  assert.equal(benzene.bands.length, 2);
  assert.equal(benzene.solvent_class, 'protic');
  assert.equal(benzene.target.length, S.grid.MOLECULAR_GRID.bins);
  assert.equal(benzene.sources.uv_reference.source, 'Hazardous Substances Data Bank (HSDB)');
  // Tampered cache bytes are refused rather than silently used.
  fs.appendFileSync(path.join(f.cache, 'raw', 'pubchem_periodictable.json'), ' ');
  assert.throws(() => build({cacheDir: f.cache, catalog: f.catalog, elements: [1, 20]}), /SHA-256/);
});

test('training ranks, ablates and exports engine-loadable models', async () => {
  const f = fixture();
  const dataset = build({cacheDir: f.cache, catalog: f.catalog, elements: [1, 20], root: f.dir});
  const archs = ['atomic_mean', 'atomic_ridge', 'atomic_mlp_tanh', 'molecular_mean', 'molecular_ridge', 'molecular_ridge_cascade',
    'molecular_mlp', 'molecular_mlp_cascade'];
  const run = () => train(dataset, {architectures: archs, folds: 2, familyCv: true, repeats: 2, jobs: 1});
  const {report, models} = await run();
  assert.equal(report.schema, 'trech_spectrum_report_v1');
  assert.deepEqual(Object.keys(models).sort(), ['spectrum_atomic', 'spectrum_molecular']);
  assert.equal(report.ranking.atomic.length, 3);
  assert.equal(report.ranking.molecular.length, 5);
  assert.equal(report.ablation.length, 2);
  const mlp = report.architectures.find(a => a.name === 'molecular_mlp');
  assert.ok(mlp.family_cv.per_family.length >= 2);
  // Atomic split-noise checks: repeated CV scores every training atom once per repetition, and
  // leave-one-chemical-group-out holds out each PubChem group block exactly once.
  assert.equal(report.protocol.atomic_repeated_cv, 2);
  assert.equal(report.protocol.atomic_group_cv, true);
  const atomRidge = report.architectures.find(a => a.name === 'atomic_ridge');
  assert.equal(atomRidge.repeated_cv.repeats, 2);
  assert.equal(atomRidge.repeated_cv.per_fold.folds, 4);
  assert.equal(atomRidge.repeated_cv.pooled.folds, 2);
  assert.ok(Number.isFinite(atomRidge.repeated_cv.pooled.r2.mean));
  const groups = new Set(dataset.atoms.filter(a => report.splits.atomic.train.includes(a.id)).map(a => a.group));
  assert.equal(atomRidge.group_cv.per_group.length, groups.size);
  assert.equal(atomRidge.group_cv.per_group.reduce((n, g) => n + g.n, 0), report.splits.atomic.train.length);
  assert.equal(atomRidge.group_cv.pooled.n, report.splits.atomic.train.length);
  assert.ok(!report.architectures.some(a => a.task === 'molecular' && (a.repeated_cv || a.group_cv)));
  assert.match(markdown(report), /leave-one-chemical-group-out/);
  const atomic = models.spectrum_atomic, molecular = models.spectrum_molecular;
  assert.equal(atomic.output_features.length, S.grid.ATOMIC_GRID.bins);
  assert.deepEqual(atomic.input_features, S.features.ATOMIC_FEATURES);
  assert.deepEqual(molecular.input_features, S.features.MOLECULAR_DESCRIPTORS.concat(S.features.ATOMIC_POOL));
  assert.deepEqual(molecular.trained_scale_bands, ['nano']);
  assert.equal(molecular.note.geant4_trained, false);
  assert.equal(molecular.trained_from.cascade_source, 'atomic_mlp_tanh');
  assert.deepEqual(molecular.trained_from.test_ids, report.splits.molecular.test);
  // Same seed and data -> identical artifacts; the worker path matches the in-thread path.
  const again = await run();
  assert.equal(JSON.stringify(again.models), JSON.stringify(models));
  assert.equal(JSON.stringify(again.report.architectures.map(a => [a.repeated_cv, a.group_cv])),
    JSON.stringify(report.architectures.map(a => [a.repeated_cv, a.group_cv])));
  const parallel = await train(dataset, {architectures: archs, folds: 2, familyCv: true, jobs: 3});
  assert.equal(JSON.stringify(parallel.models), JSON.stringify(models));
  assert.match(markdown(report), /cascade ablation/);
});

test('CLI help, build/train and the --studio JSON-lines mode', () => {
  const f = fixture();
  assert.match(execFileSync(process.execPath, [CLI, '--help'], {encoding: 'utf8'}), /Usage: node projects\/spectrum_prediction/);
  const out = path.join(f.dir, 'run');
  const common = ['--cache-dir', f.cache, '--catalog', f.catalog, '--out', out, '--elements', '1-20'];
  execFileSync(process.execPath, [CLI, 'build', ...common], {encoding: 'utf8'});
  const studio = execFileSync(process.execPath, [CLI, 'train', ...common, '--studio', '--folds', '2', '--no-family-cv', '--jobs', '2',
    '--arch', 'atomic_mlp_tanh,molecular_mean,molecular_mlp_cascade'], {encoding: 'utf8'});
  const events = studio.trim().split('\n').map(line => JSON.parse(line));
  assert.ok(events.some(e => e.event === 'architecture' && e.name === 'molecular_mlp_cascade'));
  const done = events[events.length - 1];
  assert.equal(done.event, 'done');
  const manifest = JSON.parse(fs.readFileSync(path.join(out, 'studio_manifest.json'), 'utf8'));
  assert.equal(manifest.schema, 'trech_spectrum_studio_v1');
  assert.equal(manifest.parameters.data_dir, out);
  for (const name of ['spectrum_atomic', 'spectrum_molecular'])
    assert.equal(sha(fs.readFileSync(path.join(out, 'models', name + '.json'), 'utf8')), manifest.models[name].sha256);
  const report = JSON.parse(fs.readFileSync(path.join(out, 'report.json'), 'utf8'));
  assert.equal(report.dataset_sha256, sha(fs.readFileSync(path.join(out, 'dataset.json'), 'utf8')));
  // Offline collection reuses a complete cache, and refuses to invent an empty one.
  execFileSync(process.execPath, [CLI, 'collect', ...common, '--offline'], {stdio: 'pipe'});
  assert.throws(() => execFileSync(process.execPath, [CLI, 'collect', '--offline', '--catalog', f.catalog,
    '--cache-dir', path.join(f.dir, 'empty_cache')], {stdio: 'pipe'}), /offline: no cached response/);
  assert.throws(() => execFileSync(process.execPath, [CLI, 'train', '--folds', '1'], {stdio: 'pipe'}));
});
