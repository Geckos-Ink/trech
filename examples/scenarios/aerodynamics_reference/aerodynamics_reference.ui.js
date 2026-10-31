// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"grid_x": function() { return Object.assign({}, {label: "Cells along flow", group: "Reference", default: 24, min: 16, max: 40}, {type: "integer"}); },
"ticks": function() { return Object.assign({}, {label: "Recorded frames", group: "Reference", default: 50, min: 5, max: 500}, {type: "integer"}); },
"substeps": function() { return Object.assign({}, {label: "CFL steps per frame", group: "Reference", default: 4, min: 1, max: 20}, {type: "integer"}); },
"cfl": function() { return {type:"number",label:"CFL timestep factor",group:"Reference",default:0.3,min:0.01,max:0.3}; },
"duration_s": function() { return {type:"number",label:"Physical duration (0 uses step count)",group:"Reference",unit:"s",default:0,min:0,max:0.01}; },
"mach": function() { return Object.assign({}, {label: "Inlet Mach number", group: "Boundary", default: 1.5, min: 0, max: 3}, {type: "number"}); },
"pressure_pa": function() { return Object.assign({}, {label: "Inlet pressure", group: "Boundary", unit: "Pa", default: 101325, min: 1000, max: 300000}, {type: "number"}); },
"density_kg_m3": function() { return Object.assign({}, {label: "Inlet density", group: "Boundary", unit: "kg/m³", default: 1.225, min: 0.1, max: 5}, {type: "number"}); },
"body": function() { return Object.assign({}, {label: "Fixed blunt obstacle", group: "Boundary", default: true}, {type: "boolean"}); },
"display_mode": function() { return {type:"choice",label:"Scalar representation",group:"Display",default:"volume",choices:["volume","slice","surface"]}; },
"slice_axis": function() { return {type:"choice",label:"Section normal",group:"Display",default:"z",choices:["x","y","z"]}; },
"slice_fraction": function() { return {type:"number",label:"Section position",group:"Display",default:0.5,min:0,max:1}; },
"gradient_low_ratio": function() { return {type:"number",label:"Gradient lower / inlet ratio",group:"Display",default:0.5,min:0.01,max:4}; },
"gradient_high_ratio": function() { return {type:"number",label:"Gradient upper / inlet ratio",group:"Display",default:2.5,min:0.02,max:5}; },
"opacity": function() { return {type:"number",label:"Display opacity",group:"Display",default:0.15,min:0,max:1}; },
"isovalue_ratio": function() { return {type:"number",label:"Surface / inlet ratio",group:"Display",default:1.15,min:0.1,max:3}; },
"camera_yaw": function() { return {type:"number",label:"Camera azimuth",group:"Display",unit:"deg",default:35,min:-180,max:180}; },
"camera_pitch": function() { return {type:"number",label:"Camera elevation",group:"Display",unit:"deg",default:25,min:-89,max:89}; },
"camera_projection": function() { return {type:"choice",label:"Camera projection",group:"Display",default:"perspective",choices:["perspective","orthographic"]}; },
"display_field": function() { return Object.assign({}, {label: "Recorded colour field", group: "Display", default: "temperature", choices: ["temperature", "pressure", "density"]}, {type: "choice"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "3D Euler comparison",
  description: scope, panels: {processes: true, options: true}, processes: [
    {id: "transport", label: "Air / aluminium particle transport", kind: "Geant4", description: "Separate material/energy-deposition probes; their tallies do not calibrate this comparison solver"},
    {id: "euler", label: "3D compressible flow and gas temperature", kind: "independent comparison", description: "Edit trech_euler3d_reference.js; CFL steps, wall reflections, flux balance, positive density/pressure"},
    {id: "training", label: "Learned aerodynamic scale lift", kind: "unavailable", description: "Needs particle-derived training, independent flow anchors, mesh convergence and held-out geometries/conditions"}]};
};
