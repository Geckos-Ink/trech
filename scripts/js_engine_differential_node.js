#!/usr/bin/env node
// Minimal Node/V8 host for scripts/js_engine_differential.py: evaluates a TRECH scenario's
// top-level JavaScript the way the QuickJS host does for `trech inspect`, then prints
// {engine, config} as JSON. It provides only TRECH_INCLUDE (global-scope evaluation, paths
// relative to the including file) and TRECH_READ_JSON (relative to the calling file). Native
// QuickJS host functions (TRECH_PUBCHEM, TRECH_FIELD_*, TRECH_VALUE, TRECH_INTERFACE_SEQUENCE)
// are absent, so a scenario that calls them fails here instead of being approximated.
// This is NOT an embedded-V8 TRECH host: no hooks, Geant4, models or provenance.
// --dmath installs TRECH's deterministic host math (js/trech_dmath_v8.js, the QuickJS host's
// trech_dmath compiled to WebAssembly) as the context's Math before the scenario runs.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const args = process.argv.slice(2);
const useDmath = args.includes('--dmath');
const scenario = args.find((arg) => !arg.startsWith('--'));
if (!scenario) {
  process.stderr.write('usage: js_engine_differential_node.js [--dmath] <scenario.js>\n');
  process.exit(2);
}
const stack = [];
const context = vm.createContext({});
const math = useDmath
  ? require(path.join(__dirname, '..', 'js', 'trech_dmath_v8.js')).install(vm.runInContext('Math', context)) && 'trech_dmath (WebAssembly)'
  : 'v8 builtin';
const base = () => path.dirname(stack.length ? stack[stack.length - 1] : path.resolve(scenario));
function evaluate(file) {
  const resolved = path.resolve(file);
  stack.push(resolved);
  try {
    vm.runInContext(fs.readFileSync(resolved, 'utf8'), context, { filename: resolved });
  } finally {
    stack.pop();
  }
}
context.TRECH_INCLUDE = (relative) => evaluate(path.resolve(base(), String(relative)));
context.TRECH_READ_JSON = (relative) => JSON.parse(fs.readFileSync(path.resolve(base(), String(relative)), 'utf8'));
evaluate(scenario);
const config = vm.runInContext('globalThis.TRECH_CONFIG', context);
process.stdout.write(JSON.stringify({
  engine: { name: 'v8', host: 'node', node: process.versions.node, v8: process.versions.v8, math },
  config: typeof config === 'string' ? JSON.parse(config) : config,
}) + '\n');
