# How TRECH moves between scales

[Documentation home](../README.md) · [Inference index](README.md) · [Runtime architecture](../architecture/runtime.md) · [Field evolution →](../engine/field_evolution.md)

A scale transition changes what the state describes. A list of particle steps can
become an event-level deposit. Atomic cross sections can become a molecular response.
A collection of cell states can become an observer-scale prediction. These examples
use different representations and therefore require different forms of evidence.

## What is fixed and what is decided at runtime?

The engine recognizes ordered bands `atomic → nano → micro → meso → macro → unscaled`.
These are ordering tags on declared models. Several models can occupy a band, bands can
be absent, and a bench-sized `meso` apparatus can already be the observer. There is no fixed
number of stages. The engine uses the artifacts and contracts available in a run to decide
which stages have inputs and which law covers a particular context. Model and field
discovery straight from arbitrary materials and geometry remains a research objective.
[Scale implementation](../../include/trech/ml/ScaleCascade.hpp) ·
[Inference roadmap](../../AGENTS/engine/inference/ROADMAP.md#priority-queue)

| What changes? | Mechanism | What drives the decision? |
| --- | --- | --- |
| One response from a named model | [`ctx.predict`](../engine/scenario_hooks.md#ctxpredict) | Named inputs available at the call site |
| Named facts in one context | [`ctx.cascade`](../engine/scenario_hooks.md#ctxcascade) | Declared scale and readiness of named inputs within a band |
| Population represented at a coarser level | `ctx.lift(spec)` | Per-level model and grouping metadata applied to the current population |
| State of an element, inventory or pair | `ctx.evolve`, `ctx.react`, `ctx.interact` | Loaded operator roles, input availability and per-element or per-pair training coverage when routed by domain |
| Statistical subdivisions or response laws | `ctx.detectDomains`, `ctx.learnDomains` | Feature distribution or recurring errors in a common response law |
| Local field prediction | `ctx.evolveField(spec)` | Candidate availability and accumulated prediction evidence per cell |

A cascade deepens one prediction, a hierarchy changes which objects it represents, and
an evolution operator advances state in time. An experiment can combine these operations.

## Follow a named-feature cascade

Each stage reads named facts from a shared context and merges its outputs into that
context. The ambient seed can include Geant4 event tallies, material probes and derived
optics available at the selected hook boundary. Explicit caller values can supply or
override individual facts. In each band, ready stages run first, with stable registration
order for ties. Required facts that remain absent are reported as missing. Upper bands
can consume lower-band outputs. A lower band is never revisited to use a later band's
outputs. `maxStages` and `targetOutputs` can bound the pass.

<details>
<summary>Try it with two bands and inspect the missing rungs</summary>

```sh
./build/dev/trech run examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js \
  --output build/dev/out_cascade
```

Read `cascade_result` in `build/dev/out_cascade/trech_hook_emits.jsonl`. The declaration
lists the meso model first. The run uses `edep_mev` to produce `ionization_density`
in the nano band, then `bulk_response` in the meso band. There is no micro stage.
The two maps are illustrative. For a trained path with independent Geant4 validation,
follow [atomic response → molecular response → transmission and deposition](particle_observer.md).

</details>

When same-band models share an output, their default cascade result uses the last writer.
The hook supports an explicit reference and a learned arbiter for rivals. The choice
at the end of the band can replace the shared outputs consumed by higher bands.
Read the [exact cascade and rival contract](../engine/scenario_hooks.md#ctxcascade)
and [prediction budgets](../engine/adaptive_precision.md#prediction-depth).

## Follow a population through a hierarchy

`ctx.lift` groups elements into cells, explicit groups or a group containing everything,
depending on the level's specification. It runs a set model on each group's members.
The model outputs become the group's features, its position is the weighted centroid,
and its weight is the sum of member weights. The groups then serve as members at the
next level. When the caller omits explicit levels, TRECH builds the plan from loaded
`group_lift` model declarations in scale order. Membership can vary with the supplied
population. This mechanism uses grouping rules carried by the plan or model.

<details>
<summary>What happens when a group has too many members?</summary>

A model has a trained slot capacity. Overflow blocks the group and any ancestor that
requires it. Coverage warnings also follow the lineage. Inspect `parent`, `valid`,
`overflow` and `blockedByMembers` in the [group hierarchy contract](group_hierarchy.md#in-a-hook).
The [optional observer hierarchy](particle_observer.md#optional-multi-scale-study-checkpoints)
provides a runnable study.

</details>

## Follow changing domains within a level

Position, temperature or phase can move an element into a different region of feature
space between updates. On domain-routed calls TRECH can select per-element or per-pair
laws using their training coverage. A later band can route on intermediates predicted
in an earlier band for that same element. In the furnace this lets thermal, chemical and
pair-conduction routes depend on the measured support of cell facts.
The [hook API](../engine/scenario_hooks.md#ctxevolve) specifies uncovered
elements, overlapping rival laws, reporting and explicit overrides.

`ctx.detectDomains` asks whether features themselves form distinct populations.
`ctx.learnDomains` asks whether one fitted law explains their responses. A single
continuous-looking population can contain multiple response regimes. The online learner
can split or merge regimes as evidence changes. The [domain study](multiscale_domain_study.md)
traces discovery, training, frozen deployment and comparisons against a pooled law.

For any of these paths, read the actual model trace. A required input can be absent,
an input combination can be sparse even if each input is within range, and a prediction
can carry an upstream coverage warning. [Trust metadata and re-simulation routing](../engine/scenario_hooks.md#per-stage-trust-profile-low-confidence-flags-carried-with-the-model) ·
[Training and LibTorch](libtorch.md)
