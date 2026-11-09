// Spectrum prediction: learned light spectra of atoms and molecules inside TRECH.
//
// The models and the dataset come from the JavaScript subproject projects/spectrum_prediction:
// measured NIST ASD neutral-atom lines (reached through PubChem element records) and PubChem UV/Vis
// absorption maxima train an atomic line-strength model and an atomic -> molecular envelope model,
// both exported as generic_surrogate_v1 so the engine evaluates them with its ordinary trust profile.
//
// What runs here:
//   atomic rung     ctx.cascade(element facts, ["spectrum_atomic"])  -> line-strength profile
//   molecular rung  ctx.cascade(graph descriptors + pooled atomic predictions, ["spectrum_molecular"])
// The same JS library computes the SMILES descriptors and pooling as the trainer did.
// Labels are measurements, the models are learned comparisons: nothing here is a Geant4 result.
// The Geant4 run only provides a composition-only material probe as context (single target).
TRECH_INCLUDE("../../../projects/spectrum_prediction/lib/index.js");
const SP = globalThis.TRECH_SPECTRA;

const dataDir = TRECH_PARAMETER("data_dir").trim() || "../../../data/spectrum_prediction";
const dataPath = name => dataDir.replace(/\/+$/, "") + "/" + name;
globalThis.TRECH_SPECTRUM_DATA = {
  dataset: TRECH_READ_JSON(dataPath("dataset.json")),
  report: TRECH_READ_JSON(dataPath("report.json")),
  atomicModel: TRECH_READ_JSON(dataPath("models/spectrum_atomic.json")),
  molecularModel: TRECH_READ_JSON(dataPath("models/spectrum_molecular.json"))
};
const data = globalThis.TRECH_SPECTRUM_DATA;
if (data.dataset.schema !== "trech_spectrum_dataset_v1" || data.report.schema !== "trech_spectrum_report_v1")
  throw new Error("data_dir does not hold a spectrum-prediction dataset/report");
const selection = TRECH_PARAMETER("selection");
const targetKind = TRECH_PARAMETER("target_kind");
const moleculeName = TRECH_PARAMETER("molecule");
const elementSymbol = TRECH_PARAMETER("element");
const mode = TRECH_PARAMETER("mode");
const studioMode = TRECH_PARAMETER("studio_mode");
data.studioMode = studioMode;
const density = TRECH_PARAMETER("proxy_density_gcm3");

const testIds = {atom: new Set(data.atomicModel.trained_from.test_ids), molecule: new Set(data.molecularModel.trained_from.test_ids)};
const trainIds = {atom: new Set(data.atomicModel.trained_from.train_ids), molecule: new Set(data.molecularModel.trained_from.train_ids)};
function splitOf(kind, id) { return testIds[kind].has(id) ? "test" : trainIds[kind].has(id) ? "train" : "unused"; }

const targets = [];
if (selection === "single") {
  if (targetKind === "molecule") targets.push({kind: "molecule", record: data.dataset.molecules.find(m => m.name === moleculeName)});
  else targets.push({kind: "atom", record: data.dataset.atoms.find(a => a.symbol === elementSymbol)});
} else {
  if (selection !== "all_atoms") for (const m of data.dataset.molecules)
    if (selection === "all_molecules" || testIds.molecule.has(m.id)) targets.push({kind: "molecule", record: m});
  if (selection !== "all_molecules") for (const a of data.dataset.atoms)
    if (selection === "all_atoms" || testIds.atom.has(a.id)) targets.push({kind: "atom", record: a});
}
if (!targets.length || targets.some(t => !t.record)) throw new Error("No dataset record for the selected target");

// Composition-only Geant4 probe for a single target: context facts, never a model input.
function composition(target) {
  if (target.kind === "atom") return [{element: target.record.symbol, atoms: 1}];
  const counts = SP.smiles.analyze(SP.smiles.parse(target.record.smiles)).element_counts;
  return Object.keys(counts).filter(e => counts[e] > 0).sort().map(e => ({element: e, atoms: counts[e]}));
}
const probeMaterial = selection === "single" ?
  {name: "spectrum_probe", densityGcm3: density, components: composition(targets[0])} : null;

