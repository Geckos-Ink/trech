# Shared TRECH JavaScript modules

Reusable authoring, inference adapters, process libraries and labelled comparison solvers live
here. They are dependencies, not runnable scenarios. `TRECH_INCLUDE` resolves their imports
relative to each module. Scenario bundles live in [`examples/scenarios/`](../examples/scenarios/).
See [the bundle contract](../docs/scenario_bundles.md).
`trech_ml.js` holds the host-neutral ML model definition/search library and registry resolver
shared with the `tools/ml` CLI ([contract](../docs/ml_models.md)).
`trech_geometry.js` (`TRECH_GEOMETRY`) generates procedural assemblies (grids, rings, layer
stacks, concentric shells) as plain engine volumes and audits them for overlaps/containment
before the config reaches Geant4; it decides no physics.
