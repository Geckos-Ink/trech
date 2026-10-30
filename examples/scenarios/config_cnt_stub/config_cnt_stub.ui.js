// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"cnt_diameter_nm": function() { return Object.assign({}, {
  label: "CNT diameter", group: "Nanotube", unit: "nm",
  default: 3.0, min: 1.0, max: 8.0, step: 0.25
}, {type: "number"}); },
"cnt_length_nm": function() { return Object.assign({}, {
  label: "CNT length", group: "Nanotube", unit: "nm",
  default: 100.0, min: 20.0, max: 500.0, step: 10.0
}, {type: "number"}); },
"wall_count": function() { return Object.assign({}, {
  label: "Wall count", group: "Nanotube",
  default: 5, min: 1, max: 12, step: 1
}, {type: "integer"}); },
"temperature_k": function() { return Object.assign({}, {
  label: "Temperature", group: "Environment", unit: "K",
  default: 293.15, min: 250.0, max: 400.0, step: 1.0
}, {type: "number"}); },
"electron_energy_mev": function() { return Object.assign({}, {
  label: "Electron energy", group: "Source", unit: "MeV",
  default: 0.8, min: 0.05, max: 5.0, step: 0.05
}, {type: "number"}); },
"event_count": function() { return Object.assign({}, {
  label: "Sampling level", group: "Run", unit: "events",
  default: 10, min: 1, max: 1000, step: 1
}, {type: "integer"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
