// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"grid_x": function() { return Object.assign({}, {label: "Cells along flow", group: "Reference", default: 40, min: 16, max: 96}, {type: "integer"}); },
"ticks": function() { return Object.assign({}, {label: "Recorded frames", group: "Reference", default: 50, min: 5, max: 500}, {type: "integer"}); },
"substeps": function() { return Object.assign({}, {label: "CFL steps per frame", group: "Reference", default: 4, min: 1, max: 20}, {type: "integer"}); },
"mach": function() { return Object.assign({}, {label: "Inlet Mach number", group: "Boundary", default: 1.5, min: 0, max: 3}, {type: "number"}); },
"pressure_pa": function() { return Object.assign({}, {label: "Inlet pressure", group: "Boundary", unit: "Pa", default: 101325, min: 1000, max: 300000}, {type: "number"}); },
"density_kg_m3": function() { return Object.assign({}, {label: "Inlet density", group: "Boundary", unit: "kg/m³", default: 1.225, min: 0.1, max: 5}, {type: "number"}); },
"body": function() { return Object.assign({}, {label: "Fixed blunt obstacle", group: "Boundary", default: true}, {type: "boolean"}); },
"display_field": function() { return Object.assign({}, {label: "Recorded colour field", group: "Display", default: "temperature", choices: ["temperature", "pressure", "density"]}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Aerodynamics comparison",
  description: scope, panels: {processes: true, options: true}, processes: [
    {id: "transport", label: "Air / aluminium particle transport", kind: "Geant4", description: "Separate material/energy-deposition probes; their tallies do not calibrate this comparison solver"},
    {id: "euler", label: "Compressible flow and gas temperature", kind: "independent comparison", description: "Edit trech_euler_reference.js; CFL steps, wall reflections, flux balance, positive density/pressure"},
    {id: "training", label: "Learned aerodynamic scale lift", kind: "unavailable", description: "Needs particle-derived training, independent flow anchors, mesh convergence and held-out geometries/conditions"}]};
};
