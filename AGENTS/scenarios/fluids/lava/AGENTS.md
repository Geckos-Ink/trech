# Lava lamp thermofluid — context and contracts

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

This branch covers lava lamp thermofluid. Use the linked parent and related owners for implementation contracts and source maps; the paired roadmap records its delivery and validation requirements.

Lava-lamp summaries include the cascade’s final output error metrics. The illustrative
macro outputs report `null` until the model carries held-out RMSE or interval metadata.

`detect_domains=true` records statistical subdivisions of the wax parcel positions once per
frame. `domain_method=density` uses a shared spatial scale. Each frame records
mutual-majority persistent IDs and predecessor overlaps for the wax inventory. The [domain emit](../../../../docs/engine/output_schema.md#statistical-domain-discovery-emits)
uses parcel order and carries call-local assignments.

`engine_field_evolution=true` (the default) makes the validation companion
(`lava_lamp.validation.js`, `observeFrame`) declare the carrier column to the engine through
[`ctx.evolveField`](../../../engine/lattice/AGENTS.md). The physics script declares no field:
- at each output frame it hands its observed state to the companion;
- it keeps one neutral observation, the wax heat each carrier cell received during the frame
  (`carrierWaxHeatFrameK`, accumulated in `applyThermalAndPhaseState`).

The companion's declaration covers the cylinder, the 24 cells, the cascade-inferred viscosity,
diffusivity and expansion, the heater and top exchanges, and that heat load. The engine chooses
its prediction method per context domain against the authored column, which is passed only as
the validation reference. Nothing feeds back, and the normal-path emits are byte-identical with
`false`.

`learn_domains=learn|evaluate` drives `ctx.learnDomains` on the frame-scale parcel response:
features at the start of an output interval (height, radius, wax temperature, molten fraction,
carrier temperature at the parcel, vertical velocity, and the heater temperature as run context)
and targets averaged over the fine physics
steps of that interval (heating rate, mean vertical velocity). It is a coarse-grained meso lift of
the authored step laws, never fed back into the lamp. Agreement is reported against a molten/solid
split applied afterwards. Campaign: `tools/torch/study_domain_learning.py --scenario lamp`.
