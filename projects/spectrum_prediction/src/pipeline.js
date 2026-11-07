'use strict';
// Train, cross-validate, test and export every catalogued architecture on a built dataset.
//
// Protocol (identical for every architecture):
//   1. A hash-stable held-out test split per task (20 %) is set aside and scored exactly once.
//   2. k-fold cross-validation runs on the remaining training split only.
//   3. Molecules additionally get leave-one-family-out CV (out-of-family generalisation).
//   4. The final model is refitted on the full training split; exported dense models carry the
//      test-split metrics as their engine-visible `holdout` block.
// The atomic -> molecular cascade uses the exported atomic model (fit on the atomic training
// split only) to predict a line-strength profile for every element, pooled per molecule.
const crypto = require('node:crypto');
const S = require('../lib/index.js');

const SEED = 20261107;
const SALTS = {atomic: 'trech-spectrum-atomic-v1', molecular: 'trech-spectrum-molecular-v1'};

function round(value, digits) {
  if (Array.isArray(value)) return value.map(v => round(v, digits));
  if (value && typeof value === 'object') {
    const out = {};
    for (const k of Object.keys(value)) out[k] = round(value[k], digits);
    return out;
  }
  return typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(digits || 8)) : value;
}
function sha256(text) { return crypto.createHash('sha256').update(text).digest('hex'); }
function archSeed(name) { return (SEED ^ S.validate.fnv1a(name)) >>> 0; }

function atomicSamples(dataset) {
  return dataset.atoms.map(a => ({id: a.id, x: a.features, y: a.target, group: a.group, symbol: a.symbol}));
}
function molecularSamples(dataset, summaries) {
  return dataset.molecules.map(m => {
    const inputs = S.features.moleculeInputs(m.smiles, m.solvent_class, summaries);
    return {id: m.id, name: m.name, family: m.family, x: inputs.x, graph: inputs.graph, y: m.target};
  });
}

function contextFor(spec, base) {
  return Object.assign({}, base, {inputs: S.architectures.inputSet(spec.inputs), seed: archSeed(spec.name)});
}
function score(model, samples, grid) {
  const pred = samples.map(s => model.predict(s));
  return {metrics: S.validate.metrics(samples.map(s => s.y), pred, grid), pred};
}
function crossValidate(spec, samples, k, salt, base, grid) {
  const folds = S.validate.folds(samples, k, salt), out = [];
  folds.forEach((fold, i) => {
    const train = folds.filter((_, j) => j !== i).reduce((a, f) => a.concat(f), []);
    out.push(score(S.models.fit(spec, train, contextFor(spec, base)), fold, grid).metrics);
  });
  return S.validate.summarize(out);
}
function familyCrossValidate(spec, samples, base, grid) {
  const groups = S.validate.groupFolds(samples, 'family'), perFamily = [];
  for (const g of groups) {
    const train = samples.filter(s => s.family !== g.name);
    if (!train.length || !g.samples.length) continue;
    const m = score(S.models.fit(spec, train, contextFor(spec, base)), g.samples, grid).metrics;
    perFamily.push({family: g.name, n: m.n, rmse: m.rmse, cosine: m.cosine, peak_error_nm: m.peak_error_nm});
  }
  return {summary: S.validate.summarize(perFamily), per_family: perFamily};
}

function compactMetrics(m) {
  return {n: m.n, rmse: m.rmse, mae: m.mae, r2: m.r2, cosine: m.cosine, peak_error_nm: m.peak_error_nm};
}

