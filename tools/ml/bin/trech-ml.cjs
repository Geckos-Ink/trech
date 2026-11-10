#!/usr/bin/env node
'use strict';
// trech-ml — JS model definitions, structure searches and the checkpoint store.
//
//   trech-ml inspect <file.js> [--stdin]          evaluate definitions/searches (live-edit check)
//   trech-ml list [--sort uses|recent|name|size]   registered models with usage and disk size
//   trech-ml show <name|id>                        every checkpoint of a model / one checkpoint
//   trech-ml resolve <name> [--version N] [--definition file.js]
//   trech-ml train <file.js> [--model name] [--role final|intermediate] [--activate] [--dry-run]
//   trech-ml search <file.js> [--search name] [--dry-run]
//   trech-ml register <model.json> [--name n | --definition file.js --model n] [--pt model.pt] [--role r]
//   trech-ml touch --run <dir>... | touch <id>...  record usage (from run provenance SHA-256)
//   trech-ml pin|unpin|activate <id> ; deactivate <name>
//   trech-ml delete <id> | delete <name> --all [--force] [--yes]
//   trech-ml prune [--name n] [--keep-last 3] [--unused-days D] [--roles candidate,...] [--max-bytes 2G] [--yes]
//   trech-ml verify ; trech-ml gc [--yes]
//
// Global: --store DIR (default $TRECH_MODEL_STORE or <repo>/build/model_store), --root DIR,
// --python CMD|JSON-array (default $TRECH_ML_PYTHON / $TRECH_PYTHON / python3), --json.
// Deletions print their plan and change nothing unless --yes is given.
const path = require('node:path');
const { evaluate, summarize } = require('../lib/load');
const { ModelStore, StoreError, parseBytes } = require('../lib/store');
const { Orchestrator, repoRoot } = require('../lib/orchestrate');

const FLAGS_WITH_VALUES = new Set(['store', 'root', 'python', 'sort', 'version', 'definition', 'model', 'role', 'search', 'name',
  'pt', 'keep-last', 'unused-days', 'roles', 'max-bytes', 'run', 'path', 'timeout-ms']);

function parse(argv) {
  const out = { _: [], flags: {} };
  for (let i = 0; i < argv.length; ++i) {
    const arg = argv[i];
    if (!arg.startsWith('--')) { out._.push(arg); continue; }
    const [key, inline] = arg.slice(2).split(/=(.*)/s);
    if (FLAGS_WITH_VALUES.has(key)) {
      const value = inline !== undefined ? inline : argv[++i];
      if (value === undefined) throw new StoreError('usage', '--' + key + ' needs a value');
      if (key === 'run') (out.flags.run = out.flags.run || []).push(value);
      else out.flags[key] = value;
    } else {
      out.flags[key] = true;
    }
  }
  return out;
}

function storeDir(flags, root) {
  return path.resolve(flags.store || process.env.TRECH_MODEL_STORE || path.join(root, 'build', 'model_store'));
}

function human(bytes) {
  if (bytes === null || bytes === undefined) return '-';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let v = bytes, u = 0;
  while (v >= 1024 && u < units.length - 1) { v /= 1024; ++u; }
  return (u ? v.toFixed(1) : String(v)) + ' ' + units[u];
}

function readStdin() {
  return require('node:fs').readFileSync(0, 'utf8');
}

function load(file, flags) {
  if (!file) throw new StoreError('usage', 'a definition file is required');
  const loaded = evaluate(file, { source: flags.stdin ? readStdin() : undefined, timeoutMs: flags['timeout-ms'] ? Number(flags['timeout-ms']) : undefined });
  if (!loaded.ok) throw new StoreError('definition', loaded.errors.map((e) => (e.line ? file + ':' + e.line + ': ' : '') + e.message).join('\n'));
  return loaded;
}

function pick(list, name, kind, file) {
  if (name) {
    const hit = list.find((d) => d.name === name);
    if (!hit) throw new StoreError('usage', file + ' declares no ' + kind + ' named ' + name);
    return [hit];
  }
  if (!list.length) throw new StoreError('usage', file + ' declares no ' + kind);
  return list;
}

