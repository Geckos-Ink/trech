// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"beam_tilt_deg": function() { return Object.assign({}, {
  label: "Beam incidence angle", group: "Beam", unit: "deg",
  default: 0.0, min: 0.0, max: 70.0, step: 1.0
}, {type: "number"}); },
"use_surrogate": function() { return Object.assign({}, {
  label: "Apply optics surrogate", group: "Optics", default: true
}, {type: "boolean"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
