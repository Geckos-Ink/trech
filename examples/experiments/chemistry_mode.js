// Initial Chemistry workspace: authored molecular graph + live isotope-resolved
// Geant4 material response + bounded learned response. No imposed stability law.
TRECH_INCLUDE("trech_helpers.js");
TRECH_INCLUDE("../../data/molecular_series/series.js");
TRECH_INCLUDE("trech_molecular_particle.js");
TRECH_INCLUDE("trech_chemistry.js");
TRECH_INCLUDE("trech_chemistry_scene.js");
const chem = globalThis.TRECH_CHEMISTRY;
const particle = globalThis.TRECH_MOLECULAR_PARTICLE;
const preset = TRECH_VALUE.choice("preset", {default: "ethanol", group: "Chemistry",
  label: "Starting scaffold", choices: Object.keys(globalThis.TRECH_MOLECULAR_SERIES)});
const fixture = globalThis.TRECH_MOLECULAR_SERIES[preset];
const scaffold = {atoms: fixture.elements.map((element, i) => ({element,
  position: fixture.scan[0].positions_angstrom[i]})), bonds: fixture.bonds, charge: 0};
const input = TRECH_VALUE.string("structure_json", {default: JSON.stringify(scaffold), group: "Chemistry",
  label: "Structure JSON", description: "Explicit atoms, positions (angstrom), isotope massNumber and declared bonds; no automatic valence rules."});
const singleMolecule = chem.structure(JSON.parse(input));
const sceneInput = TRECH_VALUE.string("scene_json", {default: "", group: "Chemistry", label: "Multi-molecule scene JSON"});
const sceneFile = TRECH_VALUE.string("scene_file", {default: globalThis.TRECH_CHEMISTRY_SCENE_FILE || "", group: "Chemistry", label: "JSON scene file (relative to scenario)"});
if (sceneInput.trim() && sceneFile.trim()) throw new Error("Choose inline scene_json or scene_file, not both");
const spatial = globalThis.TRECH_CHEMISTRY_SCENE;
const scene = spatial.scene(sceneFile.trim() ? TRECH_READ_JSON(sceneFile) : sceneInput.trim() ? JSON.parse(sceneInput) :
  {schema: "trech_chemistry_scene_v1", molecules: [{id: "molecule_0", structure: singleMolecule}]});
const molecule = spatial.placed(scene.molecules, scene.links);
const nuclearSamples = TRECH_VALUE.integer("nuclear_samples", {default: globalThis.TRECH_CHEMISTRY_NUCLEAR_SAMPLES || 0, min: 0, max: 32, group: "Particle probe",
  description: "Independent Geant4 nuclear initial-state configurations for explicit isotopes; not time evolution."});
const reactionInput = TRECH_VALUE.string("reaction_json", {default: "", group: "Chemistry",
  label: "Reaction experiment JSON", description: "Optional explicit species structures/counts, conserved channels and learned hazard modelPath. No built-in rates."});
const plan = reactionInput.trim() ? chem.reaction(JSON.parse(reactionInput)) : null;
const mode = TRECH_VALUE.choice("mode", {default: "predictive", choices: ["predictive", "strict"], group: "Chemistry"});
const energyEv = TRECH_VALUE.number("photon_energy_ev", {default: 3000, min: 1000, max: 30000, group: "Particle probe", unit: "eV"});
const density = TRECH_VALUE.number("proxy_density_gcm3", {default: 1, min: 0.000001, max: 30, group: "Particle probe",
  label: "Declared transport proxy density", unit: "g/cm³"});
