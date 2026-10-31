// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"particle_count_factor": function() { return {type:"number", default:1, min:.25, max:4, step:.25,
  label:"Display particle count", group:"Particles and sampling", unit:"×",
  description:"Scales water/pentane representatives and vapor tracers (balanced: 260 + 180 liquid representatives). Representation only; does not add Geant4 events or improve the cascade model. Requires a rerun to emit more points."}; }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
