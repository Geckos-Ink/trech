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
  reject({ structure: { family: 'mlp', width: 8, activation: 'relu' } }, /activation must be one of silu/);
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
