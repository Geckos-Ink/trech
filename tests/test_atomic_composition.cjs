"use strict";
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const corePath = path.join(__dirname, "../js/trech_atomic_composition.js");
const {symmetricEigen, feshbachEffective, analyze} = require(corePath);
function close(a, b, tol = 1e-11) { assert.ok(Math.abs(a - b) < tol, `${a} != ${b}`); }

const coupled = [[-0.5, 0.2], [0.2, 1.5]];
const snapshot = JSON.stringify(coupled);
const pair = symmetricEigen(coupled);
assert.equal(pair.converged, true);
assert.equal(JSON.stringify(coupled), snapshot);
close(pair.eigenvalues[0], 0.5 - Math.sqrt(1.04));
close(pair.eigenvalues[1], 0.5 + Math.sqrt(1.04));
assert.ok(pair.maxResidual < 1e-12);
assert.ok(pair.maxOrthogonalityError < 1e-12);
for (const energy of pair.eigenvalues) {
  const projected = feshbachEffective({hpp: [[-0.5]], hpq: [[0.2]], hqq: [[1.5]], energyHartree: energy});
  close(projected.matrix[0][0], energy);
  close(projected.selfEnergy[0][0], 0.04 / (energy - 1.5));
  assert.ok(projected.resolventResidualMax < 1e-12);
}

// Two retained states and two eliminated states exercise pivoting, correlations,
// and the projected eigenvectors, not just the scalar resolvent formula.
const full = [[-2, 0.1, 0.2, -0.1], [0.1, -1, 0.15, 0.25],
  [0.2, 0.15, 1, 0.3], [-0.1, 0.25, 0.3, 2]];
const eig = symmetricEigen(full);
assert.equal(eig.converged, true);
assert.ok(eig.maxResidual < 1e-11);
for (let k = 0; k < 4; ++k) {
  const projected = feshbachEffective({hpp: full.slice(0, 2).map(r => r.slice(0, 2)),
    hpq: full.slice(0, 2).map(r => r.slice(2)), hqq: full.slice(2).map(r => r.slice(2)),
    energyHartree: eig.eigenvalues[k]});
  for (let i = 0; i < 2; ++i) {
    const left = projected.matrix[i].reduce((s, x, j) => s + x * eig.eigenvectors[k][j], 0);
    close(left, eig.eigenvalues[k] * eig.eigenvectors[k][i]);
  }
}
const independent = feshbachEffective({hpp: [[-1, 0.2], [0.2, 0]], hpq: [[0], [0]], hqq: [[2]], energyHartree: -1});
assert.deepEqual(independent.matrix, [[-1, 0.2], [0.2, 0]]);
assert.deepEqual(independent.selfEnergy, [[0, 0], [0, 0]]);
assert.deepEqual(feshbachEffective({hpp: [[1]], hpq: [[]], hqq: [], energyHartree: 1}).matrix, [[1]]);
// A zero leading pivot can be nonsingular: row pivoting is required here.
close(feshbachEffective({hpp: [[0]], hpq: [[1, 2]], hqq: [[1, -1], [-1, 1]], energyHartree: 1}).matrix[0][0], 4);
assert.deepEqual(symmetricEigen([[0]]).eigenvalues, [0]);
assert.deepEqual(symmetricEigen([[1, 0], [0, 1]]).eigenvalues, [1, 1]);
const stalled = symmetricEigen(full, {maxRotations: 1});
assert.equal(stalled.converged, false);
assert.ok(stalled.maxResidual > 1e-4);

for (const matrix of [[], [[NaN]], [[Infinity]], [["1"]], [[1, 2]], [[1, 2], [3, 4]],
  Array.from({length: 33}, () => Array(33).fill(0))])
  assert.throws(() => symmetricEigen(matrix));
assert.throws(() => symmetricEigen([[1]], {tolerance: 0}));
assert.throws(() => symmetricEigen([[1]], {maxRotations: 0}));
const request = {hpp: [[-0.5]], hpq: [[0.2]], hqq: [[1.5]], energyHartree: 1.5};
assert.throws(() => feshbachEffective(request), /pole/);
assert.throws(() => feshbachEffective({...request, energyHartree: 1.5 + 1e-14}), /pole/);
assert.throws(() => feshbachEffective({...request, hpq: [[0.2, 1]]}), /column/);
assert.throws(() => feshbachEffective({...request, energyHartree: Infinity}), /finite/);
assert.throws(() => feshbachEffective({...request, hqq: [[1, 1], [1, 1]], hpq: [[1, 1]], energyHartree: 0}), /pole/);

const analysisRequest = {hamiltonianHartree: coupled, retainedDimension: 1,
  projectionEnergyHartree: pair.eigenvalues[0]};
const analysis = analyze(analysisRequest);
assert.deepEqual(analysis.request, analysisRequest);
assert.notEqual(analysis.request.hamiltonianHartree, coupled);
assert.notEqual(analysis.request.hamiltonianHartree[0], coupled[0]);
assert.deepEqual(analysis.spectrum, pair);
close(analysis.projection.matrix[0][0], pair.eigenvalues[0]);
assert.equal(analysis.origin, "supplied_matrix_reference");
assert.equal(analysis.model, "real_symmetric_closed_finite_basis");
assert.equal(analysis.units.energy, "Hartree");
assert.equal(analysis.physicalMatrixElements, "external_inputs_not_computed");
assert.equal(analysis.totalTheoryHartree, null);
assert.equal(analysis.decayWidthsHartree, null);
const spectrumOnly = analyze({hamiltonianHartree: full});
assert.deepEqual(spectrumOnly.spectrum, eig);
assert.equal(Object.prototype.hasOwnProperty.call(spectrumOnly, "projection"), false);
assert.deepEqual(analyze({hamiltonianHartree: coupled, retainedDimension: 2,
  projectionEnergyHartree: 0}).projection.matrix, coupled);
for (const bad of [null, [], 1, {}, {hamiltonianHartree: [[1]], future: true},
  {hamiltonianHartree: [[1]], retainedDimension: 1},
  {hamiltonianHartree: [[1]], projectionEnergyHartree: 0},
  {hamiltonianHartree: [[1]], retainedDimension: 0, projectionEnergyHartree: 0},
  {hamiltonianHartree: [[1]], retainedDimension: 2, projectionEnergyHartree: 0},
  {hamiltonianHartree: [[1]], retainedDimension: 1.5, projectionEnergyHartree: 0},
  {hamiltonianHartree: [[1]], retainedDimension: 1, projectionEnergyHartree: NaN}])
  assert.throws(() => analyze(bad));
assert.throws(() => analyze({hamiltonianHartree: coupled, retainedDimension: 1,
  projectionEnergyHartree: 1.5}), /pole/);

// A bare JS context has no Node globals: the same mathematical core is reusable
// by an embedded V8 or QuickJS host without filesystem/process APIs.
const sandbox = vm.createContext({});
vm.runInContext(fs.readFileSync(corePath, "utf8"), sandbox);
close(vm.runInContext("TRECH_ATOMIC_COMPOSITION.symmetricEigen([[-1, 0],[0, 2]]).eigenvalues[0]", sandbox), -1);
console.log("atomic composition: finite-basis spectra, Feshbach identity, poles, and host independence passed");
