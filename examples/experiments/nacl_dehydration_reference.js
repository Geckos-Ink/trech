// Validation fixture, not a validated crystallization prediction or metal temper model.
TRECH_INCLUDE("trech_helpers.js");
TRECH_INCLUDE("trech_crystallization_reference.js");
const side = TRECH_VALUE.integer("lattice_side", {label: "Formula-unit parcel grid", group: "Reference", default: 4, min: 2, max: 8});
const ticks = TRECH_VALUE.integer("ticks", {label: "Reference ticks", group: "Reference", default: 80, min: 20, max: 500});
const water = TRECH_VALUE.integer("water_parcels", {label: "Initial solvent parcels", group: "Reference", default: 256, min: 1, max: 4096});
const solubility = TRECH_VALUE.number("solubility_parcels", {label: "Assumed salt / solvent capacity", group: "Comparison assumptions", default: 0.45, min: 0.01, max: 10});
const probability = TRECH_VALUE.number("attachment_probability", {label: "Illustrative attachment probability", group: "Comparison assumptions", default: 0.65, min: 0, max: 1});
const drying = TRECH_VALUE.number("dehydration_fraction", {label: "Solvent removed by final hold", group: "Boundary", default: 1, min: 0, max: 1});
const reference = TRECH_CRYSTALLIZATION_REFERENCE.create({side, water, solubility, attachmentProbability: probability});
const scope = "Illustrative independent lattice-growth comparison; assumed capacity/attachment, no calibrated physical time, no Geant4-trained crystallization or metal temper prediction";
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "NaCl dehydration comparison",
  description: scope, panels: {processes: true, options: true}, processes: [
    {id: "transport", label: "NaCl / water particle transport", kind: "Geant4", description: "Homogeneous composition probes and transported event tallies; not molecular solvent dynamics"},
    {id: "growth", label: "Dehydration and connected crystal parcels", kind: "independent comparison", description: "Edit trech_crystallization_reference.js; exact Na/Cl/solvent bookkeeping, illustrative kinetics"},
    {id: "training", label: "Learned scale lift", kind: "unavailable", description: "Needs independent growth-rate / morphology data and held-out thermal-history validation before training"}]};
globalThis.TRECH_CONFIG = {
  run: {nEvents: ticks, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 100, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: 0.1, positionMm: [0, 0, -40], direction: [0, 0, 1]},
  materials: [{name: "nacl_reference", densityGcm3: 2.16,
    components: [{element: "Na", atoms: 1}, {element: "Cl", atoms: 1}]}],
  geometry: {volumes: [TRECH_HELPERS.geometry.boxVolume({name: "salt_probe", material: "nacl_reference", sizeMm: [10, 10, 5], scoreEdep: true}),
    TRECH_HELPERS.geometry.boxVolume({name: "water_probe", material: "G4_WATER", sizeMm: [10, 10, 5], positionMm: [0, 0, 15], scoreEdep: true})]},
  materialProbe: {enable: true, materials: ["nacl_reference", "G4_WATER"]},
  viz: {enable: true},
  hooks: {enable: true, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 262144,
    inputs: {reference_kind: "independent_illustrative_comparison", scope, side, ticks, water,
      solubility, attachment_probability: probability, dehydration_fraction: drying,
      clock: "comparison_step_index", parcel_pitch_mm: 2}}
};
function emit(ctx, step, state) {
  ctx.emit("crystallization_reference", {step, inventory: state, scope,
    geant4_event_edep_mev: ctx.event.edepMeV, geant4_material: ctx.materials.nacl_reference,
    learned_prediction_available: false});
  const positions = [], colors = [];
  // Solid parcels occupy connected lattice sites. Dissolved salt and solvent use
  // separated display trays: no Brownian motion or atom trajectories are invented.
  for (const p of state.occupied_sites) {positions.push(p.map(v => 2 * (v - (side - 1) / 2))); colors.push([0.9, 0.94, 1, 1]);}
  for (let i = 0; i < state.salt_dissolved; ++i) {
    positions.push([12 + (i % 8), Math.floor(i / 8) % 8, Math.floor(i / 64)]); colors.push([0.95, 0.7, 0.2, 1]);
  }
  for (let i = 0; i < state.water_liquid; ++i) {
    positions.push([-12 - (i % 8), Math.floor(i / 8) % 8, Math.floor(i / 64)]); colors.push([0.2, 0.55, 1, 0.6]);
  }
  ctx.emit("material_frame", {stream: "nacl_reference", positions_mm: positions, colors_rgba: colors,
    radii: positions.map(() => 0.42), up_axis: "y", time: step, time_unit: "step", show_geant4_scene: false,
    phase: "COMPARISON · NaCl dehydration",
    clock_text: "Step " + step + "/" + ticks + "; no calibrated physical time",
    hud_lines: ["Solvent " + state.water_liquid + "; salt " + state.salt_crystal + " solid + " + state.salt_dissolved + " dissolved"],
    legend: [{label: "Blue: solvent", color_rgba: [0.2, 0.55, 1, 1]},
      {label: "Gold: dissolved salt", color_rgba: [0.95, 0.7, 0.2, 1]},
      {label: "White: crystal parcels", color_rgba: [0.9, 0.94, 1, 1]}],
    motion_scope: scope + "; parcel positions, radii, colours and tray layout are rendering choices"});
}
globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  if (ctx.event.id === 0) emit(ctx, 0, reference.snapshot());
  const step = ctx.event.id + 1;
  const removed = Math.round(water * drying * Math.min(1, step / (0.75 * ticks)));
  emit(ctx, step, reference.step(removed, ctx.rng));
}};
