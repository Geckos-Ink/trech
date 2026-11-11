'use strict';
// node --test tools/ml/test/  (CTest: trech_ml_models_js)
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');

const { evaluate, summarize, library, LIB } = require('../lib/load');
const { ModelStore, parseBytes } = require('../lib/store');
const { Orchestrator, trainerArgs } = require('../lib/orchestrate');

// VM-realm objects have foreign prototypes; compare their JSON form.
const eq = (actual, expected, message) => assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected, message);
const FAKE = [process.execPath, path.join(__dirname, 'fake_python.cjs')];
const CLI = path.join(__dirname, '..', 'bin', 'trech-ml.cjs');

function tmp() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'trech-ml-'));
}
function write(dir, name, text) {
  const file = path.join(dir, name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
  return file;
}
function clock(start = '2026-01-01T00:00:00Z') {
  let t = Date.parse(start);
  const now = () => new Date(t);
  now.advanceDays = (d) => { t += d * 86400000; };
  return now;
}
const BASE = { name: 'demo', inputs: ['a', 'b'], outputs: ['y'], scale: 'micro',
  training: { source: 'scores', runs: ['r/train'], validationRuns: ['r/valid'], testRuns: ['r/test'] } };

function modelFile(dir, name, { inputs = ['a', 'b'], outputs = ['y'], plan = [[2, 16, 'silu'], [16, 16, 'silu'], [16, 1, 'none']], links = null, note = null } = {}) {
  const layers = plan.map(([i, o, act]) => ({ weights: Array.from({ length: o }, () => new Array(i).fill(0.5)), bias: new Array(o).fill(0), activation: act }));
  const model = { model: links ? 'generic_surrogate_v2' : 'generic_surrogate_v1', input_features: inputs, output_features: outputs,
    input_mean: [0, 0], input_std: [1, 1], output_mean: [0], output_std: [1] };
  if (links) { model.network = { layers }; model.output_transforms = links; } else model.layers = layers;
  if (note) model.note = note;
  return write(dir, name, JSON.stringify(model));
}

test('definitions validate, normalize and hash independently of key order', () => {
  const ml = library();
  const a = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 16, depth: 2 } }));
  ml.reset();
  const b = ml.defineModel({ structure: { depth: 2, width: 16, family: 'mlp' }, training: BASE.training, scale: 'micro', outputs: ['y'], inputs: ['a', 'b'], name: 'demo' });
  assert.equal(a.structure_id, b.structure_id);
  assert.equal(a.definition_hash, b.definition_hash);
  assert.equal(a.parameter_count, (2 * 16 + 16) + (16 * 16 + 16) + (16 + 1));
  eq(ml.layerPlan(2, 1, a.structure), [[2, 16, 'silu'], [16, 16, 'silu'], [16, 1, 'none']]);
  ml.reset();
  const linked = ml.defineModel(Object.assign({}, BASE, { links: { y: 'exp' }, structure: { family: 'mlp', width: 16, depth: 2 } }));
  assert.notEqual(linked.structure_id, a.structure_id, 'output links are part of structure identity');
  assert.equal(linked.signature.model, 'generic_surrogate_v2');
  const reject = (spec, pattern) => { ml.reset(); assert.throws(() => ml.defineModel(Object.assign({}, BASE, spec)), pattern); };
  reject({ structure: { family: 'mlp', width: 16 }, extra: 1 }, /unknown key 'extra'/);
  reject({ name: '9bad', structure: { family: 'linear' } }, /name must match/);
  reject({ outputs: ['a'], structure: { family: 'linear' } }, /both an input and an output/);
  reject({ structure: { family: 'linear', width: 3 } }, /linear structure takes only l2/);
  reject({ structure: { family: 'mlp', width: 8, activation: 'gelu' } }, /activation must be one of silu\/tanh\/relu\/sigmoid/);
  reject({ structure: { family: 'mlp', width: 8 }, training: { runs: ['x'], validationRuns: ['x'] } }, /must be disjoint/);
  reject({ structure: { family: 'mlp', width: 8 }, training: { source: 'hook_emits', runs: ['x'] } }, /tag is required/);
  reject({ structure: { family: 'mlp', width: 8 }, links: { z: 'exp' } }, /unknown output 'z'/);
  ml.reset();
  ml.defineModel(Object.assign({}, BASE, { structure: { family: 'linear' } }));
  assert.throws(() => ml.defineModel(Object.assign({}, BASE, { structure: { family: 'linear' } })), /defined twice/);
});

test('checkpoint signatures are read from weights and match definitions', () => {
  const ml = library();
  const dir = tmp();
  const def = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 16, depth: 2 } }));
  const sig = ml.checkpointSignature(JSON.parse(fs.readFileSync(modelFile(dir, 'm.json'), 'utf8')));
  assert.equal(ml.structureId(sig), def.structure_id);
  eq(ml.structureFromPlan(sig.layers), { family: 'mlp', width: 16, depth: 2, activation: 'silu' });
  const v2 = ml.checkpointSignature(JSON.parse(fs.readFileSync(modelFile(dir, 'l.json', { links: ['exp'] }), 'utf8')));
  eq(v2.links, ['exp']);
  assert.throws(() => ml.checkpointSignature({ model: 'ridge_optics_n_v1' }), /unsupported model kind/);
  assert.throws(() => ml.checkpointSignature(JSON.parse(fs.readFileSync(modelFile(dir, 'bad.json', { plan: [[2, 4, 'silu'], [3, 1, 'none']] }), 'utf8'))), /does not chain/);
});

