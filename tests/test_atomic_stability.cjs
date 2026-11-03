'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const atomic = require('../js/trech_atomic_stability.js');
const runner = path.resolve(__dirname, '../tools/atomic/run.cjs');
const hydrogen = atomic.solve({});
const fastGrid = {points: [511, 1023], radius: 40};

function close(actual, expected, tolerance) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} differs from ${expected} by more than ${tolerance}`);
}

test('hydrogen is a numerical bound-state solve with independent grid and box convergence', () => {
  close(hydrogen.energy.pointNucleusEv, -13.598287264283277, 0.0004);
  assert.ok(hydrogen.comparison.numericMinusAnalyticEv > 0);
  const trace = hydrogen.convergence.trace;
  const errors = trace.map(row => Math.abs(row.energyEv + 13.598287264283277));
  assert.ok(errors[0] > 3.9 * errors[1] && errors[1] > 3.9 * errors[2]);
  close(hydrogen.convergence.box.energyEv, hydrogen.energy.pointNucleusEv, 1e-8);
  close(trace.at(-1).scaledSpacing,
    hydrogen.convergence.box.scaledRadius / (hydrogen.convergence.box.points + 1), 1e-15);
  assert.equal(hydrogen.convergence.numericalChangeGoalMet, true);
  assert.equal(atomic.solve({accuracyGoalEv: 1e-8}).convergence.numericalChangeGoalMet, false);
});

test('finite size, reduced mass, and separation convention do not double count recoil', () => {
  close(hydrogen.energy.leadingFiniteSizeShiftEv, 4.5717399105e-9, 1e-19);
  assert.ok(hydrogen.energy.withLeadingFiniteSizeEv > hydrogen.energy.pointNucleusEv);
  assert.equal(hydrogen.uncertainty.finiteSizeNumericallyResolved, null);
  assert.equal(hydrogen.uncertainty.finiteSizeExceedsObservedChanges, false);
  const ion = hydrogen.stability.channels[0];
  assert.equal(ion.thresholdEv - hydrogen.energy.pointNucleusEv, ion.pointNucleusSeparationEv);
  assert.equal(hydrogen.comparison.analyticReducedMassEv - hydrogen.comparison.infiniteMassEv,
    hydrogen.comparison.analyticRecoilShiftEv);
  const deuterium = atomic.solve({neutronCount: 1, nuclearMassElectron: 3670.482967655,
    chargeRadiusFm: 2.12778, grid: fastGrid});
  close(deuterium.comparison.analyticReducedMassEv, -13.60198734708391, 1e-12);
  close(deuterium.energy.leadingFiniteSizeShiftEv, 2.9305941160e-8, 1e-18);
  const rhoRatio = deuterium.energy.reducedMassElectron / hydrogen.energy.reducedMassElectron;
  const fastHydrogen = atomic.solve({grid: fastGrid});
  close(deuterium.energy.pointNucleusEv / fastHydrogen.energy.pointNucleusEv, rhoRatio, 1e-13);
});

test('hydrogenic charge scaling and excited radial eigenvalue ranks', () => {
  const heliumIon = atomic.solve({atomicNumber: 2, neutronCount: 2, nuclearMassElectron: 7294.29954171,
    chargeRadiusFm: 1.6786, grid: fastGrid});
  close(heliumIon.comparison.analyticReducedMassEv, -54.41531251418031, 1e-11);
  const h = atomic.solve({grid: fastGrid});
  close(heliumIon.energy.pointNucleusEv / h.energy.pointNucleusEv,
    4 * heliumIon.energy.reducedMassElectron / h.energy.reducedMassElectron, 1e-12);
  for (const l of [0, 1]) {
    const excited = atomic.solve({state: {n: 2, l}});
    close(excited.energy.pointNucleusEv, -3.399571816070819, 0.0004);
    assert.equal(excited.stability.state.n, 2);
    if (l === 1) assert.equal(excited.energy.leadingFiniteSizeShiftEv, 0);
  }
});

test('box truncation is visible and electronic binding does not imply nuclear or total stability', () => {
  const smallBox = atomic.solve({grid: {points: [511, 1023], radius: 4}});
  assert.ok(smallBox.convergence.boxChangeEv > 0.01);
  assert.equal(smallBox.convergence.numericalChangeGoalMet, false);
  for (const result of [hydrogen, atomic.solve({neutronCount: 2, nuclearMassElectron: 5496.92153551,
    chargeRadiusFm: null, grid: fastGrid})]) {
    assert.equal(result.stability.electronicBinding, 'bound_in_declared_model');
    assert.equal(result.stability.overallStability, 'undetermined');
    assert.equal(result.stability.nuclearStability, 'not_computed');
    assert.equal(result.stability.weakWidthEv, null);
    assert.equal(result.stability.lifetimeSeconds, null);
    assert.equal(result.stability.survivalProbability, null);
    assert.equal(result.uncertainty.totalTheoryEv, null);
  }
  const missingRadius = atomic.solve({neutronCount: 1, nuclearMassElectron: 3670.482967655, grid: fastGrid});
  assert.equal(missingRadius.energy.leadingFiniteSizeShiftEv, null);
  assert.equal(missingRadius.energy.withLeadingFiniteSizeEv, null);
});

test('unsupported physics, typoed fields, nonfinite and unbounded workloads fail explicitly', () => {
  for (const input of [null, [], {electronCount: 2}, {atomicNumber: 11}, {state: {n: 2, l: 2}},
    {state: {n: 0}}, {state: {n: 5}}, {atomicNumber: 2}, {neutronCount: 1},
    {nuclearMassElectron: Infinity}, {nuclearMassElectron: 0}, {chargeRadiusFm: -1},
    {temperature: 300}, {environment: {}}, {nuclearMass: 1836}, {grid: {points: [127]}},
    {grid: {points: [511, 127]}}, {grid: {points: [8190, 8191]}},
    {grid: {points: [511, 16383]}}, {grid: {radius: NaN}},
    {accuracyGoalEv: 0}, {state: {spin: 0.5}}]) assert.throws(() => atomic.solve(input));
});

test('same input replays byte-identically with runtime/source/input evidence and zero inference', () => {
  const first = spawnSync(process.execPath, [runner], {encoding: 'utf8'});
  const second = spawnSync(process.execPath, [runner], {encoding: 'utf8'});
  assert.equal(first.status, 0, first.stderr);
  assert.equal(second.status, 0, second.stderr);
  assert.equal(first.stdout, second.stdout);
  const report = JSON.parse(first.stdout);
  assert.equal(report.schema, 'trech.atomic_research.v1');
  assert.equal(report.provenance.runtime.v8, process.versions.v8);
  assert.equal(report.provenance.runtime.nodeOptions, process.env.NODE_OPTIONS || '');
  assert.equal(report.provenance.geant4Derived, false);
  assert.equal(report.provenance.inferenceCount, 0);
  assert.equal(report.results[0].origin, 'independent_quantum_reference');
  assert.match(report.provenance.normalizedRequestSha256[0], /^[a-f0-9]{64}$/);
  assert.equal(report.provenance.sourceArtifacts.length, 3);
  const jitless = spawnSync(process.execPath, [runner], {
    encoding: 'utf8', env: {...process.env, NODE_OPTIONS: '--jitless'}
  });
  assert.equal(jitless.status, 0, jitless.stderr);
  assert.equal(JSON.parse(jitless.stdout).provenance.runtime.nodeOptions, '--jitless');
});

test('hydrogenic core runs without Node host APIs', () => {
  const sandbox = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../js/trech_atomic_stability.js'), 'utf8'), sandbox);
  const energy = vm.runInContext('TRECH_ATOMIC_STABILITY.solve({grid:{points:[511,1023],radius:40}}).energy.pointNucleusEv', sandbox);
  close(energy, atomic.solve({grid: fastGrid}).energy.pointNucleusEv, 1e-12);
});

test('composition CLI executes a supplied coupled problem with independent result labels', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'trech-composition-'));
  try {
    const input = path.join(temporary, 'matrix.json');
    const request = {hamiltonianHartree: [[-0.5, 0.2], [0.2, 1.5]],
      retainedDimension: 1, projectionEnergyHartree: 0.5 - Math.sqrt(1.04)};
    fs.writeFileSync(input, JSON.stringify({cases: [request]}));
    const run = spawnSync(process.execPath, [runner, '--composition', input], {encoding: 'utf8'});
    assert.equal(run.status, 0, run.stderr);
    const report = JSON.parse(run.stdout);
    assert.equal(report.provenance.mode, 'finite_basis_composition');
    const result = report.results[0];
    assert.equal(result.origin, 'supplied_matrix_reference');
    close(result.projection.matrix[0][0], result.spectrum.eigenvalues[0], 1e-12);
    assert.equal(result.totalTheoryHartree, null);
    assert.equal(result.decayWidthsHartree, null);
    const conflict = spawnSync(process.execPath, [runner, '--input', input, '--composition', input], {encoding: 'utf8'});
    assert.equal(conflict.status, 1);
    assert.match(conflict.stderr, /mutually exclusive/);
  } finally { fs.rmSync(temporary, {recursive: true, force: true}); }
});

test('batch requests, output path, and invalid input preserve concrete CLI contract', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'trech-atomic-'));
  try {
    const input = path.join(temporary, 'requests with spaces.json');
    const output = path.join(temporary, 'results.json');
    fs.writeFileSync(input, JSON.stringify({cases: [{grid: fastGrid}, {state: {n: 2, l: 1}, grid: fastGrid}]}));
    const run = spawnSync(process.execPath, [runner, '--input', input, '--output', output], {encoding: 'utf8'});
    assert.equal(run.status, 0, run.stderr);
    assert.equal(run.stdout, '');
    const report = JSON.parse(fs.readFileSync(output, 'utf8'));
    assert.equal(report.results.length, 2);
    assert.notEqual(...report.provenance.normalizedRequestSha256);
    const goodOutput = fs.readFileSync(output, 'utf8');
    for (const invalid of [{cases: []}, {cases: [{electronCount: 2}]}, {cases: [{}], typo: true}, {cases: Array(33).fill({})}]) {
      fs.writeFileSync(input, JSON.stringify(invalid));
      const rejected = spawnSync(process.execPath, [runner, '--input', input, '--output', output], {encoding: 'utf8'});
      assert.equal(rejected.status, 1);
      assert.equal(rejected.stdout, '');
      assert.equal(fs.readFileSync(output, 'utf8'), goodOutput);
    }
  } finally { fs.rmSync(temporary, {recursive: true, force: true}); }
});
