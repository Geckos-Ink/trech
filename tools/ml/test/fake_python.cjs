#!/usr/bin/env node
'use strict';
// Test double for `python -m trech_torch.train_surrogate|evolve_structure`: writes a
// generic_surrogate_v1/v2 JSON of exactly the requested shape (zero weights) plus a manifest whose
// selection metrics are a deterministic function of the shape. FAKE_FALLBACK_LINEAR=1 mimics a
// trainer without torch silently exporting a linear model; FAKE_FAIL=1 exits non-zero.
// FAKE_SEED_NOISE=<amplitude> adds a deterministic seed-dependent term to the selection metrics
// (so repeated-seed searches see spread). `-m trech_torch.validate_model` writes a validation
// report whose status is FAKE_VALIDATION (default pass).
const fs = require('node:fs');

const argv = process.argv.slice(2);
if (argv[0] !== '-m') process.exit(3);
const module_ = argv[1];
const opts = {};
for (let i = 2; i < argv.length; ++i) {
  if (!argv[i].startsWith('--')) continue;
  const key = argv[i].slice(2);
  const values = [];
  while (i + 1 < argv.length && !argv[i + 1].startsWith('--')) values.push(argv[++i]);
  opts[key] = values.length === 0 ? true : values.length === 1 ? values[0] : values;
}
if (process.env.FAKE_FAIL) { console.error('fake trainer failure'); process.exit(7); }
if (module_ === 'trech_torch.validate_model') {
  const status = process.env.FAKE_VALIDATION || 'pass';
  const gates = [{ name: 'structure', status: 'pass', detail: 'ok' }, { name: 'test_accuracy', status: status === 'fail' ? 'fail' : 'pass', detail: 'fake' },
    { name: 'beats_linear_baseline', status: status === 'warn' ? 'warn' : 'pass', detail: 'fake' }];
  fs.writeFileSync(opts.out, JSON.stringify({ schema: 'trech_ml_validation_v1', status, gates, model: { path: opts.model },
    test: { runs: [].concat(opts['test-runs'] || []), training_runs: [].concat(opts['training-runs'] || []), source: opts.source } }));
  console.log('fake validated ' + status);
  process.exit(status === 'fail' ? 1 : 0);
}
const inputs = String(opts.inputs).split(',');
const outputs = String(opts.outputs).split(',');
let width = Number(opts.hidden || 0), depth = Number(opts.depth || 2);
const widths = opts.widths ? String(opts.widths).split(',').map(Number) : null;
if (widths) { width = widths[0]; depth = widths.length; }
const acts = opts.activations ? String(opts.activations).split(',') : null;
const activationOf = (d) => (acts ? acts[d] : opts.activation || 'silu');
let linear = !!opts.linear || process.env.FAKE_FALLBACK_LINEAR === '1';
if (module_ === 'trech_torch.evolve_structure') { width = Math.min(8, Number(opts['max-width'])); depth = 1; linear = false; }
const zeros = (rows, cols) => Array.from({ length: rows }, () => new Array(cols).fill(0));
const layers = [];
if (linear) layers.push({ weights: zeros(outputs.length, inputs.length), bias: new Array(outputs.length).fill(0), activation: 'none' });
else {
  const plan = widths || Array.from({ length: depth }, () => width);
  plan.forEach((w, d) => layers.push({ weights: zeros(w, d === 0 ? inputs.length : plan[d - 1]), bias: new Array(w).fill(0), activation: activationOf(d) }));
  layers.push({ weights: zeros(outputs.length, plan[plan.length - 1]), bias: new Array(outputs.length).fill(0), activation: 'none' });
}
const links = outputs.map((o) => (String(opts['log-outputs'] || '').split(',').includes(o) ? 'exp'
  : String(opts['logit-outputs'] || '').split(',').includes(o) ? 'sigmoid' : 'identity'));
// Pretend width 16 / depth 2 fits best: deterministic, shape-dependent selection metrics.
const noiseAmp = Number(process.env.FAKE_SEED_NOISE || 0);
const noise = noiseAmp ? noiseAmp * ((((Number(opts.seed) * 2654435761) >>> 0) % 1000) / 1000 - 0.5) : 0;
const quality = (linear ? 0.5 : 0.95 - Math.abs(Math.log2(width / 16)) * 0.1 - Math.abs(depth - 2) * 0.05) + noise;
const runs = [].concat(opts['validation-runs'] || []);
const metrics = Object.fromEntries(outputs.map((o) => [o, { mae: 1 - quality, rmse: 1.2 * (1 - quality), r2: quality - (runs.join().includes('test') ? 0.01 : 0) }]));
const model = { model: links.every((l) => l === 'identity') ? 'generic_surrogate_v1' : 'generic_surrogate_v2',
  input_features: inputs, output_features: outputs, input_mean: inputs.map(() => 0), input_std: inputs.map(() => 1),
  output_mean: outputs.map(() => 0), output_std: outputs.map(() => 1), trained_from: { runs: [].concat(opts.runs), seed: Number(opts.seed) },
  holdout: { r2_min: Math.min(...outputs.map((o) => metrics[o].r2)), n: 10 } };
if (model.model === 'generic_surrogate_v2') { model.network = { layers }; model.output_transforms = links; } else model.layers = layers;
if (module_ === 'trech_torch.evolve_structure') model.trained_from.structure_search = { selection_loss: 0.1, evaluated_structures: 5 };
fs.writeFileSync(opts['out-json'], JSON.stringify(model));
if (opts.out) fs.writeFileSync(opts.out, 'fake torchscript');
if (opts.manifest) fs.writeFileSync(opts.manifest, JSON.stringify({ schema: 'trech_generic_surrogate_manifest_v1', metrics_holdout: metrics,
  training: { seed: Number(opts.seed), validation_runs: runs } }));
console.log('fake trained ' + (linear ? 'linear' : width + 'x' + depth));