test('search candidates are deterministic, deduplicated and budgeted', () => {
  const ml = library();
  const grid = ml.defineSearch(Object.assign({}, BASE, { name: 'g', space: { families: ['linear', 'mlp'], width: [8, 16], depth: { min: 1, max: 2 } },
    budget: { maxParameters: 300 } }));
  const plan = ml.candidates(grid);
  eq(plan.candidates.map((c) => c.structure_label), ['linear(l2=0.001)', 'mlp(width=8,depth=1,silu)', 'mlp(width=16,depth=1,silu)', 'mlp(width=8,depth=2,silu)']);
  assert.match(plan.skipped[0].reason, /parameter budget/);
  const random = ml.defineSearch(Object.assign({}, BASE, { name: 'r', strategy: 'random', seed: 7, space: { width: { min: 4, max: 64, factor: 2 }, depth: [1, 2, 3] }, budget: { maxCandidates: 5 } }));
  const first = JSON.parse(JSON.stringify(ml.candidates(random).candidates.map((c) => c.structure_id)));
  eq(ml.candidates(random).candidates.map((c) => c.structure_id), first);
  assert.equal(first.length, 5);
  assert.equal(ml.candidates(random).skipped.filter((s) => s.reason === 'candidate budget').length, 15 - 5);
  const custom = ml.defineSearch(Object.assign({}, BASE, { name: 'c', strategy: 'custom',
    generate: (space, h) => [{ family: 'mlp', width: 12, depth: 2 }, { family: 'mlp', depth: 2, width: 12 }, { family: 'linear', l2: h.random() > 2 ? 1 : 0.1 }] }));
  const customPlan = ml.candidates(custom);
  assert.equal(customPlan.candidates.length, 2);
  assert.equal(customPlan.skipped[0].reason, 'duplicate structure');
  const l2 = ml.defineSearch(Object.assign({}, BASE, { name: 'l2', space: { families: ['linear'], l2: [0.1, 0.01] } }));
  const l2Plan = ml.candidates(l2).candidates;
  assert.equal(l2Plan.length, 2, 'l2 variants share a structure_id but remain distinct candidates');
  assert.equal(l2Plan[0].structure_id, l2Plan[1].structure_id);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'n', training: { runs: ['a'] } })), /needs training.validationRuns/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'e', strategy: 'evolvo', links: { y: 'exp' } })), /does not export output links/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'x', strategy: 'custom' })), /needs generate/);
});

test('objectives score selection metrics and ranking breaks ties deterministically', () => {
  const ml = library();
  const s = ml.defineSearch(Object.assign({}, BASE, { name: 's', outputs: ['y', 'z'], complexityPenalty: 0.001 }));
  const d = { parameter_count: 10, structure: {}, structure_id: 'sx' };
  const m = { y: { r2: 0.9, rmse: 1, mae: 1 }, z: { r2: 0.7, rmse: 3, mae: 2 } };
  assert.ok(Math.abs(ml.score(s, m, d) - (0.3 + 0.01)) < 1e-12);
  assert.equal(ml.score(s, { y: m.y }, d), null, 'missing output metrics are unrankable');
  const custom = ml.defineSearch(Object.assign({}, BASE, { name: 'f', objective: (metrics, c) => metrics.y.rmse * c.parameter_count }));
  assert.equal(ml.score(custom, { y: { r2: 1, rmse: 2, mae: 0 } }, d), 20);
  const order = ml.rank([{ loss: 1, parameter_count: 5, structure_id: 'b' }, { loss: null, parameter_count: 1, structure_id: 'a' },
    { loss: 1, parameter_count: 5, structure_id: 'a' }, { loss: 0.5, parameter_count: 99, structure_id: 'z' }]);
  eq(order.map((r) => r.structure_id), ['z', 'a', 'b', 'a']);
});

test('the loader isolates files, reports error lines and times out runaway code', () => {
  const dir = tmp();
  write(dir, 'shared.js', 'globalThis.COLS = ["a", "b"];');
  const good = write(dir, 'good.model.js', 'TRECH_INCLUDE("shared.js");\nTRECH_ML.defineModel({name: "g", inputs: COLS, outputs: ["y"], structure: {family: "linear"}});');
  const s = summarize(evaluate(good));
  assert.equal(s.ok, true);
  assert.equal(s.definitions[0].name, 'g');
  const bad = write(dir, 'bad.model.js', '// line 1\nTRECH_ML.defineModel({name: "b", inputs: ["a"], outputs: ["y"], structure: {family: "mlp", width: 0}});');
  const e = summarize(evaluate(bad));
  assert.equal(e.ok, false);
  assert.equal(e.errors[0].line, 2);
  assert.match(e.errors[0].message, /structure.width/);
  const loop = summarize(evaluate(bad, { source: 'for(;;){}', timeoutMs: 100 }));
  assert.match(loop.errors[0].message, /timed out/);
  const noRequire = summarize(evaluate(bad, { source: 'require("fs")' }));
  assert.match(noRequire.errors[0].message, /require is not defined/);
});

test('store registers typed versions and refuses structure conflicts', () => {
  const ml = library();
  const dir = tmp();
  const store = new ModelStore(path.join(dir, 'store'), { now: clock() });
  const def = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 16, depth: 2 } }));
  const file = modelFile(dir, 'm.json');
  const v1 = store.register({ definition: def, files: [{ format: 'generic_surrogate', source: file }] });
  assert.equal(v1.id, 'demo@v1');
  assert.match(v1.files[0].path, new RegExp('^checkpoints/demo/' + def.structure_id + '/v0001/model.json$'));
  assert.equal(store.register({ definition: def, files: [{ format: 'generic_surrogate', source: file }] }).duplicate, true);
  // Same bytes under another role are a separate typed checkpoint.
  assert.equal(store.register({ definition: def, role: 'intermediate', files: [{ format: 'generic_surrogate', source: file }] }).id, 'demo@v2');
  const wrong = modelFile(dir, 'w.json', { plan: [[2, 1, 'none']] });
  assert.throws(() => store.register({ definition: def, files: [{ format: 'generic_surrogate', source: wrong }] }), /structure conflict.*linear/);
  assert.throws(() => store.register({ definition: def, files: [{ format: 'generic_surrogate', source: file }, { format: 'torchscript', source: file }] }), /must be a \.pt/);
  const pt = write(dir, 'm.pt', 'pt');
  const v3 = store.register({ definition: def, files: [{ format: 'generic_surrogate', source: modelFile(dir, 'm2.json', { note: { retrained: true } }) }, { format: 'torchscript', source: pt }] });
  eq(v3.files.map((f) => f.format), ['generic_surrogate', 'torchscript']);
  assert.equal(v3.files[1].path, v3.files[0].path.replace('model.json', 'model.pt'));
  // Imported checkpoint without a definition derives its structure from the weights.
  const imported = store.register({ name: 'other', files: [{ format: 'generic_surrogate', source: wrong }] });
  assert.equal(imported.structure_label, 'linear');
  assert.equal(imported.structure.family, 'linear');
  // Versions are never reused, even after deletion.
  store.remove('demo@v2', {});
  const again = store.register({ definition: def, role: 'intermediate', files: [{ format: 'generic_surrogate', source: file }] });
  assert.equal(again.version, 4);
  assert.equal(store.verify().ok, true);
});

