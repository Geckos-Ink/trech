#!/usr/bin/env node
'use strict';
// Test double for `python -m trech_torch.train_surrogate|evolve_structure`: writes a
// generic_surrogate_v1/v2 JSON of exactly the requested shape (zero weights) plus a manifest whose
// selection metrics are a deterministic function of the shape. FAKE_FALLBACK_LINEAR=1 mimics a
// trainer without torch silently exporting a linear model; FAKE_FAIL=1 exits non-zero.
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
const inputs = String(opts.inputs).split(',');
const outputs = String(opts.outputs).split(',');
let width = Number(opts.hidden || 0), depth = Number(opts.depth || 2);
let linear = !!opts.linear || process.env.FAKE_FALLBACK_LINEAR === '1';
if (module_ === 'trech_torch.evolve_structure') { width = Math.min(8, Number(opts['max-width'])); depth = 1; linear = false; }
const zeros = (rows, cols) => Array.from({ length: rows }, () => new Array(cols).fill(0));
const layers = [];
if (linear) layers.push({ weights: zeros(outputs.length, inputs.length), bias: new Array(outputs.length).fill(0), activation: 'none' });
else {
  for (let d = 0; d < depth; ++d) layers.push({ weights: zeros(width, d === 0 ? inputs.length : width), bias: new Array(width).fill(0), activation: 'silu' });
  layers.push({ weights: zeros(outputs.length, width), bias: new Array(outputs.length).fill(0), activation: 'none' });
}
const links = outputs.map((o) => (String(opts['log-outputs'] || '').split(',').includes(o) ? 'exp'
  : String(opts['logit-outputs'] || '').split(',').includes(o) ? 'sigmoid' : 'identity'));
// Pretend width 16 / depth 2 fits best: deterministic, shape-dependent selection metrics.
const quality = linear ? 0.5 : 0.95 - Math.abs(Math.log2(width / 16)) * 0.1 - Math.abs(depth - 2) * 0.05;
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