// One molecular architecture: k-fold CV, leave-one-family-out CV, final fit, test, export.
// Pure function of (spec, env); runs in the main thread or a worker with identical results.
function runMolecular(spec, env) {
  const grid = S.grid.MOLECULAR_GRID;
  const elementFeatures = {};
  for (const symbol of Object.keys(env.dataset.element_facts))
    elementFeatures[symbol] = S.features.vector(env.dataset.element_facts[symbol].features, S.features.ATOMIC_FEATURES);
  const base = {elementFeatures, elementSummaries: env.summaries || {}};
  const split = S.validate.holdout(molecularSamples(env.dataset, env.summaries), 0.2, SALTS.molecular);
  const t0 = Date.now();
  const cv = crossValidate(spec, split.train, env.k, SALTS.molecular, base, grid);
  const familyCv = env.familyCv ? familyCrossValidate(spec, split.train, base, grid) : null;
  const model = S.models.fit(spec, split.train, contextFor(spec, base));
  const test = score(model, split.test, grid);
  const out = {entry: {name: spec.name, task: 'molecular', family: spec.family, note: spec.note, spec, cv,
    family_cv: familyCv, test: compactMetrics(test.metrics), exported: spec.export || null}, seconds: (Date.now() - t0) / 1000};
  if (spec.export) {
    const ctx = contextFor(spec, base);
    out.exported = S.export.genericSurrogate(model, {
      outputNames: S.grid.outputNames('uv_envelope', grid), scale: 'nano',
      trainRows: split.train.map(s => S.features.vector(s.x, ctx.inputs)), testMetrics: test.metrics,
      trainedFrom: {script: 'projects/spectrum_prediction/bin/spectra.cjs', architecture: spec, seed: archSeed(spec.name),
        dataset_sha256: env.datasetSha, cascade_source: env.cascadeSource,
        train_ids: split.train.map(s => s.id), test_ids: split.test.map(s => s.id)},
      note: {geant4_trained: false, measured_labels: true, mc_sampled: false,
        label_source: 'PubChem UV/Vis absorption maxima (lambda_max, log epsilon), mostly HSDB',
        inputs: 'SMILES graph counts, measured solvent class' + (spec.inputs === 'descriptors_cascade' ?
          ', and count-weighted pooled predictions of the atomic line-strength model (cascade)' : ''),
        scope: 'Absorption envelope on 180-500 nm (32 bins) from listed maxima with a fixed 1500 cm^-1 Gaussian width; band widths and vibronic structure are not measured inputs.',
        grid}});
    out.predictions = split.test.map((s, i) => ({id: s.id, name: s.name, truth: s.y, prediction: test.pred[i]}));
  }
  return out;
}

// Run molecular architectures on up to `jobs` worker threads; results keep catalogue order.
async function runAll(specs, env, jobs, log) {
  const done = new Array(specs.length);
  const report = (i, o) => {
    done[i] = o;
    log({event: 'architecture', task: 'molecular', name: specs[i].name, cv_rmse: o.entry.cv.rmse.mean,
      test_rmse: o.entry.test.rmse, seconds: o.seconds});
  };
  if (jobs <= 1) {
    specs.forEach((spec, i) => { log({event: 'architecture_start', task: 'molecular', name: spec.name}); report(i, runMolecular(spec, env)); });
    return done;
  }
  const {Worker} = require('node:worker_threads');
  let next = 0;
  async function lane() {
    while (next < specs.length) {
      const i = next++;
      log({event: 'architecture_start', task: 'molecular', name: specs[i].name});
      const result = await new Promise((resolve, reject) => {
        const worker = new Worker(__filename, {workerData: {spec: specs[i], env}});
        worker.once('message', resolve);
        worker.once('error', reject);
        worker.once('exit', code => { if (code !== 0) reject(new Error('worker for ' + specs[i].name + ' exited ' + code)); });
      });
      report(i, result);
    }
  }
  await Promise.all(Array.from({length: Math.min(jobs, specs.length)}, lane));
  return done;
}

