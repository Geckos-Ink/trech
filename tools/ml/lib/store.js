'use strict';
// The TRECH model checkpoint store: the only writer of `trech_model_registry_v1`.
//
// Layout (relative to the store directory):
//   index.json                                     the registry (atomic rename on every write)
//   index.lock                                     advisory writer lock (pid + time)
//   checkpoints/<name>/<structure_id>/v<NNNN>/     one directory per registered version
//       model.json  model.pt  definition.json  manifest.json
//   searches/<name>/<stamp>-<hash>.json            structure-search reports
//   staging/                                       trainer scratch, removed on success or by gc
//
// Conflict rules: a version directory is never reused or overwritten (per-model version
// counters only grow); a generic_surrogate file must carry exactly the structure its
// definition declares (read from its weights, not its name); a TorchScript file is only
// accepted as the twin of such a JSON file. Usage is recorded from run provenance by SHA-256,
// i.e. by what the engine actually loaded.
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { library } = require('./load');

const SCHEMA = 'trech_model_registry_v1';
const LOCK_STALE_MS = 120000;
const MAX_TOUCHED_RUNS = 500;

class StoreError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function sha256File(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}
function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}
function pidAlive(pid) {
  try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; }
}
function dirSize(dir) {
  let total = 0;
  if (!fs.existsSync(dir)) return 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    total += entry.isDirectory() ? dirSize(full) : fs.statSync(full).size;
  }
  return total;
}
function parseBytes(text) {
  if (text === undefined || text === null || text === '') return null;
  const match = String(text).trim().match(/^(\d+(?:\.\d+)?)\s*([kmgt]?i?b?)?$/i);
  if (!match) throw new StoreError('usage', 'cannot parse byte size ' + JSON.stringify(text) + ' (e.g. 500M, 2G)');
  const unit = (match[2] || '').toLowerCase().replace(/i?b$/, '');
  const scale = { '': 1, k: 1024, m: 1024 ** 2, g: 1024 ** 3, t: 1024 ** 4 }[unit];
  return Math.round(Number(match[1]) * scale);
}

class ModelStore {
  constructor(dir, options = {}) {
    this.dir = path.resolve(dir);
    this.indexPath = path.join(this.dir, 'index.json');
    this.lockPath = path.join(this.dir, 'index.lock');
    this.now = options.now || (() => new Date());
    this.ml = options.ml || library();
  }

  empty() {
    return { schema: SCHEMA, updated_at: null, models: {}, searches: [], touched_runs: [] };
  }

  read() {
    if (!fs.existsSync(this.indexPath)) return this.empty();
    const index = JSON.parse(fs.readFileSync(this.indexPath, 'utf8'));
    if (index.schema !== SCHEMA) throw new StoreError('schema', this.indexPath + ' is not a ' + SCHEMA + ' index');
    index.searches = index.searches || [];
    index.touched_runs = index.touched_runs || [];
    return index;
  }

  _lock() {
    fs.mkdirSync(this.dir, { recursive: true });
    const deadline = Date.now() + 15000;
    for (;;) {
      try {
        const fd = fs.openSync(this.lockPath, 'wx');
        fs.writeSync(fd, JSON.stringify({ pid: process.pid, at: Date.now() }));
        fs.closeSync(fd);
        return;
      } catch (error) {
        if (error.code !== 'EEXIST') throw error;
        let holder = null;
        try { holder = JSON.parse(fs.readFileSync(this.lockPath, 'utf8')); } catch (_) { /* half-written */ }
        const stale = holder && (Date.now() - holder.at > LOCK_STALE_MS || !pidAlive(holder.pid));
        if (stale) { try { fs.unlinkSync(this.lockPath); } catch (_) { /* raced */ } continue; }
        if (Date.now() > deadline) throw new StoreError('locked', 'model store is locked by pid ' + (holder ? holder.pid : '?') + ' (' + this.lockPath + ')');
        sleep(50);
      }
    }
  }

  // Read-modify-write under the lock; the index is replaced atomically.
  mutate(fn) {
    this._lock();
    try {
      const index = this.read();
      const result = fn(index);
      index.updated_at = this.now().toISOString();
      const tmp = this.indexPath + '.tmp-' + process.pid;
      fs.writeFileSync(tmp, JSON.stringify(index, null, 2) + '\n');
      fs.renameSync(tmp, this.indexPath);
      return result;
    } finally {
      try { fs.unlinkSync(this.lockPath); } catch (_) { /* already gone */ }
    }
  }

