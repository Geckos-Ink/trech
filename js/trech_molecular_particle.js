// Shared learned particle -> atom -> molecule response. No molecular potential
// or cross-section addition law is authored here; the second model learns the
// composition map from separate Geant4 mixture probes.
TRECH_INCLUDE("../data/particle_molecule/response.js");
globalThis.TRECH_MOLECULAR_PARTICLE = (function () {
  const data = globalThis.TRECH_PARTICLE_MOLECULE;
  function models() {
    return [
      {name: "particle_atomic", scale: "atomic", path: "data/particle_molecule/atomic_response.json",
        operator_role: "particle_response", element_kind: "atom_CHNO"},
      {name: "particle_molecular", scale: "nano", path: "data/particle_molecule/molecular_response.json"}
    ];
  }
  function infer(ctx, spec, energyEv) {
    if (energyEv < data.energy_min_ev || energyEv > data.energy_max_ev)
      throw new Error("Photon energy lies outside the learned particle-response range");
    const t = 2 * Math.log(energyEv / data.energy_min_ev) /
      Math.log(data.energy_max_ev / data.energy_min_ev) - 1;
    const basis = [1, t];
    for (let k = 2; k <= data.basis_order; ++k) basis.push(2 * t * basis[k - 1] - basis[k - 2]);
    const aux = {}, state = {};
    for (const process of data.processes) state[process + "_barn"] = spec.elements.map(() => 0);
    const probe = ctx.materials.molecular_probe;
    const atomicNumbers = spec.elements.map(symbol => {
      const atom = probe.elements.find(row => row.symbol === symbol);
      if (!atom || data.atomic_numbers[symbol] !== atom.z) throw new Error("Unsupported/missing live Geant4 element");
      return atom.z;
    });
    for (const el of data.elements) {
      for (let k = 0; k <= data.basis_order; ++k) {
        aux["basis_" + el + "_" + k] = atomicNumbers.map(z => z === data.atomic_numbers[el] ? basis[k] : 0);
      }
    }
    const atomic = ctx.evolve({dt: 1, state, aux,
      fields: data.processes.map(p => ({name: p + "_barn", min: 0})),
      operator_role: "particle_response", element_kind: "atom_CHNO"});
    if (!atomic) return null; // strict mode: no synthesized atom or molecular result
    if (!atomic.ran || atomic.inferenceCount !== spec.elements.length)
      throw new Error("Missing learned atom response");
    const pooled = {};
    for (const el of data.elements)
      for (const process of data.processes) pooled[el + "_" + process + "_barn"] = 0;
    for (let i = 0; i < spec.elements.length; ++i)
      for (const process of data.processes)
        pooled[spec.elements[i] + "_" + process + "_barn"] += state[process + "_barn"][i];
    const molecular = ctx.cascade(pooled, ["particle_molecular"]);
    if (!molecular || molecular.__cascade.stagesRun !== 1)
      throw new Error("Missing learned molecular response; atom outputs are required");
    const totals = data.processes.map(p => molecular["molecule_" + p + "_barn"]);
    if (totals.some(v => !Number.isFinite(v) || v <= 0)) throw new Error("Invalid molecular response");
    return {energy_ev: energyEv, atomic_state: state, atomic_trace: atomic.trace,
      atomic_inference_count: atomic.inferenceCount, pooled, sigma_barn: totals,
      molecular_trace: molecular.__cascade, geant4_trained: true,
      label_source: "Geant4 particle-interaction cross-section data (not MC tallies)",
      scope: "independent-atom CHNO photon response, 1-30 keV; not a ground-state charge/torsion prediction"};
  }
  return {models, infer, data};
})();
