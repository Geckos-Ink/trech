// Tiny deterministic reverse-mode autodiff over dense row-major Float64 matrices.
//
// Enough for dense, set (DeepSets) and message-passing graph networks: matmul, bias, pointwise
// activations, row gather/scatter-add, concatenation, masked MSE and L2. Pure JavaScript with no
// dependency so training is reproducible on any V8/QuickJS host given the same seed.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  function tensor(rows, cols, data, param) {
    return {rows, cols, data: data || new Float64Array(rows * cols), grad: null, parents: [], back: null, param: !!param,
      needsGrad: !!param};
  }
  function fromRows(rows) {
    const r = rows.length, c = r ? rows[0].length : 0, t = tensor(r, c);
    for (let i = 0; i < r; i++) for (let j = 0; j < c; j++) t.data[i * c + j] = rows[i][j];
    return t;
  }
  function toRows(t) {
    const out = [];
    for (let i = 0; i < t.rows; i++) out.push(Array.from(t.data.subarray(i * t.cols, (i + 1) * t.cols)));
    return out;
  }
  function node(rows, cols, parents, back) {
    const t = tensor(rows, cols);
    t.parents = parents; t.back = back;
    t.needsGrad = parents.some(p => p.needsGrad);
    return t;
  }
  function g(t) { if (!t.grad) t.grad = new Float64Array(t.data.length); return t.grad; }

  function matmul(A, B) {
    if (A.cols !== B.rows) throw new Error('matmul shape ' + A.rows + 'x' + A.cols + ' * ' + B.rows + 'x' + B.cols);
    const n = A.rows, k = A.cols, m = B.cols;
    const out = node(n, m, [A, B], () => {
      const go = out.grad, ga = A.needsGrad ? g(A) : null, gb = B.needsGrad ? g(B) : null;
      for (let i = 0; i < n; i++) for (let p = 0; p < k; p++) {
        const a = A.data[i * k + p], row = i * m, col = p * m;
        if (gb && a !== 0) for (let j = 0; j < m; j++) gb[col + j] += a * go[row + j];
        if (ga) { let s = 0; for (let j = 0; j < m; j++) s += go[row + j] * B.data[col + j]; ga[i * k + p] += s; }
      }
    });
    for (let i = 0; i < n; i++) for (let p = 0; p < k; p++) {
      const a = A.data[i * k + p];
      if (a === 0) continue;
      for (let j = 0; j < m; j++) out.data[i * m + j] += a * B.data[p * m + j];
    }
    return out;
  }
  function addBias(A, b) {
    const n = A.rows, m = A.cols;
    const out = node(n, m, [A, b], () => {
      const go = out.grad, ga = g(A), gb = g(b);
      for (let i = 0; i < n * m; i++) { ga[i] += go[i]; gb[i % m] += go[i]; }
    });
    for (let i = 0; i < n * m; i++) out.data[i] = A.data[i] + b.data[i % m];
    return out;
  }
  function add(A, B) {
    if (A.rows !== B.rows || A.cols !== B.cols) throw new Error('add shape mismatch');
    const out = node(A.rows, A.cols, [A, B], () => {
      const go = out.grad, ga = g(A), gb = g(B);
      for (let i = 0; i < go.length; i++) { ga[i] += go[i]; gb[i] += go[i]; }
    });
    for (let i = 0; i < out.data.length; i++) out.data[i] = A.data[i] + B.data[i];
    return out;
  }
  const ACT = {
    none: [x => x, () => 1],
    linear: [x => x, () => 1],
    relu: [x => (x > 0 ? x : 0), (x) => (x > 0 ? 1 : 0)],
    tanh: [Math.tanh, (x, y) => 1 - y * y],
    sigmoid: [x => 1 / (1 + Math.exp(-x)), (x, y) => y * (1 - y)],
    silu: [x => x / (1 + Math.exp(-x)), x => { const s = 1 / (1 + Math.exp(-x)); return s * (1 + x * (1 - s)); }]
  };
  function act(A, kind) {
    const f = ACT[kind || 'none'];
    if (!f) throw new Error('unknown activation ' + kind);
    if (kind === 'none' || kind === 'linear' || !kind) return A;
    const out = node(A.rows, A.cols, [A], () => {
      const go = out.grad, ga = g(A);
      for (let i = 0; i < go.length; i++) ga[i] += go[i] * f[1](A.data[i], out.data[i]);
    });
    for (let i = 0; i < A.data.length; i++) out.data[i] = f[0](A.data[i]);
    return out;
  }
  function gatherRows(A, index) {
    const c = A.cols;
    const out = node(index.length, c, [A], () => {
      const go = out.grad, ga = g(A);
      for (let r = 0; r < index.length; r++) for (let j = 0; j < c; j++) ga[index[r] * c + j] += go[r * c + j];
    });
    for (let r = 0; r < index.length; r++) for (let j = 0; j < c; j++) out.data[r * c + j] = A.data[index[r] * c + j];
    return out;
  }
  // out[index[r]] += weight[r] * A[r]
  function scatterAdd(A, index, rows, weight) {
    const c = A.cols;
    const out = node(rows, c, [A], () => {
      const go = out.grad, ga = g(A);
      for (let r = 0; r < index.length; r++) {
        const w = weight ? weight[r] : 1;
        for (let j = 0; j < c; j++) ga[r * c + j] += w * go[index[r] * c + j];
      }
    });
    for (let r = 0; r < index.length; r++) {
      const w = weight ? weight[r] : 1;
      for (let j = 0; j < c; j++) out.data[index[r] * c + j] += w * A.data[r * c + j];
    }
    return out;
  }
  function concat(A, B) {
    if (A.rows !== B.rows) throw new Error('concat row mismatch');
    const n = A.rows, a = A.cols, b = B.cols, m = a + b;
    const out = node(n, m, [A, B], () => {
      const go = out.grad, ga = g(A), gb = g(B);
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < a; j++) ga[i * a + j] += go[i * m + j];
        for (let j = 0; j < b; j++) gb[i * b + j] += go[i * m + a + j];
      }
    });
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < a; j++) out.data[i * m + j] = A.data[i * a + j];
      for (let j = 0; j < b; j++) out.data[i * m + a + j] = B.data[i * b + j];
    }
    return out;
  }
  function mse(P, Y) {
    const n = P.data.length;
    const out = node(1, 1, [P], () => {
      const go = out.grad[0], gp = g(P);
      for (let i = 0; i < n; i++) gp[i] += go * 2 * (P.data[i] - Y.data[i]) / n;
    });
    let s = 0;
    for (let i = 0; i < n; i++) { const d = P.data[i] - Y.data[i]; s += d * d; }
    out.data[0] = s / n;
    return out;
  }
  function l2(params, lambda) {
    const out = node(1, 1, params, () => {
      const go = out.grad[0];
      for (const p of params) { const gp = g(p); for (let i = 0; i < p.data.length; i++) gp[i] += go * 2 * lambda * p.data[i]; }
    });
    let s = 0;
    for (const p of params) for (let i = 0; i < p.data.length; i++) s += p.data[i] * p.data[i];
    out.data[0] = lambda * s;
    return out;
  }
  function sum(a, b) {
    const out = node(1, 1, [a, b], () => { g(a)[0] += out.grad[0]; g(b)[0] += out.grad[0]; });
    out.data[0] = a.data[0] + b.data[0];
    return out;
  }

  function backward(loss) {
    const order = [], seen = new Set();
    (function visit(t) {
      if (seen.has(t)) return;
      seen.add(t);
      for (const p of t.parents) visit(p);
      order.push(t);
    })(loss);
    loss.grad = new Float64Array([1]);
    for (let i = order.length - 1; i >= 0; i--) if (order[i].back && order[i].grad && order[i].needsGrad) order[i].back();
  }

  // Glorot-uniform weights from a seeded mulberry32 stream; zero biases.
  function dense(inputs, outputs, rng) {
    const limit = Math.sqrt(6 / (inputs + outputs));
    const W = tensor(inputs, outputs, null, true);
    for (let i = 0; i < W.data.length; i++) W.data[i] = (2 * rng() - 1) * limit;
    return {W, b: tensor(1, outputs, null, true)};
  }
  function adam(params, options) {
    const lr = options.lr || 3e-3, b1 = 0.9, b2 = 0.999, eps = 1e-8;
    const m = params.map(p => new Float64Array(p.data.length)), v = params.map(p => new Float64Array(p.data.length));
    let t = 0;
    return {
      step() {
        t++;
        const c1 = 1 - Math.pow(b1, t), c2 = 1 - Math.pow(b2, t);
        params.forEach((p, k) => {
          if (!p.grad) return;
          for (let i = 0; i < p.data.length; i++) {
            const gi = p.grad[i];
            m[k][i] = b1 * m[k][i] + (1 - b1) * gi;
            v[k][i] = b2 * v[k][i] + (1 - b2) * gi * gi;
            p.data[i] -= lr * (m[k][i] / c1) / (Math.sqrt(v[k][i] / c2) + eps);
          }
          p.grad = null;
        });
      }
    };
  }
  // Release graph references after a step so intermediates are collectable.
  function zeroGrad(params) { for (const p of params) p.grad = null; }

  S.tensor = Object.freeze({tensor, fromRows, toRows, matmul, addBias, add, act, gatherRows, scatterAdd, concat,
    mse, l2, sum, backward, dense, adam, zeroGrad, ACTIVATIONS: Object.keys(ACT)});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.tensor;
})(globalThis);
