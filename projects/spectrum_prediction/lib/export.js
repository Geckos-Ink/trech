// Export a dense JS-trained model as TRECH `generic_surrogate_v1` JSON.
//
// The layout matches src/ml/GenericSurrogate.cpp: inputs are standardized with
// input_mean/input_std, layers carry weights[out][in] + bias + activation, outputs are
// destandardized with output_mean/output_std. The training hull, per-feature occupancy and a
// joint covering set follow tools/torch/trech_torch/train_surrogate.py so the engine's trust
// profile (extrapolation / starved / jointly starved) works on these models exactly as on
// Torch-trained ones. Held-out metrics are the untouched test split's, never training error.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  function jointReference(z, centers, quantile) {
    if (z.length < 2 || !z[0].length) return null;
    const k = Math.min(centers, z.length), d2 = (a, b) => a.reduce((s, v, i) => s + (v - b[i]) * (v - b[i]), 0);
    const mean = z[0].map((_, j) => z.reduce((s, r) => s + r[j], 0) / z.length);
    let first = 0;
    z.forEach((r, i) => { if (d2(r, mean) < d2(z[first], mean)) first = i; });
    const chosen = [first];
    let nearest = z.map(r => d2(r, z[first]));
    while (chosen.length < k) {
      let pick = 0;
      nearest.forEach((v, i) => { if (v > nearest[pick]) pick = i; });
      if (!(nearest[pick] > 0)) break;
      chosen.push(pick);
      nearest = nearest.map((v, i) => Math.min(v, d2(z[i], z[pick])));
    }
    const sorted = nearest.slice().sort((a, b) => a - b);
    // numpy.quantile default (linear interpolation).
    const pos = (sorted.length - 1) * Math.min(Math.max(quantile, 0), 1), lo = Math.floor(pos), hi = Math.ceil(pos);
    const q = sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
    return {metric: 'euclidean_standardized', centers: chosen.map(i => z[i].slice()), radius: Math.sqrt(q),
      quantile, max_train_distance: Math.sqrt(sorted[sorted.length - 1])};
  }

  function inputDomain(rows, inputStats, bins) {
    bins = bins || 8;
    const d = rows[0].length;
    const z = rows.map(r => r.map((v, j) => (v - inputStats.mean[j]) / inputStats.std[j]));
    const radius = [], min = [], max = [], counts = [];
    for (let j = 0; j < d; j++) {
      const col = rows.map(r => r[j]), lo = Math.min.apply(null, col), hi = Math.max.apply(null, col);
      radius.push(Math.max.apply(null, z.map(r => Math.abs(r[j]))));
      min.push(lo); max.push(hi);
      const c = new Array(bins).fill(0);
      if (hi > lo) for (const v of col) c[Math.min(bins - 1, Math.floor((v - lo) / (hi - lo) * bins))]++;
      else c[0] = col.length;
      counts.push(c);
    }
    const domain = {standardized_radius: radius, input_min: min, input_max: max, n_train_rows: rows.length,
      occupancy: {bins, counts}};
    const joint = jointReference(z, 24, 0.99);
    if (joint) domain.joint = joint;
    return domain;
  }

  function holdoutBlock(outputNames, perBin, n) {
    const rmse = {}, r2 = {};
    outputNames.forEach((name, j) => {
      rmse[name] = perBin.rmse[j];
      if (perBin.r2[j] !== null) r2[name] = perBin.r2[j];
    });
    const values = Object.keys(r2).map(k => r2[k]);
    const block = {rmse, r2, n};
    if (values.length) block.r2_min = Math.min.apply(null, values);
    return block;
  }

  // model: a dense model from models.fit; trainRows: raw input rows used for fitting.
  function genericSurrogate(model, options) {
    if (!model.exportable) throw new Error('model family ' + model.family + ' is not exportable to TRECH');
    const st = model.state;
    const out = {
      model: 'generic_surrogate_v1',
      input_features: st.inputs.slice(),
      output_features: options.outputNames.slice(),
      input_mean: st.inputStats.mean, input_std: st.inputStats.std,
      output_mean: st.outputStats.mean, output_std: st.outputStats.std,
      layers: st.layers.map(l => ({weights: l.weights, bias: l.bias, activation: l.activation === 'linear' ? 'none' : l.activation})),
      input_domain: inputDomain(options.trainRows, st.inputStats),
      trained_scale_bands: [options.scale],
      holdout: holdoutBlock(options.outputNames, options.testMetrics.per_bin, options.testMetrics.n),
      trained_from: options.trainedFrom,
      note: options.note
    };
    return out;
  }

  S.export = Object.freeze({genericSurrogate, inputDomain, jointReference});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.export;
})(globalThis);
