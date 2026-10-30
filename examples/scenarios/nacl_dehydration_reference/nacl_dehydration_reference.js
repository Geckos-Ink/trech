// Validation fixture, not a validated crystallization prediction or metal temper model.
TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_crystallization_reference.js");
const side = TRECH_PARAMETER("lattice_side");
const ticks = TRECH_PARAMETER("ticks");
const water = TRECH_PARAMETER("water_parcels");
const solubility = TRECH_PARAMETER("solubility_parcels");
const probability = TRECH_PARAMETER("attachment_probability");
const drying = TRECH_PARAMETER("dehydration_fraction");
const reference = TRECH_CRYSTALLIZATION_REFERENCE.create({side, water, solubility, attachmentProbability: probability});
const interfaceFile = TRECH_PARAMETER("interface_file");
const interfaces = interfaceFile ? TRECH_INTERFACE_SEQUENCE(TRECH_READ_JSON(interfaceFile)) : null;
const scope = "Independent inventory diagnostic; assumed capacity/attachment; no spatial solution transport, physical growth prediction or calibrated microscope data bundled";

globalThis.TRECH_CONFIG = {
  run: {nEvents: interfaces ? interfaces.frames.length : ticks, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 100, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: 0.1, positionMm: [0, 0, -40], direction: [0, 0, 1]},
  materials: [{name: "nacl_reference", densityGcm3: 2.16,
    components: [{element: "Na", atoms: 1}, {element: "Cl", atoms: 1}]}],
  geometry: {volumes: [TRECH_HELPERS.geometry.boxVolume({name: "salt_probe", material: "nacl_reference", sizeMm: [10, 10, 5], scoreEdep: true}),
    TRECH_HELPERS.geometry.boxVolume({name: "water_probe", material: "G4_WATER", sizeMm: [10, 10, 5], positionMm: [0, 0, 15], scoreEdep: true})]},
  materialProbe: {enable: true, materials: ["nacl_reference", "G4_WATER"]},
  viz: TRECH_VIEWS["nacl_dehydration_reference"]["viz0"](),
  hooks: {enable: true, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 8388608,
    inputs: {reference_kind: interfaces ? "independent_measurement" : "independent_inventory_comparison", scope, side, ticks, water,
      solubility, attachment_probability: probability, dehydration_fraction: drying,
      clock: interfaces ? "physical_seconds" : "comparison_step_index", interface_sequence: interfaces,
      visual_reference: "https://commons.wikimedia.org/wiki/File:Sodium_chloride_crystals,_light_microscopy.jpg"}}
};
function emit(ctx, step, state) {
  ctx.emit("crystallization_reference", {step, inventory: state, scope,
    geant4_event_edep_mev: ctx.event.edepMeV, geant4_material: ctx.materials.nacl_reference,
    learned_prediction_available: false});
}

globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  if (interfaces) {
    const frame = interfaces.frames[ctx.event.id];
    if (!frame) return; // Extra transport events do not invent measured interface frames.
    ctx.emit("material_frame", TRECH_VIEWS.nacl_dehydration_reference.interfaceFrame(frame, interfaces));
    return;
  }
  if (ctx.event.id === 0) ctx.emit("microscope_interface_status", {
    available:false, reason:"No calibrated measured interface recording supplied; inventory trays retired",
    visual_reference:TRECH_CONFIG.hooks.inputs.visual_reference});
  if (ctx.event.id === 0) emit(ctx, 0, reference.snapshot());
  const step = ctx.event.id + 1;
  const removed = Math.round(water * drying * Math.min(1, step / (0.75 * ticks)));
  emit(ctx, step, reference.step(removed, ctx.rng));
}};