async function train(dataset, options) {
  options = options || {};
  const log = options.log || (() => {});
  const k = options.folds || 5;
  const catalog = S.architectures.catalog(options.architectures).map(S.architectures.validate);
  const datasetSha = sha256(JSON.stringify(dataset));
  const grids = {atomic: S.grid.ATOMIC_GRID, molecular: S.grid.MOLECULAR_GRID};
  const results = [], exports = {}, testPredictions = {}, splits = {};

  // ---- atomic task -------------------------------------------------------------------------
  const atomSamples = atomicSamples(dataset);
  const atomSplit = S.validate.holdout(atomSamples, 0.2, SALTS.atomic);
  splits.atomic = {train: atomSplit.train.map(s => s.id), test: atomSplit.test.map(s => s.id)};
  let cascadeModel = null, cascadeSpec = null;
  const atomicArchs = catalog.filter(a => a.task === 'atomic');
  const needsCascade = catalog.some(a => a.task === 'molecular' && (a.inputs === 'descriptors_cascade' || a.cascadeNodeFeatures));
  if (needsCascade && !atomicArchs.some(a => a.cascadeSource)) atomicArchs.push(S.architectures.catalog().find(a => a.cascadeSource));
  for (const spec of atomicArchs) {
    log({event: 'architecture_start', task: 'atomic', name: spec.name});
    const t0 = Date.now();
    const cv = crossValidate(spec, atomSplit.train, k, SALTS.atomic, {}, grids.atomic);
    const model = S.models.fit(spec, atomSplit.train, contextFor(spec, {}));
    const test = score(model, atomSplit.test, grids.atomic);
    const entry = {name: spec.name, task: 'atomic', family: spec.family, note: spec.note, spec, cv,
      test: compactMetrics(test.metrics), exported: spec.export || null};
    results.push(entry);
    log({event: 'architecture', task: 'atomic', name: spec.name, cv_rmse: cv.rmse && cv.rmse.mean, test_rmse: test.metrics.rmse,
      seconds: (Date.now() - t0) / 1000});
    if (spec.cascadeSource) { cascadeModel = model; cascadeSpec = spec; }
    if (spec.export) {
      const ctx = contextFor(spec, {});
      exports[spec.export] = S.export.genericSurrogate(model, {
        outputNames: S.grid.outputNames('atomic_line', grids.atomic), scale: 'atomic',
        trainRows: atomSplit.train.map(s => S.features.vector(s.x, ctx.inputs)), testMetrics: test.metrics,
        trainedFrom: {script: 'projects/spectrum_prediction/bin/spectra.cjs', architecture: spec, seed: archSeed(spec.name),
          dataset_sha256: datasetSha, train_ids: splits.atomic.train, test_ids: splits.atomic.test},
        note: {geant4_trained: false, measured_labels: true, mc_sampled: false,
          label_source: 'NIST ASD neutral-atom lines (g_k*A_ki weighted) reached via PubChem element records',
          inputs: 'PubChem periodic-table facts and NIST ground level as reported by PubChem',
          scope: 'Line-strength shape on 200-1000 nm (40 bins); not a plasma emission spectrum, no level populations or instrument response.',
          grid: grids.atomic}});
      testPredictions[spec.export] = atomSplit.test.map((s, i) => ({id: s.id, truth: s.y, prediction: test.pred[i]}));
    }
  }

  // ---- atomic -> molecular cascade summaries -----------------------------------------------
  let summaries = null;
  if (cascadeModel) {
    summaries = {};
    for (const symbol of Object.keys(dataset.element_facts)) {
      const profile = cascadeModel.predict({x: dataset.element_facts[symbol].features});
      summaries[symbol] = S.features.profileSummary(profile, grids.atomic);
    }
  }

  // ---- molecular task ----------------------------------------------------------------------
  const molArchs = catalog.filter(a => a.task === 'molecular');
  if (molArchs.length) {
    const env = {dataset, summaries, k, familyCv: options.familyCv !== false, datasetSha,
      cascadeSource: cascadeSpec ? cascadeSpec.name : null};
    const molSplit = S.validate.holdout(molecularSamples(dataset, summaries), 0.2, SALTS.molecular);
    splits.molecular = {train: molSplit.train.map(s => s.id), test: molSplit.test.map(s => s.id)};
    const outcomes = await runAll(molArchs, env, options.jobs || 1, log);
    for (const o of outcomes) {
      results.push(o.entry);
      if (o.exported) { exports[o.entry.exported] = o.exported; testPredictions[o.entry.exported] = o.predictions; }
    }
  }

  // ---- ablations: same family/hyper-parameters with vs. without the atomic cascade ---------
  const byName = {};
  for (const r of results) byName[r.name] = r;
  const ablation = [['molecular_ridge', 'molecular_ridge_cascade'], ['molecular_mlp', 'molecular_mlp_cascade'],
    ['molecular_mpnn', 'molecular_mpnn_cascade']].filter(([a, b]) => byName[a] && byName[b]).map(([a, b]) => ({
    without: a, with: b,
    cv_rmse_delta: byName[b].cv.rmse.mean - byName[a].cv.rmse.mean,
    test_rmse_delta: byName[b].test.rmse - byName[a].test.rmse,
    family_cv_rmse_delta: byName[a].family_cv && byName[b].family_cv ? byName[b].family_cv.summary.rmse.mean - byName[a].family_cv.summary.rmse.mean : null
  }));
  const ranking = {};
  for (const task of ['atomic', 'molecular'])
    ranking[task] = results.filter(r => r.task === task).sort((a, b) => a.cv.rmse.mean - b.cv.rmse.mean || (a.name < b.name ? -1 : 1)).map(r => r.name);

  const report = round({
    schema: 'trech_spectrum_report_v1',
    dataset_sha256: datasetSha,
    protocol: {seed: SEED, folds: k, holdout_fraction: 0.2, salts: SALTS, family_cv: options.familyCv !== false,
      ranking_metric: 'mean k-fold CV RMSE (target units) on the training split; test metrics are reported, never used for selection'},
    counts: {atoms: dataset.atoms.length, molecules: dataset.molecules.length,
      atomic_train: splits.atomic.train.length, atomic_test: splits.atomic.test.length,
      molecular_train: splits.molecular ? splits.molecular.train.length : 0, molecular_test: splits.molecular ? splits.molecular.test.length : 0},
    grids, splits, ranking, architectures: results, ablation,
    cascade: cascadeSpec ? {source: cascadeSpec.name, element_summaries: summaries} : null,
    exports: Object.keys(exports).reduce((o, name) => (o[name] = {architecture: exports[name].trained_from.architecture.name,
      holdout_r2_min: exports[name].holdout.r2_min === undefined ? null : exports[name].holdout.r2_min}, o), {}),
    test_predictions: testPredictions,
    honesty: {geant4_trained: false, measured_labels: true,
      statement: 'Models learn measured spectra from PubChem/NIST facts and graph topology. They are learned predictions for comparison, not Geant4 results, and the atomic rung is not particle-trained.'}
  }, 8);
  return {report, models: round(exports, 12)};
}

