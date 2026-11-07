// Named feature vocabularies shared by training (Node) and the TRECH scenario (QuickJS).
//
// Atomic inputs are PubChem element facts (periodic-table row + NIST ground level reported by
// PubChem). Molecular inputs are SMILES graph counts plus the measured solvent class. The
// atomic -> molecular lift pools the *atomic model's predicted* line-strength profiles over the
// molecule's atoms; it is the learned cascade rung studied by the ablation in the report.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  const ATOMIC_FEATURES = ['z', 'atomic_mass', 'period', 'valence_s', 'valence_p', 'valence_d', 'valence_f',
    'ionization_energy_ev', 'electronegativity', 'electronegativity_missing', 'electron_affinity_ev',
    'electron_affinity_missing', 'atomic_radius_pm', 'atomic_radius_missing', 'ground_multiplicity',
    'ground_L', 'ground_J', 'ground_odd', 'ground_missing'];

  function atomicFeatures(facts) {
    const config = facts.configuration || (S.pubchem ? S.pubchem.parseConfiguration(facts.electron_configuration) : null);
    if (!config) throw new Error('No parseable electron configuration for ' + facts.symbol);
    const g = facts.ground_level || null;
    const val = (v, fallback) => (v === null || v === undefined || !Number.isFinite(v) ? fallback : v);
    if (!Number.isFinite(facts.ionization_energy_ev)) throw new Error('No ionization energy for ' + facts.symbol);
    return {z: facts.z, atomic_mass: facts.atomic_mass, period: config.n_max, valence_s: config.s,
      valence_p: config.p, valence_d: config.d, valence_f: config.f,
      ionization_energy_ev: facts.ionization_energy_ev,
      electronegativity: val(facts.electronegativity, 0), electronegativity_missing: Number.isFinite(facts.electronegativity) ? 0 : 1,
      electron_affinity_ev: val(facts.electron_affinity_ev, 0), electron_affinity_missing: Number.isFinite(facts.electron_affinity_ev) ? 0 : 1,
      atomic_radius_pm: val(facts.atomic_radius_pm, 0), atomic_radius_missing: Number.isFinite(facts.atomic_radius_pm) ? 0 : 1,
      ground_multiplicity: g ? g.multiplicity : 0, ground_L: g ? g.L : 0, ground_J: g ? g.J : 0,
      ground_odd: g && g.odd ? 1 : 0, ground_missing: g ? 0 : 1};
  }

  const MOLECULAR_DESCRIPTORS = ['n_C', 'n_H', 'n_N', 'n_O', 'n_S', 'n_P', 'n_halogen', 'heavy_atoms', 'ring_rank',
    'double_bonds', 'triple_bonds', 'aromatic_bonds', 'pi_atoms', 'pi_fraction', 'largest_pi_system', 'pi_systems',
    'auxochrome_atoms', 'largest_extended_system', 'carbonyl_groups', 'nitrile_groups', 'azo_groups', 'nitro_groups',
    'charged_atoms', 'fragments', 'solvent_protic', 'solvent_aprotic', 'solvent_nonpolar'];
  const ATOMIC_POOL = ['atomic_pool_strength', 'atomic_pool_centroid_nm', 'atomic_pool_q1', 'atomic_pool_q2',
    'atomic_pool_q3', 'atomic_pool_q4'];
  const NODE_ELEMENTS = ['C', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I'];
  const NODE_FEATURES = NODE_ELEMENTS.map(e => 'is_' + e).concat(['is_other', 'aromatic', 'charge', 'hcount',
    'degree', 'pi_centre', 'auxochrome']);

  function molecularDescriptor(analysis, solventClass) {
    const c = analysis.element_counts, get = k => c[k] || 0;
    return {n_C: get('C'), n_H: get('H'), n_N: get('N'), n_O: get('O'), n_S: get('S'), n_P: get('P'),
      n_halogen: get('F') + get('Cl') + get('Br') + get('I'), heavy_atoms: analysis.heavy_atoms, ring_rank: analysis.ring_rank,
      double_bonds: analysis.double_bonds, triple_bonds: analysis.triple_bonds, aromatic_bonds: analysis.aromatic_bonds,
      pi_atoms: analysis.pi_atoms, pi_fraction: analysis.heavy_atoms ? analysis.pi_atoms / analysis.heavy_atoms : 0,
      largest_pi_system: analysis.largest_pi_system, pi_systems: analysis.pi_systems, auxochrome_atoms: analysis.auxochrome_atoms,
      largest_extended_system: analysis.largest_extended_system, carbonyl_groups: analysis.carbonyl_groups,
      nitrile_groups: analysis.nitrile_groups, azo_groups: analysis.azo_groups, nitro_groups: analysis.nitro_groups,
      charged_atoms: analysis.charged_atoms, fragments: analysis.fragments,
      solvent_protic: solventClass === 'protic' ? 1 : 0, solvent_aprotic: solventClass === 'aprotic' ? 1 : 0,
      solvent_nonpolar: solventClass === 'nonpolar' ? 1 : 0};
  }

  // Graph tensors for set/graph architectures: one row per heavy atom, undirected edge list.
  function graphTensors(graph, analysis) {
    const degree = graph.atoms.map(() => 0);
    for (const b of graph.bonds) { degree[b.a]++; degree[b.b]++; }
    const nodes = graph.atoms.map((a, i) => NODE_ELEMENTS.map(e => (a.element === e ? 1 : 0)).concat([
      NODE_ELEMENTS.indexOf(a.element) < 0 ? 1 : 0, a.aromatic ? 1 : 0, a.charge, a.hcount || 0, degree[i],
      analysis.pi_flags[i] ? 1 : 0, analysis.auxochrome_flags[i] ? 1 : 0]));
    return {nodes, elements: graph.atoms.map(a => a.element), edges: graph.bonds.map(b => [b.a, b.b])};
  }

  // Summary of one predicted atomic line-strength profile (atomic grid).
  function profileSummary(profile, grid) {
    const c = S.grid.centers(grid);
    const total = profile.reduce((s, v) => s + Math.max(0, v), 0);
    const quarter = Math.floor(profile.length / 4);
    const band = q => profile.slice(q * quarter, (q + 1) * quarter).reduce((s, v) => s + v, 0) / quarter;
    return {atomic_pool_strength: total / profile.length,
      atomic_pool_centroid_nm: total > 0 ? profile.reduce((s, v, i) => s + Math.max(0, v) * c[i], 0) / total : (grid.start + grid.stop) / 2,
      atomic_pool_q1: band(0), atomic_pool_q2: band(1), atomic_pool_q3: band(2), atomic_pool_q4: band(3)};
  }
  // Count-weighted mean of per-element summaries over every atom (implicit H included).
  function poolAtomic(elementCounts, summaries) {
    const out = {};
    for (const k of ATOMIC_POOL) out[k] = 0;
    let n = 0;
    for (const element of Object.keys(elementCounts)) {
      const count = elementCounts[element];
      if (!count) continue;
      const s = summaries[element];
      if (!s) throw new Error('No atomic-model summary for element ' + element);
      for (const k of ATOMIC_POOL) out[k] += count * s[k];
      n += count;
    }
    if (n) for (const k of ATOMIC_POOL) out[k] /= n;
    return out;
  }

  // One molecule -> every input form used by the catalogue (shared by trainer and scenario).
  // `summaries` (element -> atomic-model profile summary) is optional; without it the
  // cascade features are absent and only non-cascade architectures can consume the record.
  function moleculeInputs(smiles, solventClass, summaries) {
    const graph = S.smiles.parse(smiles), analysis = S.smiles.analyze(graph);
    const descriptor = molecularDescriptor(analysis, solventClass);
    const pooled = summaries ? poolAtomic(analysis.element_counts, summaries) : null;
    return {analysis, descriptor, pooled, x: Object.assign({}, descriptor, pooled || {}),
      graph: graphTensors(graph, analysis)};
  }

  function vector(record, names) {
    return names.map(name => {
      const v = record[name];
      if (!Number.isFinite(v)) throw new Error('Missing or non-finite feature ' + name);
      return v;
    });
  }

  S.features = Object.freeze({ATOMIC_FEATURES, MOLECULAR_DESCRIPTORS, ATOMIC_POOL, NODE_ELEMENTS, NODE_FEATURES,
    atomicFeatures, molecularDescriptor, graphTensors, profileSummary, poolAtomic, moleculeInputs, vector});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.features;
})(globalThis);
