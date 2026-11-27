// Declarative architecture catalogue. Adding a study variant means adding an entry here; the
// pipeline trains, cross-validates and ranks every entry the same way.
//
// Fields: name, task ('atomic' | 'molecular'), family (mean|knn|ridge|mlp|deepsets|mpnn),
// inputs (a named input set below), family hyper-parameters, and optional export name. Exported
// entries must be dense (ridge/mlp) so TRECH's GenericSurrogate can evaluate them unchanged.
// An atomic entry with `cascadeSource: <source>` is the atomic model whose predicted profiles a
// molecular entry with `cascade: <source>` pools ('pubchem' when a molecular entry names none).
// The *_geant4 entries add the Geant4 atomic response (mean excitation energy and per-atom
// photo-absorption cross sections, catalog/geant4_atomic.json) to the atomic inputs.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};
  const F = () => S.features;

  function inputSet(name) {
    const sets = {
      atomic: F().ATOMIC_FEATURES,
      atomic_geant4: F().ATOMIC_FEATURES.concat(F().GEANT4_ATOMIC_FEATURES),
      geant4: ['z'].concat(F().GEANT4_ATOMIC_FEATURES),
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
    {name: 'atomic_mlp_tanh', task: 'atomic', family: 'mlp', inputs: 'atomic', cascadeSource: 'pubchem',
      layers: [{units: 32, activation: 'tanh'}, {units: 32, activation: 'tanh'}], epochs: 1500, lr: 3e-3, l2: 2e-3,
      note: 'Two tanh layers on PubChem facts; the PubChem-fed cascade source (exported to TRECH until 2026-11-27).'},
    {name: 'atomic_mlp_silu_wide', task: 'atomic', family: 'mlp', inputs: 'atomic',
      layers: [{units: 64, activation: 'silu'}], epochs: 1500, lr: 2e-3, l2: 5e-3,
      note: 'One wide SiLU layer; capacity/regularisation contrast to the tanh stack.'},
    {name: 'atomic_knn3_geant4', task: 'atomic', family: 'knn', inputs: 'atomic_geant4', k: 3,
      note: 'Nearest elements in PubChem facts plus the Geant4 atomic response.'},
    {name: 'atomic_ridge_geant4', task: 'atomic', family: 'ridge', inputs: 'atomic_geant4', lambda: 3,
      note: 'Ridge on PubChem facts plus the Geant4 atomic response (I, photo-absorption 10 eV-10 keV).'},
    {name: 'atomic_mlp_tanh_geant4', task: 'atomic', family: 'mlp', inputs: 'atomic_geant4', cascadeSource: 'geant4', export: 'spectrum_atomic',
      layers: [{units: 32, activation: 'tanh'}, {units: 32, activation: 'tanh'}], epochs: 1500, lr: 3e-3, l2: 2e-3,
      note: 'The tanh stack with the Geant4 atomic response added; exported to TRECH as the atomic rung (inputs read from a live Geant4 probe) and the Geant4-fed cascade source.'},
    {name: 'atomic_mlp_silu_wide_geant4', task: 'atomic', family: 'mlp', inputs: 'atomic_geant4',
      layers: [{units: 64, activation: 'silu'}], epochs: 1500, lr: 2e-3, l2: 5e-3,
      note: 'The wide SiLU layer with the Geant4 atomic response added.'},
    {name: 'atomic_mlp_tanh_geant4_only', task: 'atomic', family: 'mlp', inputs: 'geant4',
      layers: [{units: 32, activation: 'tanh'}, {units: 32, activation: 'tanh'}], epochs: 1500, lr: 3e-3, l2: 2e-3,
      note: 'The tanh stack on Z and the Geant4 atomic response only: no PubChem facts.'},

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
    {name: 'molecular_mlp_cascade', task: 'molecular', family: 'mlp', inputs: 'descriptors_cascade',
      layers: [{units: 32, activation: 'tanh'}], epochs: 1200, lr: 3e-3, l2: 3e-3,
      note: 'Same network plus pooled PubChem-fed atomic-model predictions (the cascade rung exported to TRECH until 2026-11-27).'},
    {name: 'molecular_ridge_cascade_geant4', task: 'molecular', family: 'ridge', inputs: 'descriptors_cascade', cascade: 'geant4', lambda: 3,
      note: 'Ridge cascade pooling the Geant4-fed atomic model instead of the PubChem-only one.'},
    {name: 'molecular_mlp_cascade_geant4', task: 'molecular', family: 'mlp', inputs: 'descriptors_cascade', cascade: 'geant4',
      export: 'spectrum_molecular', layers: [{units: 32, activation: 'tanh'}], epochs: 1200, lr: 3e-3, l2: 3e-3,
      note: 'MLP cascade pooling the Geant4-fed atomic model: the atomic -> molecular cascade rung exported to TRECH.'},
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
      note: 'Message passing with each node also carrying the atomic model\'s predicted line-strength summary.'},
    {name: 'molecular_mpnn_cascade_geant4', task: 'molecular', family: 'mpnn', inputs: 'solvent', globalInputs: true,
      atomicNodeFeatures: true, cascadeNodeFeatures: true, cascade: 'geant4', units: 16, steps: 3, readout: 'sum+mean', activation: 'tanh',
      head: [{units: 32, activation: 'tanh'}], epochs: 500, lr: 3e-3, l2: 1e-3,
      note: 'Message passing whose node summaries come from the Geant4-fed atomic model.'}
  ];
  const CASCADE_SOURCES = ['pubchem', 'geant4'];
  // Which atomic model a molecular entry pools, or null when it pools none.
  function cascadeOf(spec) {
    if (spec.task !== 'molecular' || !(spec.inputs === 'descriptors_cascade' || spec.cascadeNodeFeatures)) return null;
    return spec.cascade || 'pubchem';
  }
  function usesGeant4(spec) {
    return spec.inputs === 'atomic_geant4' || spec.inputs === 'geant4' || cascadeOf(spec) === 'geant4';
  }

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
    if (spec.cascadeSource !== undefined && CASCADE_SOURCES.indexOf(spec.cascadeSource) < 0) throw new Error(spec.name + ': unknown cascadeSource ' + spec.cascadeSource);
    if (spec.cascade !== undefined && (CASCADE_SOURCES.indexOf(spec.cascade) < 0 || !cascadeOf(spec))) throw new Error(spec.name + ': bad cascade ' + spec.cascade);
    inputSet(spec.inputs);
    return spec;
  }

  S.architectures = Object.freeze({catalog, inputSet, validate, cascadeOf, usesGeant4, CASCADE_SOURCES});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.architectures;
})(globalThis);