test('resolution honours version, active and structure; QuickJS-style modelEntry uses TRECH_READ_JSON', () => {
  const ml = library();
  const dir = tmp();
  const store = new ModelStore(path.join(dir, 'store'), { now: clock() });
  const def16 = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 16, depth: 2 } }));
  ml.reset();
  const defLin = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'linear' } }));
  store.register({ definition: def16, files: [{ format: 'generic_surrogate', source: modelFile(dir, 'a.json') }] });
  store.register({ definition: defLin, files: [{ format: 'generic_surrogate', source: modelFile(dir, 'b.json', { plan: [[2, 1, 'none']] }) }] });
  const index = store.read();
  assert.equal(ml.resolve(index, 'demo').id, 'demo@v2');
  assert.equal(ml.resolve(index, 'demo', { definition: def16 }).id, 'demo@v1');
  assert.equal(ml.resolve(index, 'demo', { version: 1 }).id, 'demo@v1');
  assert.throws(() => ml.resolve(index, 'demo', { version: 2, definition: def16 }), /structure conflict/);
  store.activate('demo@v1');
  assert.equal(ml.resolve(store.read(), 'demo').resolved_by, 'active');
  assert.equal(ml.resolve(store.read(), 'demo', { definition: defLin }).id, 'demo@v2', 'an incompatible active checkpoint is skipped');
  // QuickJS path: the index is read relative to the calling scenario.
  const context = vm.createContext({ TRECH_READ_JSON: (p) => JSON.parse(fs.readFileSync(path.join(dir, p), 'utf8')) });
  vm.runInContext(fs.readFileSync(LIB, 'utf8'), context);
  const entry = context.TRECH_ML.modelEntry('demo', { index: 'store/index.json' });
  assert.equal(entry.path, 'store/checkpoints/demo/' + def16.structure_id + '/v0001/model.json');
  assert.equal(entry.scale, undefined);
  assert.equal(entry.registry.resolved_by, 'active');
  const fallback = context.TRECH_ML.modelEntry('missing', { index: 'nope/index.json', fallbackPath: 'data/x.json', scale: 'meso' });
  eq(JSON.parse(JSON.stringify(fallback)), { name: 'missing', path: 'data/x.json', scale: 'meso', registry: { checkpoint: null, fallback: true } });
  assert.throws(() => context.TRECH_ML.modelEntry('missing', { index: 'nope/index.json' }), /cannot read registry index/);
});

test('usage comes from run provenance hashes and is counted once per run', () => {
  const ml = library();
  const dir = tmp();
  const now = clock();
  const store = new ModelStore(path.join(dir, 'store'), { now });
  const def = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'linear' } }));
  const rec = store.register({ definition: def, files: [{ format: 'generic_surrogate', source: modelFile(dir, 'a.json', { plan: [[2, 1, 'none']] }) }] });
  const run = path.join(dir, 'run');
  write(run, 'trech_provenance.jsonl', JSON.stringify({ phase: 'run_start', config_hash: 'abc', model_artifacts: { models: [
    { name: 'demo', loaded: true, sha256: rec.files[0].sha256 }, { name: 'other', loaded: true, sha256: '0'.repeat(64) }] } }) + '\n');
  eq(store.touchRun(run).touched, ['demo@v1']);
  assert.equal(store.touchRun(run).already_recorded, true);
  const c = store.read().models.demo.checkpoints[0];
  assert.equal(c.use_count, 1);
  assert.ok(c.last_used_at);
  store.touch({ ids: ['demo@v1'] });
  assert.equal(store.summary().models[0].use_count, 2);
});

test('prune keeps pinned, active and newest versions and frees least-recently-used space', () => {
  const ml = library();
  const dir = tmp();
  const now = clock();
  const store = new ModelStore(path.join(dir, 'store'), { now });
  const def = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 4, depth: 1 } }));
  const ids = [];
  for (let i = 0; i < 6; ++i) {
    const file = modelFile(dir, 'm' + i + '.json', { plan: [[2, 4, 'silu'], [4, 1, 'none']] });
    const json = JSON.parse(fs.readFileSync(file, 'utf8'));
    json.layers[0].bias[0] = i; // distinct bytes
    fs.writeFileSync(file, JSON.stringify(json));
    ids.push(store.register({ definition: def, role: i === 5 ? 'candidate' : 'final', files: [{ format: 'generic_surrogate', source: file }] }).id);
    now.advanceDays(10);
  }
  store.setPinned(ids[0], true);
  store.activate(ids[1]);
  store.touch({ ids: [ids[2]] }); // used "today"
  const plan = store.prunePlan({ keepLast: 2 });
  // newest final/best = v4, v5 (v6 is a candidate); v1 pinned, v2 active.
  eq(plan.delete.map((d) => d.id).sort(), [ids[2], ids[5]].sort());
  eq(store.prunePlan({ keepLast: 2, unusedDays: 5 }).delete.map((d) => d.id), [ids[5]]);
  eq(store.prunePlan({ keepLast: 2, roles: ['candidate'] }).delete.map((d) => d.id), [ids[5]]);
  const total = plan.total_bytes;
  const one = store.prunePlan({ keepLast: 2, maxBytes: total - 1 });
  assert.equal(one.delete.length, 1);
  assert.equal(one.delete[0].id, ids[5], 'least recently used first');
  assert.equal(one.fits, true);
  const result = store.prune({ keepLast: 2 });
  assert.equal(result.removed.length, 2);
  assert.ok(!fs.existsSync(path.join(store.dir, 'checkpoints', 'demo', def.structure_id, 'v0003')));
  const blocked = store.deletePlan('demo', { all: true });
  eq(blocked.blocked.map((b) => b.reason).sort(), ['active', 'pinned']);
  assert.equal(store.remove('demo', { all: true, force: true }).removed.length, 4);
  eq(store.read().models, {});
  assert.ok(!fs.existsSync(path.join(store.dir, 'checkpoints', 'demo')), 'empty model directories are removed');
  assert.equal(parseBytes('1.5G'), Math.round(1.5 * 1024 ** 3));
  assert.equal(parseBytes('500MiB'), 500 * 1024 ** 2);
});

