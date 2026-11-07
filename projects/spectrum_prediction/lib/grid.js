// Spectral grids and the target representations learned by every architecture.
//
// Representation choices (documented in docs/spectrum_prediction.md):
// - Atoms: NIST ASD neutral-atom lines are binned on a fixed wavelength grid and weighted by
//   g_k*A_ki (transition probability times upper-level degeneracy). Lines without A_ki are
//   counted but carry no weight. Bins are log-compressed relative to the strongest bin, so the
//   target is a *line-strength shape*, not a plasma emission spectrum (no level populations,
//   temperature, density or instrument response are modelled).
// - Molecules: PubChem lists measured UV/Vis absorption maxima (lambda_max, log epsilon), not
//   band shapes. Each maximum becomes a Gaussian in wavenumber with a fixed declared width; the
//   target is log10(1 + epsilon(lambda)) / 5. The width is a representation choice, not a fit.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  const ATOMIC_GRID = Object.freeze({
    kind: 'atomic_line_strength_v1', unit: 'nm', start: 200, stop: 1000, bins: 40,
    weight: 'g_k*A_ki (s^-1)', compression: 'log10(1+999*I/Imax)/3', minWeightedLines: 5
  });
  const MOLECULAR_GRID = Object.freeze({
    kind: 'uv_absorption_envelope_v1', unit: 'nm', start: 180, stop: 500, bins: 32,
    sigma_cm1: 1500, compression: 'log10(1+epsilon)/5'
  });

  function width(grid) { return (grid.stop - grid.start) / grid.bins; }
  function centers(grid) {
    const w = width(grid);
    return Array.from({length: grid.bins}, (_, i) => grid.start + (i + 0.5) * w);
  }
  function binIndex(grid, wavelengthNm) {
    if (!(wavelengthNm >= grid.start && wavelengthNm < grid.stop)) return -1;
    return Math.min(grid.bins - 1, Math.floor((wavelengthNm - grid.start) / width(grid)));
  }
  function outputNames(prefix, grid) {
    return Array.from({length: grid.bins}, (_, i) => prefix + '_b' + String(i).padStart(2, '0'));
  }

  // lines: [{wavelength_nm, aki, gk}] -> {target, weightedLines, totalLines} or null.
  function atomicProfile(lines, grid) {
    grid = grid || ATOMIC_GRID;
    const raw = new Array(grid.bins).fill(0);
    let weighted = 0, total = 0;
    for (const line of lines) {
      const b = binIndex(grid, line.wavelength_nm);
      if (b < 0) continue;
      total++;
      if (!(line.aki > 0) || !(line.gk > 0)) continue;
      raw[b] += line.aki * line.gk;
      weighted++;
    }
    const max = Math.max.apply(null, raw);
    if (weighted < grid.minWeightedLines || !(max > 0)) return null;
    return {target: raw.map(v => Math.log10(1 + 999 * v / max) / 3), weightedLines: weighted,
      totalLines: total, maxBinWeight: max};
  }

  // bands: [{wavelength_nm, log_epsilon}] -> target vector (bands without epsilon are ignored).
  function molecularEnvelope(bands, grid) {
    grid = grid || MOLECULAR_GRID;
    const use = bands.filter(b => Number.isFinite(b.log_epsilon));
    if (!use.length) return null;
    const s2 = 2 * grid.sigma_cm1 * grid.sigma_cm1;
    return centers(grid).map(lambda => {
      const nu = 1e7 / lambda;
      let eps = 0;
      for (const band of use) {
        const d = nu - 1e7 / band.wavelength_nm;
        eps += Math.pow(10, band.log_epsilon) * Math.exp(-d * d / s2);
      }
      return Math.log10(1 + eps) / 5;
    });
  }

  // Wavelength of the strongest bin; null for an empty/flat vector.
  function peakWavelength(vector, grid) {
    let best = -1, value = -Infinity;
    for (let i = 0; i < vector.length; i++) if (vector[i] > value) { value = vector[i]; best = i; }
    if (best < 0 || !(value > 0)) return null;
    return centers(grid)[best];
  }
  // Local maxima above a fraction of the global maximum, strongest first.
  function peaks(vector, grid, fraction) {
    const c = centers(grid), max = Math.max.apply(null, vector), out = [];
    const floor = (fraction === undefined ? 0.5 : fraction) * max;
    for (let i = 0; i < vector.length; i++) {
      const left = i === 0 ? -Infinity : vector[i - 1], right = i === vector.length - 1 ? -Infinity : vector[i + 1];
      if (vector[i] >= left && vector[i] > right && vector[i] >= floor && vector[i] > 0)
        out.push({wavelength_nm: c[i], value: vector[i]});
    }
    return out.sort((a, b) => b.value - a.value);
  }
  // Inverse of the molecular compression, for reporting epsilon in physical units.
  function epsilonFromTarget(value) { return Math.pow(10, 5 * value) - 1; }

  S.grid = Object.freeze({ATOMIC_GRID, MOLECULAR_GRID, width, centers, binIndex, outputNames,
    atomicProfile, molecularEnvelope, peakWavelength, peaks, epsilonFromTarget});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.grid;
})(globalThis);
