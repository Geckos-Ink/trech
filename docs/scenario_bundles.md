# JavaScript scenario bundles

Every shipped scenario has its own folder under `examples/scenarios/<name>/`:

| File | Responsibility |
| --- | --- |
| `<name>.js` | Materials, geometry, physical inputs, interactions, inference, state evolution and engine hooks |
| `<name>.view.js` | Recorded-state presentation, visualization tags, colors, legends, HUD, display clocks and render surfaces |
| `<name>.validation.js` | Expected behavior, comparison references, numerical acceptance predicates and output checks |
| `<name>.ui.js` | Typed parameter definitions, documentation, bounds, units, choices and optional Studio panel/process descriptions |

Reusable TRECH JavaScript modules live in `js/`; committed data modules/models stay in `data/`.
Intentional include-error fixtures live in `tests/fixtures/js/`. There are 69 scenario
bundles. A wrapper such as `molecular_01_ethane` still includes the shared `molecular_series`
scenario, so it inherits that scenario's companion definitions.

Each bundle has a generated section in [the scenario purity report](TRECH_current_scenarios_purity.md):
its inference-versus-authored-law grade, static normal-path evidence, model provenance and recorded
validation results. After adding or changing a bundle, regenerate it with
`PYTHONPATH=tools/validation python3 -m trech_validation.purity`. CTest
`trech_scenario_purity_report` fails while it is stale.

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
run, positive event count and no dropped hook emits) and then any exported family gate. Missing
output fails. A companion may declare `family_case` (the `cases.py` suite case name),
`family_summary` and `family_checks`; that suite case then takes its pass/fail verdict from these
checks, read through `trech inspect` with `RUNS_DIR/trech` (or `TRECH_BIN`). Python keeps only the
report summary and measured values. The shared evaluator is
[`declarative.py`](../tools/validation/trech_validation/declarative.py):

```js
{"id": "deformable_wall_contrast", "tag": "pascal_summary",
 "field": "validation.deformable_wall_displacement", "op": "gt",
 "reference": {"tag": "pascal_summary", "field": "validation.rigid_wall_displacement"}, "scale": 10}
```

A check selects the last row of a run-relative JSONL file (`tag` reads a hook-emit payload,
`phase` filters score rows), follows a dotted `field` (`list[key=value]`, `list[2]`) and compares
with `eq ne gt ge lt le` or `within` (`abs_tol`/`rel_tol`) against `expected` or a second
selector `reference`, optionally times `scale`. Booleans compare only to booleans; an absent row,
field or reference fails unless `missing` explicitly substitutes for an absent field. Use
`--output-only` to grade output integrity alone.

List aggregates grade every element rather than the first match. `list[*]` projects over all
elements and `list[?key=value]` over every matching one; the rest of the path is read from each.
A projected field must declare `aggregate`: `count`, `min`, `max`, `max_abs`, `sum`, `mean`
(finite numbers) or `all`/`any` (booleans). Apart from `count`, an empty projection, an element
lacking the field or a wrongly typed element yields no value and fails, so a vacuous `all` never
passes. One projection per path.

`derive` computes a statistic from the selected element (or from each projected element,
before `aggregate`): `{"fn": name, "args": [...]}` where each argument is a path relative to
that element or a nested `derive`. Functions are `abs(x)`, `difference(a, b)`, `ratio(a, b)`
(b ≠ 0), `list_sum(list)`, `list_length(list)` and `chi2_sf(chi2, dof)`, the chi-square
survival probability shared with `cases.py`. An absent, non-finite or wrongly typed argument
leaves the value undefined and the check fails.

```js
{"id": "spectrum_shape_p", "phase": "run_end",
 "field": "analytic_checks[?type=compton_energy_transfer]",
 "derive": {"fn": "chi2_sf", "args": ["transfer_histogram_chi2", "transfer_histogram_dof"]},
 "aggregate": "min", "op": "ge", "expected": 0.001}
```

```js
{"id": "primaries_contained", "phase": "run_end",
 "field": "analytic_checks[?type=csda_range].primaries_transmitted",
 "aggregate": "max", "op": "eq", "expected": 0}
```

Eighteen families are exported: Pascal, osmosis, H2O molecule/cluster/bulk/diffusion,
glass-of-water waves, CNT band structure/logic gates, MR water/image line, the driver-recorded
MR tissue contrast and brain image, and the Beer-Lambert, CSDA-range, photofraction,
Klein-Nishina Compton (mean transfer, edge, χ² spectrum/angular shape, closure) and 10 MeV
pair-fraction analytic cross-checks. Their suite verdicts match the previous Python logic on the recorded Release runs.
Pascal is stricter only in failing an absent rigid-wall displacement rather than reading it as
zero; the analytic and MR gates also state the relative-error, correlation and contrast
thresholds that were previously implicit in engine flags or driver scripts.

**Multi-run sweeps.** A gate spanning several runs of one scenario (an energy or condition
sweep) is declared in `family_sweeps`: each entry names its `family_case`, ordered `runs`
(`{"id", "params"}`) and `checks`. The grader maps every run id to an output directory; each
run's recorded `--param` set (provenance `cli_args`) must equal its declared `params` exactly
(numbers compare numerically), and an unmapped run fails its checks. Every sweep check declares
one scope: `run` (one id), `each_run` (`true` or a list of ids; one record per run) or
`series_aggregate`, which selects the same value from each run (`runs` narrows the subset, in
declared order) and reduces across runs with any ordinary aggregate,
`strictly_increasing`/`strictly_decreasing`, `first_over_last`/`last_over_first` or
`argmax`/`argmin` (the id of the unique extreme run; a tie fails). `derive` also offers
`binomial_z(measured, predicted, n)`, defined for 0 < predicted < 1 and integer n > 0.

```js
{"id": "measured_peak", "runs": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end",
 "field": "analytic_checks[?type=photonuclear_fraction].geant4_measured", "aggregate": "max",
 "series_aggregate": "argmax", "op": "eq", "expected": "e23000keV"}
```

The photofraction energy sweep (10–100 keV), the pair threshold/energy sweep (1–30 MeV with
the default 10 MeV run declared as `params: {}`) and the photonuclear giant-dipole gate are
exported; on the recorded Release runs they pass 22/22, 44/44 and 27/27 checks, matching the
previous Python verdicts. `scripts/validate_scenario.py SCENARIO --sweep CASE --run ID=DIR ...`
grades one sweep outside the suite. The photonuclear final-state and model-comparison gates,
operator/reference pairs and lava/foam/chemistry multi-condition gates still evaluate in
`cases.py` and dedicated `scripts/validate_*.py` tools; tracked in the
[bundle roadmap](../AGENTS/scenarios/bundles/ROADMAP.md). A moved tolerance does not add
experimental evidence or close an existing physics gap.

UI descriptors and validation metadata do not enter physics config. Existing rendering tags and
comparison references retain their existing config serialization. Changing a resolved physical
parameter still changes config/hash as before. Source locations are inventoried; source content
is not newly embedded in run provenance. Existing media sidecars/native screenshot manifests
retain their historical source identities; future deliberate captures use the new paths.
