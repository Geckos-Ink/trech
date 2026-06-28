# Test scenario: passive membrane efflux (cellular clearance)

`examples/experiments/testscenario_efflux.js` — a classic biological phenomenon
(a cell automatically expelling a foreign/waste organic molecule following
physical law) rendered as a **TRECH-simulation-vs-classical-formula** comparison,
in the style of the bulk-water g(r) demo.

This scenario was introduced (2026-06-28) to replace the osmotic-dehydration
framing as the headline biological video: "dehydration" was unsatisfying because
it foregrounded water leaving rather than a recognizable, law-governed expulsion
of a specific molecule.

## The phenomenon

A cell rids itself of a small **lipophilic waste / xenobiotic** molecule. Being
hydrophobic, it dissolves into and diffuses across the lipid bilayer (Overton's
rule — no channel needed), down its concentration gradient, into a well-mixed
extracellular sink (the bloodstream carries it away). Polar **essential**
molecules cannot enter the lipid core and are retained — the membrane is
selective by chemistry, not size.

## The TRECH thesis, end to end

| Scale | What | How |
|---|---|---|
| Nanoscale | membrane vs cytosol EM interaction coefficient μ | `G4EmCalculator` (the analytic Beer-Lambert cross-check machinery), 30 keV soft-photon proxy; emitted live as `analytic_checks` (μ_lipid ≈ 0.0291/mm, μ_water ≈ 0.0377/mm) |
| Mesoscale | per-encounter permeation probability p_cross | scaled by the Geant4 cytosol/membrane interaction ratio (≈1.30); coarse-grained Langevin MD in the deterministic hook layer (one Geant4 event = one tick) |
| Macroscale | first-order clearance law | the simulated internal count N(t) is fit log-linearly and compared to the closed form `N(t) = N₀·e^(−k t)` (Fick, well-mixed cell into a sink, k = P·A/V) |

Result (seed 71081923, 6000 ticks): **R² ≈ 0.985**, half-life ≈ 1226 ticks,
78/80 waste cleared, 30/30 essentials retained, back-derived permeability
P_eff ≈ 0.0079 units/tick.

## Honest scope

Same as every TRECH MD demo: Geant4 transports particles but **cannot** compute
molecular partitioning/diffusion, so the permeation is a classical coarse-grained
model and the **Geant4 → permeability mapping is illustrative** (flagged in the
scenario and on the video). What is genuinely validated is that random
microscopic permeation events reproduce the macroscopic first-order law — a
self-consistency cross-check of stochastic kinetics against the closed form, in
the same family as the analytic Beer-Lambert check.

## Outputs

- `efflux_snapshot` (every 50 ticks): per-molecule `{id, k, s, x, y}` (state
  `s`: 0 inside / 2 cleared-leaving) + `waste_inside`/`waste_cleared`/
  `retained_inside`.
- `efflux_summary` (run end): the log-linear `fit` (`rate_per_tick`,
  `r_squared`, `half_life_ticks`, `permeability_eff_units_per_tick`), the
  `geant4` anchors, the full `series`, and a `validation` block
  (`first_order_kinetics`, `waste_cleared`, `essentials_retained`,
  `geant4_param_present`).
- `analytic_checks` in `trech_scores.jsonl`: the live Geant4 μ values.

## Validation & rendering

- Guarded by `efflux_first_order_kinetics` (category `fluid`) in the validation
  suite; wired into `scripts/run_validation_suite.sh` (`N_EVENTS_EFFLUX`).
- Rendered by `tools/viz/demos/render_efflux.py` → `efflux_clearance.mp4`/`.gif`
  (the README headline biological video).

## Possible next steps

- An *active* efflux pump variant (P-glycoprotein) compared to Michaelis–Menten
  saturation kinetics.
- A genuine microscale Geant4 sub-simulation to measure a transport quantity at
  the membrane scale, replacing the illustrative μ-ratio mapping.
- A two-species partition sweep (vary lipophilicity) to trace P vs the Geant4
  interaction contrast.