test('verify and gc find modified files and orphan directories', () => {
  const ml = library();
  const dir = tmp();
  const store = new ModelStore(path.join(dir, 'store'));
  const def = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'linear' } }));
  const rec = store.register({ definition: def, files: [{ format: 'generic_surrogate', source: modelFile(dir, 'a.json', { plan: [[2, 1, 'none']] }) }] });
  fs.appendFileSync(path.join(store.dir, rec.files[0].path), ' ');
  assert.equal(store.verify().files[0].status, 'modified');
  fs.mkdirSync(path.join(store.dir, 'checkpoints', 'ghost', 'sx', 'v0001'), { recursive: true });
  eq(store.gcPlan().orphans.map((o) => o.path), [path.join('checkpoints', 'ghost', 'sx', 'v0001')]);
  store.gc();
  assert.equal(store.gcPlan().orphans.length, 0);
});

test('orchestrator trains, rejects trainer fallbacks, and runs an honest search', async () => {
  const dir = tmp();
  const defs = write(dir, 'demo.model.js', `
    TRECH_ML.defineModel({name: "demo", inputs: ["a", "b"], outputs: ["y"], links: {y: "exp"},
      structure: {family: "mlp", width: 16, depth: 2}, training: {runs: ["runs/train"], testRuns: ["runs/test"], torchscript: true}});
    TRECH_ML.defineSearch({name: "demo_search", inputs: ["a", "b"], outputs: ["y"],
      training: {runs: ["runs/train"], validationRuns: ["runs/valid"], testRuns: ["runs/test"]},
      space: {families: ["linear", "mlp"], width: [8, 16, 32], depth: [1, 2]}, keepCandidates: 2, activate: true});`);
  const loaded = evaluate(defs);
  assert.equal(loaded.ok, true);
  const events = [];
  const store = new ModelStore(path.join(dir, 'store'), { now: clock() });
  const orch = new Orchestrator(store, { root: dir, python: FAKE, emit: (e) => events.push(e) });
  const args = trainerArgs(loaded.definitions[0], { root: dir, outJson: 'o.json', manifest: 'm.json', holdoutRuns: ['runs/test'] });
  assert.ok(args.includes('--log-outputs') && args.includes('--hidden') && args[args.indexOf('--validation-runs') + 1] === path.join(dir, 'runs/test'));
  const rec = await orch.train(loaded.definitions[0]);
  assert.equal(rec.holdout_source, 'test_runs');
  eq(rec.files.map((f) => f.format), ['generic_surrogate', 'torchscript']);
  eq(rec.links, ['exp']);
  process.env.FAKE_FALLBACK_LINEAR = '1';
  try {
    await assert.rejects(orch.train(loaded.definitions[0]), /structure conflict.*torch is missing/);
  } finally { delete process.env.FAKE_FALLBACK_LINEAR; }
  assert.equal(store.read().models.demo.checkpoints.length, 1, 'a conflicting checkpoint is not registered');
  assert.equal(fs.readdirSync(path.join(store.dir, 'staging')).length, 0, 'staging is cleaned up');
  const report = await orch.search(loaded, loaded.searches[0]);
  assert.equal(report.evaluated, 7);
  assert.equal(report.ranking[0].structure_label, 'mlp(width=16,depth=2,silu)');
  assert.equal(report.best.holdout_source, 'test_runs');
  assert.equal(report.retrain_identical, true);
  assert.equal(report.discarded_candidates.length, 5);
  const entry = store.read().models.demo_search;
  assert.equal(entry.checkpoints.filter((c) => c.role === 'candidate').length, 2);
  assert.equal(entry.active, report.best.checkpoint);
  assert.ok(fs.existsSync(path.join(store.dir, report.report)));
  assert.ok(events.some((e) => e.event === 'candidate' && e.loss !== null));
});

test('per-layer structures: canonical identity, exported plans and trainer arguments', () => {
  const ml = library();
  const uniform = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 16, depth: 2 } }));
  ml.reset();
  const spelled = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', widths: [16, 16], activations: ['silu', 'silu'] } }));
  assert.equal(spelled.structure_id, uniform.structure_id, 'a per-layer spelling of a uniform net keeps its identity');
  assert.equal(spelled.definition_hash, uniform.definition_hash);
  eq(spelled.structure, { family: 'mlp', width: 16, depth: 2, activation: 'silu' });
  ml.reset();
  const taper = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', widths: [32, 16, 8], activation: 'tanh' } }));
  eq(ml.layerPlan(2, 1, taper.structure), [[2, 32, 'tanh'], [32, 16, 'tanh'], [16, 8, 'tanh'], [8, 1, 'none']]);
  assert.equal(taper.parameter_count, (2 * 32 + 32) + (32 * 16 + 16) + (16 * 8 + 8) + (8 + 1));
  assert.equal(taper.structure_label, 'mlp(32→16→8,tanh)');
  ml.reset();
  const mixed = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', widths: [12, 6], activations: ['tanh', 'relu'] } }));
  assert.equal(mixed.structure_label, 'mlp(12:tanh→6:relu)');
  assert.notEqual(mixed.structure_id, taper.structure_id);
  // Read back from weights: the same plan maps to the same canonical structure and identity.
  const dir = tmp();
  const sig = ml.checkpointSignature(JSON.parse(fs.readFileSync(modelFile(dir, 'mixed.json', { plan: [[2, 12, 'tanh'], [12, 6, 'relu'], [6, 1, 'none']] }), 'utf8')));
  eq(ml.structureFromPlan(sig.layers), { family: 'mlp', widths: [12, 6], activations: ['tanh', 'relu'] });
  assert.equal(ml.structureId(sig), mixed.structure_id);
  eq(ml.structureFromPlan([[2, 4, 'gelu'], [4, 1, 'none']]).family, 'layers', 'an activation the trainer cannot export stays an opaque plan');
  const args = trainerArgs(mixed, { root: dir, outJson: 'o.json', manifest: 'm.json' });
  eq(args.slice(args.indexOf('--widths'), args.indexOf('--widths') + 4), ['--widths', '12,6', '--activations', 'tanh,relu']);
  assert.ok(!args.includes('--hidden'));
  ml.reset();
  const tanhUniform = ml.defineModel(Object.assign({}, BASE, { structure: { family: 'mlp', width: 8, depth: 3, activation: 'tanh' } }));
  const uniformArgs = trainerArgs(tanhUniform, { root: dir, outJson: 'o.json', manifest: 'm.json' });
  eq(uniformArgs.slice(uniformArgs.indexOf('--hidden'), uniformArgs.indexOf('--hidden') + 6), ['--hidden', '8', '--depth', '3', '--activation', 'tanh']);
  assert.ok(!trainerArgs(uniform, { root: dir, outJson: 'o.json', manifest: 'm.json' }).includes('--activation'), 'SiLU commands are unchanged');
  const reject = (structure, pattern) => { ml.reset(); assert.throws(() => ml.defineModel(Object.assign({}, BASE, { structure })), pattern); };
  reject({ family: 'mlp', widths: [8], width: 8 }, /either structure.widths/);
  reject({ family: 'mlp', widths: [8, 4], activations: ['silu'] }, /one activation per hidden layer/);
  reject({ family: 'mlp', widths: [] }, /non-empty array/);
  reject({ family: 'linear', widths: [4] }, /linear structure takes only l2/);
});