function sortModels(models, key) {
  const by = {
    uses: (a, b) => b.use_count - a.use_count || (b.last_used_at || '').localeCompare(a.last_used_at || '') || a.name.localeCompare(b.name),
    recent: (a, b) => (b.last_used_at || '').localeCompare(a.last_used_at || '') || a.name.localeCompare(b.name),
    size: (a, b) => b.size_bytes - a.size_bytes || a.name.localeCompare(b.name),
    name: (a, b) => a.name.localeCompare(b.name)
  }[key || 'uses'];
  if (!by) throw new StoreError('usage', '--sort must be uses, recent, name or size');
  return models.slice().sort(by);
}

async function main(argv) {
  const { _: args, flags } = parse(argv);
  const command = args.shift();
  const root = path.resolve(flags.root || repoRoot());
  const json = !!flags.json;
  const print = (value, text) => process.stdout.write(json ? JSON.stringify(value) + '\n' : (typeof text === 'function' ? text(value) : text || JSON.stringify(value, null, 2)) + '\n');
  if (!command || command === 'help' || flags.help) {
    process.stdout.write(require('node:fs').readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).slice(0, 22).map((l) => l.slice(3)).join('\n') + '\n');
    return 0;
  }
  if (command === 'inspect') {
    const file = args[0] || flags.path;
    if (!file) throw new StoreError('usage', 'inspect needs a file');
    const loaded = evaluate(file, { source: flags.stdin ? readStdin() : undefined, timeoutMs: flags['timeout-ms'] ? Number(flags['timeout-ms']) : undefined });
    const summary = summarize(loaded);
    print(summary, (s) => [s.file + (s.ok ? '  OK' : '  ERRORS'),
      ...s.definitions.map((d) => '  model  ' + d.name + '  ' + d.structure_label + '  ' + d.structure_id + '  params=' + d.parameter_count +
        '  [' + d.inputs.join(',') + '] → [' + d.outputs.join(',') + ']' + (d.scale ? '  @' + d.scale : '')),
      ...s.searches.map((x) => '  search ' + x.name + '  ' + x.strategy + '  candidates=' + x.candidates.length + '  objective=' + x.objective),
      ...s.errors.map((e) => '  ' + (e.warning ? 'warning' : 'error') + (e.line ? ' line ' + e.line : '') + ': ' + e.message)].join('\n'));
    return summary.ok ? 0 : 1;
  }

  const store = new ModelStore(storeDir(flags, root));
  const emit = json ? (event) => process.stdout.write(JSON.stringify(event) + '\n')
    : (event) => process.stderr.write((event.event === 'trainer' ? '    ' + event.line : event.event === 'candidate'
      ? '  [' + event.index + '/' + event.total + '] ' + event.structure_label + '  loss=' + (event.loss === null ? 'n/a' : event.loss.toPrecision(5)) + (event.error ? '  ERROR ' + event.error.split('\n')[0] : '')
      : '[' + event.event + '] ' + (event.message || event.checkpoint || '')) + '\n');
  const orchestrator = new Orchestrator(store, { root, python: flags.python, emit });

  switch (command) {
    case 'list': {
      const summary = store.summary();
      summary.models = sortModels(summary.models, flags.sort);
      if (json) { print(summary); return 0; }
      const rows = summary.models.map((m) => [m.name, String(m.versions), String(m.use_count), m.last_used_at || 'never', human(m.size_bytes),
        m.active || '-', m.pinned ? String(m.pinned) : '-']);
      const head = ['model', 'versions', 'uses', 'last used', 'size', 'active', 'pinned'];
      const widths = head.map((h, i) => Math.max(h.length, ...rows.map((r) => r[i].length)));
      const fmt = (r) => r.map((c, i) => c.padEnd(widths[i])).join('  ');
      print(null, [store.dir + '  (' + human(summary.total_bytes) + ')', fmt(head), ...rows.map(fmt)].join('\n'));
      return 0;
    }
    case 'show': {
      const index = store.read();
      const ref = args[0];
      const entry = index.models[ref];
      const hit = entry ? null : store.find(index, ref);
      if (!entry && !hit) throw new StoreError('missing', 'no model or checkpoint ' + ref);
      const value = entry || hit.checkpoint;
      print(value, (v) => v.checkpoints ? [v.name + '  active=' + (v.active || '-'), ...v.checkpoints.map((c) => '  ' + c.id.padEnd(28) + ' ' +
        c.role.padEnd(12) + c.structure_label.padEnd(30) + c.structure_id + '  uses=' + c.use_count + '  last=' + (c.last_used_at || 'never') +
        '  ' + human(c.size_bytes) + (c.pinned ? '  PINNED' : '') + (c.holdout_source ? '  holdout=' + c.holdout_source : ''))].join('\n') : JSON.stringify(v, null, 2));
      return 0;
    }
    case 'resolve': {
      let definition = null;
      if (flags.definition) definition = pick(load(flags.definition, {}).definitions, flags.model || args[0], 'model', flags.definition)[0];
      const checkpoint = store.ml.resolve(store.read(), args[0], { version: flags.version ? Number(flags.version) : undefined, definition });
      const file = checkpoint.files.find((f) => f.format === 'generic_surrogate');
      const value = Object.assign({}, checkpoint, { absolute_path: path.join(store.dir, file.path) });
      print(value, (v) => v.id + ' (' + v.resolved_by + ')  ' + v.absolute_path);
      return 0;
    }
    case 'train': {
      const file = args[0];
      const loaded = load(file, flags);
      const defs = pick(loaded.definitions, flags.model, 'model definition', file);
      if (flags['dry-run']) {
        print(defs.map((d) => ({ name: d.name, structure_id: d.structure_id, command: orchestrator.plan(d, d.training.testRuns.length ? d.training.testRuns : d.training.validationRuns) })),
          (v) => v.map((p) => p.name + ' ' + p.structure_id + '\n  ' + p.command.join(' ')).join('\n'));
        return 0;
      }
      const records = [];
      for (const d of defs) records.push(await orchestrator.train(d, { role: flags.role || 'final', activate: !!flags.activate, sourceFile: path.relative(root, path.resolve(file)) }));
      if (json) emit({ event: 'done', checkpoints: records.map((r) => r.id) });
      else print(null, records.map((r) => (r.duplicate ? 'unchanged (identical bytes) ' : 'registered ') + r.id + '  ' + r.structure_label + '  ' + r.structure_id).join('\n'));
      return 0;
    }
    case 'search': {
      const file = args[0];
      const loaded = load(file, flags);
      const searches = pick(loaded.searches, flags.search, 'structure search', file);
      if (flags['dry-run']) {
        const summary = summarize(loaded).searches.filter((s) => searches.some((x) => x.name === s.name));
        print(summary, (v) => v.map((s) => s.name + ' (' + s.strategy + ', objective ' + s.objective + ')\n' + s.candidates.map((c) =>
          '  ' + c.structure_label.padEnd(32) + c.structure_id + '  params=' + c.parameter_count).join('\n') +
          (s.skipped.length ? '\n  skipped: ' + s.skipped.map((k) => k.structure + ' (' + k.reason + ')').join(', ') : '')).join('\n'));
        return 0;
      }
      const reports = [];
      for (const s of searches) reports.push(await orchestrator.search(loaded, s, { sourceFile: path.relative(root, path.resolve(file)) }));
      if (json) emit({ event: 'done', reports: reports.map((r) => r.report), best: reports.map((r) => r.best && r.best.checkpoint) });
      else print(null, reports.map((r) => r.name + ': best ' + (r.best ? r.best.checkpoint + ' ' + r.best.structure_label + ' (selection loss ' +
        r.best.selection_loss + ', holdout ' + r.best.holdout_source + ')' : 'none') + '\n  report ' + path.join(store.dir, r.report)).join('\n'));
      return 0;
    }
    case 'register': {
      const source = args[0];
      if (!source) throw new StoreError('usage', 'register needs a model .json');
      let definition = null;
      if (flags.definition) definition = pick(load(flags.definition, {}).definitions, flags.model, 'model', flags.definition)[0];
      const files = [{ format: 'generic_surrogate', source: path.resolve(source) }];
      if (flags.pt) files.push({ format: 'torchscript', source: path.resolve(flags.pt) });
      const record = store.register({ name: flags.name || (definition && definition.name), definition, files, role: flags.role || 'final',
        holdoutSource: 'carried', sourceFile: flags.definition ? path.relative(root, path.resolve(flags.definition)) : path.relative(root, path.resolve(source)) });
      print(record, (r) => (r.duplicate ? 'unchanged (identical bytes) ' : 'registered ') + r.id + '  ' + r.structure_label + '  ' + r.structure_id);
      return 0;
    }
    case 'touch': {
      const results = [];
      for (const run of flags.run || []) results.push(store.touchRun(path.resolve(run)));
      if (args.length) results.push(store.touch({ ids: args }));
      if (!results.length) throw new StoreError('usage', 'touch needs --run <dir> or checkpoint ids');
      print(results, (v) => v.map((r) => (r.run ? r.run + ': ' : '') + (r.already_recorded ? 'already recorded' : r.touched.length ? 'used ' + r.touched.join(', ') : 'no registered checkpoint was loaded')).join('\n'));
      return 0;
    }
    case 'pin': case 'unpin': {
      const record = store.setPinned(args[0], command === 'pin');
      print(record, (r) => r.id + (r.pinned ? ' pinned' : ' unpinned'));
      return 0;
    }
    case 'activate': {
      const record = store.activate(args[0]);
      print(record, (r) => r.name + ' active = ' + r.id);
      return 0;
    }
    case 'deactivate': {
      print(store.deactivate(args[0]), (r) => r.name + ' has no active checkpoint (newest final/best resolves)');
      return 0;
    }
    case 'delete': {
      const options = { all: !!flags.all, force: !!flags.force };
      const plan = store.deletePlan(args[0], options);
      if (!flags.yes) {
        print(Object.assign({ dry_run: true }, plan), (p) => ['would delete ' + p.delete.length + ' checkpoint(s), ' + human(p.bytes) + ':',
          ...p.delete.map((d) => '  ' + d.id), ...p.blocked.map((b) => '  kept ' + b.id + ' (' + b.reason + '; --force to delete)'), 're-run with --yes to delete'].join('\n'));
        return plan.delete.length ? 2 : 0;
      }
      const result = store.remove(args[0], options);
      print(result, (r) => 'deleted ' + r.removed.map((x) => x.id).join(', ') + ' (' + human(r.bytes_freed) + ' freed)' +
        (r.blocked.length ? '; kept ' + r.blocked.map((b) => b.id + ' (' + b.reason + ')').join(', ') : ''));
      return 0;
    }
    case 'prune': {
      const policy = {
        name: flags.name || null,
        keepLast: flags['keep-last'] !== undefined ? Number(flags['keep-last']) : 3,
        unusedDays: flags['unused-days'] !== undefined ? Number(flags['unused-days']) : null,
        roles: flags.roles ? String(flags.roles).split(',').map((r) => r.trim()).filter(Boolean) : null,
        maxBytes: parseBytes(flags['max-bytes'])
      };
      if (!Number.isInteger(policy.keepLast) || policy.keepLast < 0) throw new StoreError('usage', '--keep-last must be a non-negative integer');
      if (policy.unusedDays !== null && !(policy.unusedDays >= 0)) throw new StoreError('usage', '--unused-days must be >= 0');
      const result = flags.yes ? store.prune(policy) : Object.assign({ dry_run: true }, store.prunePlan(policy));
      print(result, (r) => [(r.dry_run ? 'would delete ' : 'deleted ') + r.delete.length + ' checkpoint(s), freeing ' + human(r.bytes_freed) +
        ' of ' + human(r.total_bytes), ...r.delete.map((d) => '  ' + d.id.padEnd(28) + d.role.padEnd(12) + 'uses=' + d.use_count + '  idle ' + d.idle_days + ' d  ' + human(d.size_bytes)),
      r.dry_run ? 're-run with --yes to delete' : ''].join('\n'));
      return 0;
    }
    case 'verify': {
      const result = store.verify();
      print(result, (r) => r.files.map((f) => f.status.padEnd(9) + f.id + '  ' + f.path).join('\n') + '\n' + (r.ok ? 'all checkpoints intact' : 'PROBLEMS FOUND'));
      return result.ok ? 0 : 1;
    }
    case 'gc': {
      const result = flags.yes ? store.gc() : Object.assign({ dry_run: true }, store.gcPlan());
      print(result, (r) => (r.dry_run ? 'would remove ' : 'removed ') + r.orphans.length + ' orphan dir(s), ' + human(r.bytes) +
        r.orphans.map((o) => '\n  ' + o.path).join(''));
      return 0;
    }
    default:
      throw new StoreError('usage', 'unknown command ' + command + ' (run trech-ml help)');
  }
}

main(process.argv.slice(2)).then((code) => { process.exitCode = code; }, (error) => {
  const payload = { event: 'error', code: error.code || 'error', message: String(error.message || error) };
  if (process.argv.includes('--json')) process.stdout.write(JSON.stringify(payload) + '\n');
  process.stderr.write('trech-ml: ' + payload.message + '\n');
  process.exitCode = error.code === 'usage' ? 64 : 1;
});