const events = TRECH_VALUE.integer("events", {default: 16, min: 1, max: 10000, group: "Particle probe"});
if (events < scene.frames.length) throw new Error("events must cover all supplied scene frames");
const naturalCHNO = molecule.atoms.every(a => !a.massNumber && ["H", "C", "N", "O"].indexOf(a.element) >= 0);
const particleSupported = naturalCHNO && molecule.charge === 0;
const models = particleSupported ? particle.models() : [];
if (plan && plan.modelPath) models.push({name: "chemistry_reaction", path: plan.modelPath, scale: "nano"});
const materials = [{name: "molecular_probe", densityGcm3: density, components: chem.components(molecule)}];
if (plan) for (const s of plan.species)
  materials.push({name: "chem_species_" + s.name, densityGcm3: density, components: chem.components(s.structure)});
globalThis.TRECH_CONFIG = {
  detector: {worldSizeMm: 20, worldMaterial: "molecular_probe"},
  physics: {list: "QBBC_LIV"}, beam: {particle: "gamma", energyMeV: energyEv / 1e6, direction: [0, 0, 1]},
  run: {nEvents: events, seed: 20261027, threads: 1}, determinism: {mode}, materials, models,
  viz: {enable: true, maxTrajectories: 16},
  materialProbe: {enable: true, includeIsotopes: true, materials: materials.map(m => m.name),
    interactions: {particle: "gamma", processes: ["phot", "compt", "Rayl"], energiesMeV: [energyEv / 1e6]}},
  hooks: {maxEmitsPerCallback: 8, maxEmitPayloadBytes: 4194304,
    inputs: {schema: "trech_chemistry_inputs_v1", structure: molecule, scene, reaction: plan,
      scaffold_source: "Authored/editable coordinates; preset originates in independent RHF/STO-3G scan, not Geant4"}}
};
if (nuclearSamples) globalThis.TRECH_CONFIG.materialProbe.nuclearSamples = {configurations: nuclearSamples, seed: 20261027};
const state = plan ? Object.fromEntries(plan.species.map(s => [s.name, [s.count]])) : null;
function atomFacts(s, probe) {
  if (!probe || !probe.available) throw new Error("Missing live Geant4 material probe");
  return s.atoms.map(atom => {
    const row = probe.elements.find(e => e.symbol === atom.element && (atom.massNumber ?
      !e.natural_isotopic_composition && e.isotopes.length === 1 && e.isotopes[0].a === atom.massNumber :
      e.natural_isotopic_composition));
    if (!row) throw new Error("Missing isotope/element in live Geant4 probe");
    return {element: atom.element, z: row.z, requested_mass_number: atom.massNumber || null,
      neutrons: atom.massNumber ? atom.massNumber - row.z : null,
      atomic_mass_amu: row.atomic_mass_amu, isotopes: row.isotopes,
      position: atom.position};
  });
}
function emitStructure(ctx) {
  const facts = atomFacts(molecule, ctx.materials.molecular_probe);
  const electrons = facts.reduce((sum, a) => sum + a.z, 0) - molecule.charge;
  if (electrons < 0) throw new Error("Net charge exceeds nuclear proton count");
  const response = particleSupported ? particle.infer(ctx, {elements: molecule.atoms.map(a => a.element)}, energyEv) : null;
  const capabilities = {
    electron_density: {available: scene.frames.some(f => f.fields.some(field => field.particle === "electron" &&
      (mode !== "strict" || field.source.kind !== "inferred"))), reason:
      "Only explicitly supplied density fields are shown, with their source; no molecular wavefunction is synthesized by Geant4 transport"},
    nuclear_initial_states: {available: ctx.materials.molecular_probe.elements.some(e => e.nuclear_samples && e.nuclear_samples.available),
      reason: "Geant4 independent nuclear initial-state samples for explicit isotopes; not wavefunctions or physical time evolution"},
    particle_response: {available: !!response, reason: response ? response.scope : mode === "strict" ?
      "Strict mode disables learned inference" : "No isotope/ion/non-CHNO particle model validated for this structure"},
    stability: {available: false, reason: "No validated geometry-conditioned stability model attached"},
    polarization: {available: false, reason: "No transferable electronic-response model attached"},
    reactions: {available: false, model_attached: !!(plan && plan.modelPath), reason:
      "See reaction-step results for operator execution. Atomistic mechanisms and supplied-model validation are not established by this workspace"}
  };
  ctx.emit("chemistry_state", {schema: "trech_chemistry_state_v1", structure: molecule, atoms: facts,
    electron_count: electrons, mode, capabilities, particle_response: response,
    expected_particle_model_sha256: response ? particle.data.model_sha256 : null,
    geant4_material: ctx.materials.molecular_probe,
    scene, geometry_source: "authored coordinates and declared bonds; no inferred equilibrium or bond stability",
    transport_scope: "homogeneous composition proxy, not atom-resolved molecular geometry",
    reaction_plan: plan});
  const palette = {H: [0.9, 0.94, 1, 1], C: [0.32, 0.39, 0.48, 1], N: [0.37, 0.48, 1, 1], O: [1, 0.34, 0.28, 1]};
  const frame = globalThis.TRECH_HELPERS.observer.frame({positions: molecule.atoms.map(a => a.position),
    colors: molecule.atoms.map(a => palette[a.element] || [0.65, 0.8, 0.6, 1]),
    radii: molecule.atoms.map(a => a.element === "H" ? 0.16 : 0.25), bonds: molecule.bonds.map(b => b.slice(0, 2)),
    lengthUnit: "angstrom", upAxis: "y", physicalTimeS: 0, phase: "Chemistry: authored structure",
    clockText: "Structure inspection; no molecular dynamics",
    motionScope: "Authored coordinates/bonds; display radii/colors are representation. Stability and polarization unavailable."});
  frame.stream = "chemistry_structure";
  frame.molecule_ids = molecule.molecule_ids;
  ctx.emit("material_frame", frame);
}
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    if (ctx.event.id === 0) {
      // Check every declared species through Geant4 even if no reaction model is supplied.
      if (plan) for (const s of plan.species) {
        const facts = atomFacts(s.structure, ctx.materials["chem_species_" + s.name]);
        if (facts.reduce((sum, a) => sum + a.z, 0) < s.structure.charge)
          throw new Error("Reaction species charge exceeds nuclear proton count");
      }
      emitStructure(ctx);
      const ensembles = ctx.materials.molecular_probe.elements.filter(e => e.nuclear_samples).map(e =>
        ({element: e.symbol, data: e.nuclear_samples}));
      if (ensembles.length) ctx.emit("chemistry_nuclear_ensemble", {ensembles,
        scope: "One-nucleus fm views; independent Geant4 initial states, not orbital paths or physical time"});
    }
    if (ctx.event.id < scene.frames.length) {
      const f = scene.frames[ctx.event.id];
      const visible = f.fields.filter(field => mode !== "strict" || field.source.kind !== "inferred");
      ctx.emit("quantum_frame", {schema: "trech_quantum_frame_v1", time_kind: scene.time_kind,
        cursor: f.cursor, physical_time_s: f.physical_time_s, structure: f.structure, fields: visible,
        omitted_fields: f.fields.filter(field => !visible.includes(field)).map(field => ({id: field.id, reason: "strict_inference_disabled"})),
        scope: "Supplied number-density fields and samples; no classical electron orbits or sample identities"});
    }
    if (plan) {
      const result = plan.modelPath ? ctx.react({dt: plan.dt, species: plan.species.map(s => s.name), state,
        channels: plan.channels, conservation: plan.conservation, models: ["chemistry_reaction"]}) : null;
      ctx.emit("chemistry_reaction_step", {step: ctx.event.id, inventory: state, result,
        status: mode === "strict" ? "strict_disabled" : !plan.modelPath ? "model_unavailable" : result && result.ran ? "supplied_model" : "blocked",
        physical_time_s: null, scope: "discrete inventory operator; no atomistic reaction path or calibrated physical clock"});
    }
  }
};
