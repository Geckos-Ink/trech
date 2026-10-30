# JavaScript scenario bundles

Every shipped scenario has its own folder under `examples/scenarios/<name>/`:

| File | Responsibility |
| --- | --- |
| `<name>.js` | Materials, geometry, physical inputs, interactions, inference, state evolution and engine hooks |
| `<name>.view.js` | Recorded-state presentation, visualization tags, colors, legends, HUD, display clocks and render surfaces |
| `<name>.validation.js` | Expected behavior, comparison references, numerical acceptance predicates and output checks |
| `<name>.ui.js` | Typed parameter definitions, documentation, bounds, units, choices and optional Studio panel/process descriptions |

Reusable TRECH JavaScript modules live in `js/`; committed data modules/models stay in `data/`.
Intentional include-error fixtures live in `tests/fixtures/js/`. There are 63 shipped scenario
bundles. A wrapper such as `molecular_01_ethane` still includes the shared `molecular_series`
scenario, so it inherits that scenario's companion definitions.

Run or inspect the physics entry point:

```sh
build/dev/trech inspect examples/scenarios/h2o_fluid/h2o_fluid.js
build/dev/trech run examples/scenarios/h2o_fluid/h2o_fluid.js \
  --param temperature_k=300 --output build/out_h2o
python3 scripts/validate_scenario.py examples/scenarios/h2o_fluid/h2o_fluid.js build/out_h2o
```

The ordinary C++ `JsRuntime` loads existing companions in order: UI, view, validation, then the
physics entry point. This applies equally to a CLI root, library evaluation and `TRECH_INCLUDE`.
Relative includes and JSON reads resolve against the currently evaluated source. Each evaluated
file appears in `trech inspect`'s `authoring.sources`, with the root first. A companion syntax or
execution error retains its filename and stack. Single-file user experiments remain supported;
companions are optional for them. Old `examples/experiments/*.js` paths have been removed.

UI factories declare parameters lazily, preserving dependencies on physics constants and imported
modules without duplicating defaults. For example, `example.ui.js` can contain:

```js
TRECH_PARAMETERS({
  temperature_k: function() {
    return {type: "number", default: 293.15, min: 273.15, max: 373.15,
      unit: "K", label: "Temperature", group: "Environment",
      description: "Initial bath temperature."};
  }
});
globalThis.TRECH_UI_DESCRIPTOR = function() {
  globalThis.TRECH_STUDIO = {schema: "trech_studio_v1", title: "Example",
    panels: {options: true, processes: true}};
};
```

The physics script reads `const temperatureK = TRECH_PARAMETER("temperature_k");`.
The same C++ `TRECH_VALUE` validator enforces type/range/choices and resolves `--param` in CLI,
library and Studio use. Existing inline `TRECH_VALUE.*` declarations remain supported. Each
bundle's saved UI descriptor runs after its physics script, allowing process descriptions to
reference its compiled plan. Nested descriptors run before the parent descriptor.

Views register functions in `TRECH_VIEWS["example"]`. Physics hooks pass recorded state to them
when emitting material/fluid frames. Shared physics and comparison solvers remain in `js/`.
Rendering functions preserve existing physical clocks, RNG calls and emitted fields; a display
color, glyph, surface or authored layout does not become a Geant4 prediction by changing files.
Physical optics and measured/inferred response calculations remain in the physics source.
A scenario with no authored display overrides has an empty view registry and uses the viewer's
ordinary defaults. Studio lists entry points in its browser and exposes companions in the source
editor through the engine's source inventory. Run remains bound to the physics root.

Validation companions register JSON metadata in `TRECH_VALIDATIONS["example"]` and numerical
predicates/reference factories in `TRECH_CHECKS["example"]`. Predicates retain the original
summary fields and tolerances. They grade observed state; they do not advance it. Optics comparison
references still enter their existing config fields, preserving their provenance/hash contract.
`authoring.validation` exposes the JSON declarations outside physics config.

`scripts/validate_scenario.py` checks a supplied run against the declared output contract (completed
run, positive event count and no dropped hook emits). Missing output fails. These checks establish
output integrity only. Family-specific numerical validation remains in the existing
`tools/validation/trech_validation/cases.py` suite and dedicated `scripts/validate_*.py` tools;
embedded acceptance predicates now live beside the scenario in its validation file. A source move
does not add missing experimental evidence or close an existing physics gap. General export of
all Python family validators as standalone declarative checks remains tracked in both roadmaps.

UI descriptors and validation metadata do not enter physics config. Existing rendering tags and
comparison references retain their existing config serialization. Changing a resolved physical
parameter still changes config/hash as before. Source locations are inventoried; source content
is not newly embedded in run provenance. Existing media sidecars/native screenshot manifests
retain their historical source identities; future deliberate captures use the new paths.
