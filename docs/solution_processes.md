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

`trech_process_operators.js` supplies the common element and spatial-neighbour binding boundary for domain libraries. The
solution library uses it for all four operations, recording `operator_contracts` in its recipe
plan and thus config/hash/provenance. The bindings accept ordinary per-element JS arrays and
a scalar material kind or a declared per-element kind field; both continuous and integer
operations can cover several elements.

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

### Per-element material kinds

A shared binding can read each element's current kind from a declared state field instead of
using a scalar `element_kind`:

```js
const thermal = TRECH_PROCESS_OPERATORS.bind({
  id: "thermal", operation: "evolve", operator_role: "thermal_preparation",
  element_kinds: {field: "material_kind", allowed: ["material_a", "material_b"]},
  fields: [{name: "temperature_k", unit: "K", min: 0}],
  context: [{name: "bath_temperature_k", unit: "K", min: 0}],
  provenance: {basis: "Authored interface; supplied material responses require validation"}
});
const state = {temperature_k: [293.15, 303.15], material_kind: ["material_a", "material_b"]};
const report = thermal.advance(ctx, state, dtSeconds, {bath_temperature_k: 373.15});
```

Declare exactly one of scalar `element_kind` or `element_kinds: {field, allowed}`. The allowed
set must be nonempty and unique, with nonblank strings and no embedded NULs. The kind field must
be distinct from numeric state, auxiliary
and context names. Its array must match the numeric element count, have no holes and contain only
allowed strings. Invalid arrays return `invalid_binding` before catalog/operator calls.

The binding copies the kind array on every call. A domain stage may change assignments between
calls; the next invocation selects using the new kinds. Numeric proposals never commit changes to
the kind field. All kinds currently share the same numeric declarations, topology and expected
model IO; kind dispatch supplies no material-transition law or transport. Explicit spatial-neighbour
bindings are described below.

These calls set C++ `require_complete_selection: true`. Missing or ambiguous operator selection
for any active kind blocks the batch before inference, state writes or reaction sequence allocation.
The bound report returns `operator_blocked` and retains the engine's `incomplete_selection` reason
and per-kind selection groups. The process runtime preserves its state and clock. Ordinary raw
engine calls retain partial execution unless they explicitly enable that gate.

Selection completeness does not certify input availability within selected model stages or physical
validity. Missing intermediate inputs can still skip stages under the normal engine contract;
domain libraries remain responsible for stronger proposal and completion invariants.

With artifact pins, the complete loaded role/kind group is the union over **all allowed kinds**,
including currently inactive ones. Pins do not themselves guarantee that every kind has an operator.
With `model_units`, each allowed kind must have a loaded group whose IO union separately matches
the common expected labels. A missing inactive group's metadata also blocks. This conservative
check prevents one material's metadata from hiding a missing or incompatible response in another.
Observed artifacts retain globally unique model names and loaded content IDs as usual.

### Spatial neighbour bindings

`operation: "interact"` binds the engine's learned pair operator to explicit x/y/z state
arrays. This example declares an exchange interface, with no supplied response law:

```js
const exchange = TRECH_PROCESS_OPERATORS.bind({
  id: "local_exchange", operation: "interact", operator_role: "local_exchange",
  element_kinds: {field: "material_kind", allowed: ["material_a", "material_b"]},
  fields: [{name: "energy_j", unit: "J", symmetry: "antisymmetric"}],
  aux: [{name: "mass_kg", unit: "kg", min: 0}],
  spatial: {axes: {x: "x_m", y: "y_m", z: "z_m"}, unit: "m", cutoff: 0.001,
    max_pairs: 100000},
  provenance: {basis: "Declared exchange interface; response validation required"}
});
// draft contains equal-length energy_j, mass_kg, x_m, y_m, z_m, material_kind arrays.
// Record exchange.contract in hooks.inputs; call within a predictive process stage:
const report = exchange.advance(ctx, draft, dtSeconds);
```

All three axes are mandatory, distinct, finite arrays with the numeric element count.
Coordinate names must be separate from writable, auxiliary, context and kind fields. Positions,
auxiliary arrays and kinds are detached on every call and never committed by this binding.
Coordinates may change between calls through authored state preparation; no advection or moving
interface law is supplied. The positive finite cutoff uses the declared coordinate unit;
optional `max_pairs` is a positive safe integer. Absent limits leave the engine search unbounded.
Each writable field requires explicit `antisymmetric` or `symmetric` symmetry.

The C++ engine enumerates neighbours using all three coordinates, in canonical index order,
and owns model selection, ambient particle facts, pair contributions and inference accounting.
Per-element material kinds select canonical unordered combinations (`material_a|material_b`).
Member kind names cannot contain `|` or unpaired Unicode surrogates. Scalar `element_kind`
retains the raw engine's single operator-kind identifier semantics. Pair kind ordering matches
the C++ UTF-8 comparison, including supplementary Unicode characters.

Every spatial binding enables `require_complete_selection`. With per-element kinds, the C++
gate conservatively checks **all combinations of kinds present in the call**, even when no such
pair lies within the cutoff. Missing or ambiguous selections block before inference and writes.
Optional pins cover the complete loaded group union over all combinations of **allowed** kinds.
Unit checks require each allowed combination's loaded IO union separately, including inactive
combinations; one material's metadata cannot supply another's missing response. Selection
completeness does not certify stage input readiness; skipped inputs remain visible in engine traces.

`model_units` checks member inputs using `a_<field>` / `b_<field>` for writable and auxiliary
declarations. Geometry inputs `r`, `dx`, `dy`, `dz` must use the spatial unit, `ux`, `uy`, `uz`
use `1`, and `dt` uses `s`. Derivative/increment output units remain explicit authored labels.
No coordinate conversion or dimensional analysis is performed.

