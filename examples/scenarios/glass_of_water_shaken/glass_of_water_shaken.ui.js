// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"particle_count_factor": function() { return {type:"number", default:1, min:.25, max:2, step:.25,
  label:"Simulation particle count", group:"Particles and sampling", unit:"×",
  description:"Approximate factor relative to the balanced fill lattice. More particles reduce spacing at fixed glass size and total water mass. Requires a rerun; convergence is not established by count alone."}; },
"render_grid_mm": function() { return {type:"number", default:2, min:.5, max:4, step:.25,
  label:"Merge surface grid spacing", group:"Rendering", unit:"mm",
  description:"Smaller spacing draws a finer water boundary. Display only; Studio surface detail can refine this further."}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
