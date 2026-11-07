#!/usr/bin/env node
'use strict';
// TRECH spectrum-prediction subproject CLI (Node.js >= 18; no npm dependencies).
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const ROOT = path.resolve(__dirname, '../../..');
const PROJECT = path.resolve(__dirname, '..');
const DEFAULTS = {
  cacheDir: path.join(ROOT, 'build/spectrum_prediction/cache'),
  out: path.join(ROOT, 'build/spectrum_prediction/run'),
  catalog: path.join(PROJECT, 'catalog/molecules.json'),
  publish: path.join(ROOT, 'data/spectrum_prediction'),
  elements: [1, 56]
};
const USAGE = `Usage: node projects/spectrum_prediction/bin/spectra.cjs <command> [options]

Commands
  collect   Fetch PubChem element/compound records and the NIST ASD line lists PubChem links to
  build     Normalize the cache into <out>/dataset.json (offline)
  train     Cross-validate, test and export every architecture in lib/architectures.js
  all       collect + build + train
  publish   Copy <out>/{dataset,report,models} into data/spectrum_prediction (committed fixture)

Options
  --cache-dir DIR     raw response cache          (default build/spectrum_prediction/cache)
  --out DIR           run output directory        (default build/spectrum_prediction/run)
  --dataset FILE      dataset for train           (default <out>/dataset.json)
  --catalog FILE      molecule name catalogue     (default projects/spectrum_prediction/catalog/molecules.json)
  --elements A-B      atomic-number range         (default 1-56)
  --arch a,b          train only these architectures or tasks (atomic, molecular)
  --folds K           cross-validation folds      (default 5)
  --no-family-cv      skip leave-one-family-out molecular CV
  --jobs N            molecular architectures trained in parallel worker threads (default: CPU count, max 8)
  --offline           never use the network; missing cache entries become rejections
  --refresh           re-download cached responses
  --studio            UI extension mode: JSON-lines progress on stdout + <out>/studio_manifest.json
  -h, --help          show this help

Labels are measured spectra (NIST ASD, PubChem/HSDB). Trained models are learned comparisons,
not Geant4 results. See docs/spectrum_prediction.md.
`;

function parseArgs(argv) {
  const opts = Object.assign({}, DEFAULTS, {command: argv[0]});
  const value = (i, name) => { if (argv[i + 1] === undefined || argv[i + 1].startsWith('--')) throw new Error(name + ' needs a value'); return argv[i + 1]; };
  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--cache-dir') opts.cacheDir = path.resolve(value(i++, a));
    else if (a === '--out') opts.out = path.resolve(value(i++, a));
    else if (a === '--dataset') opts.dataset = path.resolve(value(i++, a));
    else if (a === '--catalog') opts.catalog = path.resolve(value(i++, a));
    else if (a === '--elements') {
      const m = /^(\d+)-(\d+)$/.exec(value(i++, a));
      if (!m || Number(m[1]) < 1 || Number(m[2]) > 118 || Number(m[1]) > Number(m[2])) throw new Error('--elements expects A-B within 1-118');
      opts.elements = [Number(m[1]), Number(m[2])];
    } else if (a === '--arch') opts.architectures = value(i++, a).split(',').map(s => s.trim()).filter(Boolean);
    else if (a === '--folds') { opts.folds = Number(value(i++, a)); if (!(opts.folds >= 2 && opts.folds <= 20)) throw new Error('--folds expects 2-20'); }
    else if (a === '--no-family-cv') opts.familyCv = false;
    else if (a === '--jobs') { opts.jobs = Number(value(i++, a)); if (!(opts.jobs >= 1 && opts.jobs <= 64)) throw new Error('--jobs expects 1-64'); }
    else if (a === '--offline') opts.offline = true;
    else if (a === '--refresh') opts.refresh = true;
    else if (a === '--studio') opts.studio = true;
    else throw new Error('unknown option ' + a);
  }
  return opts;
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const text = JSON.stringify(value, null, 1) + '\n';
  fs.writeFileSync(file, text);
  return crypto.createHash('sha256').update(text).digest('hex');
}
const rel = p => path.relative(ROOT, p) || '.';

