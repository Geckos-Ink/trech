// Independent Euler comparison for a fixed blunt body; not a Geant4 aero prediction.
TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_euler_reference.js");
const nx = TRECH_PARAMETER("grid_x");
const ticks = TRECH_PARAMETER("ticks");
const substeps = TRECH_PARAMETER("substeps");
const mach = TRECH_PARAMETER("mach");
const pressure = TRECH_PARAMETER("pressure_pa");
const rho = TRECH_PARAMETER("density_kg_m3");
const body = TRECH_PARAMETER("body");
const field = TRECH_PARAMETER("display_field");
const ny = Math.round(nx * 0.6), dx = 0.4 / nx;
const assumptions = {nx, ny, dx, gamma: 1.4, gasConstant: 287.05, rho, pressure, mach, body};
const solver = TRECH_EULER_REFERENCE.create(assumptions);
const scope = "Independent inviscid ideal-gas Euler comparison, first-order Rusanov; no Geant4-trained aerodynamic response, viscous heating, solid heat transfer, deformation, breakage or explosion";

globalThis.TRECH_CONFIG = {
  run: {nEvents: ticks, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 600, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: 0.1, positionMm: [0, 0, -250], direction: [0, 0, 1]},
  geometry: {volumes: [TRECH_HELPERS.geometry.boxVolume({name: "body_material_probe", material: "G4_Al", sizeMm: [20, 20, 20], scoreEdep: true})]},
  materialProbe: {enable: true, materials: ["G4_AIR", "G4_Al"]},
  viz: TRECH_VIEWS["aerodynamics_reference"]["viz0"](),
  hooks: {enable: true, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 2097152,
    inputs: {reference_kind: "independent_classical_comparison", scope, assumptions, ticks, substeps,
      display_field: field, colour_scope: "Fixed comparison ratios 0.5–2.5 of inlet; display saturation does not clamp recorded numbers"}}
};
function emit(ctx) {
  const s = solver.snapshot(), inletTemperature = pressure / (rho * assumptions.gasConstant);
  ctx.emit("aerodynamics_reference", {scope, time_s: s.time_s, steps: s.steps,
    integral: s.integral, boundary_exchange: s.boundary_exchange, balance_residual: s.balance_residual,
    columns: ["x_m", "y_m", "rho_kg_m3", "vx_m_s", "vy_m_s", "pressure_pa", "temperature_k"],
    cells: s.cells.map(c => [c.x, c.y, c.rho, c.vx, c.vy, c.p, c.temperature]),
    geant4_event_edep_mev: ctx.event.edepMeV, learned_prediction_available: false});
  const values = s.cells.map(c => field === "pressure" ? c.p : field === "density" ? c.rho : c.temperature);
  const reference = field === "pressure" ? pressure : field === "density" ? rho : inletTemperature;
  const positions = s.cells.map(c => [c.x, c.y]).concat(s.solid_positions);
  ctx.emit("material_frame", TRECH_VIEWS["aerodynamics_reference"]["frame1"](dx, field, ny, positions, reference, s, scope, values));
}
globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  if (ctx.event.id === 0) emit(ctx);
  for (let i = 0; i < substeps; ++i) solver.advance();
  emit(ctx);
}};
