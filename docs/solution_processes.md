# Reusable JS process libraries

Scenarios declare preparation and intent; reusable JS libraries own state, units, process
topology, conservation, stopping conditions and calls to engine operators.

```js
TRECH_INCLUDE("trech_solution_processes.js");
const experiment = TRECH_SOLUTION_PROCESSES.solution({
  water: {parcels: 256}, salt: {formula: "NaCl", parcels: 64},
  parcelAmountMol: 1e-6, temperatureK: 293.15
}).mix().heat({bathTemperatureK: 373.15})
  .evaporate({remainingFraction: 0.05})
  .crystallize({solidFraction: 0.95}).compile();
const process = experiment.create();
// hooks.inputs.recipe = experiment.plan; serialize it in the run's config/hash.
// onEventEnd(ctx): ctx.emit("process_recipe_state", process.step(ctx, 0.1));
```

`water_salt_recipe.js` is the small complete runnable authoring example. It **currently blocks**
on missing models; no salt crystallization trajectory is generated. This replaces hand-written
event schedules with a real operator execution boundary, not a scripted outcome.

## Library responsibilities

`trech_process_runtime.js` is physics-agnostic: detached state snapshots, strict-mode gating,
sequential completion, positive seconds per step, operator reports, blocked stages and validation
before committing a model's proposed state. Rejected proposals do not change recipe state;
inference/RNG already used by an operator remains counted and disclosed in its report.

`trech_solution_processes.js` is the first domain library. It explicitly supports H2O + NaCl,
with equally sized molar parcels and five conserved inventories: liquid/vapour water, original
solid salt, dissolved salt and crystal salt. Temperature uses K. Units and counts must be supplied;
there are no implicit physical concentrations, heat capacities or rates.

`trech_process_operators.js` supplies the common binding boundary for domain libraries. The
solution library uses it for all four operations, recording `operator_contracts` in its recipe
plan and thus config/hash/provenance. The bindings accept ordinary per-element JS arrays and
a scalar material kind; both continuous and integer operations can cover several elements.

| Process | Engine operation | Contextual operator role | Completion |
| --- | --- | --- | --- |
| mix | `ctx.react` solid → dissolved | `solution_dissolution` | original solid inventory depleted |
| heat | `ctx.evolve` thermal state | `solution_thermal` | within the declared bath-temperature tolerance |
| evaporate | `ctx.react` liquid → vapour | `solution_evaporation` | declared remaining solvent fraction |
| crystallize | `ctx.react` dissolved → crystal | `solution_crystallization` | declared crystal fraction |

