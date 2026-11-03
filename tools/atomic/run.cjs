'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const atomic = require('../../js/trech_atomic_stability.js');
const composition = require('../../js/trech_atomic_composition.js');

const usage = `Usage: trech-atomic [--input request.json | --composition matrices.json] [--output result.json]
       node tools/atomic/run.cjs [--input request.json | --composition matrices.json] [--output result.json]

Runs an independent one-electron quantum research reference on Node.js/V8.
With no input: hydrogen 1s. --composition analyzes supplied finite-basis matrices.
Input: one request or {"cases":[request,...]} (max 32).
See docs/atomic_stability.md for units, supported fields, and scientific limits.
This output is not a Geant4 result, nuclear lifetime, or theory of everything.
`;
function sha(text) { return crypto.createHash('sha256').update(text).digest('hex'); }
function main(args) {
  if (args.length === 1 && (args[0] === '--help' || args[0] === '-h')) {
    process.stdout.write(usage); return;
  }
  if (!process.versions.v8 || Number(process.versions.node.split('.')[0]) < 18)
    throw new Error('Node.js >=18 with a V8 runtime is required');
  const options = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--input', '--composition', '--output'].includes(args[i]) || !args[i + 1] || options[args[i]])
      throw new Error('Unknown, duplicate, or incomplete argument: ' + args[i]);
    options[args[i]] = args[i + 1];
  }
  if (options['--input'] && options['--composition']) throw new Error('--input and --composition are mutually exclusive');
  let source = '{}';
  const inputPath = options['--input'] || options['--composition'];
  if (inputPath) {
    if (fs.statSync(inputPath).size > 1024 * 1024) throw new Error('Input exceeds 1 MiB');
    source = fs.readFileSync(inputPath, 'utf8');
  }
  const input = JSON.parse(source);
  let cases;
  if (input && typeof input === 'object' && !Array.isArray(input) && Object.hasOwn(input, 'cases')) {
    if (Object.keys(input).length !== 1 || !Array.isArray(input.cases) || input.cases.length < 1 || input.cases.length > 32)
      throw new Error('Batch input must contain only cases, with 1 to 32 requests');
    cases = input.cases;
  } else cases = [input];
  // Compute/validate everything before opening the output path.
  const results = cases.map(value => options['--composition'] ? composition.analyze(value) : atomic.solve(value));
  const artifacts = ['js/trech_atomic_stability.js', 'js/trech_atomic_composition.js', 'tools/atomic/run.cjs'].map(name => ({
    path: name, sha256: sha(fs.readFileSync(path.resolve(__dirname, '../..', name)))
  }));
  const output = {
    schema: 'trech.atomic_research.v1',
    provenance: {maturity: 'phase_a_research_reference',
      runtime: {host: 'Node.js', node: process.versions.node, v8: process.versions.v8,
        platform: process.platform, architecture: process.arch, flags: process.execArgv,
        nodeOptions: process.env.NODE_OPTIONS || ''},
      mode: options['--composition'] ? 'finite_basis_composition' : 'hydrogenic',
      constants: atomic.constants, sourceArtifacts: artifacts, inputSha256: sha(source),
      normalizedRequestSha256: results.map(result => sha(JSON.stringify(result.request))),
      rng: 'none', seed: null, inferenceCount: 0, geant4Version: null,
      geant4Derived: false, learned: false},
    results
  };
  const encoded = JSON.stringify(output, null, 2) + '\n';
  if (options['--output']) fs.writeFileSync(options['--output'], encoded);
  else process.stdout.write(encoded);
}
try { main(process.argv.slice(2)); }
catch (error) { process.stderr.write('TRECH atomic research error: ' + error.message + '\n'); process.exitCode = 1; }
