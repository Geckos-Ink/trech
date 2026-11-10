'use strict';
// Train definitions and run structure searches through the existing Python trainers
// (tools/torch/trech_torch/train_surrogate.py and evolve_structure.py), registering every
// produced checkpoint in the ModelStore. This module never fits a model itself.
//
// Honesty rules enforced here:
// - search candidates are scored on SELECTION runs (training.validationRuns) only;
// - when training.testRuns exist, the winner is re-trained with the test runs as its carried
//   holdout, so the deployed model reports untouched-test accuracy (and the report says whether
//   the re-trained weights are byte-identical to the selected candidate);
// - without test runs the winner's carried holdout is labelled `selection` (optimistic).
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { callBounded } = require('./load');

function repoRoot() {
  return path.resolve(__dirname, '../../..');
}

function pythonCommand(options = {}) {
  const raw = options.python || process.env.TRECH_ML_PYTHON || process.env.TRECH_PYTHON || 'python3';
  if (Array.isArray(raw)) return raw.slice();
  const text = String(raw).trim();
  if (text.startsWith('[')) return JSON.parse(text);
  return [text];
}

function expandRuns(list, root) {
  const out = [];
  for (const item of list) {
    const full = path.isAbsolute(item) ? item : path.join(root, item);
    if (/[*?[]/.test(item) && typeof fs.globSync === 'function') {
      const hits = fs.globSync(full).sort();
      if (!hits.length) throw new Error('no run directories match ' + item);
      out.push(...hits);
    } else {
      out.push(full);
    }
  }
  return out;
}

function trainerArgs(definition, { root, outJson, outPt, manifest, holdoutRuns }) {
  const t = definition.training;
  if (!t.runs.length) throw new Error('definition ' + definition.name + ' has no training.runs');
  const args = ['-m', 'trech_torch.train_surrogate', '--runs', ...expandRuns(t.runs, root)];
  if (holdoutRuns && holdoutRuns.length) args.push('--validation-runs', ...expandRuns(holdoutRuns, root));
  args.push('--source', t.source);
  if (t.tag) args.push('--tag', t.tag);
  if (t.expand) args.push('--expand', t.expand);
  args.push('--inputs', definition.inputs.join(','), '--outputs', definition.outputs.join(','));
  const logOut = definition.outputs.filter((_, i) => definition.links[i] === 'exp');
  const logitOut = definition.outputs.filter((_, i) => definition.links[i] === 'sigmoid');
  if (logOut.length) args.push('--log-outputs', logOut.join(','));
  if (logitOut.length) args.push('--logit-outputs', logitOut.join(','));
  const s = definition.structure;
  if (s.family === 'linear') args.push('--linear', '--l2', String(s.l2));
  else args.push('--hidden', String(s.width), '--depth', String(s.depth));
  args.push('--epochs', String(t.epochs), '--lr', String(t.lr), '--seed', String(t.seed), '--holdout', String(t.holdout));
  if (t.lrFinalFactor !== 1) args.push('--lr-final-factor', String(t.lrFinalFactor));
  if (t.teacher) args.push('--teacher', t.teacher);
  if (t.measured !== null) args.push('--measured', t.measured ? 'true' : 'false');
  if (t.note) args.push('--note', t.note);
  args.push('--out-json', outJson, '--manifest', manifest);
  if (outPt) args.push('--out', outPt);
  return args;
}

function evolvoArgs(search, { root, outJson }) {
  const t = search.training;
  const args = ['-m', 'trech_torch.evolve_structure', '--runs', ...expandRuns(t.runs, root),
    '--validation-runs', ...expandRuns(t.validationRuns, root), '--test-runs', ...expandRuns(t.testRuns, root),
    '--inputs', search.inputs.join(','), '--outputs', search.outputs.join(','), '--source', t.source];
  if (t.tag) args.push('--tag', t.tag);
  args.push('--epochs', String(t.epochs), '--generations', String(search.budget.generations),
    '--population', String(search.budget.population), '--max-depth', String(Math.max(...search.space.depth)),
    '--max-width', String(Math.max(...search.space.width)), '--max-parameters', String(search.budget.maxParameters),
    '--time-budget', String(search.budget.seconds), '--seed', String(search.seed), '--out-json', outJson);
  return args;
}

function runProcess(command, args, { cwd, onLine }) {
  return new Promise((resolve) => {
    const env = Object.assign({}, process.env);
    const torchPath = path.join(repoRoot(), 'tools', 'torch');
    env.PYTHONPATH = env.PYTHONPATH ? torchPath + path.delimiter + env.PYTHONPATH : torchPath;
    let child;
    try {
      child = spawn(command[0], command.slice(1).concat(args), { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (error) {
      resolve({ code: -1, tail: String(error.message) });
      return;
    }
    let tail = '';
    const relay = (stream) => {
      let buffer = '';
      stream.on('data', (chunk) => {
        buffer += chunk.toString('utf8');
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) { tail = (tail + line + '\n').slice(-4000); if (onLine && line.trim()) onLine(line); }
      });
      stream.on('end', () => { if (buffer.trim()) { tail = (tail + buffer).slice(-4000); if (onLine) onLine(buffer); } });
    };
    relay(child.stdout);
    relay(child.stderr);
    child.on('error', (error) => resolve({ code: -1, tail: tail + String(error.message) }));
    child.on('close', (code) => resolve({ code, tail }));
  });
}

class Orchestrator {
  constructor(store, options = {}) {
    this.store = store;
    this.root = path.resolve(options.root || repoRoot());
    this.python = pythonCommand(options);
    this.emit = options.emit || (() => {});
    this.now = options.now || (() => new Date());
  }

  plan(definition, holdoutRuns) {
    const staging = '<staging>';
    return this.python.concat(trainerArgs(definition, { root: this.root, outJson: path.join(staging, 'model.json'),
      outPt: definition.training.torchscript ? path.join(staging, 'model.pt') : null,
      manifest: path.join(staging, 'manifest.json'), holdoutRuns }));
  }

  // Train one definition into staging; returns {files, manifest, staging} or throws.
  async _train(definition, holdoutRuns, label) {
    const staging = this.store.stagingDir();
    const outJson = path.join(staging, 'model.json');
    const outPt = definition.training.torchscript ? path.join(staging, 'model.pt') : null;
    const manifestPath = path.join(staging, 'manifest.json');
    const args = trainerArgs(definition, { root: this.root, outJson, outPt, manifest: manifestPath, holdoutRuns });
    this.emit({ event: 'stage', stage: 'train', message: label + ': ' + definition.structure_label + ' (' + definition.structure_id + ')' });
    const result = await runProcess(this.python, args, { cwd: this.root, onLine: (line) => this.emit({ event: 'trainer', line }) });
    if (result.code !== 0 || !fs.existsSync(outJson)) {
      fs.rmSync(staging, { recursive: true, force: true });
      throw new Error('trainer failed (exit ' + result.code + ') for ' + definition.name + ' ' + definition.structure_label + ':\n' + result.tail.slice(-1500));
    }
    const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null;
    const files = [{ format: 'generic_surrogate', source: outJson }];
    if (outPt && fs.existsSync(outPt)) files.push({ format: 'torchscript', source: outPt });
    return { files, manifest, staging };
  }

  _register(definition, trained, { role, holdoutSource, search = null, sourceFile = null }) {
    try {
      return this.store.register({ definition, files: trained.files, role, manifest: trained.manifest,
        metrics: trained.manifest ? trained.manifest.metrics_holdout : null, holdoutSource,
        trainedFrom: trained.manifest ? trained.manifest.training : null, search, sourceFile, move: true });
    } finally {
      fs.rmSync(trained.staging, { recursive: true, force: true });
    }
  }

  // Plain training of a fixed structure. The carried holdout is the test runs when declared,
  // else the validation runs, else the trainer's random row split.
  async train(definition, { role = 'final', activate = false, sourceFile = null } = {}) {
    const t = definition.training;
    const holdoutRuns = t.testRuns.length ? t.testRuns : t.validationRuns;
    const holdoutSource = t.testRuns.length ? 'test_runs' : t.validationRuns.length ? 'validation_runs' : 'random_rows';
    const trained = await this._train(definition, holdoutRuns, 'train');
    const record = this._register(definition, trained, { role, holdoutSource, sourceFile });
    if (activate && !record.duplicate) this.store.activate(record.id);
    this.emit({ event: 'registered', checkpoint: record.id, structure_id: record.structure_id, duplicate: !!record.duplicate, metrics: record.metrics });
    return record;
  }

  async search(loaded, search, { sourceFile = null } = {}) {
    const started = this.now();
    const report = { schema: 'trech_ml_search_report_v1', name: search.name, strategy: search.strategy, search_hash: search.search_hash,
      objective: search.objective, complexity_penalty: search.complexityPenalty, started_at: started.toISOString(), definition_file: sourceFile,
      selection_runs: search.training.validationRuns, test_runs: search.training.testRuns, results: [], skipped: [], evaluated: 0 };
    if (search.strategy === 'evolvo') return this._evolvo(loaded, search, report, sourceFile);
    const plan = callBounded(loaded, () => loaded.ml.candidates(search));
    report.skipped = plan.skipped;
    this.emit({ event: 'stage', stage: 'search', message: search.name + ': ' + plan.candidates.length + ' candidate structures (' + plan.skipped.length + ' skipped)' });
    const deadline = search.budget.seconds > 0 ? Date.now() + search.budget.seconds * 1000 : Infinity;
    for (let i = 0; i < plan.candidates.length; ++i) {
      const candidate = plan.candidates[i];
      if (Date.now() >= deadline && report.evaluated > 0) {
        report.skipped.push(...plan.candidates.slice(i).map((c) => ({ structure: c.structure_label, reason: 'time budget' })));
        break;
      }
      const row = { structure: candidate.structure, structure_label: candidate.structure_label, structure_id: candidate.structure_id,
        parameter_count: candidate.parameter_count, loss: null, metrics: null, checkpoint: null, error: null };
      try {
        const trained = await this._train(candidate, search.training.validationRuns, 'candidate ' + (i + 1) + '/' + plan.candidates.length);
        const metrics = trained.manifest ? trained.manifest.metrics_holdout : null;
        row.metrics = metrics;
        row.loss = callBounded(loaded, () => loaded.ml.score(search, metrics, candidate));
        const record = this._register(candidate, trained, { role: 'candidate', holdoutSource: 'selection_runs',
          search: { name: search.name, search_hash: search.search_hash }, sourceFile });
        row.checkpoint = record.id;
      } catch (error) {
        row.error = String(error.message || error);
      }
      report.evaluated += 1;
      report.results.push(row);
      this.emit(Object.assign({ event: 'candidate', index: i + 1, total: plan.candidates.length }, row));
    }
    const ranked = loaded.ml.rank(report.results.filter((r) => r.loss !== null && r.checkpoint));
    report.ranking = ranked.map((r, i) => ({ rank: i + 1, structure_label: r.structure_label, structure_id: r.structure_id, loss: r.loss,
      parameter_count: r.parameter_count, checkpoint: r.checkpoint }));
    if (!ranked.length) {
      report.best = null;
      report.finished_at = this.now().toISOString();
      report.report = this.store.recordSearch(report);
      throw Object.assign(new Error('no candidate of ' + search.name + ' produced a rankable selection score'), { report });
    }
    const winner = ranked[0];
    const winnerDef = plan.candidates.find((c) => c.structure_id === winner.structure_id && c.structure_label === winner.structure_label);
    let best;
    if (search.training.testRuns.length) {
      const trained = await this._train(winnerDef, search.training.testRuns, 'winner on test runs');
      const candidateModel = this._layers(winner.checkpoint);
      const retrainedModel = JSON.parse(fs.readFileSync(trained.files[0].source, 'utf8'));
      const identical = JSON.stringify(candidateModel) === JSON.stringify(retrainedModel.network ? retrainedModel.network.layers : retrainedModel.layers);
      best = this._register(winnerDef, trained, { role: 'best', holdoutSource: 'test_runs', sourceFile,
        search: { name: search.name, search_hash: search.search_hash, selection_loss: winner.loss, selected_from: winner.checkpoint, retrain_identical: identical } });
      report.retrain_identical = identical;
    } else {
      const source = this._file(winner.checkpoint);
      best = this.store.register({ definition: winnerDef, files: [{ format: 'generic_surrogate', source }], role: 'best',
        holdoutSource: 'selection_runs', metrics: winner.metrics || null, sourceFile, note: 'no test runs declared: carried accuracy is the selection score (optimistic)',
        search: { name: search.name, search_hash: search.search_hash, selection_loss: winner.loss, selected_from: winner.checkpoint } });
    }
    report.best = { checkpoint: best.id, structure_label: best.structure_label, structure_id: best.structure_id, selection_loss: winner.loss,
      holdout_source: best.holdout_source, metrics: best.metrics };
    if (search.activate) this.store.activate(best.id);
    // Disk hygiene: keep only the best `keepCandidates` candidate checkpoints of this search.
    const keep = new Set(ranked.slice(0, search.keepCandidates).map((r) => r.checkpoint));
    report.discarded_candidates = [];
    for (const r of report.results) {
      if (r.checkpoint && !keep.has(r.checkpoint)) {
        this.store.remove(r.checkpoint, { force: true });
        report.discarded_candidates.push(r.checkpoint);
      }
    }
    report.finished_at = this.now().toISOString();
    report.report = this.store.recordSearch(report);
    this.emit({ event: 'search_done', name: search.name, message: search.name + ' best ' + (report.best ? report.best.checkpoint : 'none'), best: report.best, report: report.report });
    return report;
  }

  _file(id) {
    const index = this.store.read();
    const hit = this.store.find(index, id);
    return path.join(this.store.dir, hit.checkpoint.files.find((f) => f.format === 'generic_surrogate').path);
  }
  _layers(id) {
    const model = JSON.parse(fs.readFileSync(this._file(id), 'utf8'));
    return model.network ? model.network.layers : model.layers;
  }

  async _evolvo(loaded, search, report, sourceFile) {
    const staging = this.store.stagingDir();
    const outJson = path.join(staging, 'model.json');
    this.emit({ event: 'stage', stage: 'search', message: search.name + ': Evolvo structure search (bounded MLP width/depth)' });
    const result = await runProcess(this.python, evolvoArgs(search, { root: this.root, outJson }), { cwd: this.root,
      onLine: (line) => this.emit({ event: 'trainer', line }) });
    if (result.code !== 0 || !fs.existsSync(outJson)) {
      fs.rmSync(staging, { recursive: true, force: true });
      throw new Error('evolvo search failed (exit ' + result.code + '):\n' + result.tail.slice(-1500));
    }
    const model = JSON.parse(fs.readFileSync(outJson, 'utf8'));
    const structure = loaded.ml.structureFromPlan(loaded.ml.checkpointSignature(model).layers);
    const definition = instantiate(loaded, search, structure);
    const meta = model.trained_from && model.trained_from.structure_search || {};
    try {
      const best = this.store.register({ definition, files: [{ format: 'generic_surrogate', source: outJson }], role: 'best',
        holdoutSource: 'test_runs', metrics: model.holdout || null, sourceFile, move: true,
        search: { name: search.name, search_hash: search.search_hash, selection_loss: meta.selection_loss, backend: 'evolvo',
          evaluated_structures: meta.evaluated_structures } });
      report.evaluated = meta.evaluated_structures || 0;
      report.evolvo = meta;
      report.best = { checkpoint: best.id, structure_label: best.structure_label, structure_id: best.structure_id,
        selection_loss: meta.selection_loss, holdout_source: 'test_runs', metrics: best.metrics };
      if (search.activate) this.store.activate(best.id);
    } finally {
      fs.rmSync(staging, { recursive: true, force: true });
    }
    report.finished_at = this.now().toISOString();
    report.report = this.store.recordSearch(report);
    this.emit({ event: 'search_done', name: search.name, message: search.name + ' best ' + (report.best ? report.best.checkpoint : 'none'), best: report.best, report: report.report });
    return report;
  }
}

// A candidate definition for an arbitrary structure of a search (Evolvo's pick).
function instantiate(loaded, search, structure) {
  const custom = Object.assign({}, search, { strategy: 'custom' });
  Object.defineProperty(custom, 'generateFunction', { value: () => [structure] });
  Object.defineProperty(custom, 'objectiveFunction', { value: null });
  custom.budget = Object.assign({}, search.budget, { maxCandidates: 1, maxParameters: 1e9 });
  const plan = callBounded(loaded, () => loaded.ml.candidates(custom));
  return plan.candidates[0];
}

module.exports = { Orchestrator, trainerArgs, evolvoArgs, pythonCommand, repoRoot, expandRuns };