test('search spaces cover activations, tapered shapes and explicit layouts', () => {
  const ml = library();
  const s = ml.defineSearch(Object.assign({}, BASE, { name: 'shapes', space: { families: ['mlp'], width: [16], depth: [1, 2],
    shapes: ['uniform', 'taper'], activations: ['silu', 'tanh'], layouts: [[24, 12, 6]] } }));
  eq(ml.candidates(s).candidates.map((c) => c.structure_label), [
    'mlp(width=16,depth=1,silu)', 'mlp(width=16,depth=1,tanh)',
    'mlp(width=16,depth=2,silu)', 'mlp(width=16,depth=2,tanh)', 'mlp(16→8,silu)', 'mlp(16→8,tanh)',
    'mlp(24→12→6,silu)', 'mlp(24→12→6,tanh)']);
  eq(ml.candidates(s).skipped.map((k) => k.reason), ['duplicate structure', 'duplicate structure'], 'a one-layer taper is the uniform net');
  const before = ml.defineSearch(Object.assign({}, BASE, { name: 'plain', space: { families: ['linear', 'mlp'], width: [8, 16], depth: [1, 2] } }));
  eq(ml.candidates(before).candidates.map((c) => c.structure_label), ['linear(l2=0.001)', 'mlp(width=8,depth=1,silu)',
    'mlp(width=16,depth=1,silu)', 'mlp(width=8,depth=2,silu)', 'mlp(width=16,depth=2,silu)'], 'the default space keeps the original grid order');
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'b', space: { shapes: ['diamond'] } })), /space.shapes\[\] must be one of/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'c', space: { families: ['linear'], layouts: [[4]] } })), /layouts needs 'mlp'/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'd', strategy: 'evolvo', space: { activations: ['tanh'] } })), /uniform SiLU/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'e', selectionRule: 'one_standard_error' })), /needs repeats >= 2/);
  assert.throws(() => ml.defineSearch(Object.assign({}, BASE, { name: 'f', repeats: 0 })), /repeats must be an integer/);
});

test('repeated-seed statistics and selection rules report selection noise honestly', () => {
  const ml = library();
  eq(ml.lossStats([0.2]), { mean: 0.2, std: null, stderr: null, n: 1 });
  const st = ml.lossStats([0.1, 0.2, 0.3]);
  assert.ok(Math.abs(st.mean - 0.2) < 1e-12 && Math.abs(st.std - 0.1) < 1e-12 && Math.abs(st.stderr - 0.1 / Math.sqrt(3)) < 1e-12);
  eq(ml.lossStats([0.1, null]).mean, null, 'a failed seed makes the candidate unrankable');
  const rows = [
    { structure_id: 'big', structure_label: 'big', loss: 0.100, loss_stderr: 0.010, parameter_count: 900 },
    { structure_id: 'mid', structure_label: 'mid', loss: 0.105, loss_stderr: 0.010, parameter_count: 300 },
    { structure_id: 'small', structure_label: 'small', loss: 0.180, loss_stderr: 0.010, parameter_count: 50 }];
  const minLoss = ml.select({ selectionRule: 'min_loss' }, rows);
  assert.equal(minLoss.winner.structure_id, 'big');
  assert.equal(minLoss.distinguishable, false, 'the runner-up is within two combined standard errors');
  eq(minLoss.tied.map((r) => r.structure_id), ['mid']);
  const parsimony = ml.select({ selectionRule: 'one_standard_error' }, rows);
  assert.equal(parsimony.winner.structure_id, 'mid', 'the one-SE rule prefers the smaller net within one standard error');
  const unmeasured = ml.select({ selectionRule: 'min_loss' }, rows.map((r) => Object.assign({}, r, { loss_stderr: null })));
  assert.equal(unmeasured.measured, false);
  assert.equal(unmeasured.distinguishable, null, 'one seed never claims a settled ordering');
});