  stagingDir() {
    const dir = path.join(this.dir, 'staging', process.pid + '-' + crypto.randomBytes(4).toString('hex'));
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  }

  // ---- registration -------------------------------------------------------------------------

  // Inspect the files to register and decide their structure BEFORE anything is copied.
  _validateFiles(definition, files) {
    const json = files.filter((f) => f.format === 'generic_surrogate');
    if (json.length !== 1) throw new StoreError('conflict', 'a checkpoint needs exactly one generic_surrogate .json file (got ' + json.length + ')');
    for (const f of files) {
      if (!this.ml.FORMATS.includes(f.format)) throw new StoreError('conflict', 'unknown checkpoint format ' + f.format);
      if (!fs.existsSync(f.source)) throw new StoreError('missing', 'checkpoint file not found: ' + f.source);
      const ext = path.extname(f.source).toLowerCase();
      if ((f.format === 'generic_surrogate' && ext !== '.json') || (f.format === 'torchscript' && ext !== '.pt'))
        throw new StoreError('conflict', f.format + ' checkpoint must be a ' + (f.format === 'torchscript' ? '.pt' : '.json') + ' file: ' + f.source);
    }
    let model;
    try { model = JSON.parse(fs.readFileSync(json[0].source, 'utf8')); } catch (error) {
      throw new StoreError('conflict', 'cannot parse ' + json[0].source + ': ' + error.message);
    }
    let signature;
    try { signature = this.ml.checkpointSignature(model); } catch (error) { throw new StoreError('conflict', error.message); }
    const structureId = this.ml.structureId(signature);
    const structure = this.ml.structureFromPlan(signature.layers);
    if (definition) {
      if (definition.name && !/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(definition.name)) throw new StoreError('usage', 'invalid model name ' + definition.name);
      if (definition.structure_id && definition.structure_id !== structureId) {
        throw new StoreError('conflict', 'structure conflict: ' + json[0].source + ' carries ' + structureId + ' ' +
          this.ml.describeStructure(structure) + ' [' + signature.inputs.join(',') + ' → ' + signature.outputs.join(',') +
          '] but definition ' + definition.name + ' declares ' + definition.structure_id + ' ' + definition.structure_label +
          ' [' + definition.inputs.join(',') + ' → ' + definition.outputs.join(',') + ']. ' +
          'Nothing was registered (did the trainer fall back to a linear model because torch is missing?).');
      }
    }
    return { model, signature, structureId, structure };
  }

