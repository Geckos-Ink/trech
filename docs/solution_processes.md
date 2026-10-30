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

## What still needs implementation

This is orchestration, not a new phase-change model. No validated dissolution, energy transport,
evaporation or crystallization model is bundled. Heating is sequential thermal preparation;
latent-heat/energy coupling during subsequent operations is unavailable. Single-channel integer
transitions are bounded to the existing one-transition-per-element/call contract, not a calibrated
macroscopic rate. Spatial cells, diffusion/advection, interfaces, simultaneous coupled processes,
nucleation and reversible growth/dissolution require additional process/operator support.

Microscope-like crystallization needs recorded 3D liquid/solute fields, nucleation sites and
moving crystal/liquid interfaces with conserved material exchange. Inventory counts cannot
supply those positions or surface shapes. The recipe reports `spatial_state_available:false`;
it deliberately emits no replacement ball trajectories. The older lattice example is an
inventory diagnostic, not microscopy or a salt-in-water simulation.

Similarly, the airflow example is a 2D Euler slice. Extruding it or adding transparent colours
does not make its dynamics 3D. True 3D pressure/temperature fields and authored JS camera,
section, surface and transparent-volume controls remain roadmap work. Representation must stay
separate from physical dimensionality and model validity.
