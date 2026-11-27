'use strict';
// Train, cross-validate, test and export every catalogued architecture on a built dataset.
//
// Protocol (identical for every architecture):
//   1. A hash-stable held-out test split per task (20 %) is set aside and scored exactly once.
//   2. k-fold cross-validation runs on the remaining training split only.
//   3. Molecules additionally get leave-one-family-out CV (out-of-family generalisation).
//      Atoms, whose test split holds only a handful of elements, additionally get repeated
//      k-fold CV (R re-salted fold assignments, per-fold and pooled out-of-fold metrics) and
//      leave-one-chemical-group-out CV, so atomic R² is not read from one small split. These
//      are reported next to, never instead of, the ranking CV.
//   4. The final model is refitted on the full training split; exported dense models carry the
//      test-split metrics as their engine-visible `holdout` block.
// The atomic -> molecular cascade uses an atomic model (fit on the atomic training split only)
// to predict a line-strength profile for every element, pooled per molecule. There is one
// cascade per atomic source: 'pubchem' (PubChem facts) and 'geant4' (plus the Geant4 atomic
// response); a molecular entry names the source it pools.
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
// `oof` (optional {truth, pred}) collects every sample's out-of-fold prediction, the
// calibration set of the exported models' prediction intervals.
function crossValidate(spec, samples, k, salt, base, grid, oof) {
  const folds = S.validate.folds(samples, k, salt), out = [];
  folds.forEach((fold, i) => {
    const train = folds.filter((_, j) => j !== i).reduce((a, f) => a.concat(f), []);
    const scored = score(S.models.fit(spec, train, contextFor(spec, base)), fold, grid);
    out.push(scored.metrics);
    if (oof) fold.forEach((sample, j) => { oof.truth.push(sample.y); oof.pred.push(scored.pred[j]); });
  });
  return S.validate.summarize(out);
}
const INTERVAL_COVERAGE = 0.9;
function collector() { return {truth: [], pred: []}; }
// Per-bin split-conformal interval from in-distribution CV residuals, graded on the test split
// and on out-of-group predictions; the out-of-group residuals also give their own (wider)
// calibrated widths so the report shows how far the in-distribution interval under-covers.
function predictionInterval(outputNames, inDist, test, outOfGroup, groupSource) {
  const U = S.uncertainty, cal = U.calibrate(inDist.truth, inDist.pred, INTERVAL_COVERAGE);
  const named = v => outputNames.reduce((o, name, j) => ((o[name] = v[j]), o), {});
  const block = {method: 'split_conformal_cv_abs_residual', nominal_coverage: INTERVAL_COVERAGE, marginal: 'per output bin',
    calibration: {source: 'out-of-fold predictions of the ranking k-fold CV on the training split', n: cal.n, capped: cal.capped},
    half_width: named(cal.half_width), mean_width: U.meanWidth(cal.half_width),
    achieved: {test: U.coverage(test.truth, test.pred, cal.half_width)}};
  if (outOfGroup && outOfGroup.truth.length) {
    const og = U.calibrate(outOfGroup.truth, outOfGroup.pred, INTERVAL_COVERAGE);
    block.achieved.out_of_group = Object.assign({source: groupSource}, U.coverage(outOfGroup.truth, outOfGroup.pred, cal.half_width));
    block.out_of_group = {source: groupSource, n: og.n, capped: og.capped, half_width: named(og.half_width),
      mean_width: U.meanWidth(og.half_width), width_ratio: U.meanWidth(og.half_width) / U.meanWidth(cal.half_width)};
  }
  return block;
}
function intervalSummary(block) {
  return {nominal_coverage: block.nominal_coverage, n_calibration: block.calibration.n, capped: block.calibration.capped,
    mean_width: block.mean_width, test: block.achieved.test, out_of_group: block.achieved.out_of_group || null,
    out_of_group_width_ratio: block.out_of_group ? block.out_of_group.width_ratio : null};
}
// R repetitions of k-fold CV, each with its own salted fold assignment. `per_fold` summarises
// all R*k fold metrics; `pooled` scores each repetition's concatenated out-of-fold predictions
// (one R² over every training sample, far less noisy than a 6-element test split) and
// summarises those R values.
function repeatedCrossValidate(spec, samples, k, repeats, salt, base, grid) {
  const perFold = [], pooled = [];
  for (let r = 0; r < repeats; r++) {
    const folds = S.validate.folds(samples, k, salt + ':repeat' + r), truth = [], pred = [];
    folds.forEach((fold, i) => {
      const train = folds.filter((_, j) => j !== i).reduce((a, f) => a.concat(f), []);
      const scored = score(S.models.fit(spec, train, contextFor(spec, base)), fold, grid);
      perFold.push(scored.metrics);
      fold.forEach((sample, j) => { truth.push(sample.y); pred.push(scored.pred[j]); });
    });
    pooled.push(S.validate.metrics(truth, pred, grid));
  }
  return {repeats, folds: k, per_fold: S.validate.summarize(perFold), pooled: S.validate.summarize(pooled)};
}
// Leave-one-chemical-group-out CV for atoms (PubChem group block: noble gas, halogen, ...).
// `pooled` scores the concatenated held-out predictions of every group once.
function atomicGroupCrossValidate(spec, samples, base, grid, oof) {
  const groups = S.validate.groupFolds(samples, 'group'), perGroup = [], truth = [], pred = [];
  for (const g of groups) {
    const train = samples.filter(s => (s.group || 'unassigned') !== g.name);
    if (!train.length || !g.samples.length) continue;
    const scored = score(S.models.fit(spec, train, contextFor(spec, base)), g.samples, grid);
    const m = scored.metrics;
    perGroup.push({group: g.name, n: m.n, rmse: m.rmse, cosine: m.cosine, peak_error_nm: m.peak_error_nm});
    g.samples.forEach((sample, j) => { truth.push(sample.y); pred.push(scored.pred[j]); });
  }
  if (oof) { oof.truth.push(...truth); oof.pred.push(...pred); }
  return {summary: S.validate.summarize(perGroup), per_group: perGroup,
    pooled: truth.length ? compactMetrics(S.validate.metrics(truth, pred, grid)) : null};
}
function familyCrossValidate(spec, samples, base, grid, oof) {
  const groups = S.validate.groupFolds(samples, 'family'), perFamily = [];
  for (const g of groups) {
    const train = samples.filter(s => s.family !== g.name);
    if (!train.length || !g.samples.length) continue;
    const scored = score(S.models.fit(spec, train, contextFor(spec, base)), g.samples, grid), m = scored.metrics;
    if (oof) g.samples.forEach((sample, j) => { oof.truth.push(sample.y); oof.pred.push(scored.pred[j]); });
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
  const source = S.architectures.cascadeOf(spec) || 'pubchem';
  const summaries = env.summaries ? env.summaries[source] || null : null;
  const base = {elementFeatures, elementSummaries: summaries || {}};
  const split = S.validate.holdout(molecularSamples(env.dataset, summaries), 0.2, SALTS.molecular);
  const t0 = Date.now();
  const oof = spec.export ? collector() : null, familyOof = spec.export ? collector() : null;
  const cv = crossValidate(spec, split.train, env.k, SALTS.molecular, base, grid, oof);
  const familyCv = env.familyCv ? familyCrossValidate(spec, split.train, base, grid, familyOof) : null;
  const model = S.models.fit(spec, split.train, contextFor(spec, base));
  const test = score(model, split.test, grid);
  const out = {entry: {name: spec.name, task: 'molecular', family: spec.family, note: spec.note, spec, cv,
    family_cv: familyCv, test: compactMetrics(test.metrics), exported: spec.export || null}, seconds: (Date.now() - t0) / 1000};
  if (spec.export) {
    const ctx = contextFor(spec, base), outputNames = S.grid.outputNames('uv_envelope', grid);
    const interval = predictionInterval(outputNames, oof, {truth: split.test.map(s => s.y), pred: test.pred},
      familyOof, 'leave-one-family-out CV on the training split');
    out.entry.interval = intervalSummary(interval);
    out.exported = S.export.genericSurrogate(model, {
      outputNames, scale: 'nano', predictionInterval: interval,
      trainRows: split.train.map(s => S.features.vector(s.x, ctx.inputs)), testMetrics: test.metrics,
      trainedFrom: {script: 'projects/spectrum_prediction/bin/spectra.cjs', architecture: spec, seed: archSeed(spec.name),
        dataset_sha256: env.datasetSha, cascade_source: env.cascadeSources[source] || null,
        train_ids: split.train.map(s => s.id), test_ids: split.test.map(s => s.id)},
      note: {geant4_trained: false, measured_labels: true, mc_sampled: false,
        label_source: 'PubChem UV/Vis absorption maxima (lambda_max, log epsilon), mostly HSDB',
        inputs: 'SMILES graph counts, measured solvent class' + (spec.inputs === 'descriptors_cascade' ?
          ', and count-weighted pooled predictions of the atomic line-strength model (cascade)' +
          (source === 'geant4' ? ', whose inputs include the Geant4 atomic response' : '') : ''),
        particle_derived_inputs: source === 'geant4' && spec.inputs === 'descriptors_cascade',
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

// `exports` ({spectrum_atomic: name, spectrum_molecular: name}) moves an export to another
// catalogue entry for this run. The exported molecular cascade must pool the exported atomic
// model, because TRECH recomputes the pooled inputs with the atomic model it loads.
function withExports(list, exports) {
  if (!exports) return list;
  const out = list.map(a => Object.assign({}, a));
  for (const target of Object.keys(exports)) {
    if (['spectrum_atomic', 'spectrum_molecular'].indexOf(target) < 0) throw new Error('unknown export ' + target);
    const entry = out.find(a => a.name === exports[target]);
    if (!entry) throw new Error('export ' + target + ': architecture ' + exports[target] + ' is not in this run');
    if (entry.task !== (target === 'spectrum_atomic' ? 'atomic' : 'molecular')) throw new Error('export ' + target + ': ' + entry.name + ' is a ' + entry.task + ' entry');
    for (const a of out) if (a.export === target) delete a.export;
    entry.export = target;
  }
  return out;
}
function checkExportChain(catalog) {
  const atomic = catalog.find(a => a.export === 'spectrum_atomic'), molecular = catalog.find(a => a.export === 'spectrum_molecular');
  const source = molecular ? S.architectures.cascadeOf(molecular) : null;
  if (!atomic || !source) return;
  if (atomic.cascadeSource !== source)
    throw new Error('spectrum_molecular (' + molecular.name + ') pools the ' + source + ' atomic model, but spectrum_atomic is ' + atomic.name +
      '; TRECH would pool a different model than the one trained on');
}

async function train(dataset, options) {
  options = options || {};
  const log = options.log || (() => {});
  const k = options.folds || 5;
  const repeats = options.repeats === undefined ? 5 : options.repeats;
  const groupCv = options.groupCv !== false;
  const requested = withExports(S.architectures.catalog(options.architectures), options.exports).map(S.architectures.validate);
  // Geant4 entries need a dataset built with catalog/geant4_atomic.json. Without one they are
  // skipped and reported; naming one explicitly is an error.
  const hasGeant4 = !!dataset.geant4_atomic, skipped = [];
  const catalog = requested.filter(spec => {
    if (hasGeant4 || !S.architectures.usesGeant4(spec)) return true;
    if (options.architectures && options.architectures.indexOf(spec.name) >= 0)
      throw new Error(spec.name + ' needs Geant4 atomic inputs: build the dataset with catalog/geant4_atomic.json');
    skipped.push({name: spec.name, reason: 'dataset has no Geant4 atomic catalogue'});
    return false;
  });
  checkExportChain(catalog);
  const datasetSha = sha256(JSON.stringify(dataset));
  const grids = {atomic: S.grid.ATOMIC_GRID, molecular: S.grid.MOLECULAR_GRID};
  const results = [], exports = {}, testPredictions = {}, splits = {};

  // ---- atomic task -------------------------------------------------------------------------
  const atomSamples = atomicSamples(dataset);
  const atomSplit = S.validate.holdout(atomSamples, 0.2, SALTS.atomic);
  splits.atomic = {train: atomSplit.train.map(s => s.id), test: atomSplit.test.map(s => s.id)};
  const cascadeModels = {}, cascadeSpecs = {};
  const atomicArchs = catalog.filter(a => a.task === 'atomic');
  for (const source of S.architectures.CASCADE_SOURCES) {
    const needed = catalog.some(a => S.architectures.cascadeOf(a) === source);
    if (needed && !atomicArchs.some(a => a.cascadeSource === source))
      atomicArchs.push(S.architectures.catalog().find(a => a.cascadeSource === source));
  }
  for (const spec of atomicArchs) {
    log({event: 'architecture_start', task: 'atomic', name: spec.name});
    const t0 = Date.now();
    const oof = spec.export ? collector() : null, groupOof = spec.export ? collector() : null;
    const cv = crossValidate(spec, atomSplit.train, k, SALTS.atomic, {}, grids.atomic, oof);
    const model = S.models.fit(spec, atomSplit.train, contextFor(spec, {}));
    const test = score(model, atomSplit.test, grids.atomic);
    const entry = {name: spec.name, task: 'atomic', family: spec.family, note: spec.note, spec, cv,
      test: compactMetrics(test.metrics), exported: spec.export || null};
    if (repeats > 0) entry.repeated_cv = repeatedCrossValidate(spec, atomSplit.train, k, repeats, SALTS.atomic, {}, grids.atomic);
    if (groupCv) entry.group_cv = atomicGroupCrossValidate(spec, atomSplit.train, {}, grids.atomic, groupOof);
    results.push(entry);
    log({event: 'architecture', task: 'atomic', name: spec.name, cv_rmse: cv.rmse && cv.rmse.mean, test_rmse: test.metrics.rmse,
      seconds: (Date.now() - t0) / 1000});
    if (spec.cascadeSource) { cascadeModels[spec.cascadeSource] = model; cascadeSpecs[spec.cascadeSource] = spec; }
    if (spec.export) {
      const ctx = contextFor(spec, {}), outputNames = S.grid.outputNames('atomic_line', grids.atomic);
      const interval = predictionInterval(outputNames, oof, {truth: atomSplit.test.map(s => s.y), pred: test.pred},
        groupCv ? groupOof : null, 'leave-one-chemical-group-out CV on the training split');
      entry.interval = intervalSummary(interval);
      exports[spec.export] = S.export.genericSurrogate(model, {
        outputNames, scale: 'atomic', predictionInterval: interval,
        trainRows: atomSplit.train.map(s => S.features.vector(s.x, ctx.inputs)), testMetrics: test.metrics,
        trainedFrom: {script: 'projects/spectrum_prediction/bin/spectra.cjs', architecture: spec, seed: archSeed(spec.name),
          dataset_sha256: datasetSha, train_ids: splits.atomic.train, test_ids: splits.atomic.test},
        note: {geant4_trained: false, measured_labels: true, mc_sampled: false,
          particle_derived_inputs: S.architectures.usesGeant4(spec),
          label_source: 'NIST ASD neutral-atom lines (g_k*A_ki weighted) reached via PubChem element records',
          inputs: S.architectures.usesGeant4(spec) ?
            'PubChem periodic-table facts, NIST ground level as reported by PubChem, and the Geant4 atomic response ' +
            '(mean excitation energy, per-atom photo-absorption cross sections; read from a live Geant4 material probe in TRECH)' :
            'PubChem periodic-table facts and NIST ground level as reported by PubChem',
          scope: 'Line-strength shape on 200-1000 nm (40 bins); not a plasma emission spectrum, no level populations or instrument response.',
          grid: grids.atomic}});
      testPredictions[spec.export] = atomSplit.test.map((s, i) => ({id: s.id, truth: s.y, prediction: test.pred[i]}));
    }
  }

  // ---- atomic -> molecular cascade summaries, one set per atomic source --------------------
  let summaries = null;
  for (const source of Object.keys(cascadeModels)) {
    summaries = summaries || {};
    summaries[source] = {};
    for (const symbol of Object.keys(dataset.element_facts)) {
      const profile = cascadeModels[source].predict({x: dataset.element_facts[symbol].features});
      summaries[source][symbol] = S.features.profileSummary(profile, grids.atomic);
    }
  }
  const cascadeSources = {};
  for (const source of Object.keys(cascadeSpecs)) cascadeSources[source] = cascadeSpecs[source].name;

  // ---- molecular task ----------------------------------------------------------------------
  const molArchs = catalog.filter(a => a.task === 'molecular');
  if (molArchs.length) {
    const env = {dataset, summaries, k, familyCv: options.familyCv !== false, datasetSha, cascadeSources};
    const molSplit = S.validate.holdout(molecularSamples(dataset, summaries && summaries.pubchem), 0.2, SALTS.molecular);
    splits.molecular = {train: molSplit.train.map(s => s.id), test: molSplit.test.map(s => s.id)};
    const outcomes = await runAll(molArchs, env, options.jobs || 1, log);
    for (const o of outcomes) {
      results.push(o.entry);
      if (o.exported) { exports[o.entry.exported] = o.exported; testPredictions[o.entry.exported] = o.predictions; }
    }
  }

  // ---- ablations: same family/hyper-parameters with vs. without one addition ---------------
  //   cascade          molecular model with vs. without pooled PubChem-fed atomic predictions
  //   geant4_atomic    atomic model with vs. without the Geant4 atomic response as inputs
  //   cascade_geant4   molecular cascade pooling the Geant4-fed vs. the PubChem-fed atomic model
  //   geant4_cascade   molecular model with vs. without pooled Geant4-fed atomic predictions
  const byName = {};
  for (const r of results) byName[r.name] = r;
  const PAIRS = [
    ['cascade', 'molecular_ridge', 'molecular_ridge_cascade'], ['cascade', 'molecular_mlp', 'molecular_mlp_cascade'],
    ['cascade', 'molecular_mpnn', 'molecular_mpnn_cascade'],
    ['geant4_atomic', 'atomic_knn3', 'atomic_knn3_geant4'], ['geant4_atomic', 'atomic_ridge', 'atomic_ridge_geant4'],
    ['geant4_atomic', 'atomic_mlp_tanh', 'atomic_mlp_tanh_geant4'], ['geant4_atomic', 'atomic_mlp_silu_wide', 'atomic_mlp_silu_wide_geant4'],
    ['cascade_geant4', 'molecular_ridge_cascade', 'molecular_ridge_cascade_geant4'],
    ['cascade_geant4', 'molecular_mlp_cascade', 'molecular_mlp_cascade_geant4'],
    ['cascade_geant4', 'molecular_mpnn_cascade', 'molecular_mpnn_cascade_geant4'],
    ['geant4_cascade', 'molecular_ridge', 'molecular_ridge_cascade_geant4'], ['geant4_cascade', 'molecular_mlp', 'molecular_mlp_cascade_geant4'],
    ['geant4_cascade', 'molecular_mpnn', 'molecular_mpnn_cascade_geant4']];
  const groupRmse = r => r.family_cv ? r.family_cv.summary.rmse.mean : r.group_cv && r.group_cv.summary.rmse ? r.group_cv.summary.rmse.mean : null;
  const ablation = PAIRS.filter(([, a, b]) => byName[a] && byName[b]).map(([kind, a, b]) => {
    const ga = groupRmse(byName[a]), gb = groupRmse(byName[b]);
    const row = {kind, task: byName[a].task, without: a, with: b,
      cv_rmse_delta: byName[b].cv.rmse.mean - byName[a].cv.rmse.mean,
      test_rmse_delta: byName[b].test.rmse - byName[a].test.rmse};
    // Out-of-group generalisation: leave-one-family-out (molecules), leave-one-group-out (atoms).
    if (row.task === 'molecular') row.family_cv_rmse_delta = ga !== null && gb !== null ? gb - ga : null;
    else row.group_cv_rmse_delta = ga !== null && gb !== null ? gb - ga : null;
    return row;
  });
  const ranking = {};
  for (const task of ['atomic', 'molecular'])
    ranking[task] = results.filter(r => r.task === task).sort((a, b) => a.cv.rmse.mean - b.cv.rmse.mean || (a.name < b.name ? -1 : 1)).map(r => r.name);

  const report = round({
    schema: 'trech_spectrum_report_v1',
    dataset_sha256: datasetSha,
    protocol: {seed: SEED, folds: k, holdout_fraction: 0.2, salts: SALTS, family_cv: options.familyCv !== false,
      atomic_repeated_cv: repeats, atomic_group_cv: groupCv,
      ranking_metric: 'mean k-fold CV RMSE (target units) on the training split; test metrics are reported, never used for selection'},
    counts: {atoms: dataset.atoms.length, molecules: dataset.molecules.length,
      atomic_train: splits.atomic.train.length, atomic_test: splits.atomic.test.length,
      molecular_train: splits.molecular ? splits.molecular.train.length : 0, molecular_test: splits.molecular ? splits.molecular.test.length : 0},
    grids, splits, ranking, architectures: results, ablation,
    cascade: cascadeSpecs.pubchem ? {source: cascadeSpecs.pubchem.name, element_summaries: summaries.pubchem} : null,
    cascades: Object.keys(cascadeSpecs).reduce((o, src) => (o[src] = {source: cascadeSpecs[src].name, element_summaries: summaries[src]}, o), {}),
    geant4_atomic: dataset.geant4_atomic || null,
    skipped,
    exports: Object.keys(exports).reduce((o, name) => (o[name] = {architecture: exports[name].trained_from.architecture.name,
      holdout_r2_min: exports[name].holdout.r2_min === undefined ? null : exports[name].holdout.r2_min}, o), {}),
    test_predictions: testPredictions,
    honesty: {geant4_trained: false, measured_labels: true,
      particle_derived_inputs: Object.keys(exports).filter(name => exports[name].note.particle_derived_inputs),
      statement: 'Models learn measured spectra from PubChem/NIST facts, graph topology and, for *_geant4 entries, the Geant4 atomic response ' +
        '(mean excitation energy, photo-absorption cross sections) as inputs. Labels are measurements: these are learned predictions for comparison, not Geant4 results.'}
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
    if (task === 'atomic' && rows.some(r => r.repeated_cv || r.group_cv)) {
      const p = report.protocol;
      lines.push(`Split-noise check on the training split: ${p.atomic_repeated_cv}× repeated ${p.folds}-fold CV ` +
        '(per-fold RMSE; pooled R² over each repetition\'s out-of-fold predictions) and leave-one-chemical-group-out CV.', '',
        '| Architecture | Repeated-CV RMSE | Pooled R² | Pooled cosine | Group-CV RMSE | Group-CV pooled R² |',
        '| --- | --- | --- | --- | --- | --- |');
      for (const r of rows) {
        const rc = r.repeated_cv, gc = r.group_cv;
        lines.push(`| ${r.name} | ${rc ? fmt(rc.per_fold.rmse.mean) + ' ± ' + fmt(rc.per_fold.rmse.std) : '—'} | ` +
          `${rc && rc.pooled.r2 ? fmt(rc.pooled.r2.mean) + ' ± ' + fmt(rc.pooled.r2.std) : '—'} | ` +
          `${rc && rc.pooled.cosine ? fmt(rc.pooled.cosine.mean) : '—'} | ` +
          `${gc && gc.summary.rmse ? fmt(gc.summary.rmse.mean) + ' ± ' + fmt(gc.summary.rmse.std) : '—'} | ` +
          `${gc && gc.pooled ? fmt(gc.pooled.r2) : '—'} |`);
      }
      lines.push('');
    }
  }
  const intervals = report.architectures.filter(a => a.interval);
  if (intervals.length) {
    lines.push('## Calibrated prediction intervals (exported models)', '',
      `Per-bin split-conformal intervals at ${fmt(intervals[0].interval.nominal_coverage, 2)} nominal coverage, calibrated on the ` +
      'out-of-fold residuals of the ranking CV. Coverage is per (sample, bin) cell; "all bins" is the stricter simultaneous fraction. ' +
      'Out-of-group rows apply the same interval to leave-one-family/group-out predictions.', '',
      '| Export | Calibration n | Mean width | Test coverage | Test min-bin | Test all bins | Out-of-group coverage | Out-of-group width ratio |',
      '| --- | --- | --- | --- | --- | --- | --- | --- |');
    for (const a of intervals) {
      const iv = a.interval;
      lines.push(`| ${a.exported} | ${iv.n_calibration}${iv.capped ? ' (capped)' : ''} | ${fmt(iv.mean_width)} | ${fmt(iv.test.cells)} | ` +
        `${fmt(iv.test.min_bin)} | ${fmt(iv.test.samples_all_bins)} | ${iv.out_of_group ? fmt(iv.out_of_group.cells) : '—'} | ` +
        `${iv.out_of_group_width_ratio === null ? '—' : fmt(iv.out_of_group_width_ratio, 2) + '×'} |`);
    }
    lines.push('');
  }
  const KINDS = {cascade: 'Atomic → molecular cascade ablation', geant4_atomic: 'Geant4 atomic-input ablation',
    cascade_geant4: 'Cascade source ablation (Geant4-fed vs PubChem-fed atomic model)',
    geant4_cascade: 'Geant4-fed cascade ablation (with vs without pooled Geant4-fed atomic predictions)'};
  const INTRO = {cascade: 'Negative deltas mean the pooled atomic-model features helped.',
    geant4_atomic: 'Same atomic architecture with and without the Geant4 atomic response (mean excitation energy, photo-absorption 10 eV–10 keV) as inputs. Negative deltas mean the Geant4 inputs helped; the group column is leave-one-chemical-group-out CV.',
    cascade_geant4: 'Same molecular architecture pooling the Geant4-fed instead of the PubChem-fed atomic model. Negative deltas favour the Geant4-fed rung.',
    geant4_cascade: 'Negative deltas mean the pooled Geant4-fed atomic predictions helped.'};
  for (const kind of Object.keys(KINDS)) {
    const rows = report.ablation.filter(a => (a.kind || 'cascade') === kind);
    if (!rows.length) continue;
    const atomic = kind === 'geant4_atomic';
    lines.push('## ' + KINDS[kind], '', INTRO[kind], '',
      `| Without | With | ΔCV RMSE | ${atomic ? 'ΔGroup-CV RMSE' : 'ΔFamily-CV RMSE'} | ΔTest RMSE |`, '| --- | --- | --- | --- | --- |');
    for (const a of rows) lines.push(`| ${a.without} | ${a.with} | ${fmt(a.cv_rmse_delta, 4)} | ${fmt(atomic ? a.group_cv_rmse_delta : a.family_cv_rmse_delta, 4)} | ${fmt(a.test_rmse_delta, 4)} |`);
    lines.push('');
  }
  if (report.skipped && report.skipped.length)
    lines.push('Skipped: ' + report.skipped.map(x => x.name + ' (' + x.reason + ')').join(', ') + '.', '');
  return lines.join('\n') + '\n';
}

module.exports = {train, markdown, runMolecular, SEED};

const threads = require('node:worker_threads');
if (!threads.isMainThread && threads.workerData && threads.workerData.spec)
  threads.parentPort.postMessage(runMolecular(threads.workerData.spec, threads.workerData.env));