test('orchestrated repeated-seed search, parsimony selection and validation verdicts', async () => {
  const dir = tmp();
  const defs = write(dir, 'rep.search.js', `
    TRECH_ML.defineSearch({name: "rep", inputs: ["a", "b"], outputs: ["y"],
      training: {runs: ["runs/train"], validationRuns: ["runs/valid"], testRuns: ["runs/test"], seed: 10},
      space: {families: ["mlp"], width: [8, 16], depth: [2], shapes: ["uniform", "taper"]},
      repeats: 3, selectionRule: "one_standard_error", keepCandidates: 1});`);
  const loaded = evaluate(defs);
  assert.equal(loaded.ok, true, JSON.stringify(loaded.errors));
  const store = new ModelStore(path.join(dir, 'store'), { now: clock() });
  const events = [];
  const orch = new Orchestrator(store, { root: dir, python: FAKE, emit: (e) => events.push(e) });
  process.env.FAKE_SEED_NOISE = '0.2';
  let report;
  try {
    report = await orch.search(loaded, loaded.searches[0], { validate: true });
  } finally { delete process.env.FAKE_SEED_NOISE; }
  eq(report.seeds, [10, 11, 12]);
  assert.equal(report.evaluated, 4);
  for (const r of report.results) {
    assert.equal(r.losses.length, 3);
    assert.equal(r.metrics_by_seed.length, 3);
    assert.ok(r.loss_stderr > 0, 'seed noise is measured');
  }
  assert.equal(store.read().models.rep.checkpoints.filter((c) => c.role === 'candidate').length, 1, 'extra seeds are never registered');
  assert.equal(report.selection.rule, 'one_standard_error');
  assert.equal(report.selection.noise_measured, true);
  assert.equal(typeof report.selection.distinguishable_from_runner_up, 'boolean');
  assert.equal(report.validation.status, 'pass');
  const best = store.find(store.read(), report.best.checkpoint).checkpoint;
  assert.equal(best.validation.status, 'pass');
  assert.ok(fs.existsSync(path.join(store.dir, best.validation.report)));
  assert.ok(events.some((e) => e.event === 'validated'));
  // Standalone validation of a model name resolves its newest best/final checkpoint.
  process.env.FAKE_VALIDATION = 'fail';
  try {
    const out = spawnSync(process.execPath, [CLI, 'validate', 'rep', '--store', store.dir, '--root', dir, '--python', JSON.stringify(FAKE),
      '--test-run', 'runs/test', '--json'], { encoding: 'utf8', env: process.env });
    assert.equal(out.status, 1, out.stderr);
    const result = JSON.parse(out.stdout.trim().split('\n').pop());
    assert.equal(result.status, 'fail');
    eq(result.failed, ['test_accuracy']);
  } finally { delete process.env.FAKE_VALIDATION; }
  assert.equal(store.find(store.read(), report.best.checkpoint).checkpoint.validation.status, 'fail', 'the latest verdict is recorded');
  assert.equal(fs.readdirSync(path.join(store.dir, 'staging')).length, 0, 'staging is cleaned up');
});

const SET_INPUTS = [];
for (let e = 0; e < 3; ++e) for (const f of ['x', 'y', 'm']) SET_INPUTS.push('p' + e + '_' + f);
SET_INPUTS.push('g');

test('DeepSets/MPNN structures: canonical identity, v3 plans, checkpoint round trip and trainer arguments', () => {
  const ml = library();
  ml.reset();
  const def = ml.defineModel({ name: 'pairs', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'mpnn', elements: 3, context: 1, mask: 2, phi: [8], rho: [4], relative: [1, 0], rounds: 2 },
    training: { runs: ['r/train'] } });
  eq(def.structure, { family: 'mpnn', elements: 3, context: 1, pool: 'sum', mask: 2, phi: [8], rho: [4], activation: 'silu',
    message: [], rounds: 2, relative: [0, 1], aggregate: 'mean' });
  assert.equal(def.signature.model, 'generic_surrogate_v3');
  eq(def.signature.layers.message, [[18, 8, 'silu']], 'message maps [h_i, h_j, rel] to the state width');
  eq(def.signature.layers.update, [[16, 8, 'silu']]);
  eq(def.signature.layers.rho, [[9, 4, 'silu'], [4, 1, 'none']]);
  // phi 3*8+8, message 18*8+8, update 16*8+8, rho 9*4+4 + 4*1+1
  assert.equal(def.parameter_count, 32 + 152 + 136 + 40 + 5);
  // Spelled-out defaults hash identically; a different pool is a different structure.
  ml.reset();
  const same = ml.defineModel({ name: 'pairs', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'mpnn', elements: 3, context: 1, mask: 2, phi: [8], rho: [4], relative: [0, 1], rounds: 2,
      pool: 'sum', aggregate: 'mean', activation: 'silu', message: [] }, training: { runs: ['r/train'] } });
  assert.equal(same.structure_id, def.structure_id);
  assert.equal(same.definition_hash, def.definition_hash);
  ml.reset();
  const other = ml.defineModel({ name: 'pairs', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'deepsets', elements: 3, context: 1, mask: 2, phi: [8], rho: [4], pool: 'max' }, training: { runs: ['r/train'] } });
  assert.notEqual(other.structure_id, def.structure_id);
  assert.match(other.structure_label, /^deepsets\(3 elements \+ 1 context, phi 8, max pool, rho 4, silu, mask 2\)$/);
  // Layout errors are reported, not silently reshaped.
  ml.reset();
  assert.throws(() => ml.defineModel({ name: 'bad', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'deepsets', elements: 4, phi: [8] }, training: { runs: ['r'] } }), /do not split into 4 equal element blocks/);
  assert.throws(() => ml.defineModel({ name: 'bad', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'deepsets', elements: 3, context: 1, phi: [8], rounds: 2 }, training: { runs: ['r'] } }), /unknown key 'rounds'/);
  assert.throws(() => ml.defineModel({ name: 'bad', inputs: SET_INPUTS, outputs: ['energy'],
    structure: { family: 'mpnn', elements: 3, context: 1, phi: [8], relative: [5] }, training: { runs: ['r'] } }), /relative feature indices/);
  // A trained v3 checkpoint (here the committed C++ parity fixture) round-trips to its structure.
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'tests', 'fixtures', 'ml_set_networks', 'mpnn.json'), 'utf8'));
  const sig = ml.checkpointSignature(fixture);
  assert.equal(sig.model, 'generic_surrogate_v3');
  const structure = ml.structureFromPlan(sig.layers);
  eq(structure, { family: 'mpnn', elements: 4, context: 1, pool: 'mean', mask: 2, phi: [5], rho: [4], activation: 'tanh',
    message: [4], rounds: 2, relative: [0, 1], aggregate: 'sum' });
  ml.reset();
  const refit = ml.defineModel({ name: 'fx', inputs: fixture.input_features, outputs: fixture.output_features, structure,
    training: { runs: ['r'] } });
  assert.equal(refit.structure_id, ml.structureId(sig), 'definition and checkpoint agree on the v3 structure id');
  const bad = JSON.parse(JSON.stringify(fixture));
  bad.network.update[0].weights.pop();
  assert.throws(() => ml.checkpointSignature(bad), /message\/update widths|update/);
  const args = trainerArgs(def, { root: '/repo', outJson: 'o.json', manifest: 'm.json' });
  const at = (flag) => args[args.indexOf(flag) + 1];
  assert.equal(at('--network'), 'mpnn');
  assert.equal(at('--set-elements'), '3');
  assert.equal(at('--set-context'), '1');
  assert.equal(at('--mask-feature'), '2');
  assert.equal(at('--phi-widths'), '8');
  assert.equal(at('--rho-widths'), '4');
  assert.equal(at('--message-widths'), '');
  assert.equal(at('--rounds'), '2');
  assert.equal(at('--relative-features'), '0,1');
  assert.equal(at('--aggregate'), 'mean');
  assert.ok(!args.includes('--hidden'), 'set networks never fall back to MLP flags');
});

