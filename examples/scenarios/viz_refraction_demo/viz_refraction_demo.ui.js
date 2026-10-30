// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"world_size_cm": function() { return Object.assign({}, {
  label: "World size", group: "Geometry", unit: "cm",
  description: "Full side length of the air world.",
  default: 20.0, min: 20.0, max: 40.0, step: 1.0
}, {type: "number"}); },
"slab_width_cm": function() { return Object.assign({}, {
  label: "Glass slab width", group: "Geometry", unit: "cm",
  default: 8.0, min: 7.0, max: 12.0, step: 0.5
}, {type: "number"}); },
"water_level_percent": function() { return Object.assign({}, {
  label: "Water level", group: "Geometry", unit: "%",
  description: "Water thickness as a percentage of the 4 cm glass depth.",
  default: 62.5, min: 20.0, max: 90.0, step: 2.5
}, {type: "number"}); },
"temperature_k": function() { return Object.assign({}, {
  label: "Temperature", group: "Environment", unit: "K",
  default: 293.15, min: 273.15, max: 333.15, step: 1.0
}, {type: "number"}); },
"incidence_deg": function() { return Object.assign({}, {
  label: "Beam incidence", group: "Source", unit: "deg",
  default: 35.0, min: 0.0, max: 65.0, step: 1.0
}, {type: "number"}); },
"photon_count": function() { return Object.assign({}, {
  label: "Sampling level", group: "Run", unit: "photons",
  default: 200, min: 10, max: 5000, step: 10
}, {type: "integer"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
