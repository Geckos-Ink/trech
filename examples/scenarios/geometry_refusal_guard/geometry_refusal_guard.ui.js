// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"inject_defects": function() { return Object.assign({}, {
  label: "Inject geometry defects", group: "Geometry",
  description: "Adds a probe box overlapping the target by 5 mm and a volume naming an " +
    "unknown material. With geometry.refuseOn \"any\" the engine must refuse to run: one " +
    "geometry_refused provenance record, no events, no scores, exit status 1.",
  default: false
}, {type: "boolean"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = undefined;
