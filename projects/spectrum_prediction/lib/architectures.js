// Declarative architecture catalogue. Adding a study variant means adding an entry here; the
// pipeline trains, cross-validates and ranks every entry the same way.
//
// Fields: name, task ('atomic' | 'molecular'), family (mean|knn|ridge|mlp|deepsets|mpnn),
// inputs (a named input set below), family hyper-parameters, and optional export name. Exported
// entries must be dense (ridge/mlp) so TRECH's GenericSurrogate can evaluate them unchanged.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};
  const F = () => S.features;

  function inputSet(name) {
    const sets = {
      atomic: F().ATOMIC_FEATURES,
      descriptors: F().MOLECULAR_DESCRIPTORS,
      descriptors_cascade: F().MOLECULAR_DESCRIPTORS.concat(F().ATOMIC_POOL),
      solvent: ['solvent_protic', 'solvent_aprotic', 'solvent_nonpolar']
    };
    if (!sets[name]) throw new Error('unknown input set ' + name);
    return sets[name].slice();
  }

  const CATALOG = [
    {name: 'atomic_mean', task: 'atomic', family: 'mean', inputs: 'atomic',
      note: 'Training-mean line-strength profile; the floor every learned model must beat.'},
    {name: 'atomic_knn3', task: 'atomic', family: 'knn', inputs: 'atomic', k: 3,
      note: 'Inverse-distance 3-nearest elements in standardized PubChem fact space.'},
    {name: 'atomic_ridge', task: 'atomic', family: 'ridge', inputs: 'atomic', lambda: 3,
      note: 'Linear map from element facts to every bin (closed form).'},
    {name: 'atomic_mlp_tanh', task: 'atomic', family: 'mlp', inputs: 'atomic', export: 'spectrum_atomic', cascadeSource: true,
      layers: [{units: 32, activation: 'tanh'}, {units: 32, activation: 'tanh'}], epochs: 1500, lr: 3e-3, l2: 2e-3,
      note: 'Two tanh layers; exported to TRECH as the atomic rung and used to pool atomic features into molecules.'},
    {name: 'atomic_mlp_silu_wide', task: 'atomic', family: 'mlp', inputs: 'atomic',
      layers: [{units: 64, activation: 'silu'}], epochs: 1500, lr: 2e-3, l2: 5e-3,
      note: 'One wide SiLU layer; capacity/regularisation contrast to the tanh stack.'},

    {name: 'molecular_mean', task: 'molecular', family: 'mean', inputs: 'descriptors',
      note: 'Training-mean UV envelope.'},
    {name: 'molecular_knn3', task: 'molecular', family: 'knn', inputs: 'descriptors', k: 3,
      note: 'Nearest molecules by graph descriptors.'},
    {name: 'molecular_ridge', task: 'molecular', family: 'ridge', inputs: 'descriptors', lambda: 3,
      note: 'Linear map from graph descriptors.'},
    {name: 'molecular_ridge_cascade', task: 'molecular', family: 'ridge', inputs: 'descriptors_cascade', lambda: 3,
      note: 'Ridge with pooled atomic-model predictions appended (cascade ablation, linear).'},
    {name: 'molecular_mlp', task: 'molecular', family: 'mlp', inputs: 'descriptors',
      layers: [{units: 32, activation: 'tanh'}], epochs: 1200, lr: 3e-3, l2: 3e-3,
      note: 'Dense network on graph descriptors only.'},
    {name: 'molecular_mlp_cascade', task: 'molecular', family: 'mlp', inputs: 'descriptors_cascade', export: 'spectrum_molecular',
      layers: [{units: 32, activation: 'tanh'}], epochs: 1200, lr: 3e-3, l2: 3e-3,
      note: 'Same network plus pooled atomic-model predictions: the atomic -> molecular cascade rung exported to TRECH.'},
    {name: 'molecular_deepsets', task: 'molecular', family: 'deepsets', inputs: 'solvent', globalInputs: true,
      atomicNodeFeatures: true, units: 24, steps: 1, readout: 'sum+mean', activation: 'tanh',
      head: [{units: 32, activation: 'tanh'}], epochs: 500, lr: 3e-3, l2: 1e-3,
      note: 'Permutation-invariant atom set (atom type + PubChem element facts), no bonds.'},
    {name: 'molecular_mpnn', task: 'molecular', family: 'mpnn', inputs: 'solvent', globalInputs: true,
      atomicNodeFeatures: true, units: 16, steps: 3, readout: 'sum+mean', activation: 'tanh',
      head: [{units: 32, activation: 'tanh'}], epochs: 500, lr: 3e-3, l2: 1e-3,
      note: 'Three message-passing steps over the bond graph: conjugation must be learned from topology.'},
    {name: 'molecular_mpnn_cascade', task: 'molecular', family: 'mpnn', inputs: 'solvent', globalInputs: true,
      atomicNodeFeatures: true, cascadeNodeFeatures: true, units: 16, steps: 3, readout: 'sum+mean', activation: 'tanh',
      head: [{units: 32, activation: 'tanh'}], epochs: 500, lr: 3e-3, l2: 1e-3,
      note: 'Message passing with each node also carrying the atomic model\'s predicted line-strength summary.'}
  ];

  function catalog(filter) {
    const list = CATALOG.map(a => Object.freeze(Object.assign({}, a)));
    if (!filter || !filter.length) return list;
    const out = list.filter(a => filter.indexOf(a.name) >= 0 || filter.indexOf(a.task) >= 0);
    const missing = filter.filter(f => f !== 'atomic' && f !== 'molecular' && !list.some(a => a.name === f));
    if (missing.length) throw new Error('unknown architecture(s): ' + missing.join(', '));
    return out;
  }
  function validate(spec) {
    if (!spec.name || !spec.task || !spec.family) throw new Error('architecture needs name/task/family');
    if (S.models.families.indexOf(spec.family) < 0) throw new Error(spec.name + ': unknown family ' + spec.family);
    if (spec.export && ['ridge', 'mlp'].indexOf(spec.family) < 0) throw new Error(spec.name + ': only dense families export to TRECH');
    for (const l of (spec.layers || []).concat(spec.head || []))
      if (!(l.units > 0) || S.tensor.ACTIVATIONS.indexOf(l.activation) < 0) throw new Error(spec.name + ': bad layer ' + JSON.stringify(l));
    inputSet(spec.inputs);
    return spec;
  }

  S.architectures = Object.freeze({catalog, inputSet, validate});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.architectures;
})(globalThis);
