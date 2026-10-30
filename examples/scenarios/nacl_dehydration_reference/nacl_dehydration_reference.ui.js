// Typed inputs for CLI, libraries and Studio. Factories resolve at the physics declaration.
TRECH_PARAMETERS({
"interface_file": function() { return {type:"string",label:"Calibrated interface recording (JSON)",group:"Microscopy",default:""}; },
"lattice_side": function() { return Object.assign({}, {label: "Formula-unit parcel grid", group: "Reference", default: 4, min: 2, max: 8}, {type: "integer"}); },
"ticks": function() { return Object.assign({}, {label: "Reference ticks", group: "Reference", default: 80, min: 20, max: 500}, {type: "integer"}); },
"water_parcels": function() { return Object.assign({}, {label: "Initial solvent parcels", group: "Reference", default: 256, min: 1, max: 4096}, {type: "integer"}); },
"solubility_parcels": function() { return Object.assign({}, {label: "Assumed salt / solvent capacity", group: "Comparison assumptions", default: 0.45, min: 0.01, max: 10}, {type: "number"}); },
"attachment_probability": function() { return Object.assign({}, {label: "Illustrative attachment probability", group: "Comparison assumptions", default: 0.65, min: 0, max: 1}, {type: "number"}); },
"dehydration_fraction": function() { return Object.assign({}, {label: "Solvent removed by final hold", group: "Boundary", default: 1, min: 0, max: 1}, {type: "number"}); }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "NaCl inventory / measured interfaces",
  description: scope, panels: {processes: true, options: true}, processes: [
    {id: "transport", label: "NaCl / water particle transport", kind: "Geant4", description: "Homogeneous composition probes and transported event tallies; not molecular solvent dynamics"},
    {id: "growth", label: "Inventory bookkeeping only", kind: "independent comparison", description: "Edit trech_crystallization_reference.js; exact Na/Cl/solvent bookkeeping, illustrative kinetics; no spatial animation"},
    {id: "microscopy", label: "Calibrated microscope interface data", kind: "external data required", description: "Supply interface_file with calibrated measured vertices, triangles, physical timestamps and documented validation; a photograph alone supplies no 3D time series"},
    {id: "training", label: "Learned scale lift", kind: "unavailable", description: "Needs independent growth-rate / morphology data and held-out thermal-history validation before training"}]};
};
