// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"container_size_cm": function() { return Object.assign({}, {
  label: "Container size", group: "Geometry", unit: "cm",
  default: 12.0, min: 12.0, max: 24.0, step: 0.5
}, {type: "number"}); },
"fluid_level_cm": function() { return Object.assign({}, {
  label: "Fluid level / extent", group: "Geometry", unit: "cm",
  default: 10.0, min: 4.0, max: 11.0, step: 0.5
}, {type: "number"}); },
"solute_size_cm": function() { return Object.assign({}, {
  label: "Solute seed size", group: "Geometry", unit: "cm",
  default: 2.0, min: 0.5, max: 4.0, step: 0.5
}, {type: "number"}); },
"temperature_k": function() { return Object.assign({}, {
  label: "Temperature", group: "Environment", unit: "K",
  default: 293.15, min: 273.15, max: 353.15, step: 1.0
}, {type: "number"}); },
"event_count": function() { return Object.assign({}, {
  label: "Sampling level", group: "Run", unit: "events",
  default: 1000, min: 10, max: 10000, step: 10
}, {type: "integer"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
