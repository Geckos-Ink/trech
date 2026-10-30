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

Units and provenance are explicit **declarations**. No unit conversion or model-unit matching is
claimed, and authored provenance is not evidence of particle-derived training. Required declared
context must be supplied: missing values block before invocation, finite zero is retained and
undeclared extra values are not forwarded. Ambient Geant4 facts still enter through the engine;
they need not be copied into authored context. Auxiliary arrays are copied and never committed.
Writable arrays are copied, checked and replaced in the draft only on acceptance. Each returned
`contract` is detached from executable closures, so edits require a new binding.

Bound reports have `{ran, accepted, contract_id, error, engine}`. `engine` retains the ordinary
unmodified operator report, including selection, trace, inference/draw counts and trust metadata.
`ran` preserves the engine's execution verdict, while `accepted` records state acceptance;
an invalid proposal can have `ran:true, accepted:false`. Inference and RNG cannot be rolled back.

| Error code | Runtime status | State/clock committed? |
| --- | --- | --- |
| `strict_disabled` | `strict_disabled` (runtime gate) | no operator call, no commit |
| `operator_unavailable`, `missing_context`, `operator_blocked` | `blocked` | no |
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

## What still needs implementation

This is orchestration, not a new phase-change model. No validated dissolution, energy transport,
evaporation or crystallization model is bundled. Heating is sequential thermal preparation;
latent-heat/energy coupling during subsequent operations is unavailable. Single-channel integer
transitions are bounded to the existing one-transition-per-element/call contract, not a calibrated
macroscopic rate. Spatial cells, diffusion/advection, interfaces, simultaneous coupled processes,
nucleation and reversible growth/dissolution require additional process/operator support.
Additional domain families, parallel/coupled scheduling, pair/spatial/per-element-kind bindings,
model-unit metadata/conversions and content-addressed model identities remain open. Shared binding
infrastructure does not establish transferable physical response across materials.

Microscope-like crystallization needs recorded 3D liquid/solute fields, nucleation sites and
moving crystal/liquid interfaces with conserved material exchange. Inventory counts cannot
supply those positions or surface shapes. The recipe reports `spatial_state_available:false`;
it deliberately emits no replacement ball trajectories. The older lattice example is an
inventory diagnostic, not microscopy or a salt-in-water simulation.

Similarly, the airflow example is a 2D Euler slice. Extruding it or adding transparent colours
does not make its dynamics 3D. True 3D pressure/temperature fields and authored JS camera,
section, surface and transparent-volume controls remain roadmap work. Representation must stay
separate from physical dimensionality and model validity.