async function main(argv) {
  if (!argv.length || argv[0] === '-h' || argv[0] === '--help') { process.stdout.write(USAGE); return; }
  if (Number(process.versions.node.split('.')[0]) < 18) throw new Error('Node.js >= 18 is required');
  const opts = parseArgs(argv);
  if (!opts.jobs) opts.jobs = Math.max(1, Math.min(8, require('node:os').availableParallelism ? require('node:os').availableParallelism() : require('node:os').cpus().length));
  const started = Date.now();
  const emit = opts.studio ? (event => process.stdout.write(JSON.stringify(Object.assign({t_s: (Date.now() - started) / 1000}, event)) + '\n'))
    : (event => {
      if (event.event === 'architecture') process.stdout.write(`  ${event.task.padEnd(9)} ${event.name.padEnd(26)} CV RMSE ${event.cv_rmse.toFixed(4)}  test RMSE ${event.test_rmse.toFixed(4)}  (${event.seconds.toFixed(1)} s)\n`);
      else if (event.event === 'stage') process.stdout.write(`[${event.stage}] ${event.message || ''}\n`);
      else if (event.event === 'retry') process.stderr.write(`retry ${event.key} ${event.status || event.reason}\n`);
    });
  const commands = {collect: ['collect'], build: ['build'], train: ['train'], all: ['collect', 'build', 'train'], publish: ['publish']}[opts.command];
  if (!commands) throw new Error('unknown command ' + opts.command + '\n' + USAGE);
  const manifest = {schema: 'trech_spectrum_studio_v1', out: rel(opts.out), stages: []};
  for (const stage of commands) {
    emit({event: 'stage', stage, message: 'starting'});
    if (stage === 'collect') {
      const {collect} = require('../src/collect.js');
      const result = await collect(Object.assign({}, opts, {log: emit}));
      const tally = list => list.reduce((m, x) => ((m[x.status] = (m[x.status] || 0) + 1), m), {});
      emit({event: 'stage', stage, message: `atoms ${JSON.stringify(tally(result.atoms))}, molecules ${JSON.stringify(tally(result.molecules))}, ${result.fetched} new responses`});
    } else if (stage === 'build') {
      const {build} = require('../src/dataset.js');
      const dataset = build(Object.assign({}, opts, {root: ROOT}));
      const sha = writeJson(path.join(opts.out, 'dataset.json'), dataset);
      manifest.dataset = {path: rel(path.join(opts.out, 'dataset.json')), sha256: sha, counts: dataset.counts};
      emit({event: 'stage', stage, message: `${dataset.counts.atoms} atoms, ${dataset.counts.molecules} molecules, ${dataset.counts.rejected} rejected`, counts: dataset.counts});
    } else if (stage === 'train') {
      const {train, markdown} = require('../src/pipeline.js');
      const datasetPath = opts.dataset || path.join(opts.out, 'dataset.json');
      const text = fs.readFileSync(datasetPath, 'utf8');
      const dataset = JSON.parse(text);
      if (dataset.schema !== 'trech_spectrum_dataset_v1') throw new Error(datasetPath + ' is not a spectrum dataset');
      const {report, models} = await train(dataset, Object.assign({}, opts, {log: emit}));
      report.dataset_sha256 = crypto.createHash('sha256').update(text).digest('hex');
      for (const name of Object.keys(models)) models[name].trained_from.dataset_sha256 = report.dataset_sha256;
      manifest.report = {path: rel(path.join(opts.out, 'report.json')), sha256: writeJson(path.join(opts.out, 'report.json'), report)};
      fs.writeFileSync(path.join(opts.out, 'report.md'), markdown(report));
      manifest.models = {};
      for (const name of Object.keys(models))
        manifest.models[name] = {path: rel(path.join(opts.out, 'models', name + '.json')), sha256: writeJson(path.join(opts.out, 'models', name + '.json'), models[name])};
      manifest.ranking = report.ranking;
      emit({event: 'stage', stage, message: 'wrote ' + rel(path.join(opts.out, 'report.md'))});
    } else if (stage === 'publish') {
      for (const file of ['dataset.json', 'report.json', 'report.md', 'models/spectrum_atomic.json', 'models/spectrum_molecular.json']) {
        const from = path.join(opts.out, file), to = path.join(opts.publish, file);
        if (!fs.existsSync(from)) throw new Error('nothing to publish: missing ' + rel(from));
        fs.mkdirSync(path.dirname(to), {recursive: true});
        fs.copyFileSync(from, to);
      }
      emit({event: 'stage', stage, message: 'copied run into ' + rel(opts.publish)});
    }
    manifest.stages.push(stage);
  }
  if (opts.studio) {
    // Studio rereads these through a TRECH run of the spectrum_prediction scenario; the
    // parameters below select this run's dataset/models instead of the committed fixture.
    manifest.scenario = 'examples/scenarios/spectrum_prediction/spectrum_prediction.js';
    manifest.parameters = {data_dir: path.resolve(opts.out)};
    writeJson(path.join(opts.out, 'studio_manifest.json'), manifest);
    emit({event: 'done', manifest: rel(path.join(opts.out, 'studio_manifest.json')), parameters: manifest.parameters});
  }
}

main(process.argv.slice(2)).catch(error => {
  process.stderr.write('spectrum-prediction error: ' + (error && error.message || error) + '\n');
  process.exitCode = 1;
});
