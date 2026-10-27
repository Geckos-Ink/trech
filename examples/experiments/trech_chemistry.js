// Authoring/data validation only. No valence, equilibrium geometry, reaction-rate
// or stability law is supplied here. C++ operators own inference and transitions.
globalThis.TRECH_CHEMISTRY = (function () {
  function integer(value, label, min, max) {
    if (!Number.isSafeInteger(value) || value < min || value > max)
      throw new Error(label + " must be an integer in [" + min + ", " + max + "]");
    return value;
  }
  function structure(raw) {
    if (!raw || !Array.isArray(raw.atoms) || raw.atoms.length < 1 || raw.atoms.length > 256)
      throw new Error("Structure requires 1–256 explicit atoms");
    const atoms = raw.atoms.map((atom, i) => {
      if (!atom || !/^[A-Z][a-z]?$/.test(atom.element)) throw new Error("Invalid element at atom " + i);
      if (!Array.isArray(atom.position) || atom.position.length !== 3 ||
          atom.position.some(v => !Number.isFinite(v) || Math.abs(v) > 1e6))
        throw new Error("Atom positions must be three finite coordinates in angstrom");
      const a = {element: atom.element, position: atom.position.slice()};
      if (atom.massNumber !== undefined) a.massNumber = integer(atom.massNumber, "massNumber", 1, 300);
      return a;
    });
    const seen = new Set();
    const bonds = (raw.bonds || []).map(b => {
      if (!Array.isArray(b) || b.length < 2 || b.length > 3) throw new Error("Bonds require [a,b,order?]");
      let a = integer(b[0], "bond index", 0, atoms.length - 1), c = integer(b[1], "bond index", 0, atoms.length - 1);
      if (a > c) { const swap = a; a = c; c = swap; }
      const key = a + ":" + c;
      if (a === c || seen.has(key)) throw new Error("Self/duplicate bonds are invalid");
      seen.add(key);
      // Existing scaffold fixtures record connectivity only. Omitted order
      // stays unknown; do not silently turn an unrecorded order into a single bond.
      return b.length === 3 ? [a, c, integer(b[2], "declared bond order", 1, 3)] : [a, c];
    });
    return {atoms, bonds, charge: integer(raw.charge === undefined ? 0 : raw.charge, "net charge", -256, 256)};
  }
  function components(s) {
    const groups = new Map();
    for (const atom of s.atoms) {
      const key = atom.element + ":" + (atom.massNumber || "natural");
      if (!groups.has(key)) groups.set(key, {element: atom.element, atoms: 0});
      const c = groups.get(key); ++c.atoms;
      if (atom.massNumber) c.massNumber = atom.massNumber;
    }
    return Array.from(groups.values());
  }
  function reaction(raw) {
    if (!raw || !Array.isArray(raw.species) || raw.species.length < 1 || raw.species.length > 32)
      throw new Error("Reaction plan requires 1–32 named species with explicit structures");
    const names = new Set();
    const species = raw.species.map(s => {
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(s.name) || names.has(s.name)) throw new Error("Invalid/duplicate species name");
      names.add(s.name);
      return {name: s.name, count: integer(s.count, "species count", 0, 1000000), structure: structure(s.structure)};
    });
    const quantities = new Map();
    for (const s of species) {
      for (const c of components(s.structure)) {
        const key = c.element + "_" + (c.massNumber || "natural");
        if (!quantities.has(key)) quantities.set(key, {});
        quantities.get(key)[s.name] = c.atoms;
      }
    }
    quantities.set("net_charge", Object.fromEntries(species.map(s => [s.name, s.structure.charge])));
    const conservation = Array.from(quantities, ([name, coefficients]) => ({name, coefficients}));
    const channelsSeen = new Set();
    if (!Array.isArray(raw.channels) || raw.channels.length < 1 || raw.channels.length > 64)
      throw new Error("Reaction plan requires 1–64 declared channels");
    const channels = raw.channels.map(c => {
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(c.name) || channelsSeen.has(c.name)) throw new Error("Invalid/duplicate channel name");
      channelsSeen.add(c.name);
      if (!c.delta || Array.isArray(c.delta) || typeof c.delta !== "object") throw new Error("Channel delta must be an object");
      const delta = {};
      for (const name of Object.keys(c.delta)) {
        if (!names.has(name)) throw new Error("Unknown species in channel delta: " + name);
        delta[name] = integer(c.delta[name], "channel delta", -1000000, 1000000);
      }
      if (!Object.values(delta).some(v => v < 0) || !Object.values(delta).some(v => v > 0))
        throw new Error("Channel must consume and produce species");
      for (const q of conservation) {
        if (species.reduce((sum, s) => sum + (q.coefficients[s.name] || 0) * (delta[s.name] || 0), 0) !== 0)
          throw new Error("Channel " + c.name + " does not conserve " + q.name);
      }
      return {name: c.name, delta};
    });
    if (raw.modelPath !== undefined && typeof raw.modelPath !== "string") throw new Error("modelPath must be a string");
    const dt = raw.dt === undefined ? 1 : raw.dt;
    if (!Number.isFinite(dt) || dt <= 0) throw new Error("Reaction dt must be positive and finite");
    // Shared context is deliberately empty: particle facts come from the engine,
    // species counts from state. No authored fallback rates/zero facts.
    return {species, channels, conservation, modelPath: raw.modelPath || "", dt};
  }
  return {structure, components, reaction};
})();
