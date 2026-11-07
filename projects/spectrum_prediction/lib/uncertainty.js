// Calibrated per-bin prediction intervals (MC-free, no extra model fits).
//
// Method: split-conformal on cross-validation residuals. Every training sample gets one
// out-of-fold prediction from the ranking k-fold CV; for each output bin the half-width is the
// finite-sample conformal quantile of |truth - prediction| over those n residuals,
// rank ceil((n + 1) * coverage). `prediction +/- half_width` then targets marginal per-bin
// coverage `coverage` for an exchangeable new sample. The out-of-fold models see (k-1)/k of the
// training split, so the widths are slightly conservative for the final refit model. They are
// graded, never assumed: coverage is measured on the untouched test split and on out-of-group
// predictions (leave-one-family/chemical-group-out), where exchangeability does not hold.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  // Conformal quantile of non-negative scores. Returns {value, capped}; `capped` means the
  // finite-sample rank exceeds n, so the largest score is used and the nominal coverage is not
  // guaranteed (too few calibration samples for the requested level).
  function conformalQuantile(scores, coverage) {
    if (!scores.length) return {value: null, capped: true};
    const sorted = scores.slice().sort((a, b) => a - b), n = sorted.length;
    const rank = Math.ceil((n + 1) * coverage);
    return rank > n ? {value: sorted[n - 1], capped: true} : {value: sorted[rank - 1], capped: false};
  }

  // truth/pred: arrays of equal-length vectors. Returns per-bin half-widths.
  function calibrate(truth, pred, coverage) {
    if (!(coverage > 0 && coverage < 1)) throw new Error('coverage must lie in (0, 1)');
    if (!truth.length || truth.length !== pred.length) throw new Error('calibration needs paired predictions');
    const m = truth[0].length, halfWidth = [];
    let capped = false;
    for (let j = 0; j < m; j++) {
      const q = conformalQuantile(truth.map((t, i) => Math.abs(t[j] - pred[i][j])), coverage);
      halfWidth.push(q.value);
      capped = capped || q.capped;
    }
    return {coverage, n: truth.length, half_width: halfWidth, capped};
  }

  // Empirical coverage of `pred +/- halfWidth`: per cell (sample, bin), per bin, and the stricter
  // fraction of samples whose every bin is covered (simultaneous; expected well below nominal).
  function coverage(truth, pred, halfWidth) {
    const n = truth.length, m = halfWidth.length, perBin = new Array(m).fill(0);
    let cells = 0, whole = 0;
    for (let i = 0; i < n; i++) {
      let all = true;
      for (let j = 0; j < m; j++) {
        const inside = Math.abs(truth[i][j] - pred[i][j]) <= halfWidth[j];
        if (inside) { cells++; perBin[j]++; } else all = false;
      }
      if (all) whole++;
    }
    const minBin = n ? Math.min.apply(null, perBin) / n : null;
    return {n, cells: n ? cells / (n * m) : null, min_bin: minBin, samples_all_bins: n ? whole / n : null};
  }

  function meanWidth(halfWidth) { return 2 * halfWidth.reduce((a, b) => a + b, 0) / halfWidth.length; }

  // Interval bounds for one prediction vector; `floor` clips the lower bound at a physical floor
  // (spectrum targets are non-negative), which never changes coverage of non-negative truth.
  function bounds(pred, halfWidth, floor) {
    const lo = pred.map((v, j) => v - halfWidth[j]), hi = pred.map((v, j) => v + halfWidth[j]);
    return {lower: floor === undefined ? lo : lo.map(v => Math.max(floor, v)), upper: hi};
  }

  S.uncertainty = Object.freeze({conformalQuantile, calibrate, coverage, meanWidth, bounds});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.uncertainty;
})(globalThis);
