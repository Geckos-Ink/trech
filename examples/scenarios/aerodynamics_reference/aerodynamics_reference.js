// Independent Euler comparison for a fixed blunt body; not a Geant4 aero prediction.
TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_euler3d_reference.js");
const nx = TRECH_PARAMETER("grid_x");
const ticks = TRECH_PARAMETER("ticks");
const substeps = TRECH_PARAMETER("substeps");
const mach = TRECH_PARAMETER("mach");
const pressure = TRECH_PARAMETER("pressure_pa");
const rho = TRECH_PARAMETER("density_kg_m3");
const body = TRECH_PARAMETER("body");
const field = TRECH_PARAMETER("display_field");
const display = Object.fromEntries(['display_mode','slice_axis','slice_fraction','opacity','isovalue_ratio','camera_yaw','camera_pitch','gradient_low_ratio','gradient_high_ratio']
  .map(name => [name,TRECH_PARAMETER(name)]));
if (!(display.gradient_high_ratio > display.gradient_low_ratio)) throw new Error("Gradient upper range must exceed lower range");
const ny = Math.round(nx * 0.6), nz = Math.max(8, Math.round(nx * 0.4)), dx = 0.4 / nx;
const assumptions = {nx, ny, nz, dx, gamma: 1.4, gasConstant: 287.05, rho, pressure, mach, body};
const solver = TRECH_EULER3D_REFERENCE.create(assumptions);
const scope = "Independent 3D inviscid ideal-gas Euler comparison, first-order Rusanov; no Geant4-trained aerodynamic response, viscous heating, solid heat transfer, deformation, breakage or explosion";

globalThis.TRECH_CONFIG = {
  run: {nEvents: ticks, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 600, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: 0.1, positionMm: [0, 0, -250], direction: [0, 0, 1]},
  geometry: {volumes: [TRECH_HELPERS.geometry.boxVolume({name: "body_material_probe", material: "G4_Al", sizeMm: [20, 20, 20], scoreEdep: true})]},
  materialProbe: {enable: true, materials: ["G4_AIR", "G4_Al"]},
  viz: TRECH_VIEWS["aerodynamics_reference"]["viz0"](),
  hooks: {enable: true, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 4194304,
    inputs: {reference_kind: "independent_classical_comparison", scope, assumptions, ticks, substeps,
      display_field: field, display, colour_scope: "Authored inlet-relative scalar transfer; display saturation does not clamp recorded numbers"}}
};
function emit(ctx) {
  const s = solver.snapshot(), inletTemperature = pressure / (rho * assumptions.gasConstant);
  ctx.emit("aerodynamics_reference", {scope, time_s: s.time_s, steps: s.steps,
    integral: s.integral, boundary_exchange: s.boundary_exchange, balance_residual: s.balance_residual,
    columns: ["x_m", "y_m", "z_m", "rho_kg_m3", "vx_m_s", "vy_m_s", "vz_m_s", "pressure_pa", "temperature_k"],
    cells: s.cells.map(c => [c.x, c.y, c.z, c.rho, c.vx, c.vy, c.vz, c.p, c.temperature]),
    geant4_event_edep_mev: ctx.event.edepMeV, learned_prediction_available: false});
  const values = s.cells.map(c => field === "pressure" ? c.p : field === "density" ? c.rho : c.temperature);
  const reference = field === "pressure" ? pressure : field === "density" ? rho : inletTemperature;
  const positions = s.solid_positions;
  ctx.emit("material_frame", TRECH_VIEWS["aerodynamics_reference"]["frame1"](dx, field, ny, nz, positions, reference, s, scope, values, display));
}
globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  if (ctx.event.id === 0) emit(ctx);
  for (let i = 0; i < substeps; ++i) solver.advance();
  emit(ctx);
}};
