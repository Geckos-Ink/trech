// Minimal SMILES reader -> explicit molecular graph, plus topological graph descriptors.
//
// Implicit hydrogens follow the SMILES specification's organic-subset valence table (a
// syntax rule of the notation, not a chemistry model). Descriptors are pure graph counts:
// ring rank, bond orders, and connected components of atoms that carry multiple/aromatic
// bonds ("pi centres"). No Hückel, Woodward-Fieser or other spectroscopic rule is applied.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  const ORGANIC = {B: [3], C: [4], N: [3, 5], O: [2], P: [3, 5], S: [2, 4, 6], F: [1], Cl: [1], Br: [1], I: [1]};
  const AROMATIC = {b: 'B', c: 'C', n: 'N', o: 'O', p: 'P', s: 'S', se: 'Se', as: 'As'};
  const BOND = {'-': 1, '=': 2, '#': 3, '$': 4, ':': 1.5, '/': 1, '\\': 1};
  const LONE_PAIR = {N: true, O: true, S: true, F: true, Cl: true, Br: true, I: true, P: true, Se: true};

  function parse(smiles) {
    const text = String(smiles || '').trim();
    if (!text) throw new Error('empty SMILES');
    const atoms = [], bonds = [], rings = {}, stack = [];
    let prev = -1, pendingBond = null, i = 0;
    function addAtom(atom) {
      const index = atoms.length;
      atoms.push(atom);
      if (prev >= 0) addBond(prev, index, pendingBond);
      pendingBond = null;
      prev = index;
    }
    function addBond(a, b, symbol) {
      const both = atoms[a].aromatic && atoms[b].aromatic;
      const order = symbol ? BOND[symbol] : (both ? 1.5 : 1);
      bonds.push({a, b, order, aromatic: order === 1.5});
    }
    while (i < text.length) {
      const ch = text[i];
      if (ch === '(') { if (prev < 0) throw new Error('branch before atom in ' + text); stack.push(prev); i++; continue; }
      if (ch === ')') { if (!stack.length) throw new Error('unbalanced ) in ' + text); prev = stack.pop(); i++; continue; }
      if (ch === '.') { prev = -1; pendingBond = null; i++; continue; }
      if (BOND[ch] !== undefined) { pendingBond = ch; i++; continue; }
      if (ch === '%' || (ch >= '0' && ch <= '9')) {
        let label;
        if (ch === '%') { label = text.substr(i + 1, 2); i += 3; } else { label = ch; i++; }
        if (prev < 0) throw new Error('ring closure before atom in ' + text);
        if (rings[label]) {
          const open = rings[label];
          addBond(open.atom, prev, pendingBond || open.bond);
          delete rings[label];
        } else rings[label] = {atom: prev, bond: pendingBond};
        pendingBond = null;
        continue;
      }
      if (ch === '[') {
        const close = text.indexOf(']', i);
        if (close < 0) throw new Error('unclosed [ in ' + text);
        const m = /^(\d+)?(se|as|[A-Z][a-z]?|[bcnops])(@{1,2}(?:TH\d|AL\d|SP\d|TB\d+|OH\d+)?)?(H\d*)?([+-]+\d*)?(?::\d+)?$/.exec(text.slice(i + 1, close));
        if (!m) throw new Error('unsupported bracket atom ' + text.slice(i, close + 1));
        const aromatic = AROMATIC[m[2]] !== undefined && m[2] === m[2].toLowerCase();
        let charge = 0;
        if (m[5]) {
          const sign = m[5][0] === '+' ? 1 : -1;
          const digits = m[5].replace(/[+-]/g, '');
          charge = sign * (digits ? Number(digits) : m[5].length);
        }
        addAtom({element: aromatic ? AROMATIC[m[2]] : m[2], aromatic, charge, isotope: m[1] ? Number(m[1]) : null,
          hcount: m[4] ? (m[4].length > 1 ? Number(m[4].slice(1)) : 1) : 0, bracket: true});
        i = close + 1;
        continue;
      }
      const two = text.substr(i, 2);
      if (two === 'Cl' || two === 'Br') { addAtom({element: two, aromatic: false, charge: 0, isotope: null, hcount: null, bracket: false}); i += 2; continue; }
      if (ORGANIC[ch]) { addAtom({element: ch, aromatic: false, charge: 0, isotope: null, hcount: null, bracket: false}); i++; continue; }
      if (AROMATIC[ch]) { addAtom({element: AROMATIC[ch], aromatic: true, charge: 0, isotope: null, hcount: null, bracket: false}); i++; continue; }
      throw new Error('unsupported SMILES token "' + ch + '" in ' + text);
    }
    if (stack.length) throw new Error('unbalanced ( in ' + text);
    if (Object.keys(rings).length) throw new Error('unclosed ring bond in ' + text);
    // Implicit hydrogens for organic-subset atoms (SMILES valence table).
    const degreeSum = atoms.map(() => 0), aromaticBonds = atoms.map(() => 0);
    for (const b of bonds) {
      for (const k of [b.a, b.b]) {
        if (b.aromatic) aromaticBonds[k]++; else degreeSum[k] += b.order;
      }
    }
    atoms.forEach((atom, k) => {
      if (atom.hcount !== null) return;
      const used = degreeSum[k] + aromaticBonds[k] + (atom.aromatic && aromaticBonds[k] ? 1 : 0);
      const allowed = ORGANIC[atom.element] || [];
      const target = allowed.find(v => v >= used);
      atom.hcount = target === undefined ? 0 : Math.max(0, Math.round(target - used));
    });
    return {smiles: text, atoms, bonds};
  }

  function components(n, edges) {
    const parent = Array.from({length: n}, (_, i) => i);
    const find = x => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
    for (const [a, b] of edges) { const ra = find(a), rb = find(b); if (ra !== rb) parent[ra] = rb; }
    return parent.map((_, i) => find(i));
  }
  function largestGroup(labels, include) {
    const sizes = {};
    labels.forEach((l, i) => { if (include[i]) sizes[l] = (sizes[l] || 0) + 1; });
    const values = Object.keys(sizes).map(k => sizes[k]);
    return {largest: values.length ? Math.max.apply(null, values) : 0, count: values.length};
  }

  function analyze(graph) {
    const n = graph.atoms.length;
    const counts = {H: 0};
    graph.atoms.forEach(a => { counts[a.element] = (counts[a.element] || 0) + 1; counts.H += a.hcount || 0; });
    const neighbours = graph.atoms.map(() => []);
    for (const b of graph.bonds) { neighbours[b.a].push({atom: b.b, bond: b}); neighbours[b.b].push({atom: b.a, bond: b}); }
    const pi = graph.atoms.map((a, i) => a.aromatic || neighbours[i].some(e => e.bond.order >= 1.5));
    const piEdges = graph.bonds.filter(b => pi[b.a] && pi[b.b]).map(b => [b.a, b.b]);
    const piGroups = largestGroup(components(n, piEdges), pi);
    // Lone-pair heteroatoms directly attached to a pi centre (auxochrome positions, topologically).
    const aux = graph.atoms.map((a, i) => !pi[i] && !!LONE_PAIR[a.element] && neighbours[i].some(e => pi[e.atom]));
    const extended = pi.map((p, i) => p || aux[i]);
    const extEdges = graph.bonds.filter(b => extended[b.a] && extended[b.b]).map(b => [b.a, b.b]);
    const extGroups = largestGroup(components(n, extEdges), extended);
    const allLabels = components(n, graph.bonds.map(b => [b.a, b.b]));
    const fragmentCount = new Set(allLabels).size;
    const orderCount = o => graph.bonds.filter(b => b.order === o).length;
    const has = (i, element, order) => neighbours[i].some(e => graph.atoms[e.atom].element === element && e.bond.order === order);
    let carbonyl = 0, nitrile = 0, azo = 0, nitro = 0;
    graph.atoms.forEach((a, i) => {
      if (a.element === 'C' && has(i, 'O', 2)) carbonyl++;
      if (a.element === 'C' && has(i, 'N', 3)) nitrile++;
      if (a.element === 'N' && has(i, 'N', 2)) azo++;
      if (a.element === 'N' && neighbours[i].filter(e => graph.atoms[e.atom].element === 'O').length >= 2 && has(i, 'O', 2)) nitro++;
    });
    return {atom_count: n, heavy_atoms: graph.atoms.filter(a => a.element !== 'H').length, element_counts: counts,
      ring_rank: graph.bonds.length - n + fragmentCount, fragments: fragmentCount,
      single_bonds: orderCount(1), double_bonds: orderCount(2), triple_bonds: orderCount(3), aromatic_bonds: orderCount(1.5),
      aromatic_atoms: graph.atoms.filter(a => a.aromatic).length, pi_atoms: pi.filter(Boolean).length,
      largest_pi_system: piGroups.largest, pi_systems: piGroups.count, auxochrome_atoms: aux.filter(Boolean).length,
      largest_extended_system: extGroups.largest, carbonyl_groups: carbonyl, nitrile_groups: nitrile,
      azo_groups: azo / 2, nitro_groups: nitro, charged_atoms: graph.atoms.filter(a => a.charge !== 0).length,
      pi_flags: pi, auxochrome_flags: aux};
  }

  S.smiles = Object.freeze({parse, analyze});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.smiles;
})(globalThis);