globalThis.TRECH_CONFIG = {
  detector: {worldSizeMm: 20, worldMaterial: probeMaterial ? "spectrum_probe" : "G4_Galactic"},
  beam: {particle: "e-", energyMeV: 0.1, direction: [0, 0, 1]},
  run: {nEvents: 1, seed: 20261107, threads: 1},
  determinism: {mode},
  materials: probeMaterial ? [probeMaterial] : [],
  materialProbe: probeMaterial ? {enable: true, materials: ["spectrum_probe"]} : {enable: false},
  models: [
    {name: "spectrum_atomic", scale: "atomic", path: dataPath("models/spectrum_atomic.json")},
    {name: "spectrum_molecular", scale: "nano", path: dataPath("models/spectrum_molecular.json")}
  ],
  viz: TRECH_VIEWS["spectrum_prediction"]["viz0"](),
  hooks: {maxEmitsPerCallback: 512, maxEmitPayloadBytes: 1048576,
    inputs: studioMode ? {schema: "trech_spectrum_inputs_v1", selection, target_kind: targetKind,
      molecule: moleculeName, element: elementSymbol, data_dir: dataDir,
      dataset_counts: data.dataset.counts, report_dataset_sha256: data.report.dataset_sha256} : undefined}
};
if (!studioMode) delete globalThis.TRECH_CONFIG.hooks.inputs;

const ATOMIC_OUT = data.atomicModel.output_features, MOLECULAR_OUT = data.molecularModel.output_features;
const GRIDS = {atom: data.dataset.grids.atomic, molecule: data.dataset.grids.molecular};

function stageTrust(result) {
  const trace = result && result.__cascade && result.__cascade.trace && result.__cascade.trace[0];
  if (!trace) return null;
  return {model: trace.model, scale: trace.scale, ran: trace.ran, inDomain: trace.inDomain, extrapolation: trace.extrapolation,
    outOfDomainInputs: trace.outOfDomainInputs, starvedInputs: trace.starvedInputs, jointStarved: trace.jointStarved,
    jointMeasured: trace.jointMeasured, holdoutR2: trace.holdoutR2, holdoutSamples: trace.holdoutSamples};
}
function vectorFrom(result, names) {
  if (!result) return null;
  const v = names.map(n => result[n]);
  return v.every(Number.isFinite) ? v : null;
}
// Calibrated per-bin interval as the ENGINE reports it (stage outputAccuracy, read from the
// model's prediction_interval block) next to the measured holdout rmse. Lower bounds clip at
// the targets' physical floor of 0. Null when inference is off or the model carries none.
function intervalFrom(result, names, predicted) {
  const trace = result && result.__cascade && result.__cascade.trace && result.__cascade.trace[0];
  const acc = trace && trace.outputAccuracy;
  if (!predicted || !acc) return null;
  const half = names.map(n => acc[n] ? acc[n].interval_half_width : undefined);
  if (!half.every(Number.isFinite)) return null;
  const b = SP.uncertainty.bounds(predicted, half, 0);
  return {lower: b.lower, upper: b.upper, half_width: half, nominal_coverage: acc[names[0]].interval_coverage,
    holdout_rmse: names.map(n => Number.isFinite(acc[n].rmse) ? acc[n].rmse : null),
    marginal: "per bin", source: "engine outputAccuracy from the model prediction_interval (split-conformal CV residuals)"};
}
function intervalCoverage(measured, predicted, interval) {
  return interval ? SP.uncertainty.coverage([measured], [predicted], interval.half_width).cells : null;
}
function atomicPrediction(ctx, symbol, cache) {
  if (cache[symbol]) return cache[symbol];
  const facts = data.dataset.element_facts[symbol];
  if (!facts) throw new Error("No PubChem element facts for " + symbol);
  const result = ctx.cascade(Object.assign({}, facts.features), ["spectrum_atomic"]);
  const profile = vectorFrom(result, ATOMIC_OUT);
  cache[symbol] = {profile, result, interval: intervalFrom(result, ATOMIC_OUT, profile)};
  return cache[symbol];
}
function compare(measured, predicted, grid) {
  if (!predicted) return null;
  let se = 0;
  measured.forEach((v, i) => { se += (v - predicted[i]) * (v - predicted[i]); });
  const pm = SP.grid.peakWavelength(measured, grid), pp = SP.grid.peakWavelength(predicted, grid);
  return {rmse: Math.sqrt(se / measured.length), cosine: SP.validate.cosine(measured, predicted),
    measured_peak_nm: pm, predicted_peak_nm: pp, peak_error_nm: pm !== null && pp !== null ? Math.abs(pm - pp) : null};
}

