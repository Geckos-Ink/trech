'use strict';
// Evaluate model-definition / structure-search files in an isolated VM context.
//
// Definition files are host-neutral JavaScript (the same source can be TRECH_INCLUDE'd by a
// scenario), so they get only what QuickJS scenarios get from this library: TRECH_ML,
// TRECH_INCLUDE and TRECH_READ_JSON relative to the including file. No require/process/fs.
// Every evaluation and every call back into authored functions runs under a time limit, so a
// half-typed loop in Studio's live editor cannot hang the inspector.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const LIB = path.resolve(__dirname, '../../../js/trech_ml.js');
const DEFAULT_TIMEOUT_MS = 2000;

function locate(error, filename) {
  const stack = String(error && error.stack || '');
  const escaped = filename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = stack.match(new RegExp(escaped + ':(\\d+)(?::(\\d+))?'));
  return match ? { line: Number(match[1]), column: match[2] ? Number(match[2]) : null } : { line: null, column: null };
}

function evaluate(file, options = {}) {
  const timeout = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  const filename = path.resolve(file);
  const source = options.source !== undefined ? options.source : fs.readFileSync(filename, 'utf8');
  const logs = [];
  const stack = [filename];
  const context = vm.createContext({
    console: { log: (...a) => logs.push(a.map(String).join(' ')), warn: (...a) => logs.push(a.map(String).join(' ')),
      error: (...a) => logs.push(a.map(String).join(' ')) }
  });
  const run = (code, name) => vm.runInContext(code, context, { filename: name, timeout });
  context.TRECH_INCLUDE = (relative) => {
    const target = path.resolve(path.dirname(stack[stack.length - 1]), String(relative));
    if (target === LIB) return undefined; // already installed
    if (stack.includes(target)) throw new Error('TRECH_INCLUDE cycle: ' + target);
    stack.push(target);
    try { return run(fs.readFileSync(target, 'utf8'), target); } finally { stack.pop(); }
  };
  context.TRECH_READ_JSON = (relative) => {
    const target = path.resolve(path.dirname(stack[stack.length - 1]), String(relative));
    return JSON.parse(fs.readFileSync(target, 'utf8'));
  };
  run(fs.readFileSync(LIB, 'utf8'), LIB);
  const ml = context.TRECH_ML;
  const result = { file: filename, ok: true, definitions: [], searches: [], errors: [], logs, ml, context, timeout };
  try {
    run(source, filename);
  } catch (error) {
    result.ok = false;
    result.errors.push(Object.assign({ message: String(error && error.message || error) }, locate(error, filename)));
  }
  const declared = ml.declarations();
  result.definitions = declared.definitions;
  result.searches = declared.searches;
  if (result.ok && !result.definitions.length && !result.searches.length) {
    result.errors.push({ message: 'file declares no TRECH_ML.defineModel(...) or TRECH_ML.defineSearch(...)', line: null, column: null, warning: true });
  }
  return result;
}

// Call TRECH_ML helpers that may execute authored functions (custom objective / generator)
// inside the file's VM context, under the same time limit.
function callBounded(loaded, fn) {
  loaded.context.__trech_bounded = fn;
  try {
    return vm.runInContext('__trech_bounded()', loaded.context, { timeout: loaded.timeout });
  } finally {
    delete loaded.context.__trech_bounded;
  }
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

// The JSON summary Studio and `trech-ml inspect --json` show.
function summarize(loaded) {
  const searches = loaded.searches.map((search) => {
    let plan = null, error = null;
    try { plan = callBounded(loaded, () => loaded.ml.candidates(search)); } catch (e) { error = String(e.message || e); }
    return Object.assign(plain(search), {
      candidates: plan ? plan.candidates.map((c) => ({ structure: c.structure, structure_label: c.structure_label,
        structure_id: c.structure_id, parameter_count: c.parameter_count })) : [],
      skipped: plan ? plan.skipped : [],
      candidate_note: plan && plan.note || null,
      candidate_error: error
    });
  });
  return { schema: 'trech_ml_inspection_v1', file: loaded.file, ok: loaded.ok && searches.every((s) => !s.candidate_error),
    definitions: plain(loaded.definitions), searches, errors: loaded.errors.concat(searches.filter((s) => s.candidate_error)
      .map((s) => ({ message: s.candidate_error, line: null, column: null }))), logs: loaded.logs };
}

// A sandbox with just TRECH_ML, for operations that need the library but no definition file.
function library() {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(LIB, 'utf8'), context, { filename: LIB });
  return context.TRECH_ML;
}

module.exports = { evaluate, callBounded, summarize, library, LIB };
