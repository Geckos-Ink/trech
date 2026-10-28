// Multi-entity authoring and supplied-field validation. Geometry operations only;
// no forces, orbital templates, molecular boundary/rate laws or nuclear dynamics.
globalThis.TRECH_CHEMISTRY_SCENE = (function () {
  const chem = globalThis.TRECH_CHEMISTRY;
  function vector(v, label) {
    if (!Array.isArray(v) || v.length !== 3 || v.some(x => !Number.isFinite(x) || Math.abs(x) > 1e6))
      throw new Error(label + " requires three finite coordinates");
    return v.slice();
  }
  function molecules(raw) {
    if (!Array.isArray(raw) || !raw.length || raw.length > 64) throw new Error("Scene requires 1–64 molecules/atomic entities");
    const seen = new Set();
    const result = raw.map(m => {
      if (!m || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(m.id) || seen.has(m.id)) throw new Error("Invalid/duplicate molecule id");
      seen.add(m.id);
      return {id: m.id, structure: chem.structure(m.structure), position: vector(m.position || [0, 0, 0], "placement"),
        rotation_deg: vector(m.rotation_deg || [0, 0, 0], "rotation")};
    });
    if (result.reduce((n, m) => n + m.structure.atoms.length, 0) > 256) throw new Error("Scene atom limit is 256");
    return result;
  }
  function placed(entities, links) {
    const atoms = [], bonds = [], molecule_ids = [], offsets = {};
    let charge = 0;
    for (const m of entities) {
      offsets[m.id] = atoms.length; charge += m.structure.charge;
      const angles = m.rotation_deg.map(x => x * Math.PI / 180);
      const c = angles.map(Math.cos), s = angles.map(Math.sin);
      for (const atom of m.structure.atoms) {
        const p = atom.position;
        const x1 = p[0], y1 = c[0] * p[1] - s[0] * p[2], z1 = s[0] * p[1] + c[0] * p[2];
        const x2 = c[1] * x1 + s[1] * z1, y2 = y1, z2 = -s[1] * x1 + c[1] * z1;
        const position = [c[2] * x2 - s[2] * y2, s[2] * x2 + c[2] * y2, z2].map((x, i) => x + m.position[i]);
        atoms.push(Object.assign({}, atom, {position})); molecule_ids.push(m.id);
      }
      for (const b of m.structure.bonds) bonds.push([offsets[m.id] + b[0], offsets[m.id] + b[1]].concat(b.slice(2)));
    }
    const declared = new Set(bonds.map(b => b[0] + ":" + b[1]));
    for (const link of links || []) {
      const endpoints = [link.a, link.b].map(end => {
        const m = end && entities.find(m => m.id === end.molecule);
        if (!m || !Number.isInteger(end.atom) || end.atom < 0 || end.atom >= m.structure.atoms.length)
          throw new Error("Cross-molecule link has an unknown endpoint");
        return offsets[m.id] + end.atom;
      }).sort((a, b) => a - b);
      const key = endpoints.join(":");
      if (endpoints[0] === endpoints[1] || declared.has(key)) throw new Error("Self/duplicate scene link");
      declared.add(key);
      if (link.order !== undefined && ![1, 2, 3].includes(link.order)) throw new Error("Invalid link order");
      bonds.push(endpoints.concat(link.order === undefined ? [] : [link.order]));
    }
    return {atoms, bonds, charge, molecule_ids};
  }
  function geometryMatches(binding, expected) {
    return binding && binding.charge === expected.charge && Array.isArray(binding.atoms) && binding.atoms.length === expected.atoms.length &&
      binding.atoms.every((a, i) => a.element === expected.atoms[i].element && a.massNumber === expected.atoms[i].massNumber &&
        Array.isArray(a.position) && a.position.length === 3 && a.position.every((v, j) => Number.isFinite(v) && Math.abs(v - expected.atoms[i].position[j]) <= 1e-8));
  }
  function fields(raw, entities) {
    if (!Array.isArray(raw) || raw.length > 16) throw new Error("Frame fields must be an array with at most 16 fields");
    const seen = new Set();
    return raw.map(f => {
      if (!f || typeof f.id !== "string" || !f.id || seen.has(f.id)) throw new Error("Invalid/duplicate field id");
      seen.add(f.id);
      if (!["electron", "proton", "neutron"].includes(f.particle)) throw new Error("Unknown probability-field particle");
      if (!["angstrom", "fm"].includes(f.length_unit)) throw new Error("Probability field requires explicit angstrom/fm units");
      if (!f.source || !["quantum_reference", "geant4", "inferred", "authored"].includes(f.source.kind) ||
          typeof f.source.method !== "string" || !f.source.method) throw new Error("Field requires explicit source kind/method");
      if (!Array.isArray(f.owner_ids) || !f.owner_ids.length || new Set(f.owner_ids).size !== f.owner_ids.length ||
          f.owner_ids.some(id => !entities.some(m => m.id === id))) throw new Error("Field owners must reference scene molecule ids");
      if (!f.grid || !Array.isArray(f.grid.shape) || f.grid.shape.length !== 3 ||
          f.grid.shape.some(n => !Number.isInteger(n) || n < 2 || n > 128)) throw new Error("Field shape must have three integer dimensions in [2,128]");
      const size = f.grid.shape.reduce((a, b) => a * b, 1);
      if (size > 131072 || !Array.isArray(f.grid.values) || f.grid.values.length !== size ||
          f.grid.values.some(v => !Number.isFinite(v) || v < 0)) throw new Error("Field must contain finite non-negative density values (max 131072)");
      if (!Number.isFinite(f.grid.spacing) || f.grid.spacing <= 0 || !Number.isFinite(f.isovalue) || f.isovalue <= 0)
        throw new Error("Field spacing and isovalue must be finite and positive");
      if (typeof f.density_unit !== "string" || !f.density_unit) throw new Error("Field requires density_unit");
      const expected = placed(entities.filter(m => f.owner_ids.includes(m.id)), []);
      if (f.particle === "electron" && !geometryMatches(f.geometry, expected))
        throw new Error("Electron density geometry/isotope/charge binding differs from its placed owners; recompute the field after editing geometry");
      const samples = f.samples || [];
      if (!Array.isArray(samples) || samples.length > 8192) throw new Error("Probability sample limit is 8192");
      if (f.orbital && (f.particle !== "electron" || f.length_unit !== "angstrom" || f.density_unit !== "probability/angstrom^3" ||
          !Number.isInteger(f.orbital.index) || f.orbital.index < 1 || !Number.isFinite(f.orbital.energy_hartree) ||
          !Number.isFinite(f.orbital.occupation) || f.orbital.occupation < 0 || f.orbital.occupation > 2))
        throw new Error("Orbital fields require an index, finite Hartree energy, occupation in [0,2], and probability/angstrom^3");
      return {id: f.id, particle: f.particle, owner_ids: f.owner_ids.slice(), length_unit: f.length_unit,
        density_unit: f.density_unit, source: Object.assign({}, f.source, {externally_supplied: true}),
        geometry: f.geometry, ...(f.orbital ? {orbital: Object.assign({}, f.orbital)} : {}),
        grid: {shape: f.grid.shape.slice(), origin: vector(f.grid.origin, "field origin"), spacing: f.grid.spacing, values: f.grid.values.slice()},
        isovalue: f.isovalue, samples: samples.map(p => vector(p, "probability sample")),
        sampling_note: f.sampling_note || "Supplied ensemble points; sample index is not particle identity or time"};
    });
  }
  function electronic(raw, recordedFields, structure) {
    if (raw === undefined || raw === null) return null;
    if (!raw.source || !["quantum_reference", "inferred"].includes(raw.source.kind) || !raw.source.method ||
        !Number.isInteger(raw.electron_count) || raw.electron_count < 0 ||
        !Number.isFinite(raw.total_energy_hartree) || !Array.isArray(raw.orbitals) || !raw.orbitals.length || raw.orbitals.length > 512)
      throw new Error("Electronic structure requires a complete sourced spectrum, electron count and finite energy");
    if (!geometryMatches(raw.geometry, structure)) throw new Error("Electronic spectrum geometry binding differs from scene; recalculate the reference");
    const seen = new Set();
    let occupation = 0;
    for (const o of raw.orbitals) {
      if (!Number.isInteger(o.index) || o.index < 1 || seen.has(o.index) || !Number.isFinite(o.energy_hartree) ||
          !Number.isFinite(o.occupation) || o.occupation < 0 || o.occupation > 2) throw new Error("Invalid/duplicate orbital state");
      seen.add(o.index); occupation += o.occupation;
      if (o.field_id) {
        const f = recordedFields.find(f => f.id === o.field_id);
        if (!f || !f.orbital || f.orbital.index !== o.index || f.orbital.energy_hartree !== o.energy_hartree ||
            f.orbital.occupation !== o.occupation || f.source.kind !== raw.source.kind || !geometryMatches(f.geometry, structure))
          throw new Error("Orbital spectrum disagrees with its probability field");
      }
    }
    if (Math.abs(occupation - raw.electron_count) > 1e-8) throw new Error("Orbital occupations do not sum to the electron count");
    return Object.assign({}, raw, {source: Object.assign({}, raw.source, {externally_supplied: true}),
      ...(raw.dipole_debye ? {dipole_debye: vector(raw.dipole_debye, "dipole")} : {})});
  }
  function scene(raw) {
    if (!raw || raw.schema !== "trech_chemistry_scene_v1") throw new Error("Expected trech_chemistry_scene_v1 JSON scene");
    if (raw.length_unit !== undefined && raw.length_unit !== "angstrom") throw new Error("Molecular scene placements require angstrom units");
    const entities = molecules(raw.molecules), links = raw.links || [];
    if (!Array.isArray(links) || links.length > 1024) throw new Error("Invalid scene links");
    placed(entities, links); // endpoint validation even for a static scene
    const time_kind = raw.time_kind || "snapshot";
    if (!["snapshot", "physical", "parameter_scan"].includes(time_kind)) throw new Error("Unknown scene clock");
    const inputFrames = raw.frames || [];
    if (!Array.isArray(inputFrames) || inputFrames.length > 128 || time_kind === "snapshot" && inputFrames.length > 1)
      throw new Error("Scene supports <=128 frames; snapshots have at most one");
    let previous = -Infinity;
    const fieldSchemas = new Map();
    const frames = inputFrames.map(f => {
      const entitiesAtFrame = f.molecules ? molecules(f.molecules) : entities;
      const frameLinks = f.links || links;
      const structure = placed(entitiesAtFrame, frameLinks);
      // Canonical snapshots can be restored/exported and re-inspected verbatim.
      const cursor = time_kind === "snapshot" ? 0 : time_kind === "physical" ?
        (f.time_s === undefined ? f.cursor : f.time_s) : (f.parameter_value === undefined ? f.cursor : f.parameter_value);
      if (!Number.isFinite(cursor) || cursor < 0 || cursor <= previous) throw new Error("Frame clock must be explicit, finite, non-negative and strictly increasing");
      previous = cursor;
      const recordedFields = fields(f.fields || [], entitiesAtFrame);
      for (const field of recordedFields) {
        const schema = [field.particle, field.length_unit, field.density_unit].join(":");
        if (fieldSchemas.has(field.id) && fieldSchemas.get(field.id) !== schema)
          throw new Error("A field id cannot change its particle or units across frames");
        fieldSchemas.set(field.id, schema);
      }
      return {cursor, physical_time_s: time_kind === "physical" || time_kind === "snapshot" ? cursor : null,
        molecules: entitiesAtFrame, links: frameLinks, structure, fields: recordedFields,
        ...(f.electronic_structure ? {electronic_structure: electronic(f.electronic_structure, recordedFields, structure)} : {})};
    });
    return {schema: raw.schema, length_unit: "angstrom", molecules: entities, links,
      time_kind, frames, note: typeof raw.note === "string" ? raw.note : "Authored molecular placements/connectivity"};
  }
  return {scene, placed};
})();