function fmt(v, digits) { return v === null || v === undefined ? '—' : Number(v).toFixed(digits === undefined ? 3 : digits); }
function markdown(report) {
  const lines = ['# Spectrum prediction report', '', report.honesty.statement, '',
    `Dataset ${report.dataset_sha256.slice(0, 12)} · ${report.counts.atoms} atoms (${report.counts.atomic_test} test) · ` +
    `${report.counts.molecules} molecules (${report.counts.molecular_test} test) · ${report.protocol.folds}-fold CV, seed ${report.protocol.seed}.`, ''];
  for (const task of ['atomic', 'molecular']) {
    const rows = report.ranking[task].map(n => report.architectures.find(a => a.name === n));
    if (!rows.length) continue;
    lines.push('## ' + (task === 'atomic' ? 'Atomic line-strength profiles (200–1000 nm)' : 'Molecular UV absorption envelopes (180–500 nm)'), '',
      '| Architecture | Family | CV RMSE | CV cosine | ' + (task === 'molecular' ? 'Family-CV RMSE | ' : '') + 'Test RMSE | Test R² | Test cosine | Test peak error (nm) | Export |',
      '| --- | --- | --- | --- | ' + (task === 'molecular' ? '--- | ' : '') + '--- | --- | --- | --- | --- |');
    for (const r of rows) {
      lines.push(`| ${r.name} | ${r.family} | ${fmt(r.cv.rmse.mean)} ± ${fmt(r.cv.rmse.std)} | ${fmt(r.cv.cosine.mean)} | ` +
        (task === 'molecular' ? `${r.family_cv ? fmt(r.family_cv.summary.rmse.mean) : '—'} | ` : '') +
        `${fmt(r.test.rmse)} | ${fmt(r.test.r2)} | ${fmt(r.test.cosine)} | ${fmt(r.test.peak_error_nm, 1)} | ${r.exported || ''} |`);
    }
    lines.push('');
  }
  if (report.ablation.length) {
    lines.push('## Atomic → molecular cascade ablation', '', 'Negative deltas mean the pooled atomic-model features helped.', '',
      '| Without | With cascade | ΔCV RMSE | ΔFamily-CV RMSE | ΔTest RMSE |', '| --- | --- | --- | --- | --- |');
    for (const a of report.ablation) lines.push(`| ${a.without} | ${a.with} | ${fmt(a.cv_rmse_delta, 4)} | ${fmt(a.family_cv_rmse_delta, 4)} | ${fmt(a.test_rmse_delta, 4)} |`);
    lines.push('');
  }
  return lines.join('\n') + '\n';
}

module.exports = {train, markdown, runMolecular, SEED};

const threads = require('node:worker_threads');
if (!threads.isMainThread && threads.workerData && threads.workerData.spec)
  threads.parentPort.postMessage(runMolecular(threads.workerData.spec, threads.workerData.env));
