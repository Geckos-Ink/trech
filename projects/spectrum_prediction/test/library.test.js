'use strict';
// node --test projects/spectrum_prediction/test
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const S = require('../lib/index.js');

const close = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg || ''} ${a} vs ${b}`);

test('lib stays host-neutral so the TRECH QuickJS scenario can include it', () => {
  const dir = path.join(__dirname, '../lib');
  for (const file of fs.readdirSync(dir)) {
    const text = fs.readFileSync(path.join(dir, file), 'utf8');
    if (file === 'index.js') continue;
    assert.doesNotMatch(text, /\brequire\(|\bprocess\.|\bBuffer\b|node:/, file + ' must not use Node APIs');
    assert.match(text, /globalThis\);\s*$/, file + ' must attach to globalThis');
  }
});

test('NIST ASD CSV parsing keeps observed/Ritz wavelengths, A_ki and degeneracies', () => {
  const csv = ['obs_wl_air(nm),ritz_wl_air(nm),intens,Aki(s^-1),Acc,Ei(cm-1),Ek(cm-1),conf_i,term_i,J_i,conf_k,term_k,J_k,g_i,g_k,Type,',
    '"=""656.279""","=""656.2819""","=""500000""","=""4.4101e+07""",AAA,"=""82258.9""","=""97492.3""","=""2p""","=""2P*""","=""3/2""","=""3d""","=""2D""","=""5/2""",4,6,,',
    '"=""""","=""486.135""","=""""","=""""",,"=""82259""","=""[102823]""","=""2""","=""""","=""""","=""4""","=""""","=""""",8,32,,'].join('\n');
  const parsed = S.nist.parseLines(csv);
  assert.equal(parsed.medium, 'air');
  assert.equal(parsed.lines.length, 2);
  assert.deepEqual([parsed.lines[0].wavelength_nm, parsed.lines[0].aki, parsed.lines[0].gk, parsed.lines[0].observed], [656.279, 4.4101e7, 6, true]);
  assert.deepEqual([parsed.lines[1].wavelength_nm, parsed.lines[1].aki, parsed.lines[1].observed, parsed.lines[1].ek_cm1], [486.135, null, false, 102823]);
  assert.throws(() => S.nist.parseLines('<!DOCTYPE html><html>error</html>'), /HTML/);
  assert.match(S.nist.linesUrl('Na', 200, 1000), /spectra=Na%20I&.*low_w=200&upp_w=1000.*format=2/);
});

test('UV statements: accepted log/linear epsilon forms, rejected catalogue numbers and E(1%)', () => {
  const parse = t => S.pubchem.parseUvStatement(t);
  const bands = t => parse(t).bands.map(b => [b.wavelength_nm, b.log_epsilon === null ? null : Number(b.log_epsilon.toFixed(3))]);
  assert.deepEqual(bands('MAX ABSORPTION (ALCOHOL): 221 NM (LOG E= 5.04); 275.5 NM (LOG E= 3.76)'), [[221, 5.04], [275.5, 3.76]]);
  assert.equal(parse('MAX ABSORPTION (ALCOHOL): 221 NM (LOG E= 5.04)').solvent_class, 'protic');
  assert.equal(parse('MAX ABSORPTION (CYCLOHEXANE): 251 NM (LOG E= 3.1)').solvent_class, 'nonpolar');
  assert.deepEqual(bands('MAX ABSORPTION (ETHYL ALC): 219 (LOG E= 3.89); 253 (LOG E= 2.27)'), [[219, 3.89], [253, 2.27]]);
  assert.deepEqual(bands('UV log epsilon = 3.25 at 290 nm'), [[290, 3.25]]);
  assert.deepEqual(bands('UV max (ethanol): 250 nm (epsilon 13800)'), [[250, 4.14]]);
  assert.deepEqual(bands('Max absorption (ethanol):  230, 260, 319 nm (epsilon = 20,800, 16,200, 6,290)'), [[230, 4.318], [260, 4.21], [319, 3.799]]);
  assert.deepEqual(bands('UV max = 276 nm'), [[276, null]]);
  assert.equal(parse('UV: 89 (Sadtler Research Laboratories Spectral Collection)'), null);
  assert.equal(parse('Maximum in cyclohexane at 453 nm to 456 nm'), null);
  assert.deepEqual(bands('MAX ABSORPTION: 370 NM (E= 776, 1%, 1 CM)'), [[370, null]]);
  const shoulder = parse('MAX ABSORPTION (ALC): 276 NM SHOULDER (LOG E= 3.16), 218.5 NM (LOG E= 3.78)');
  assert.deepEqual(shoulder.bands.map(b => b.shoulder), [false, true]);
  // Malformed source text loses the unreadable band rather than inventing one.
  assert.deepEqual(bands('Max absorption (alcohol): 324 nm (log e= 3.45 nm (log e= 3.73); 357 nm (log e= 3.89)'), [[324, 3.45], [357, 3.89]]);
  const chosen = S.pubchem.chooseUv([parse('UV max = 276 nm'), parse('MAX ABSORPTION (ALCOHOL): 207 NM (LOG E= 3.97); 260 NM (LOG E= 2.48)')]);
  assert.equal(chosen.with_epsilon, 2);
});

test('element facts: configuration and ground-level parsing', () => {
  assert.deepEqual(S.pubchem.parseGroundLevel('2S1/2'), {term: '2S1/2', multiplicity: 2, L: 0, J: 0.5, odd: false});
  assert.equal(S.pubchem.parseGroundLevel('4S°3/2').odd, true);
  assert.equal(S.pubchem.parseGroundLevel('n/a'), null);
  const cfg = S.pubchem.parseConfiguration('[Ar]4s2 3d10 4p1');
  assert.deepEqual([cfg.s, cfg.p, cfg.d, cfg.f, cfg.n_max, cfg.core], [2, 1, 10, 0, 4, 'Ar']);
  const features = S.features.atomicFeatures({z: 8, symbol: 'O', atomic_mass: 15.999, electron_configuration: '[He]2s2 2p4',
    ionization_energy_ev: 13.618, electronegativity: 3.44, electron_affinity_ev: null, atomic_radius_pm: 152,
    ground_level: S.pubchem.parseGroundLevel('3P2')});
  assert.equal(features.electron_affinity_missing, 1);
  assert.equal(features.ground_multiplicity, 3);
  assert.deepEqual(Object.keys(features), S.features.ATOMIC_FEATURES);
});

test('SMILES graphs: implicit H, rings, pi systems and functional-group counts', () => {
  const a = s => S.smiles.analyze(S.smiles.parse(s));
  const benzene = a('C1=CC=CC=C1');
  assert.deepEqual([benzene.element_counts.H, benzene.ring_rank, benzene.largest_pi_system], [6, 1, 6]);
  const aromatic = a('c1ccccc1O');
  assert.deepEqual([aromatic.element_counts.H, aromatic.aromatic_atoms, aromatic.auxochrome_atoms, aromatic.largest_extended_system], [6, 6, 1, 7]);
  const nitro = a('C1=CC=C(C=C1)[N+](=O)[O-]');
  assert.deepEqual([nitro.nitro_groups, nitro.charged_atoms, nitro.element_counts.H], [1, 2, 5]);
  assert.equal(a('CC(=O)C').carbonyl_groups, 1);
  assert.equal(a('C1=CC=C(C=C1)N=NC2=CC=CC=C2').azo_groups, 1);
  assert.equal(a('CC#N').nitrile_groups, 1);
  assert.equal(a('[Na+].[Cl-]').fragments, 2);
  assert.equal(a('C(Cl)(Cl)(Cl)Cl').element_counts.Cl, 4);
  assert.throws(() => S.smiles.parse('C1CC'), /unclosed ring/);
  assert.throws(() => S.smiles.parse('C(C'), /unbalanced/);
  const inputs = S.features.moleculeInputs('C1=CC=CC=C1', 'protic');
  assert.deepEqual(Object.keys(inputs.descriptor), S.features.MOLECULAR_DESCRIPTORS);
  assert.equal(inputs.graph.nodes[0].length, S.features.NODE_FEATURES.length);
  assert.equal(inputs.pooled, null);
});

test('grid representations and atomic pooling', () => {
  const g = S.grid.ATOMIC_GRID;
  const lines = [500, 501, 502, 503, 504].map(w => ({wavelength_nm: w, aki: 1e7, gk: 2})).concat([{wavelength_nm: 900, aki: null, gk: 3}]);
  const profile = S.grid.atomicProfile(lines, g);
  assert.equal(profile.weightedLines, 5);
  assert.equal(profile.totalLines, 6);
  assert.equal(Math.max(...profile.target), 1);
  assert.equal(S.grid.peakWavelength(profile.target, g), 510);
  assert.equal(S.grid.atomicProfile(lines.slice(0, 2), g), null);
  const env = S.grid.molecularEnvelope([{wavelength_nm: 255, log_epsilon: 4}], S.grid.MOLECULAR_GRID);
  close(Math.max(...env), Math.log10(1 + 1e4) / 5, 0.01, 'envelope peak');
  assert.equal(S.grid.peakWavelength(env, S.grid.MOLECULAR_GRID), 255);
  close(S.grid.epsilonFromTarget(Math.log10(1 + 1e4) / 5), 1e4, 1e-6);
  const summary = S.features.profileSummary(profile.target, g);
  const pooled = S.features.poolAtomic({C: 1, H: 3}, {C: summary, H: Object.assign({}, summary, {atomic_pool_strength: 0})});
  close(pooled.atomic_pool_strength, summary.atomic_pool_strength / 4, 1e-12);
  assert.throws(() => S.features.poolAtomic({N: 1}, {}), /No atomic-model summary/);
});

test('autodiff gradients match finite differences for every graph op', () => {
  const t = S.tensor, rng = TRECH_RANDOM.mulberry32(11);
  const X = t.fromRows([[0.1, -0.3, 0.5], [0.7, 0.2, -0.4], [-0.2, 0.9, 0.3]]), Y = t.fromRows([[0.2, -0.1], [0.5, 0.3]]);
  const e = t.dense(3, 4, rng), m = t.dense(4, 4, rng), h = t.dense(9, 2, rng), G = t.fromRows([[1], [0]]);
  const params = [e.W, e.b, m.W, h.W, h.b];
  const f = () => {
    let H = t.act(t.addBias(t.matmul(X, e.W), e.b), 'tanh');
    H = t.act(t.add(H, t.scatterAdd(t.gatherRows(t.matmul(H, m.W), [0, 1, 1, 2]), [1, 0, 2, 1], 3)), 'silu');
    const P = t.concat(t.concat(t.scatterAdd(H, [0, 0, 1], 2), t.scatterAdd(H, [0, 0, 1], 2, [0.5, 0.5, 1])), G);
    return t.sum(t.mse(t.addBias(t.matmul(P, h.W), h.b), Y), t.l2([e.W], 0.01));
  };
  t.backward(f());
  let worst = 0;
  for (const p of params) for (let i = 0; i < p.data.length; i++) {
    const analytic = p.grad[i], v = p.data[i];
    p.data[i] = v + 1e-6; const up = f().data[0];
    p.data[i] = v - 1e-6; const down = f().data[0];
    p.data[i] = v;
    const numeric = (up - down) / 2e-6;
    worst = Math.max(worst, Math.abs(numeric - analytic) / (Math.abs(numeric) + Math.abs(analytic) + 1e-9));
  }
  assert.ok(worst < 1e-5, 'relative gradient error ' + worst);
});

function linearSamples(n) {
  const rng = TRECH_RANDOM.mulberry32(3), out = [];
  for (let i = 0; i < n; i++) {
    const a = rng() * 2 - 1, b = rng() * 2 - 1;
    out.push({id: 'r' + i, x: {a, b}, y: [2 * a - b + 0.5, -a + 3 * b]});
  }
  return out;
}

test('model families: ridge recovers a linear map; MLP is deterministic; kNN/mean baselines', () => {
  const samples = linearSamples(60), ctx = {inputs: ['a', 'b'], seed: 5};
  const ridge = S.models.fit({name: 'r', family: 'ridge', lambda: 1e-9}, samples, ctx);
  const p = ridge.predict({x: {a: 0.3, b: -0.2}});
  close(p[0], 2 * 0.3 + 0.2 + 0.5, 1e-6, 'ridge out0');
  close(p[1], -0.3 - 0.6, 1e-6, 'ridge out1');
  const spec = {name: 'm', family: 'mlp', layers: [{units: 8, activation: 'tanh'}], epochs: 300, lr: 1e-2, l2: 0};
  const m1 = S.models.fit(spec, samples, ctx), m2 = S.models.fit(spec, samples, ctx);
  assert.deepEqual(m1.predict(samples[0]), m2.predict(samples[0]));
  assert.ok(m1.history[m1.history.length - 1].loss < m1.history[0].loss / 10, 'MLP loss decreases');
  assert.deepEqual(S.models.fit({name: 'k', family: 'knn', k: 1}, samples, ctx).predict(samples[4]), samples[4].y);
  const mean = S.models.fit({name: 'mean', family: 'mean'}, samples, ctx).predict(samples[0]);
  close(mean[0], samples.reduce((s, r) => s + r.y[0], 0) / samples.length, 1e-12);
  assert.throws(() => S.models.fit({name: 'x', family: 'transformer'}, samples, ctx), /unknown model family/);
});

test('graph families train on molecular graphs with cascade node features', () => {
  const smiles = ['C1=CC=CC=C1', 'CC(=O)C', 'C1=CC=C2C=CC=CC2=C1', 'CCO', 'C1=CC=C(C=C1)O', 'CC=CC=O'];
  const summary = {atomic_pool_strength: 0.3, atomic_pool_centroid_nm: 600, atomic_pool_q1: 0.2, atomic_pool_q2: 0.3, atomic_pool_q3: 0.4, atomic_pool_q4: 0.3};
  const summaries = {C: summary, H: summary, O: Object.assign({}, summary, {atomic_pool_q1: 0.5})};
  const samples = smiles.map((s, i) => {
    const inputs = S.features.moleculeInputs(s, 'protic', summaries);
    return {id: 'm' + i, x: inputs.x, graph: inputs.graph, y: [inputs.analysis.largest_pi_system / 10, inputs.analysis.element_counts.O || 0]};
  });
  const facts = {C: S.features.ATOMIC_FEATURES.map((_, i) => i), H: S.features.ATOMIC_FEATURES.map(() => 1), O: S.features.ATOMIC_FEATURES.map((_, i) => -i)};
  const ctx = {inputs: ['solvent_protic', 'solvent_aprotic', 'solvent_nonpolar'], seed: 9, elementFeatures: facts, elementSummaries: summaries};
  for (const family of ['mpnn', 'deepsets']) {
    const model = S.models.fit({name: family, family, globalInputs: true, atomicNodeFeatures: true, cascadeNodeFeatures: true,
      units: 8, steps: 2, readout: 'sum+mean', head: [{units: 8, activation: 'tanh'}], epochs: 200, lr: 1e-2, l2: 0}, samples, ctx);
    assert.ok(model.history[model.history.length - 1].loss < model.history[0].loss, family + ' loss decreases');
    assert.equal(model.predict(samples[2]).length, 2);
  }
});

test('architecture catalogue validates and exports only dense families', () => {
  const all = S.architectures.catalog().map(S.architectures.validate);
  assert.ok(all.some(a => a.export === 'spectrum_atomic' && a.cascadeSource));
  assert.ok(all.some(a => a.export === 'spectrum_molecular' && a.inputs === 'descriptors_cascade'));
  assert.throws(() => S.architectures.validate({name: 'bad', task: 'molecular', family: 'mpnn', inputs: 'solvent', export: 'x'}), /dense/);
  assert.throws(() => S.architectures.catalog(['nope']), /unknown architecture/);
  assert.equal(S.architectures.catalog(['atomic']).every(a => a.task === 'atomic'), true);
});

test('generic_surrogate_v1 export reproduces the JS model with the engine layout', () => {
  const samples = linearSamples(40).map(s => Object.assign(s, {y: [Math.tanh(s.x.a) + s.x.b, s.x.a * s.x.b]}));
  const ctx = {inputs: ['a', 'b'], seed: 1};
  const model = S.models.fit({name: 'm', family: 'mlp', layers: [{units: 6, activation: 'silu'}], epochs: 200, lr: 1e-2}, samples, ctx);
  const metrics = S.validate.metrics(samples.map(s => s.y), samples.map(s => model.predict(s)), S.grid.MOLECULAR_GRID);
  const exported = S.export.genericSurrogate(model, {outputNames: ['o0', 'o1'], scale: 'nano', testMetrics: metrics,
    trainRows: samples.map(s => [s.x.a, s.x.b]), trainedFrom: {}, note: {}});
  assert.equal(exported.model, 'generic_surrogate_v1');
  assert.deepEqual(exported.trained_scale_bands, ['nano']);
  assert.equal(exported.layers[0].weights.length, 6);
  assert.equal(exported.layers[0].weights[0].length, 2);
  assert.equal(exported.input_domain.occupancy.counts[0].reduce((a, b) => a + b, 0), 40);
  assert.ok(exported.input_domain.joint.radius >= 0 && exported.input_domain.joint.centers.length <= 24);
  assert.ok(Number.isFinite(exported.holdout.r2_min));
  // GenericSurrogate::predict: z = (x - mean)/std -> layers -> y * std + mean.
  const engine = x => {
    let h = x.map((v, i) => (v - exported.input_mean[i]) / exported.input_std[i]);
    h = S.models.evalDense(exported.layers, h);
    return h.map((v, o) => v * exported.output_std[o] + exported.output_mean[o]);
  };
  for (const s of samples.slice(0, 5)) {
    const a = engine([s.x.a, s.x.b]), b = model.predict(s);
    a.forEach((v, i) => close(v, b[i], 1e-12));
  }
});

test('hash splits are stable when records are added', () => {
  const ids = Array.from({length: 50}, (_, i) => ({id: 'x' + i}));
  const first = S.validate.holdout(ids, 0.2, 'salt');
  const second = S.validate.holdout(ids.concat([{id: 'new1'}, {id: 'new2'}]), 0.2, 'salt');
  for (const s of first.test) assert.ok(second.test.some(t => t.id === s.id));
  const folds = S.validate.folds(ids, 5, 'salt');
  assert.equal(folds.reduce((n, f) => n + f.length, 0), 50);
  const m = S.validate.metrics([[1, 0], [0, 1]], [[1, 0], [0, 1]], S.grid.MOLECULAR_GRID);
  assert.deepEqual([m.rmse, m.r2, m.cosine], [0, 1, 1]);
});

test('split-conformal intervals: finite-sample rank, capping, coverage and exchangeable calibration', () => {
  const U = S.uncertainty;
  // n = 9 scores at 0.9 -> rank ceil(10 * 0.9) = 9 -> the largest score, not capped.
  assert.deepEqual(U.conformalQuantile([1, 2, 3, 4, 5, 6, 7, 8, 9], 0.9), {value: 9, capped: false});
  assert.deepEqual(U.conformalQuantile([3, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], 0.9), {value: 18, capped: false});
  // n = 4 cannot certify 0.9 (rank 5 > 4): the largest score is used and flagged.
  assert.deepEqual(U.conformalQuantile([4, 1, 3, 2], 0.9), {value: 4, capped: true});
  assert.throws(() => U.calibrate([[0]], [[0]], 1), /coverage/);
  const cov = U.coverage([[0, 0], [1, 1]], [[0.1, 0.5], [1, 1]], [0.2, 0.2]);
  assert.deepEqual([cov.cells, cov.min_bin, cov.samples_all_bins], [0.75, 0.5, 0.5]);
  const b = U.bounds([0.05, 1], [0.1, 0.1], 0);
  assert.deepEqual(b.lower.map(v => +v.toFixed(12)), [0, 0.9]);
  // Exchangeable synthetic residuals: calibration on one half covers ~90 % of the other.
  const rng = TRECH_RANDOM.mulberry32(7), gauss = () => Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
  const make = n => Array.from({length: n}, () => [[0, 0, 0], [gauss(), 2 * gauss(), 0.5 * gauss()]]);
  const cal = make(400), held = make(4000);
  const fit = U.calibrate(cal.map(r => r[0]), cal.map(r => r[1]), 0.9);
  assert.ok(Math.abs(fit.half_width[1] / fit.half_width[0] - 2) < 0.35, 'widths scale with per-bin residual spread');
  const got = U.coverage(held.map(r => r[0]), held.map(r => r[1]), fit.half_width);
  assert.ok(got.cells > 0.87 && got.cells < 0.94, 'held-out cell coverage near nominal: ' + got.cells);
  assert.ok(got.samples_all_bins < got.cells, 'simultaneous coverage is stricter than marginal');
});
