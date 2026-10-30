// Independent Euler comparison for a fixed blunt body; not a Geant4 aero prediction.
TRECH_INCLUDE("trech_helpers.js");
TRECH_INCLUDE("trech_euler_reference.js");
const nx = TRECH_VALUE.integer("grid_x", {label: "Cells along flow", group: "Reference", default: 40, min: 16, max: 96});
const ticks = TRECH_VALUE.integer("ticks", {label: "Recorded frames", group: "Reference", default: 50, min: 5, max: 500});
const substeps = TRECH_VALUE.integer("substeps", {label: "CFL steps per frame", group: "Reference", default: 4, min: 1, max: 20});
const mach = TRECH_VALUE.number("mach", {label: "Inlet Mach number", group: "Boundary", default: 1.5, min: 0, max: 3});
const pressure = TRECH_VALUE.number("pressure_pa", {label: "Inlet pressure", group: "Boundary", unit: "Pa", default: 101325, min: 1000, max: 300000});
const rho = TRECH_VALUE.number("density_kg_m3", {label: "Inlet density", group: "Boundary", unit: "kg/m³", default: 1.225, min: 0.1, max: 5});
const body = TRECH_VALUE.boolean("body", {label: "Fixed blunt obstacle", group: "Boundary", default: true});
const field = TRECH_VALUE.choice("display_field", {label: "Recorded colour field", group: "Display", default: "temperature", choices: ["temperature", "pressure", "density"]});
const ny = Math.round(nx * 0.6), dx = 0.4 / nx;
const assumptions = {nx, ny, dx, gamma: 1.4, gasConstant: 287.05, rho, pressure, mach, body};
const solver = TRECH_EULER_REFERENCE.create(assumptions);
const scope = "Independent inviscid ideal-gas Euler comparison, first-order Rusanov; no Geant4-trained aerodynamic response, viscous heating, solid heat transfer, deformation, breakage or explosion";
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Aerodynamics comparison",
  description: scope, panels: {processes: true, options: true}, processes: [
    {id: "transport", label: "Air / aluminium particle transport", kind: "Geant4", description: "Separate material/energy-deposition probes; their tallies do not calibrate this comparison solver"},
    {id: "euler", label: "Compressible flow and gas temperature", kind: "independent comparison", description: "Edit trech_euler_reference.js; CFL steps, wall reflections, flux balance, positive density/pressure"},
    {id: "training", label: "Learned aerodynamic scale lift", kind: "unavailable", description: "Needs particle-derived training, independent flow anchors, mesh convergence and held-out geometries/conditions"}]};
globalThis.TRECH_CONFIG = {
  run: {nEvents: ticks, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 600, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: 0.1, positionMm: [0, 0, -250], direction: [0, 0, 1]},
  geometry: {volumes: [TRECH_HELPERS.geometry.boxVolume({name: "body_material_probe", material: "G4_Al", sizeMm: [20, 20, 20], scoreEdep: true})]},
  materialProbe: {enable: true, materials: ["G4_AIR", "G4_Al"]},
  viz: {enable: true},
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
  ctx.emit("material_frame", {stream: "aerodynamics_reference", time_s: s.time_s,
    positions_mm: positions.map(p => [1000 * (p[0] - 0.2), 1000 * (p[1] - ny * dx / 2), 0]),
    colors_rgba: values.map(v => {const f = Math.max(0, Math.min(1, (v / reference - 0.5) / 2)); return [f, 0.3, 1 - f, 0.9];})
      .concat(s.solid_positions.map(() => [0.7, 0.72, 0.75, 1])),
    vectors: s.cells.map(c => [c.vx * 0.02, c.vy * 0.02, 0]).concat(s.solid_positions.map(() => [0, 0, 0])),
    up_axis: "y", show_geant4_scene: false,
    phase: "COMPARISON · air " + field,
    clock_text: "t = " + (s.time_s * 1000).toFixed(3) + " ms; CFL step " + s.steps,
    hud_lines: [(field === "temperature" ? "Gas temperature" : field) + ": " + Math.min(...values).toFixed(1) +
      "–" + Math.max(...values).toFixed(1) + (field === "temperature" ? " K" : field === "pressure" ? " Pa" : " kg/m³")],
    legend: [{label: "Blue → red: 0.5–2.5× inlet", color_rgba: [0.5, 0.3, 0.5, 1]},
      {label: "Grey: fixed obstacle", color_rgba: [0.7, 0.72, 0.75, 1]}],
    motion_scope: scope + "; cell centres, display colours and velocity arrows scaled by 0.02 mm/(m/s) are representation"});
}
globalThis.TRECH_HOOKS = {onEventEnd(ctx) {
  if (ctx.event.id === 0) emit(ctx);
  for (let i = 0; i < substeps; ++i) solver.advance();
  emit(ctx);
}};