All operators use `element_kind: "aqueous_nacl"`. Model registrations belong in ordinary
`config.models`, with the matching role/kind and scale, named IO, measured training domain and
held-out errors. Context contains live ambient Geant4 facts through the normal host, common
`parcel_amount_mol`, and the declared `bath_temperature_k`; state/aux supplies inventories and
temperature. Discrete channels use `hazard_dissolve`, `hazard_evaporate` or `hazard_precipitate`
(or the engine's existing hazard/weight interface). Thermal outputs use `d_temperature_k_dt`
or `set_temperature_k`. The library adds no model weights or synthetic training truth.

Exact H/O/Na/Cl vectors enter every discrete operation. Nonnegative safe integer inventories,
unchanged total salt/water and positive finite temperature are checked before state commit.
No operator selection or inference logic is reimplemented in Studio. Missing/ambiguous operators
or required facts block the stage. Strict mode invokes no operator or RNG. `compile()` seals
the recipe; returned metadata is detached from executable closures.

## Shared operator contracts

A library declares its operation, role/material kind, writable fields (or integer species),
read-only auxiliary arrays, scalar context, explicit units and provenance basis. For example,
this declares an interface to an externally supplied thermal operator; it supplies no heating law:

```js
TRECH_INCLUDE("trech_process_operators.js");
const thermal = TRECH_PROCESS_OPERATORS.bind({
  id: "thermal_preparation", operation: "evolve",
  operator_role: "thermal_preparation", element_kind: "declared_material",
  fields: [{name: "temperature_k", unit: "K", min: 0}],
  aux: [{name: "mass_kg", unit: "kg", min: 0}],
  context: [{name: "bath_temperature_k", unit: "K", min: 0}],
  provenance: {basis: "Engine inference; response model validation required"}
});
// Save thermal.contract with the domain plan in hooks.inputs.
// Within a predictive hook, on a runtime-owned draft:
const report = thermal.advance(ctx, draft, dtSeconds, {bath_temperature_k: 373.15});
```

`operation: "react"` instead declares `species: [{name,unit,...}]`, `channels` and
`conservation` in the existing engine topology format. Names must be unique, state and aux
disjoint, and arrays nonempty, finite and equal-length. Species, deltas, coefficients and
conservation arithmetic must fit exact JS safe integers. Topologies must conserve every declared
vector; discrete proposals must preserve each element's totals. Optional `min`/`max` bounds
apply before and after execution. Domain libraries still own their stronger invariants and
completion conditions; the solution library also requires strictly positive temperature.

Units and provenance are explicit **declarations**. Optional `model_units` checks label agreement
as described below; no unit conversion or dimensional analysis is supplied, and authored provenance
is not evidence of particle-derived training. Required declared context must be supplied:
missing values block before invocation, finite zero is retained and
undeclared extra values are not forwarded. Ambient Geant4 facts still enter through the engine;
they need not be copied into authored context. Auxiliary arrays are copied and never committed.
Writable arrays are copied, checked and replaced in the draft only on acceptance. Each returned
`contract` is detached from executable closures, so edits require a new binding.

Bound reports have `{ran, accepted, contract_id, error, engine}`. `engine` retains the ordinary
unmodified operator report, including selection, trace, inference/draw counts and trust metadata.
`ran` preserves the engine's execution verdict, while `accepted` records state acceptance;
an invalid proposal can have `ran:true, accepted:false`. Inference and RNG cannot be rolled back.

### Pinning loaded model artifacts

Optional `model_artifacts` pins the complete **loaded** catalog group with the contract's exact
role and material kind. Each pin declares a model name and its engine-reported `content_id`:

```js
const pinned = TRECH_PROCESS_OPERATORS.bind({
  ...thermal.contract,
  model_artifacts: [{name: "thermal_model", content_id: "fnv1a64:0123456789abcdef"}]
}); // Illustrative ID only: use the fingerprint of the reviewed artifact.
// Save pinned.contract in hooks.inputs with the process plan.
```

The engine computes `fnv1a64:<16 lowercase hex digits>` from the exact bytes consumed by the
loader, once at load time. Identical bytes at different paths have the same ID; whitespace
changes count. Replacing a file does not change the active model's ID or weights; a fresh load
sees the new bytes. Unloaded/failed artifacts have `content_id:null` in the catalog. JSON must
parse as one complete artifact. Catalog reads never reopen model paths.

Before invoking an operator, pinned bindings require an engine catalog and compare all loaded
models with the declared role/kind against the pins. Missing, changed, renamed or additional
matching models block before inference/RNG and leave state/clock untouched. Unloaded or unrelated
declarations do not join that group. The check is deliberately conservative: even a matching
loaded model currently missing context must be pinned. The binding does not narrow the model
list or override engine selection; required context/inputs, dependency ordering and runtime trust
checks still belong to C++. A matching fingerprint does not guarantee that the operator can run.

After a catalog check, bound reports include detached `artifacts: [{name,content_id}]` with the
observed matching group, including on a mismatch or subsequent engine rejection. Strict mode
returns before catalog access; contracts without pins do not read the catalog. Pin definitions
and returned metadata remain detached from execution closures.

These are noncryptographic byte fingerprints using the existing provenance hash algorithm,
not authenticity, collision-resistance, unit compatibility or physical-validation proofs.
Authored pins enter config/hash only when the domain plan includes the contract in `hooks.inputs`;
actual artifacts enter emitted reports when the caller records them. There is no automatic
run-wide model-artifact manifest. Cryptographic identities and a run-wide manifest remain open.

### Checking model unit labels

Portable JSON models may carry `feature_units`, using complete maps of their natural named
inputs and decoded outputs. For example, a thermal response artifact with one forcing input
and one temperature-rate output can declare:

```json
{
  "feature_units": {
    "inputs": {"forcing": "K/s"},
    "outputs": {"d_temperature_k_dt": "K/s"}
  }
}
```

Both maps must contain exactly the model's IO names, with nonblank string labels and no extra
features. Null, partial, extra or nonstring declarations fail C++ model loading; absence preserves
legacy loading with unknown units. Metadata is loaded with the weights and fingerprinted in the
same byte snapshot. Catalog entries expose detached `feature_units`, or null when unavailable.
Unannotated TorchScript artifacts also have unknown units.

A process opts into checks by declaring the expected IO union for its complete loaded role/kind
group, including intermediate and ambient feature names:

```js
const checked = TRECH_PROCESS_OPERATORS.bind({
  id: "thermal", operation: "evolve", operator_role: "thermal", element_kind: "declared_material",
  fields: [{name: "temperature_k", unit: "K"}],
  context: [{name: "forcing", unit: "K/s"}],
  model_units: {
    inputs: {forcing: "K/s"},
    outputs: {d_temperature_k_dt: "K/s"}
  },
  provenance: {basis: "Authored interface; response validation required"}
});
```

Each loaded model must have complete unit metadata, every feature must match an expected label,
and every expected feature must appear in the group's IO union. Every occurrence of an intermediate
uses the same label. Expected labels overlapping state, auxiliary or context names must match those
declarations; `dt` uses `s`. These checks do not reproduce engine selection or prove that inputs are
available. Even a loaded model currently excluded by contextual selection must pass the check.

Labels compare exactly, including whitespace. Use `1` to declare dimensionless values; an absent
label never means dimensionless. Domain authors explicitly declare derivative/hazard output units;
there is no dimensional parser to derive or certify them. Matching labels do not prove physical
correctness, training origin, measured errors or conversion compatibility. The check cannot convert
Celsius to kelvin or inspect unit conventions of ambient Geant4 facts.

Missing catalog access returns `catalog_unavailable`. An empty loaded group or missing/incomplete
model unit metadata returns `unit_metadata_missing`; differing labels or missing/extra expected IO
returns `unit_mismatch`. All block before inference/RNG and preserve state/clock. After a catalog
read, reports retain observed artifact identities, including on failure. Unit checks compose with
`model_artifacts` pins, which run first, and neither checked contracts nor returned metadata alias
their execution closures. Record the contract in `hooks.inputs` as usual. Strict mode reads no
catalog; bindings without units or pins retain their prior path and never read it.

| Error code | Runtime status | State/clock committed? |
| --- | --- | --- |
| `strict_disabled` | `strict_disabled` (runtime gate) | no operator call, no commit |
| `operator_unavailable`, `missing_context`, `operator_blocked` | `blocked` | no |
| `catalog_unavailable`, `artifact_mismatch` | `blocked` | no operator call, no commit |
| `unit_metadata_missing`, `unit_mismatch` | `blocked` | no operator call, no commit |
| `invalid_context`, `invalid_binding` | `rejected` | no operator call, no commit |
| `invalid_proposal` | `rejected` | no; raw engine report retained |
| `operator_exception` | `rejected` | no; error text retained, run-level accounting remains authoritative |

Invalid contract definitions and nonpositive/nonfinite `dt` throw authoring errors. Exceptions from
engine invocation become `operator_exception`; they do not supply a fallback result. The generic
runtime keeps its existing state-validation step after a binding accepts its draft.

The C++ [read-only operator catalog](scenario_hooks.md#read-only-operator-catalog) exposes loaded
IO, role/kind, authored paths and carried training/held-out metadata. It works in strict mode and
does not invoke selection, inference or RNG. Missing artifacts stay visible as unloaded, and
missing metrics stay absent rather than becoming perfect zero errors. Catalog presence alone
cannot prove a process will run or that its response is physically valid.

`test_process_operators.cpp` checks the shared contracts with synthetic continuous/discrete maps
through the actual QuickJS/C++ host, two material kinds, strict/predictive catalog parity, metric
absence/presence, state rollback, auxiliary isolation and replay. The fixture metrics and model
outputs are test data, not kinetic validation.
The same host tests cover relative-path byte identity, replacement vs fresh load, pinned
continuous/discrete execution, strict gating and identical stochastic results with/without
rejected pin checks. Loader tests cover path-independent IDs, byte changes and failed-reload reset.
Unit tests cover malformed/absent metadata, loaded snapshot/reload behavior, v2 decoded-output labels,
multistage IO unions, contract/catalog detachment, pins combined with unit checks, strict gating and
continuous/discrete calls with identical stochastic results with/without rejected unit checks.

## What still needs implementation

This is orchestration, not a new phase-change model. No validated dissolution, energy transport,
evaporation or crystallization model is bundled. Heating is sequential thermal preparation;
latent-heat/energy coupling during subsequent operations is unavailable. Single-channel integer
transitions are bounded to the existing one-transition-per-element/call contract, not a calibrated
macroscopic rate. Spatial cells, diffusion/advection, interfaces, simultaneous coupled processes,
nucleation and reversible growth/dissolution require additional process/operator support.
Additional domain families, parallel/coupled scheduling, pair/spatial/per-element-kind bindings,
dimensional analysis/unit conversions, cryptographic identities and a run-wide artifact manifest remain
open. Shared binding infrastructure does not establish transferable physical response across materials.

Microscope-like crystallization needs recorded 3D liquid/solute fields, nucleation sites and
moving crystal/liquid interfaces with conserved material exchange. Inventory counts cannot
supply those positions or surface shapes. The recipe reports `spatial_state_available:false`;
it deliberately emits no replacement ball trajectories. The older lattice example is an
inventory diagnostic, not microscopy or a salt-in-water simulation.

Similarly, the airflow example is a 2D Euler slice. Extruding it or adding transparent colours
does not make its dynamics 3D. True 3D pressure/temperature fields and authored JS camera,
section, surface and transparent-volume controls remain roadmap work. Representation must stay
separate from physical dimensionality and model validity.
