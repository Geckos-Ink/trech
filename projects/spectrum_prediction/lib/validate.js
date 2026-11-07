// Deterministic splits and spectrum metrics.
//
// Splits hash the record identifier (FNV-1a) with a salt, so the held-out test set is stable
// when new records are collected and never depends on fetch order. Cross-validation runs only
// on the training split; the held-out test set is scored once per architecture.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  function fnv1a(text) {
    let h = 0x811c9dc5;
    const s = String(text);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h >>> 0;
  }
  function holdout(samples, fraction, salt) {
    const test = [], train = [];
    for (const s of samples) ((fnv1a(salt + ':' + s.id) % 10000) < fraction * 10000 ? test : train).push(s);
    if (!test.length || !train.length) throw new Error('holdout split left an empty side; collect more records');
    return {train, test};
  }
  function folds(samples, k, salt) {
    const order = samples.slice().sort((a, b) => fnv1a(salt + ':' + a.id) - fnv1a(salt + ':' + b.id) || (a.id < b.id ? -1 : 1));
    const out = Array.from({length: k}, () => []);
    order.forEach((s, i) => out[i % k].push(s));
    return out.filter(f => f.length);
  }
  // Leave-one-group-out folds (e.g. molecular family), for out-of-family generalisation.
  function groupFolds(samples, key) {
    const groups = {};
    for (const s of samples) (groups[s[key] || 'unassigned'] = groups[s[key] || 'unassigned'] || []).push(s);
    return Object.keys(groups).sort().map(name => ({name, samples: groups[name]}));
  }

  function cosine(a, b) {
    let ab = 0, aa = 0, bb = 0;
    for (let i = 0; i < a.length; i++) { ab += a[i] * b[i]; aa += a[i] * a[i]; bb += b[i] * b[i]; }
    return aa > 0 && bb > 0 ? ab / Math.sqrt(aa * bb) : 0;
  }
  function metrics(truth, pred, grid) {
    const n = truth.length, m = truth[0].length;
    let se = 0, ae = 0, peak = 0, peakN = 0, cos = 0;
    const binMean = new Array(m).fill(0), sst = new Array(m).fill(0), sse = new Array(m).fill(0);
    truth.forEach(t => t.forEach((v, j) => { binMean[j] += v / n; }));
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < m; j++) {
        const d = pred[i][j] - truth[i][j];
        se += d * d; ae += Math.abs(d); sse[j] += d * d;
        sst[j] += (truth[i][j] - binMean[j]) * (truth[i][j] - binMean[j]);
      }
      cos += cosine(truth[i], pred[i]);
      const pt = S.grid.peakWavelength(truth[i], grid), pp = S.grid.peakWavelength(pred[i], grid);
      if (pt !== null && pp !== null) { peak += Math.abs(pt - pp); peakN++; }
    }
    const sstTotal = sst.reduce((a, b) => a + b, 0), sseTotal = sse.reduce((a, b) => a + b, 0);
    return {n, rmse: Math.sqrt(se / (n * m)), mae: ae / (n * m), r2: sstTotal > 0 ? 1 - sseTotal / sstTotal : null,
      cosine: cos / n, peak_error_nm: peakN ? peak / peakN : null,
      per_bin: {rmse: sse.map(v => Math.sqrt(v / n)), mae: null,
        r2: sst.map((v, j) => (v > 1e-12 ? 1 - sse[j] / v : null))}};
  }
  function summarize(list) {
    const keys = ['rmse', 'mae', 'r2', 'cosine', 'peak_error_nm'], out = {folds: list.length};
    for (const k of keys) {
      const v = list.map(x => x[k]).filter(Number.isFinite);
      if (!v.length) { out[k] = null; continue; }
      const mean = v.reduce((a, b) => a + b, 0) / v.length;
      out[k] = {mean, std: Math.sqrt(v.reduce((a, b) => a + (b - mean) * (b - mean), 0) / v.length)};
    }
    return out;
  }

  S.validate = Object.freeze({fnv1a, holdout, folds, groupFolds, cosine, metrics, summarize});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.validate;
})(globalThis);
