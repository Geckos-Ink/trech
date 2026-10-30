// Independent, illustrative lattice-growth comparison. No Geant4-trained kinetics.
// Sites represent NaCl formula-unit PARCELS; their pitch is a display choice.
(function() {
  if (globalThis.TRECH_CRYSTALLIZATION_REFERENCE) return;
  function create(o) {
    const side = o.side, total = side * side * side;
    if (!Number.isInteger(side) || side < 2 || side > 12 ||
        !Number.isInteger(o.water) || o.water < 1 || !Number.isFinite(o.solubility) || o.solubility <= 0 ||
        !Number.isFinite(o.attachmentProbability) || o.attachmentProbability < 0 || o.attachmentProbability > 1)
      throw new Error("Invalid crystallization comparison inputs");
    const occupied = new Set();
    const xyz = i => [i % side, Math.floor(i / side) % side, Math.floor(i / (side * side))];
    const index = p => p[0] + side * (p[1] + side * p[2]);
    let water = o.water;
    function step(removed, rng) {
      if (!Number.isInteger(removed) || removed < o.water - water || removed > o.water)
        throw new Error("Dehydration must be monotone and conserve solvent inventory");
      water = o.water - removed;
      const target = Math.max(0, total - Math.floor(o.solubility * water));
      for (let attempt = 0; attempt < 16 && occupied.size < target; ++attempt) {
        const frontier = new Set();
        if (!occupied.size) frontier.add(index([Math.floor(side / 2), Math.floor(side / 2), Math.floor(side / 2)]));
        for (const site of occupied) {
          const p = xyz(site);
          for (let axis = 0; axis < 3; ++axis) for (const sign of [-1, 1]) {
            const q = p.slice(); q[axis] += sign;
            if (q[axis] >= 0 && q[axis] < side && !occupied.has(index(q))) frontier.add(index(q));
          }
        }
        const candidates = Array.from(frontier).sort((a, b) => a - b);
        if (!candidates.length) break;
        if (rng.uniform() < o.attachmentProbability)
          occupied.add(candidates[Math.floor(rng.uniform() * candidates.length)]);
      }
      return snapshot();
    }
    function snapshot() {
      return {water_liquid: water, water_vapour: o.water - water,
        salt_dissolved: total - occupied.size, salt_crystal: occupied.size,
        sodium_total: total, chlorine_total: total, solvent_total: o.water,
        occupied_sites: Array.from(occupied).sort((a, b) => a - b).map(xyz)};
    }
    return {step, snapshot};
  }
  globalThis.TRECH_CRYSTALLIZATION_REFERENCE = {create};
})();