test('set-network search spaces, run folds and calibration runs validate', () => {
  const ml = library();
  ml.reset();
  const search = ml.defineSearch({ name: 'sets', inputs: SET_INPUTS, outputs: ['energy'],
    training: { runs: ['r/a', 'r/b', 'r/c', 'r/d'], testRuns: ['r/t'], calibrationRuns: ['r/cal'] },
    space: { families: ['deepsets', 'mpnn'], width: [8], depth: [1, 2], set: { elements: 3, context: 1, mask: 2, relative: [0, 1] },
      rounds: [1, 2] }, runFolds: 2, repeats: 1, selectionRule: 'one_standard_error' });
  assert.equal(search.runFolds, 2);
  eq(search.training.calibrationRuns, ['r/cal']);
  assert.equal(search.training.intervalCoverage, 0.9);
  const plan = ml.candidates(search);
  eq(plan.candidates.map((c) => c.structure.family), ['deepsets', 'deepsets', 'mpnn', 'mpnn', 'mpnn', 'mpnn']);
  eq(plan.candidates.filter((c) => c.structure.family === 'mpnn').map((c) => c.structure.rounds), [1, 2, 1, 2]);
  assert.ok(plan.candidates.every((c) => c.signature.model === 'generic_surrogate_v3'));
  ml.reset();
  assert.throws(() => ml.defineSearch({ name: 's', inputs: SET_INPUTS, outputs: ['energy'], training: { runs: ['r/a'], validationRuns: ['r/v'] },
    space: { families: ['deepsets'] } }), /space.set/);
  assert.throws(() => ml.defineSearch({ name: 's2', inputs: ['a'], outputs: ['y'], training: { runs: ['r/a'] } }), /validationRuns .* or runFolds/);
  assert.throws(() => ml.defineModel({ name: 'c', inputs: ['a'], outputs: ['y'],
    structure: { family: 'linear' }, training: { runs: ['r/a'], calibrationRuns: ['r/a'] } }), /calibration run lists must be disjoint/);
  assert.throws(() => ml.defineSearch({ name: 's3', inputs: ['a'], outputs: ['y'], strategy: 'evolvo', runFolds: 2,
    training: { runs: ['r/a', 'r/b'], testRuns: ['r/t'] } }), /does not rotate selection runs/);
  // Folds: deterministic, disjoint, every run selects exactly once, no fold empty.
  const runs = ['r/1', 'r/2', 'r/3', 'r/4', 'r/5', 'r/6', 'r/7'];
  const folds = ml.runFolds(runs.slice().reverse(), 3, 42);
  eq(folds, JSON.parse(JSON.stringify(ml.runFolds(runs, 3, 42))), 'fold assignment ignores input order');
  eq(folds.flatMap((f) => f.selection).sort(), runs);
  for (const f of folds) {
    assert.ok(f.selection.length >= 2);
    assert.equal(f.selection.filter((r) => f.training.includes(r)).length, 0);
    assert.equal(f.selection.length + f.training.length, runs.length);
  }
  assert.notDeepEqual(JSON.parse(JSON.stringify(ml.runFolds(runs, 3, 43))), JSON.parse(JSON.stringify(folds)), 'the seed reshuffles folds');
  assert.throws(() => ml.runFolds(['a'], 2, 1), /at least 2 distinct runs/);
  // Runs replaying one configuration (same group key) are dealt as one unit and never split.
  const grouped = ml.runFolds(runs, 3, 42, { 'r/2': 'h1', 'r/5': 'h1', 'r/6': 'h1', 'r/3': 'h2', 'r/7': 'h2' });
  for (const f of grouped) {
    const has = (r) => f.selection.includes(r);
    assert.ok(['r/2', 'r/5', 'r/6'].every(has) || !['r/2', 'r/5', 'r/6'].some(has), 'group h1 stays together');
    assert.ok(['r/3', 'r/7'].every(has) || !['r/3', 'r/7'].some(has), 'group h2 stays together');
  }
  eq(grouped.flatMap((f) => f.selection).sort(), runs);
  eq(grouped[0].merged_groups.map((g) => g.join(',')).sort(), ['r/2,r/5,r/6', 'r/3,r/7']);
  eq(ml.runFolds(runs, 3, 42, {}), JSON.parse(JSON.stringify(folds)), 'no keys: same deal as ungrouped');
  assert.throws(() => ml.runFolds(['a', 'b', 'c'], 3, 1, { a: 'h', b: 'h' }), /after merging runs that replay one configuration/);
  // Fold statistics: SE across folds; seed spread reported separately.
  const st = ml.foldStats([[1.0, 1.2], [2.0, 2.2], [3.0, 3.2]]);
  assert.ok(Math.abs(st.mean - 2.1) < 1e-12);
  assert.ok(Math.abs(st.stderr - 1 / Math.sqrt(3)) < 1e-12);
  assert.ok(Math.abs(st.seed_std - Math.sqrt(0.02)) < 1e-12);
  // Paired comparison: a constant per-fold advantage is distinguishable even when the folds
  // themselves differ a lot (shared fold difficulty cancels).
  const a = { loss: 2.0, loss_stderr: 0.58, fold_means: [1.0, 2.0, 3.0], parameter_count: 10, structure_id: 'a' };
  const b = { loss: 2.1, loss_stderr: 0.58, fold_means: [1.1, 2.1, 3.1], parameter_count: 20, structure_id: 'b' };
  const chosen = ml.select({ selectionRule: 'min_loss' }, [a, b]);
  assert.equal(chosen.paired, true);
  assert.equal(chosen.distinguishable, true);
  const unpaired = ml.select({ selectionRule: 'min_loss' }, [{ loss: 2.0, loss_stderr: 0.58, parameter_count: 10, structure_id: 'a' },
    { loss: 2.1, loss_stderr: 0.58, parameter_count: 20, structure_id: 'b' }]);
  assert.equal(unpaired.distinguishable, false);
});

