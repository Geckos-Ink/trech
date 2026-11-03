// IASF finite-basis mathematical research helpers. Matrix elements must be
// supplied by a separately validated physical model in one energy convention.
// Real symmetric closed sectors only: no open-channel widths or QED matching.
(function (root) {
  "use strict";
  const MAX_DIMENSION = 32;

  function finite(x, label) {
    if (typeof x !== "number" || !Number.isFinite(x))
      throw new Error(label + " must be a finite number");
    return x;
  }
  function tolerance(value, fallback, label) {
    if (value === undefined) return fallback;
    finite(value, label);
    if (value < 1e-16 || value > 1e-4)
      throw new Error(label + " must be between 1e-16 and 1e-4");
    return value;
  }
  function rectangular(matrix, rows, cols, label) {
    if (!Array.isArray(matrix) || matrix.length !== rows)
      throw new Error(label + " has invalid row count");
    return matrix.map(function (row) {
      if (!Array.isArray(row) || row.length !== cols)
        throw new Error(label + " has invalid column count");
      return row.map(function (x) { return finite(x, label + " entry"); });
    });
  }
  function symmetric(matrix, label, allowEmpty) {
    if (!Array.isArray(matrix) || matrix.length > MAX_DIMENSION ||
        (!allowEmpty && matrix.length === 0))
      throw new Error(label + " must have dimension 1.." + MAX_DIMENSION);
    const a = rectangular(matrix, matrix.length, matrix.length, label);
    for (let i = 0; i < a.length; ++i)
      for (let j = 0; j < i; ++j)
        if (a[i][j] !== a[j][i])
          throw new Error(label + " must be exactly real symmetric");
    return a;
  }
  function zeros(n, m) { return Array.from({length: n}, () => Array(m).fill(0)); }
  function magnitude(a) {
    let result = 0;
    for (const row of a) for (const x of row) result = Math.max(result, Math.abs(x));
    return result;
  }
  function normOne(a) {
    let result = 0;
    for (let j = 0; j < a.length; ++j) {
      let sum = 0;
      for (let i = 0; i < a.length; ++i) sum += Math.abs(a[i][j]);
      result = Math.max(result, sum);
    }
    return result;
  }

  // Maximum-pivot Jacobi rotations. Input is scaled before arithmetic; the
  // caller receives sorted eigenpairs and actual equation/orthogonality errors.
  function symmetricEigen(matrix, options) {
    options = options || {};
    const original = symmetric(matrix, "matrix", false), n = original.length;
    const relativeTolerance = tolerance(options.tolerance, 1e-13, "tolerance");
    const maxRotations = options.maxRotations === undefined ? 50 * n * n : options.maxRotations;
    if (!Number.isSafeInteger(maxRotations) || maxRotations < 1 || maxRotations > 1000000)
      throw new Error("maxRotations must be an integer in 1..1000000");
    const scale = magnitude(original) || 1;
    const a = original.map(row => row.map(x => x / scale));
    const v = zeros(n, n);
    for (let i = 0; i < n; ++i) v[i][i] = 1;
    let rotations = 0, offDiagonalMax = 0;
    for (;;) {
      let p = 0, q = 0;
      offDiagonalMax = 0;
      for (let i = 0; i < n; ++i) for (let j = i + 1; j < n; ++j)
        if (Math.abs(a[i][j]) > offDiagonalMax) {
          offDiagonalMax = Math.abs(a[i][j]); p = i; q = j;
        }
      if (offDiagonalMax <= relativeTolerance || rotations >= maxRotations) break;
      const tau = (a[q][q] - a[p][p]) / (2 * a[p][q]);
      const t = (tau < 0 ? -1 : 1) / (Math.abs(tau) + Math.hypot(1, tau));
      const c = 1 / Math.sqrt(1 + t * t), s = t * c, apq = a[p][q];
      a[p][p] -= t * apq; a[q][q] += t * apq;
      a[p][q] = a[q][p] = 0;
      for (let k = 0; k < n; ++k) {
        if (k !== p && k !== q) {
          const kp = a[k][p], kq = a[k][q];
          a[k][p] = a[p][k] = c * kp - s * kq;
          a[k][q] = a[q][k] = s * kp + c * kq;
        }
        const vp = v[k][p], vq = v[k][q];
        v[k][p] = c * vp - s * vq; v[k][q] = s * vp + c * vq;
      }
      ++rotations;
    }
    const order = Array.from({length: n}, (_, i) => i).sort((i, j) => a[i][i] - a[j][j]);
    const eigenvalues = order.map(i => finite(a[i][i] * scale, "eigenvalue"));
    const eigenvectors = order.map(i => v.map(row => row[i]));
    let maxResidual = 0, maxOrthogonalityError = 0;
    for (let k = 0; k < n; ++k) {
      let residualSquared = 0;
      for (let i = 0; i < n; ++i) {
        let error = -(eigenvalues[k] / scale) * eigenvectors[k][i];
        for (let j = 0; j < n; ++j) error += (original[i][j] / scale) * eigenvectors[k][j];
        residualSquared += error * error;
      }
      maxResidual = Math.max(maxResidual, Math.sqrt(residualSquared));
      for (let j = 0; j <= k; ++j) {
        let overlap = 0;
        for (let i = 0; i < n; ++i) overlap += eigenvectors[k][i] * eigenvectors[j][i];
        maxOrthogonalityError = Math.max(maxOrthogonalityError, Math.abs(overlap - (j === k ? 1 : 0)));
      }
    }
    return {
      eigenvalues, eigenvectors, converged: offDiagonalMax <= relativeTolerance,
      rotations, maxResidual: finite(maxResidual * scale, "residual"),
      maxOrthogonalityError, offDiagonalMax: finite(offDiagonalMax * scale, "off-diagonal error")
    };
  }

  function factor(a, threshold) {
    const lu = a.map(row => row.slice()), n = a.length;
    const permutation = Array.from({length: n}, (_, i) => i);
    for (let k = 0; k < n; ++k) {
      let p = k;
      for (let i = k + 1; i < n; ++i) if (Math.abs(lu[i][k]) > Math.abs(lu[p][k])) p = i;
      if (Math.abs(lu[p][k]) <= threshold)
        throw new Error("Feshbach resolvent at or too near a pole; enlarge the retained sector");
      [lu[k], lu[p]] = [lu[p], lu[k]];
      [permutation[k], permutation[p]] = [permutation[p], permutation[k]];
      for (let i = k + 1; i < n; ++i) {
        lu[i][k] /= lu[k][k];
        for (let j = k + 1; j < n; ++j) lu[i][j] -= lu[i][k] * lu[k][j];
      }
    }
    return function (b) {
      const x = permutation.map(i => b[i]);
      for (let i = 0; i < n; ++i) for (let j = 0; j < i; ++j) x[i] -= lu[i][j] * x[j];
      for (let i = n - 1; i >= 0; --i) {
        for (let j = i + 1; j < n; ++j) x[i] -= lu[i][j] * x[j];
        x[i] = finite(x[i] / lu[i][i], "resolvent solution");
      }
      return x;
    };
  }

  // Closed-sector Feshbach identity evaluated at an explicitly supplied energy.
  // Solves linear systems with pivoting; no imaginary broadening or inverse is
  // substituted at a singularity. This does not find nonlinear eigenvalues.
  function feshbachEffective(request) {
    if (!request || typeof request !== "object") throw new Error("request is required");
    const hpp = symmetric(request.hpp, "hpp", false), p = hpp.length;
    const hqq = symmetric(request.hqq, "hqq", true), q = hqq.length;
    const hpq = rectangular(request.hpq, p, q, "hpq");
    const energy = finite(request.energyHartree, "energyHartree");
    const poleTolerance = tolerance(request.poleTolerance, 1e-12, "poleTolerance");
    const selfEnergy = zeros(p, p), matrix = hpp.map(row => row.slice());
    if (q === 0) return {matrix, selfEnergy, resolventReciprocalCondition: 1, resolventResidualMax: 0};
    const shifted = hqq.map((row, i) => row.map((x, j) =>
      finite((i === j ? energy : 0) - x, "resolvent matrix")));
    // Scale against the input energies as well as E-Hqq, so even a scalar
    // resolvent close to its pole is rejected rather than reporting condition=1.
    const scale = Math.max(Math.abs(energy), magnitude(hqq), magnitude(shifted));
    if (scale === 0) throw new Error("Feshbach resolvent at a pole");
    const a = shifted.map(row => row.map(x => x / scale));
    const solve = factor(a, poleTolerance), aNorm = normOne(a);
    let inverseNorm = 0;
    // Estimate ||A^-1||_1 by separate solves, discarding each unit-column.
    for (let j = 0; j < q; ++j) {
      const unit = Array(q).fill(0); unit[j] = 1;
      inverseNorm = Math.max(inverseNorm, solve(unit).reduce((sum, x) => sum + Math.abs(x), 0));
    }
    const reciprocalCondition = 1 / (aNorm * inverseNorm);
    if (!Number.isFinite(reciprocalCondition) || reciprocalCondition <= poleTolerance)
      throw new Error("Feshbach resolvent is ill-conditioned; enlarge the retained sector");
    const solutions = [];
    let residualMax = 0;
    for (let j = 0; j < p; ++j) {
      const b = hpq[j].map(x => finite(x / scale, "scaled coupling")), x = solve(b);
      solutions.push(x);
      for (let i = 0; i < q; ++i) {
        let residual = -b[i];
        for (let k = 0; k < q; ++k) residual += a[i][k] * x[k];
        residualMax = Math.max(residualMax, Math.abs(residual));
      }
    }
    for (let i = 0; i < p; ++i) for (let j = i; j < p; ++j) {
      let ij = 0, ji = 0;
      for (let k = 0; k < q; ++k) {
        ij += hpq[i][k] * solutions[j][k]; ji += hpq[j][k] * solutions[i][k];
      }
      // Average the two independently evaluated contractions to retain exact
      // symmetry after floating-point solves; solve residuals remain visible.
      const value = finite(0.5 * ij + 0.5 * ji, "self-energy");
      selfEnergy[i][j] = selfEnergy[j][i] = value;
      matrix[i][j] = matrix[j][i] = finite(hpp[i][j] + value, "effective Hamiltonian");
    }
    return {matrix, selfEnergy, resolventReciprocalCondition: reciprocalCondition,
      resolventResidualMax: finite(residualMax * scale, "resolvent residual")};
  }

  // Auditable finite-basis entry point. A supplied Hamiltonian is an external
  // mathematical input, not a computed atom, nuclear response, or lifetime.
  function analyze(request) {
    if (!request || typeof request !== "object" || Array.isArray(request))
      throw new Error("composition request must be an object");
    const allowed = ["hamiltonianHartree", "retainedDimension", "projectionEnergyHartree"];
    for (const key of Object.keys(request))
      if (allowed.indexOf(key) < 0) throw new Error("unknown composition request field: " + key);
    const matrix = symmetric(request.hamiltonianHartree, "hamiltonianHartree", false);
    const hasRetained = Object.prototype.hasOwnProperty.call(request, "retainedDimension");
    const hasEnergy = Object.prototype.hasOwnProperty.call(request, "projectionEnergyHartree");
    if (hasRetained !== hasEnergy)
      throw new Error("retainedDimension and projectionEnergyHartree must be supplied together");
    const normalized = {hamiltonianHartree: matrix.map(row => row.slice())};
    let projection;
    if (hasRetained) {
      const p = request.retainedDimension;
      if (!Number.isSafeInteger(p) || p < 1 || p > matrix.length)
        throw new Error("retainedDimension must be an integer in 1..matrix dimension");
      const energy = finite(request.projectionEnergyHartree, "projectionEnergyHartree");
      normalized.retainedDimension = p;
      normalized.projectionEnergyHartree = energy;
      projection = feshbachEffective({hpp: matrix.slice(0, p).map(row => row.slice(0, p)),
        hpq: matrix.slice(0, p).map(row => row.slice(p)),
        hqq: matrix.slice(p).map(row => row.slice(p)), energyHartree: energy});
    }
    const spectrum = symmetricEigen(matrix);
    if (!spectrum.converged) throw new Error("finite-basis eigensolver did not converge");
    const result = {request: normalized, origin: "supplied_matrix_reference",
      model: "real_symmetric_closed_finite_basis", units: {energy: "Hartree"}, spectrum,
      physicalMatrixElements: "external_inputs_not_computed", totalTheoryHartree: null,
      decayWidthsHartree: null};
    if (projection !== undefined) result.projection = projection;
    return result;
  }

  const api = Object.freeze({symmetricEigen, feshbachEffective, analyze, maxDimension: MAX_DIMENSION});
  root.TRECH_ATOMIC_COMPOSITION = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(globalThis);
