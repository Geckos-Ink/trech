# Core concepts

[Documentation home](README.md) · [First run](first_run.md) · [Runtime architecture →](architecture/runtime.md)

## System

A **system** is the part of the physical world the experiment describes and the
conditions under which you study it. In the first run it is a water volume exposed to an
electron source. In the lava lamp it includes the vessel, carrier liquid, wax, heater
and surroundings used to drive or bound the thermal and fluid response.

In TRECH the description is spread across configuration and scenario state.

| Question | Example | Where it lives |
| --- | --- | --- |
| What is present? | Water, wax, glass and their compositions | `materials`, material references such as `G4_WATER` |
| Where is it? | World, vessel and interior volumes | `environment` and `geometry.volumes` |
| What acts on it? | Beam, temperature conditions, sources or initial motion | `beam`, typed scenario inputs and initial state |
| What can change? | Particle energy, parcel positions, temperature or molecule counts | Geant4 track state or named element, pair or field state |
| What is the question? | Deposit per event, transmission fraction, temperature profile or phase fraction | Native scores, hook emits and validation expectations |

<details>
<summary>How does the JSON system block fit in?</summary>

`config.system` controls run-level aggregation and labels. For example, the volume for
deposit per unit volume comes from `system.volumeMm3` if positive, then the configured
medium box if present, then the world. This volume is a normalization for aggregate tallies.
The apparatus itself is described by materials, geometry and source, and a number such as
`system_edep_mev_per_mm3` does not carry spatial coordinates.
[Aggregation fields](engine/output_schema.md#trech_scoresjsonl)

</details>

## State, interaction and observable

**State** holds the quantities needed at a particular instant or simulation step. It can
be continuous, such as temperature and position, or discrete, such as how many molecules
of each species occupy a cell. An **interaction** couples parts of the state. For example,
one pair transfers heat, gaining and losing the same amount on opposite sides of the pair.
An **observable** answers a question about the state or its history, such as the uncollided
photon fraction after many events or the mean charge temperature at the end of a furnace run.

A **Geant4 event** holds one or more simulated primaries and their descendants. Some scenarios use
event completion to trigger an update of separate hook-layer state. These scenarios define
their own physical time per update. Playback can use a third clock for presentation. Check
which clock a plot uses before reading a rate from it.
[Geant4 and hook lifecycle](architecture/runtime.md#during-the-run)

## Field

A **field** assigns a quantity to locations in a region. Temperature is a scalar field
`T(x, y, z, t)` in kelvin. Fluid velocity is a vector field with three components at each
location. A cell grid represents a field with finitely many values, usually cell means.
A lamp's vertical temperature column uses one mean per horizontal slab. The same
physical region can also be represented by wax parcels with positions and temperatures.

| Representation | Example question it can answer |
| --- | --- |
| Aggregate scalar | How much energy was deposited per unit volume over the run? |
| Element state | What is the temperature and position of this wax parcel? |
| Cell field | Where in the carrier is it hotter and how does that change in time? |
| Rendered surface | Where did Studio draw the boundary reconstructed from emitted state? |

`ctx.evolveField` is the engine's validation-facing API for advancing a **scalar
continuum field**. Geant4's electromagnetic transport fields act on charged particles
and have a different contract. A density or orbital in the Studio Field Explorer can
also be a recorded quantum reference. [Field evolution](engine/field_evolution.md) ·
[Geant4 field capabilities](engine/GEANT4_features_and_limits.md#36-fields-spin-geometry-and-infrastructure) ·
[Studio density and orbital views](studio/chemistry_probability.md)

## Scale and domain

A **scale** describes the characteristic size or level of representation of a
quantity. A **context** is the set of named facts available to a prediction, such as
composition, photon energy or neighboring temperatures. A **domain** is a region of
that context where a grouping or law has statistical support. Two domains can sit at
the same scale. For example, cold-grain and hot-melt responses can differ within a
single furnace grid. [Scales, groups and domains](inference/multiscale.md)

## Where the result comes from

| Source | Example |
| --- | --- |
| Geant4 transport | A sampled electron track or energy-deposit tally |
| Derived Geant4 fact | A material probe's number density, or an interaction-table value |
| Learned prediction | A frozen model's estimate of a transmission fraction |
| Comparison or validation reference | A hook-layer molecular dynamics run, an analytic limit or an independent quantum calculation |
| Rendering | A viewer's interpolated surface, color map or accelerated replay |

One experiment can contain several rows of this table. Follow the source of the
specific quantity you intend to use. [Read the evidence](validation/README.md)