test('orchestrated whole-run fold search measures run noise, refits the winner and calibrates only the final model', async () => {
  const dir = tmp();
  const defs = write(dir, 'folds.search.js', `
    TRECH_ML.defineSearch({name: "folds", inputs: ["a", "b"], outputs: ["y"],
      training: {runs: ["runs/train_*"], validationRuns: ["runs/valid_1"], testRuns: ["runs/test_1"],
                 calibrationRuns: ["runs/cal_1"], seed: 5},
      space: {families: ["mlp"], width: [8, 16], depth: [2]},
      runFolds: 3, repeats: 2, keepCandidates: 1});`);
  for (const r of ['train_1', 'train_2', 'train_3', 'train_4', 'train_5', 'valid_1', 'test_1', 'cal_1']) fs.mkdirSync(path.join(dir, 'runs', r), { recursive: true });
  // train_1 and train_4 replay one configuration (same provenance config_hash): one fold unit.
  for (const r of ['train_1', 'train_4']) fs.writeFileSync(path.join(dir, 'runs', r, 'trech_provenance.jsonl'), JSON.stringify({ config_hash: 'fnv1a64:replayed' }) + '\n');
  fs.writeFileSync(path.join(dir, 'runs', 'train_2', 'trech_provenance.jsonl'), JSON.stringify({ config_json: '{"x":1}' }) + '\n');
  const loaded = evaluate(defs);
  assert.equal(loaded.ok, true, JSON.stringify(loaded.errors));
  const store = new ModelStore(path.join(dir, 'store'), { now: clock() });
  const orch = new Orchestrator(store, { root: dir, python: FAKE });
  process.env.FAKE_RUN_NOISE = '0.2';
  process.env.FAKE_SEED_NOISE = '0.02';
  let report;
  try {
    report = await orch.search(loaded, loaded.searches[0], { validate: true });
  } finally { delete process.env.FAKE_RUN_NOISE; delete process.env.FAKE_SEED_NOISE; }
  const verdict = JSON.parse(fs.readFileSync(path.join(store.dir, report.validation.report), 'utf8'));
  assert.equal(verdict.test.training_runs.length, 6, 'validation sees every run the refit was trained on');
  assert.equal(report.run_folds.length, 3);
  eq(report.run_fold_groups.merged, [['runs/train_1', 'runs/train_4']]);
  assert.equal(report.run_fold_groups.hashed_runs, 3);
  assert.match(report.run_fold_groups.note, /cannot be detected/);
  assert.ok(report.run_folds.some((f) => f.selection.includes('runs/train_1') && f.selection.includes('runs/train_4')), 'a replayed configuration selects as one unit');
  eq(report.run_folds.flatMap((f) => f.selection).sort(), ['runs/train_1', 'runs/train_2', 'runs/train_3', 'runs/train_4', 'runs/train_5', 'runs/valid_1']);
  assert.ok(report.run_folds.every((f) => !f.selection.includes('runs/test_1') && !f.training.includes('runs/cal_1')), 'test/calibration runs never enter folds');
  for (const r of report.results) {
    assert.equal(r.fold_losses.length, 3);
    assert.ok(r.fold_losses.every((f) => f.length === 2));
    assert.equal(r.metrics_by_seed.length, 6);
    assert.ok(r.loss_stderr > 0, 'between-run noise is measured');
    assert.ok(typeof r.seed_std === 'number');
  }
  assert.match(report.selection.noise_source, /whole-run folds \(3\) x seeds \(2\)/);
  assert.equal(report.selection.paired_comparison, true);
  assert.equal(report.retrain_identical, null);
  assert.equal(store.read().models.folds.checkpoints.filter((c) => c.role === 'candidate').length, 1);
  const best = store.find(store.read(), report.best.checkpoint).checkpoint;
  assert.equal(best.holdout_source, 'test_runs');
  const model = JSON.parse(fs.readFileSync(path.join(store.dir, best.files[0].path), 'utf8'));
  assert.equal(model.trained_from.runs.length, 6, 'the winner is refit on every fold run');
  assert.ok(model.prediction_interval && model.prediction_interval.runs[0].endsWith('cal_1'), 'the final model carries the calibration-run interval');
  const candidate = store.read().models.folds.checkpoints.find((c) => c.role === 'candidate');
  const candModel = JSON.parse(fs.readFileSync(path.join(store.dir, candidate.files[0].path), 'utf8'));
  assert.equal(candModel.prediction_interval, undefined, 'candidates are not calibrated');
  assert.equal(fs.readdirSync(path.join(store.dir, 'staging')).length, 0);
});

test('CLI inspects unsaved drafts from stdin and never deletes without --yes', () => {
  const dir = tmp();
  const file = write(dir, 'x.model.js', '');
  const draft = 'TRECH_ML.defineModel({name: "x", inputs: ["a"], outputs: ["y"], structure: {family: "linear"}});';
  const out = spawnSync(process.execPath, [CLI, 'inspect', file, '--stdin', '--json'], { input: draft, encoding: 'utf8' });
  assert.equal(out.status, 0, out.stderr);
  assert.equal(JSON.parse(out.stdout).definitions[0].name, 'x');
  const ml = library();
  const store = new ModelStore(path.join(dir, 'store'));
  store.register({ definition: ml.defineModel({ name: 'x', inputs: ['a', 'b'], outputs: ['y'], structure: { family: 'linear' } }),
    files: [{ format: 'generic_surrogate', source: modelFile(dir, 'a.json', { plan: [[2, 1, 'none']] }) }] });
  const dry = spawnSync(process.execPath, [CLI, 'delete', 'x@v1', '--store', store.dir, '--json'], { encoding: 'utf8' });
  assert.equal(dry.status, 2);
  assert.equal(JSON.parse(dry.stdout).dry_run, true);
  assert.equal(store.read().models.x.checkpoints.length, 1);
  const list = spawnSync(process.execPath, [CLI, 'list', '--store', store.dir, '--json'], { encoding: 'utf8' });
  assert.equal(JSON.parse(list.stdout).models[0].name, 'x');
  const yes = spawnSync(process.execPath, [CLI, 'delete', 'x@v1', '--store', store.dir, '--yes', '--json'], { encoding: 'utf8' });
  assert.equal(yes.status, 0, yes.stderr);
  eq(store.read().models, {});
});