function predictTarget(ctx, target, cache) {
  const r = target.record, grid = GRIDS[target.kind];
  const base = {kind: target.kind, id: r.id, split: splitOf(target.kind, r.id),
    grid: {unit: grid.unit, start: grid.start, stop: grid.stop, bins: grid.bins, centers: SP.grid.centers(grid), kind: grid.kind},
    measured: r.target, measured_label: "measured reference (representation of " +
      (target.kind === "atom" ? "NIST ASD g_k*A_ki line list" : "PubChem UV/Vis maxima") + ")"};
  if (target.kind === "atom") {
    const a = atomicPrediction(ctx, r.symbol, cache);
    return Object.assign(base, {label: r.symbol + " I", z: r.z, lines: r.lines, sources: r.sources,
      predicted: a.profile, interval: a.interval, interval_covered_fraction: intervalCoverage(r.target, a.profile, a.interval),
      metrics: compare(r.target, a.profile, grid), stages: [stageTrust(a.result)].filter(Boolean),
      model: "spectrum_atomic", model_inputs: data.dataset.element_facts[r.symbol].features});
  }
  const elements = Object.keys(SP.smiles.analyze(SP.smiles.parse(r.smiles)).element_counts);
  const summaries = {}, atomicStages = [];
  let available = true;
  for (const e of elements) {
    const a = atomicPrediction(ctx, e, cache);
    if (!a.profile) { available = false; continue; }
    summaries[e] = SP.features.profileSummary(a.profile, GRIDS.atom);
    atomicStages.push(Object.assign({element: e}, stageTrust(a.result)));
  }
  let predicted = null, molecularStage = null, inputs = null, interval = null;
  if (available) {
    inputs = SP.features.moleculeInputs(r.smiles, r.solvent_class, summaries).x;
    const result = ctx.cascade(inputs, ["spectrum_molecular"]);
    predicted = vectorFrom(result, MOLECULAR_OUT);
    interval = intervalFrom(result, MOLECULAR_OUT, predicted);
    molecularStage = stageTrust(result);
  }
  return Object.assign(base, {label: r.name, cid: r.cid, formula: r.formula, smiles: r.smiles, family: r.family,
    solvent: r.solvent, solvent_class: r.solvent_class, measured_bands: r.bands, sources: {uv_text: r.sources.uv_text,
      uv_reference: r.sources.uv_reference, uv_url: r.sources.uv.url},
    predicted, interval, interval_covered_fraction: intervalCoverage(r.target, predicted, interval),
    metrics: compare(r.target, predicted, grid), model: "spectrum_molecular", model_inputs: inputs,
    atomic_pool: inputs ? SP.features.ATOMIC_POOL.reduce((o, k) => ((o[k] = inputs[k]), o), {}) : null,
    stages: atomicStages.concat(molecularStage ? [molecularStage] : [])});
}

const HONESTY = {geant4_trained: false, measured_labels: true,
  statement: "Learned prediction from measured spectra (comparison only); not a Geant4 result. Strict mode disables it."};