  register({ name, definition = null, files, role = 'final', metrics = null, holdoutSource = null, trainedFrom = null,
    search = null, manifest = null, sourceFile = null, note = null, move = false }) {
    if (!this.ml.ROLES.includes(role)) throw new StoreError('usage', 'role must be one of ' + this.ml.ROLES.join('/'));
    name = name || (definition && definition.name);
    if (!name || !/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(name)) throw new StoreError('usage', 'a valid model name is required');
    const checked = this._validateFiles(definition, files);
    const hashes = files.map((f) => ({ format: f.format, source: f.source, sha256: sha256File(f.source), size_bytes: fs.statSync(f.source).size }));
    const jsonHash = hashes.find((h) => h.format === 'generic_surrogate').sha256;
    return this.mutate((index) => {
      const entry = index.models[name] || (index.models[name] = { name, active: null, next_version: 1, checkpoints: [], created_at: this.now().toISOString() });
      const twin = entry.checkpoints.find((c) => c.role === role && c.files.some((f) => f.format === 'generic_surrogate' && f.sha256 === jsonHash));
      if (twin) return Object.assign({ duplicate: true }, twin);
      const version = entry.next_version++;
      const rel = path.posix.join('checkpoints', name, checked.structureId, 'v' + String(version).padStart(4, '0'));
      const target = path.join(this.dir, rel);
      if (fs.existsSync(target)) throw new StoreError('conflict', 'refusing to overwrite existing checkpoint directory ' + target);
      fs.mkdirSync(target, { recursive: true });
      const stored = hashes.map((h) => {
        const file = h.format === 'torchscript' ? 'model.pt' : 'model.json';
        const dest = path.join(target, file);
        if (move) { try { fs.renameSync(h.source, dest); } catch (_) { fs.copyFileSync(h.source, dest); } } else fs.copyFileSync(h.source, dest);
        if (sha256File(dest) !== h.sha256) throw new StoreError('io', 'copy of ' + h.source + ' does not match its hash');
        return { format: h.format, path: path.posix.join(rel, file), sha256: h.sha256, size_bytes: h.size_bytes };
      });
      const effective = definition || { name, inputs: checked.signature.inputs, outputs: checked.signature.outputs,
        links: checked.signature.links, structure: checked.structure, structure_label: this.ml.describeStructure(checked.structure),
        structure_id: checked.structureId, scale: null, imported: true };
      fs.writeFileSync(path.join(target, 'definition.json'), JSON.stringify(effective, null, 2) + '\n');
      if (manifest) fs.writeFileSync(path.join(target, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
      const record = {
        id: name + '@v' + version,
        name, version, role,
        format: 'generic_surrogate',
        structure_id: checked.structureId,
        structure: checked.structure,
        structure_label: this.ml.describeStructure(checked.structure),
        model_kind: checked.model.model,
        inputs: checked.signature.inputs,
        outputs: checked.signature.outputs,
        links: checked.signature.links,
        scale: effective.scale || null,
        parameter_count: checked.signature.layers.reduce((s, l) => s + l[0] * l[1] + l[1], 0),
        files: stored,
        size_bytes: stored.reduce((s, f) => s + f.size_bytes, 0),
        created_at: this.now().toISOString(),
        last_used_at: null,
        use_count: 0,
        pinned: false,
        definition: { file: sourceFile, hash: definition ? definition.definition_hash || null : null, imported: !definition },
        metrics: metrics || (checked.model.holdout || null),
        holdout_source: holdoutSource,
        trained_from: trainedFrom || checked.model.trained_from || null,
        search: search || null,
        note: note || null
      };
      entry.checkpoints.push(record);
      return record;
    });
  }

  // ---- queries --------------------------------------------------------------------------------

  find(index, ref) {
    for (const entry of Object.values(index.models)) {
      const hit = entry.checkpoints.find((c) => c.id === ref);
      if (hit) return { entry, checkpoint: hit };
    }
    return null;
  }

  summary(index = this.read()) {
    const models = Object.values(index.models).map((entry) => {
      const cps = entry.checkpoints;
      const last = cps.map((c) => c.last_used_at).filter(Boolean).sort().pop() || null;
      return {
        name: entry.name,
        active: entry.active,
        versions: cps.length,
        latest_version: cps.reduce((m, c) => Math.max(m, c.version), 0),
        structures: [...new Set(cps.map((c) => c.structure_id))].length,
        use_count: cps.reduce((s, c) => s + (c.use_count || 0), 0),
        last_used_at: last,
        size_bytes: cps.reduce((s, c) => s + c.size_bytes, 0),
        pinned: cps.filter((c) => c.pinned).length,
        scale: (cps.find((c) => c.scale) || {}).scale || null
      };
    });
    return { schema: 'trech_model_store_summary_v1', store: this.dir, index: this.indexPath,
      total_bytes: models.reduce((s, m) => s + m.size_bytes, 0), models, index_data: index };
  }

  // ---- usage ----------------------------------------------------------------------------------

  touch(refs, { when = null, runKey = null } = {}) {
    return this.mutate((index) => {
      if (runKey && index.touched_runs.includes(runKey)) return { touched: [], already_recorded: true };
      const at = (when || this.now()).toISOString();
      const touched = [];
      for (const entry of Object.values(index.models)) {
        for (const c of entry.checkpoints) {
          const hit = refs.ids && refs.ids.includes(c.id) ||
            refs.sha256 && c.files.some((f) => refs.sha256.includes(f.sha256));
          if (!hit) continue;
          c.use_count = (c.use_count || 0) + 1;
          if (!c.last_used_at || c.last_used_at < at) c.last_used_at = at;
          touched.push(c.id);
        }
      }
      if (runKey && touched.length) {
        index.touched_runs.push(runKey);
        if (index.touched_runs.length > MAX_TOUCHED_RUNS) index.touched_runs.splice(0, index.touched_runs.length - MAX_TOUCHED_RUNS);
      }
      return { touched, already_recorded: false };
    });
  }

  // Record usage from a run's provenance: the SHA-256 of every model the engine loaded.
  touchRun(runDir) {
    const file = path.join(runDir, 'trech_provenance.jsonl');
    if (!fs.existsSync(file)) throw new StoreError('missing', 'no trech_provenance.jsonl in ' + runDir);
    const lines = fs.readFileSync(file, 'utf8').split('\n').filter((l) => l.trim());
    let artifacts = null, runStart = null;
    for (const line of lines) {
      let record;
      try { record = JSON.parse(line); } catch (_) { continue; }
      if (record.model_artifacts) artifacts = record.model_artifacts;
      if (record.phase === 'run_start' && !runStart) runStart = record;
    }
    const sha = artifacts && Array.isArray(artifacts.models)
      ? artifacts.models.filter((m) => m.loaded && typeof m.sha256 === 'string').map((m) => m.sha256) : [];
    const stat = fs.statSync(file);
    const runKey = path.resolve(runDir) + '#' + (runStart && runStart.config_hash || '') + '#' + stat.mtimeMs;
    if (!sha.length) return { touched: [], loaded_models: 0, run: runDir };
    return Object.assign(this.touch({ sha256: sha }, { when: stat.mtime, runKey }), { loaded_models: sha.length, run: runDir });
  }

  // ---- management -----------------------------------------------------------------------------

  setPinned(id, pinned) {
    return this.mutate((index) => {
      const hit = this.find(index, id);
      if (!hit) throw new StoreError('missing', 'no checkpoint ' + id);
      hit.checkpoint.pinned = !!pinned;
      return hit.checkpoint;
    });
  }

  activate(id) {
    return this.mutate((index) => {
      const hit = this.find(index, id);
      if (!hit) throw new StoreError('missing', 'no checkpoint ' + id);
      if (hit.checkpoint.role === 'candidate' || hit.checkpoint.role === 'intermediate')
        throw new StoreError('usage', id + ' is a ' + hit.checkpoint.role + ' checkpoint; only final/best checkpoints can be active');
      hit.entry.active = id;
      return hit.checkpoint;
    });
  }

  deactivate(name) {
    return this.mutate((index) => {
      const entry = index.models[name];
      if (!entry) throw new StoreError('missing', 'no model ' + name);
      entry.active = null;
      return { name, active: null };
    });
  }

  _removeCheckpoint(index, entry, checkpoint) {
    const dir = path.join(this.dir, path.dirname(checkpoint.files[0].path));
    const freed = dirSize(dir);
    fs.rmSync(dir, { recursive: true, force: true });
    // Remove now-empty structure / model directories, never the store root.
    for (let parent = path.dirname(dir); parent.startsWith(path.join(this.dir, 'checkpoints') + path.sep); parent = path.dirname(parent)) {
      try { if (fs.readdirSync(parent).length) break; fs.rmdirSync(parent); } catch (_) { break; }
    }
    entry.checkpoints = entry.checkpoints.filter((c) => c.id !== checkpoint.id);
    if (entry.active === checkpoint.id) entry.active = null;
    if (!entry.checkpoints.length) delete index.models[entry.name];
    return { id: checkpoint.id, bytes: freed };
  }

  // Plan a deletion without touching anything; pinned/active checkpoints need force.
  deletePlan(ref, { all = false, force = false } = {}) {
    const index = this.read();
    let targets;
    if (all) {
      const entry = index.models[ref];
      if (!entry) throw new StoreError('missing', 'no model ' + ref);
      targets = entry.checkpoints;
    } else {
      const hit = this.find(index, ref);
      if (!hit) throw new StoreError('missing', 'no checkpoint ' + ref + (index.models[ref] ? ' (use --all to delete every version of ' + ref + ')' : ''));
      targets = [hit.checkpoint];
    }
    const blocked = targets.filter((c) => !force && (c.pinned || index.models[c.name].active === c.id))
      .map((c) => ({ id: c.id, reason: c.pinned ? 'pinned' : 'active' }));
    return { delete: targets.filter((c) => !blocked.some((b) => b.id === c.id)).map((c) => ({ id: c.id, size_bytes: c.size_bytes,
      role: c.role, last_used_at: c.last_used_at, use_count: c.use_count })), blocked,
    bytes: targets.filter((c) => !blocked.some((b) => b.id === c.id)).reduce((s, c) => s + c.size_bytes, 0) };
  }

  remove(ref, options = {}) {
    const plan = this.deletePlan(ref, options);
    return this.mutate((index) => {
      const removed = [];
      for (const item of plan.delete) {
        const hit = this.find(index, item.id);
        if (hit) removed.push(this._removeCheckpoint(index, hit.entry, hit.checkpoint));
      }
      return { removed, blocked: plan.blocked, bytes_freed: removed.reduce((s, r) => s + r.bytes, 0) };
    });
  }

  // Disk-space policy. Pinned and active checkpoints are always kept, as are the newest
  // `keepLast` final/best versions of each model. Of the rest, a checkpoint is deletable when
  // it matches `roles` (if given) and has not been used/created for `unusedDays` (if given).
  // With `maxBytes`, deletable checkpoints are removed least-recently-used first only until the
  // store fits; otherwise every deletable checkpoint is removed.
  prunePlan({ name = null, keepLast = 3, unusedDays = null, roles = null, maxBytes = null } = {}, index = this.read()) {
    const now = this.now().getTime();
    const keep = [], candidates = [];
    let total = 0;
    for (const entry of Object.values(index.models)) {
      const cps = entry.checkpoints;
      total += cps.reduce((s, c) => s + c.size_bytes, 0);
      if (name && entry.name !== name) { cps.forEach((c) => keep.push({ id: c.id, reason: 'other model' })); continue; }
      const newest = cps.filter((c) => c.role === 'final' || c.role === 'best').sort((a, b) => b.version - a.version).slice(0, keepLast).map((c) => c.id);
      for (const c of cps) {
        const lastTouch = c.last_used_at || c.created_at;
        const idleDays = (now - Date.parse(lastTouch)) / 86400000;
        let reason = null;
        if (c.pinned) reason = 'pinned';
        else if (entry.active === c.id) reason = 'active';
        else if (newest.includes(c.id)) reason = 'newest ' + keepLast;
        else if (roles && !roles.includes(c.role)) reason = 'role ' + c.role + ' not selected';
        else if (unusedDays !== null && idleDays < unusedDays) reason = 'used within ' + unusedDays + ' days';
        if (reason) keep.push({ id: c.id, reason });
        else candidates.push({ id: c.id, name: entry.name, role: c.role, size_bytes: c.size_bytes, last_used_at: c.last_used_at,
          use_count: c.use_count || 0, idle_days: Math.floor(idleDays), lru: lastTouch });
      }
    }
    candidates.sort((a, b) => (a.lru < b.lru ? -1 : a.lru > b.lru ? 1 : a.id < b.id ? -1 : 1));
    let chosen = candidates;
    if (maxBytes !== null) {
      chosen = [];
      let size = total;
      for (const c of candidates) {
        if (size <= maxBytes) { keep.push({ id: c.id, reason: 'store fits ' + maxBytes + ' bytes' }); continue; }
        chosen.push(c);
        size -= c.size_bytes;
      }
    }
    const bytes = chosen.reduce((s, c) => s + c.size_bytes, 0);
    return { policy: { name, keep_last: keepLast, unused_days: unusedDays, roles, max_bytes: maxBytes },
      delete: chosen.map(({ lru, ...rest }) => rest), keep, total_bytes: total, bytes_freed: bytes, total_after: total - bytes,
      fits: maxBytes === null ? null : total - bytes <= maxBytes };
  }

  prune(policy) {
    return this.mutate((index) => {
      const plan = this.prunePlan(policy, index);
      const removed = [];
      for (const item of plan.delete) {
        const hit = this.find(index, item.id);
        if (hit) removed.push(this._removeCheckpoint(index, hit.entry, hit.checkpoint));
      }
      return Object.assign(plan, { removed });
    });
  }

  // Re-hash every registered file; report missing or modified checkpoints.
  verify() {
    const index = this.read();
    const results = [];
    for (const entry of Object.values(index.models)) for (const c of entry.checkpoints) for (const f of c.files) {
      const full = path.join(this.dir, f.path);
      const status = !fs.existsSync(full) ? 'missing' : sha256File(full) === f.sha256 ? 'ok' : 'modified';
      results.push({ id: c.id, format: f.format, path: f.path, status });
    }
    return { ok: results.every((r) => r.status === 'ok'), files: results };
  }

  // Directories under checkpoints/ that no index record owns, plus leftover staging dirs.
  gcPlan() {
    const index = this.read();
    const owned = new Set();
    for (const entry of Object.values(index.models)) for (const c of entry.checkpoints) owned.add(path.join(this.dir, path.dirname(c.files[0].path)));
    const orphans = [];
    const root = path.join(this.dir, 'checkpoints');
    const walk = (dir, depth) => {
      if (!fs.existsSync(dir)) return;
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (!e.isDirectory()) continue;
        const full = path.join(dir, e.name);
        if (depth === 2) { if (!owned.has(full)) orphans.push({ path: path.relative(this.dir, full), bytes: dirSize(full) }); } else walk(full, depth + 1);
      }
    };
    walk(root, 0);
    const staging = path.join(this.dir, 'staging');
    if (fs.existsSync(staging)) for (const e of fs.readdirSync(staging)) {
      const pid = Number(e.split('-')[0]);
      if (!pidAlive(pid)) orphans.push({ path: path.relative(this.dir, path.join(staging, e)), bytes: dirSize(path.join(staging, e)) });
    }
    return { orphans, bytes: orphans.reduce((s, o) => s + o.bytes, 0) };
  }

  gc() {
    this._lock();
    try {
      const plan = this.gcPlan();
      for (const o of plan.orphans) fs.rmSync(path.join(this.dir, o.path), { recursive: true, force: true });
      return plan;
    } finally {
      try { fs.unlinkSync(this.lockPath); } catch (_) { /* gone */ }
    }
  }

  // Keep a validator report (trech_torch.validate_model, schema trech_ml_validation_v1) and
  // attach its verdict to the checkpoint. The verdict never upgrades trust: it records which
  // gates passed, failed or only warned on the data the validator was given.
  recordValidation(id, report) {
    if (!report || report.schema !== 'trech_ml_validation_v1') throw new StoreError('usage', 'not a trech_ml_validation_v1 report');
    const hit = this.find(this.read(), id);
    if (!hit) throw new StoreError('missing', 'no checkpoint ' + id);
    const at = this.now().toISOString();
    const dir = path.join(this.dir, 'validations', hit.checkpoint.name);
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, at.replace(/[:.]/g, '-') + '-v' + String(hit.checkpoint.version).padStart(4, '0') + '.json');
    fs.writeFileSync(file, JSON.stringify(report, null, 2) + '\n');
    const gates = report.gates || [];
    const summary = {
      status: report.status,
      at,
      report: path.relative(this.dir, file).split(path.sep).join('/'),
      test_runs: (report.test && report.test.runs) || [],
      passed: gates.filter((g) => g.status === 'pass').map((g) => g.name),
      failed: gates.filter((g) => g.status === 'fail').map((g) => g.name),
      warned: gates.filter((g) => g.status === 'warn').map((g) => g.name),
      skipped: gates.filter((g) => g.status === 'skip').map((g) => g.name)
    };
    this.mutate((index) => {
      const again = this.find(index, id);
      if (again) again.checkpoint.validation = summary;
    });
    return summary;
  }

  recordSearch(report) {
    const dir = path.join(this.dir, 'searches', report.name);
    fs.mkdirSync(dir, { recursive: true });
    const stamp = report.finished_at.replace(/[:.]/g, '-');
    const file = path.join(dir, stamp + '-' + report.search_hash.slice(-8) + '.json');
    fs.writeFileSync(file, JSON.stringify(report, null, 2) + '\n');
    const rel = path.relative(this.dir, file).split(path.sep).join('/');
    this.mutate((index) => {
      index.searches.push({ name: report.name, strategy: report.strategy, finished_at: report.finished_at, report: rel,
        best: report.best ? report.best.checkpoint : null, evaluated: report.evaluated, search_hash: report.search_hash });
      if (index.searches.length > 200) index.searches.splice(0, index.searches.length - 200);
    });
    return rel;
  }
}

module.exports = { ModelStore, StoreError, parseBytes, sha256File, SCHEMA };