Bounds, finite proposals and ordinary process commit checks still apply. An executed proposal
from a budget-truncated neighbour search returns `invalid_proposal`, `ran:true`, `accepted:false`: state and the process
clock are not committed, and the original trace/counts disclose inference already performed.
An empty neighbourhood makes the engine return `ran:false` and blocks this process step.
Antisymmetry enforces opposite pair contributions before bounds; clipping, floating-point sums
and a physically inappropriate response can still defeat a domain's global conservation law.
Domain validation remains necessary. Persistent links and pair-owned state are not supported by
this binding; raw `ctx.interact` retains those capabilities and optional partial execution.

Raw C++ `ctx.interact` also rejects supplied positions unless all x/y/z arrays exactly cover
the elements with finite numbers; absent axes never become synthetic zero coordinates. Array
and Float64Array positions are supported. Omit positions entirely for link-only calls without
geometry inputs. Strict calls still return before parsing or inference.

### Pinning loaded model artifacts

Optional `model_artifacts` pins the complete **loaded** catalog group with the contract's exact
role and material kind. Each pin declares a model name and an algorithm-qualified byte identity:

```js
const pinned = TRECH_PROCESS_OPERATORS.bind({
  ...thermal.contract,
  model_artifacts: [{name: "thermal_model", content_id: "fnv1a64:0123456789abcdef"}]
}); // Illustrative ID only: use the fingerprint of the reviewed artifact.
// Save pinned.contract in hooks.inputs with the process plan.
```

The engine computes `fnv1a64:<16 lowercase hex digits>` from the exact bytes consumed by the
loader, once at load time. It also computes `sha256` (64 lowercase hex digits) and `size_bytes`
from those same bytes. To pin the cryptographic digest, use
`{name: artifact.name, content_id: "sha256:" + artifact.sha256}` from the reviewed catalog entry.
FNV and SHA-256 pins may coexist in a contract; a SHA-256 pin never falls back to FNV if its digest
is absent. Identical bytes at different paths have the same ID; whitespace
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

After a catalog check, bound reports include detached `artifacts: [{name,content_id,sha256}]` with the
observed matching group, including on a mismatch or subsequent engine rejection. Strict mode
returns before catalog access; contracts without pins do not read the catalog. Pin definitions
and returned metadata remain detached from execution closures.

FNV remains noncryptographic; SHA-256 provides a cryptographic byte digest. Neither is an
authenticity/signature, unit-compatibility or physical-validation proof.
Authored pins enter config/hash only when the domain plan includes the contract in `hooks.inputs`;
actual artifacts enter emitted reports when the caller records them. Independently, GeantRunner
records a name-sorted [`model_artifacts`](output_schema.md#scenario-model-artifact-manifest) snapshot
of all scenario-registry models in both provenance phases and run-end scores. This includes failed
loads and point/cascade models without operators, and never reopens paths to reconstruct identities.
No-model runs omit the manifest; config hashes remain unchanged. Separate stratifier/optics loaders
and artifact signatures remain outside this manifest. Optional Torch loading uses the same snapshot,
now exercised by the conditional C++ backend gate. Raw `.pt` modules have no named IO/unit metadata
for these generic process bindings; use portable named-IO JSON. Synthetic backend checks do not
validate any physical response.

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
`test_process_materials.cpp` adds changed-kind dispatch, distinct per-kind hazards, detached kind
arrays, cross-kind proposal rollback, per-kind unit unions, complete-group pins and pre-inference
selection gates. Rejected checks preserve the next reaction's sequence and exact stochastic replay;
raw continuous/discrete partial-selection behavior remains covered. These are synthetic interfaces,
not calibrated material-response tests.
`test_process_spatial.cpp` exercises synthetic 3D neighbour exchange through the actual host:
z-dependent geometry, dynamic cross-material dispatch, complete-selection gates, whole-pair-group
pins/units, read-only isolation, invalid/truncated proposal rollback, strict mode and exact replay.
These are execution-contract checks, not validation of heat or mass transport.

## What still needs implementation

This is orchestration, not a new phase-change model. No validated dissolution, energy transport,
evaporation or crystallization model is bundled. Heating is sequential thermal preparation;
latent-heat/energy coupling during subsequent operations is unavailable. Single-channel integer
transitions are bounded to the existing one-transition-per-element/call contract, not a calibrated
macroscopic rate. Spatial cells, diffusion/advection, interfaces, simultaneous coupled processes,
nucleation and reversible growth/dissolution require additional process/operator support.
Additional domain families, parallel/coupled scheduling, persistent-link/pair-state bindings, per-kind numeric/IO schemas,
dimensional analysis/unit conversions, manifest coverage of separate stratifier/optics loaders and
artifact signatures remain open. Shared binding infrastructure does not establish transferable
physical response across materials.

Microscope-like crystallization needs recorded 3D liquid/solute fields, nucleation sites and
moving crystal/liquid interfaces with conserved material exchange. Inventory counts cannot
supply those positions or surface shapes. The recipe reports `spatial_state_available:false`;
it deliberately emits no replacement ball trajectories. The older lattice example now emits inventory diagnostics only; its tray animation is retired.
Optional C++-inspected external interface recordings replay supplied triangles on a physical clock,
without claiming that format inspection verifies accuracy; no calibrated data is bundled.

The current airflow example evolves a genuine 3D independent Euler comparison with x/y/z
momentum and fluxes. Recorded pressure/temperature/density grids carry JS-authored camera,
section, surface and transparent-volume controls. External accuracy/convergence and a learned
particle-derived aerodynamic lift remain open. Representation remains separate from physical
validity; see [the reference contract](process_references.md).
