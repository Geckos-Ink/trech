// Model families for spectrum prediction. Every family consumes a declarative architecture
// spec (see architectures.js) and the same sample format:
//   {id, x: {named descriptor values}, graph?: {nodes, edges, elements}, y: [target vector]}
// Inputs/outputs are standardized on the training split only. Training is deterministic for a
// given seed (mulberry32 from js/trech_random.js) and full-batch.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};
  const T = () => S.tensor;

  function rngFor(seed) { return root.TRECH_RANDOM.mulberry32(seed >>> 0); }
  function stats(rows, minStd) {
    const d = rows[0].length, n = rows.length, mean = new Array(d).fill(0), std = new Array(d).fill(0);
    for (const r of rows) for (let j = 0; j < d; j++) mean[j] += r[j] / n;
    for (const r of rows) for (let j = 0; j < d; j++) std[j] += (r[j] - mean[j]) * (r[j] - mean[j]) / n;
    for (let j = 0; j < d; j++) { std[j] = Math.sqrt(std[j]); if (!(std[j] > minStd)) std[j] = 1; }
    return {mean, std};
  }
  const standardize = (row, s) => row.map((v, j) => (v - s.mean[j]) / s.std[j]);
  const destandardize = (row, s) => row.map((v, j) => v * s.std[j] + s.mean[j]);

  function inputRows(samples, ctx) { return samples.map(s => S.features.vector(s.x, ctx.inputs)); }

  // ---- baselines ---------------------------------------------------------------------------
  function fitMean(spec, train) {
    const mean = stats(train.map(s => s.y), 0).mean;
    return {family: 'mean', predict: () => mean.slice(), state: {mean}};
  }
  function fitKnn(spec, train, ctx) {
    const rows = inputRows(train, ctx), st = stats(rows, 1e-12), z = rows.map(r => standardize(r, st));
    const k = Math.min(spec.k || 3, train.length);
    return {family: 'knn', state: {k, stats: st}, predict(sample) {
      const q = standardize(S.features.vector(sample.x, ctx.inputs), st);
      const d = z.map((r, i) => ({i, d: Math.sqrt(r.reduce((s, v, j) => s + (v - q[j]) * (v - q[j]), 0))}))
        .sort((a, b) => a.d - b.d || a.i - b.i).slice(0, k);
      const w = d.map(e => 1 / (e.d + 1e-6)), total = w.reduce((a, b) => a + b, 0);
      const out = new Array(train[0].y.length).fill(0);
      d.forEach((e, n) => train[e.i].y.forEach((v, j) => { out[j] += w[n] * v / total; }));
      return out;
    }};
  }

  // ---- ridge (closed form, exportable as one linear layer) ---------------------------------
  function cholesky(A, n) {
    const L = new Float64Array(n * n);
    for (let i = 0; i < n; i++) for (let j = 0; j <= i; j++) {
      let s = A[i * n + j];
      for (let k = 0; k < j; k++) s -= L[i * n + k] * L[j * n + k];
      if (i === j) { if (!(s > 0)) throw new Error('ridge system not positive definite'); L[i * n + i] = Math.sqrt(s); }
      else L[i * n + j] = s / L[j * n + j];
    }
    return L;
  }
  function solveCholesky(L, n, b) {
    const y = new Float64Array(n), x = new Float64Array(n);
    for (let i = 0; i < n; i++) { let s = b[i]; for (let k = 0; k < i; k++) s -= L[i * n + k] * y[k]; y[i] = s / L[i * n + i]; }
    for (let i = n - 1; i >= 0; i--) { let s = y[i]; for (let k = i + 1; k < n; k++) s -= L[k * n + i] * x[k]; x[i] = s / L[i * n + i]; }
    return x;
  }
  function fitRidge(spec, train, ctx) {
    const rows = inputRows(train, ctx), xs = stats(rows, 1e-12), ys = stats(train.map(s => s.y), 1e-6);
    const X = rows.map(r => standardize(r, xs)), Y = train.map(s => standardize(s.y, ys));
    const d = X[0].length, m = Y[0].length, lambda = spec.lambda === undefined ? 1 : spec.lambda;
    const A = new Float64Array(d * d);
    for (const r of X) for (let i = 0; i < d; i++) for (let j = 0; j < d; j++) A[i * d + j] += r[i] * r[j];
    for (let i = 0; i < d; i++) A[i * d + i] += lambda;
    const L = cholesky(A, d), W = [];
    for (let o = 0; o < m; o++) {
      const b = new Float64Array(d);
      X.forEach((r, n) => { for (let i = 0; i < d; i++) b[i] += r[i] * Y[n][o]; });
      W.push(Array.from(solveCholesky(L, d, b)));
    }
    // Standardized targets are centred, so the bias is exactly zero.
    const layers = [{weights: W, bias: new Array(m).fill(0), activation: 'none'}];
    return denseModel('ridge', layers, xs, ys, ctx);
  }

  // ---- dense networks ----------------------------------------------------------------------
  function evalDense(layers, x) {
    let h = x;
    for (const layer of layers) {
      const f = ACT_EVAL[layer.activation || 'none'];
      h = layer.weights.map((row, o) => f(row.reduce((s, w, i) => s + w * h[i], layer.bias[o])));
    }
    return h;
  }
  const ACT_EVAL = {none: x => x, linear: x => x, relu: x => (x > 0 ? x : 0), tanh: Math.tanh,
    sigmoid: x => 1 / (1 + Math.exp(-x)), silu: x => x / (1 + Math.exp(-x))};
  function denseModel(family, layers, xs, ys, ctx) {
    return {family, exportable: true, state: {layers, inputStats: xs, outputStats: ys, inputs: ctx.inputs.slice()},
      predict(sample) { return destandardize(evalDense(layers, standardize(S.features.vector(sample.x, ctx.inputs), xs)), ys); },
      // Hidden-layer activations: the learned embedding used for analysis/visualisation.
      embed(sample) {
        let h = standardize(S.features.vector(sample.x, ctx.inputs), xs);
        for (const layer of layers.slice(0, -1)) h = evalDense([layer], h);
        return h;
      }};
  }
  function denseParams(sizes, rng) {
    const out = [];
    for (let i = 0; i + 1 < sizes.length; i++) out.push(T().dense(sizes[i], sizes[i + 1], rng));
    return out;
  }
  function runDense(params, activations, X) {
    const t = T();
    let h = X;
    params.forEach((p, i) => { h = t.act(t.addBias(t.matmul(h, p.W), p.b), activations[i]); });
    return h;
  }
  function flatParams(list) { const out = []; for (const p of list) out.push(p.W, p.b); return out; }
  function train(spec, params, forward, Y) {
    const t = T(), all = flatParams(params), opt = t.adam(all, {lr: spec.lr || 3e-3});
    const epochs = spec.epochs || 800, l2 = spec.l2 === undefined ? 1e-4 : spec.l2, history = [];
    for (let e = 0; e < epochs; e++) {
      const P = forward();
      const loss = l2 > 0 ? t.sum(t.mse(P, Y), t.l2(all.filter((_, i) => i % 2 === 0), l2)) : t.mse(P, Y);
      t.backward(loss);
      opt.step();
      if (e % Math.max(1, Math.floor(epochs / 20)) === 0 || e === epochs - 1) history.push({epoch: e, loss: loss.data[0]});
    }
    return history;
  }
  function fitMlp(spec, trainSet, ctx) {
    const t = T(), rows = inputRows(trainSet, ctx), xs = stats(rows, 1e-12), ys = stats(trainSet.map(s => s.y), 1e-6);
    const X = t.fromRows(rows.map(r => standardize(r, xs))), Y = t.fromRows(trainSet.map(s => standardize(s.y, ys)));
    const hidden = spec.layers || [{units: 32, activation: 'tanh'}];
    const sizes = [rows[0].length].concat(hidden.map(l => l.units), [trainSet[0].y.length]);
    const acts = hidden.map(l => l.activation).concat(['none']);
    const params = denseParams(sizes, rngFor(ctx.seed));
    const history = train(spec, params, () => runDense(params, acts, X), Y);
    const layers = params.map((p, i) => ({
      weights: Array.from({length: p.W.cols}, (_, o) => Array.from({length: p.W.rows}, (_, k) => p.W.data[k * p.W.cols + o])),
      bias: Array.from(p.b.data), activation: acts[i]}));
    const model = denseModel('mlp', layers, xs, ys, ctx);
    model.history = history;
    return model;
  }

  // ---- set and graph networks --------------------------------------------------------------
  function nodeRow(sample, i, ctx, spec) {
    let row = sample.graph.nodes[i].slice();
    const element = sample.graph.elements[i];
    if (spec.atomicNodeFeatures) {
      const facts = ctx.elementFeatures[element];
      if (!facts) throw new Error('No atomic facts for node element ' + element);
      row = row.concat(facts);
    }
    if (spec.cascadeNodeFeatures) {
      const summary = ctx.elementSummaries[element];
      if (!summary) throw new Error('No atomic-model summary for node element ' + element);
      row = row.concat(S.features.vector(summary, S.features.ATOMIC_POOL));
    }
    return row;
  }
  function batchGraphs(samples, ctx, spec, nodeStats, globalStats) {
    const t = T(), nodes = [], graphOf = [], src = [], dst = [], meanWeight = [];
    samples.forEach((s, gi) => {
      const offset = nodes.length, n = s.graph.nodes.length;
      for (let i = 0; i < n; i++) { nodes.push(nodeRow(s, i, ctx, spec)); graphOf.push(gi); meanWeight.push(1 / n); }
      for (const [a, b] of s.graph.edges) { src.push(offset + a, offset + b); dst.push(offset + b, offset + a); }
    });
    const ns = nodeStats || stats(nodes, 1e-12);
    const out = {X: t.fromRows(nodes.map(r => standardize(r, ns))), graphOf, src, dst, meanWeight, count: samples.length, nodeStats: ns};
    if (spec.globalInputs) {
      const rows = inputRows(samples, ctx), gs = globalStats || stats(rows, 1e-12);
      out.G = t.fromRows(rows.map(r => standardize(r, gs)));
      out.globalStats = gs;
    }
    return out;
  }
  function graphForward(p, batch, spec) {
    const t = T();
    let h = t.act(t.addBias(t.matmul(batch.X, p.embed.W), p.embed.b), spec.activation || 'tanh');
    if (spec.family === 'mpnn') {
      for (const step of p.steps) {
        const messages = t.scatterAdd(t.gatherRows(t.matmul(h, step.msg.W), batch.src), batch.dst, h.rows);
        h = t.act(t.addBias(t.add(t.matmul(h, step.self.W), messages), step.self.b), spec.activation || 'tanh');
      }
    } else {
      for (const layer of p.steps) h = t.act(t.addBias(t.matmul(h, layer.self.W), layer.self.b), spec.activation || 'tanh');
    }
    let pooled = spec.readout === 'mean' ? t.scatterAdd(h, batch.graphOf, batch.count, batch.meanWeight)
      : t.scatterAdd(h, batch.graphOf, batch.count);
    if (spec.readout === 'sum+mean') pooled = t.concat(pooled, t.scatterAdd(h, batch.graphOf, batch.count, batch.meanWeight));
    if (batch.G) pooled = t.concat(pooled, batch.G);
    return runDense(p.head, p.headActs, pooled);
  }
  function fitGraph(spec, trainSet, ctx) {
    const t = T(), rng = rngFor(ctx.seed), units = spec.units || 24;
    const batch = batchGraphs(trainSet, ctx, spec);
    const ys = stats(trainSet.map(s => s.y), 1e-6), Y = t.fromRows(trainSet.map(s => standardize(s.y, ys)));
    const p = {embed: t.dense(batch.X.cols, units, rng), steps: []};
    for (let i = 0; i < (spec.steps === undefined ? 2 : spec.steps); i++)
      p.steps.push(spec.family === 'mpnn' ? {msg: t.dense(units, units, rng), self: t.dense(units, units, rng)} : {self: t.dense(units, units, rng)});
    const pooledWidth = units * (spec.readout === 'sum+mean' ? 2 : 1) + (batch.G ? batch.G.cols : 0);
    const head = spec.head || [{units: 32, activation: 'tanh'}];
    p.head = denseParams([pooledWidth].concat(head.map(l => l.units), [trainSet[0].y.length]), rng);
    p.headActs = head.map(l => l.activation).concat(['none']);
    const list = [p.embed].concat(...p.steps.map(s => (s.msg ? [s.msg, s.self] : [s.self])), p.head);
    const history = train(spec, list, () => graphForward(p, batch, spec), Y);
    return {family: spec.family, exportable: false, history, state: {units},
      predict(sample) {
        const b = batchGraphs([sample], ctx, spec, batch.nodeStats, batch.globalStats);
        return destandardize(Array.from(graphForward(p, b, spec).data), ys);
      }};
  }

  const FAMILIES = {mean: fitMean, knn: fitKnn, ridge: fitRidge, mlp: fitMlp, deepsets: fitGraph, mpnn: fitGraph};
  function fit(spec, trainSet, ctx) {
    const f = FAMILIES[spec.family];
    if (!f) throw new Error('unknown model family ' + spec.family);
    if (!trainSet.length) throw new Error('empty training set for ' + spec.name);
    return f(spec, trainSet, ctx);
  }

  S.models = Object.freeze({fit, families: Object.keys(FAMILIES), evalDense, stats, standardize, destandardize});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.models;
})(globalThis);