// Trainer-reported split-noise checks (atomic only): repeated re-salted k-fold CV and
// leave-one-chemical-group-out CV on the training split. Copied for display; they
// are never used for ranking and Studio does not recompute them.
function splitNoise(a) {
  const rc = a.repeated_cv, gc = a.group_cv;
  if (!rc && !gc) return null;
  return {
    repeated_cv: rc ? {repeats: rc.repeats, folds: rc.folds, per_fold_rmse: rc.per_fold.rmse,
      pooled_r2: rc.pooled.r2 || null, pooled_cosine: rc.pooled.cosine || null} : null,
    group_cv: gc ? {groups: gc.per_group.length, rmse: gc.summary.rmse || null,
      pooled_r2: gc.pooled ? gc.pooled.r2 : null,
      per_group: gc.per_group.map(g => ({group: g.group, n: g.n, rmse: g.rmse}))} : null
  };
}

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const cache = {}, records = [];
    for (const target of targets) {
      const record = predictTarget(ctx, target, cache);
      record.inference = mode === "strict" ? "disabled_strict" : record.predicted ? "predicted" : "unavailable";
      record.honesty = HONESTY;
      record.display = TRECH_VIEWS["spectrum_prediction"]["display1"](record);
      records.push(record);
      ctx.emit("spectrum_prediction", record);
    }
    const scored = {atom: records.filter(r => r.kind === "atom" && r.predicted), molecule: records.filter(r => r.kind === "molecule" && r.predicted)};
    const summary = {selection, mode, counts: {targets: records.length, predicted: records.filter(r => r.predicted).length},
      honesty: HONESTY, models: {}};
    for (const kind of ["atom", "molecule"]) {
      if (!scored[kind].length) continue;
      const m = SP.validate.metrics(scored[kind].map(r => r.measured), scored[kind].map(r => r.predicted), GRIDS[kind]);
      const withInterval = scored[kind].filter(r => r.interval);
      const cov = withInterval.length ? SP.uncertainty.coverage(withInterval.map(r => r.measured), withInterval.map(r => r.predicted),
        withInterval[0].interval.half_width) : null;
      summary.models[kind === "atom" ? "spectrum_atomic" : "spectrum_molecular"] = {n: m.n, rmse: m.rmse, cosine: m.cosine,
        peak_error_nm: m.peak_error_nm, r2: m.r2,
        interval_coverage: cov ? {nominal: withInterval[0].interval.nominal_coverage, cells: cov.cells, min_bin: cov.min_bin,
          samples_all_bins: cov.samples_all_bins, n: cov.n} : null, splits: scored[kind].reduce((o, r) => ((o[r.split] = (o[r.split] || 0) + 1), o), {})};
    }
    ctx.emit("spectrum_summary", summary);
    if (studioMode) {
      const rep = data.report;
      ctx.emit("spectrum_model_report", {dataset_sha256: rep.dataset_sha256, counts: rep.counts, protocol: rep.protocol,
        ranking: rep.ranking, ablation: rep.ablation, honesty: rep.honesty, exports: rep.exports,
        architectures: rep.architectures.map(a => ({name: a.name, task: a.task, family: a.family, note: a.note,
          exported: a.exported, cv_rmse: a.cv.rmse, cv_cosine: a.cv.cosine,
          family_cv_rmse: a.family_cv ? a.family_cv.summary.rmse : null, test: a.test, interval: a.interval || null,
          split_noise: splitNoise(a)}))});
    }
    if (probeMaterial) {
      const probe = ctx.materials && ctx.materials.spectrum_probe;
      ctx.emit("spectrum_geant4_context", {material: probeMaterial, available: !!(probe && probe.available),
        density_g_per_cm3: probe ? probe.density_g_per_cm3 : null,
        electron_density_per_cm3: probe ? probe.electron_density_per_cm3 : null,
        mean_excitation_energy_ev: probe ? probe.mean_excitation_energy_ev : null,
        note: "Geant4 facts for the same composition at a declared proxy density. Context for future particle-trained lifts; not a spectrum model input."});
    }
  }
};
