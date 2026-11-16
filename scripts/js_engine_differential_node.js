#!/usr/bin/env node
// Minimal Node/V8 host for scripts/js_engine_differential.py: evaluates a TRECH scenario's
// top-level JavaScript the way the QuickJS host does for `trech inspect`, then prints
// {engine, config} as JSON. It provides only TRECH_INCLUDE (global-scope evaluation, paths
// relative to the including file) and TRECH_READ_JSON (relative to the calling file). Native
// QuickJS host functions (TRECH_PUBCHEM, TRECH_FIELD_*, TRECH_VALUE, TRECH_INTERFACE_SEQUENCE)
// are absent, so a scenario that calls them fails here instead of being approximated.
// This is NOT an embedded-V8 TRECH host: no hooks, Geant4, models or provenance.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const scenario = process.argv[2];
if (!scenario) {
  process.stderr.write('usage: js_engine_differential_node.js <scenario.js>\n');
  process.exit(2);
}
const stack = [];
const context = vm.createContext({});
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
  engine: { name: 'v8', host: 'node', node: process.versions.node, v8: process.versions.v8 },
  config: typeof config === 'string' ? JSON.parse(config) : config,
}) + '\n');
