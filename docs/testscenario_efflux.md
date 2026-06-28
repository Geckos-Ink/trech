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

A cell rids itself of a small **lipophilic waste / xenobiotic** molecule
(**benzene**). Being hydrophobic, it dissolves into and diffuses across the lipid
bilayer (Overton's rule — no channel needed), down its concentration gradient,
into a well-mixed extracellular sink (the bloodstream carries it away). The polar
**essential** molecule (**D-glucose**, the cell's fuel) cannot enter the lipid
core and is retained — the membrane is selective by chemistry, not size.

The two molecules are **real substances grounded in PubChem**. Validation fetches
them into a build-local cache (`TRECH_PUBCHEM_CACHE_DIR`, usually
`build/dev/pubchem_cache`) and the scenario loads them with `TRECH_PUBCHEM`.
Their measured **XLogP** (octanol-water partition coefficient) decides
selectivity — benzene `+2.1` (lipophilic → permeates), D-glucose `−2.6` (polar
→ retained) — and their molar masses set the relative thermal speeds. Their 2D
structures are shown in the render video when PNGs are present in the cache.

## Motion: directed flow, not random jitter

Inside the cell the molecules do **not** jitter randomly. The integrator is a
drift-diffusion (overdamped-Langevin) model with three terms: a *persistent*
random velocity (smooth paths), a coherent **cytoplasmic-streaming** flow (a slow
rigid rotation — an organized internal flow, volume-preserving so it does not
bias escape), and a mild outward **efflux drift** for the lipophilic permeant (it
descends the chemical-potential gradient toward the exterior, like a particle
settling at terminal velocity). The result reads as an organized swirl that
gradually drains the waste outward (~79% of permeant steps share the circulation
direction), while diffusion keeps the interior well-mixed so the escape stays
memoryless and the clearance stays first-order.

## The TRECH thesis, end to end

| Source | What | How |
|---|---|---|
| PubChem | WHICH molecule permeates (selectivity) | measured **XLogP** (Overton's rule): benzene `+2.1` lipophilic → permeates; D-glucose `−2.6` polar → retained. Loaded via `TRECH_PUBCHEM`, emitted in the `pubchem` payload. |
| Geant4 (nanoscale) | HOW FAST it permeates (rate scale) | `G4EmCalculator` membrane vs cytosol EM interaction coefficient μ (the analytic Beer-Lambert machinery, 30 keV proxy); emitted live as `analytic_checks` (μ_lipid ≈ 0.0291/mm, μ_water ≈ 0.0377/mm → ratio ≈ 1.30). |
| Geant4 (event drive) | per-tick activation | the same 30 keV gamma probe is transported each event; `onEventEnd` reads `ctx.event` energy deposit, track length, and step counts to modulate the permeability for that tick. |
| Mesoscale | per-encounter permeation probability p_cross | scaled by the Geant4 interaction ratio and event activation; drift-diffusion MD in the deterministic hook layer (one Geant4 event = one tick) |
| Macroscale | first-order clearance law | the simulated internal count N(t) is fit log-linearly and compared to the closed form `N(t) = N₀·e^(−k t)` (Fick, well-mixed cell into a sink, k = P·A/V) |

Result (seed 71081923, 6000 ticks): **R² ≈ 0.992**, half-life ≈ 1786 ticks,
72/80 waste cleared, 30/30 essentials retained, and positive Geant4 event drive
(12,789 steps, 4.99 MeV deposited).

## Honest scope

The **PubChem XLogP selectivity is a real measured anchor** — the cleared vs
retained decision follows the substances' actual partition coefficients
(Overton's rule). The **Geant4 → permeation-rate mapping is illustrative**
(flagged in the scenario and on the video): Geant4 transports particles but
cannot compute molecular partitioning/diffusion, so the rate scale uses the EM
interaction ratio as a stand-in. What is genuinely validated is that the
microscopic drift-diffusion permeation reproduces the macroscopic first-order
law — a self-consistency cross-check of stochastic kinetics against the closed
form, in the same family as the analytic Beer-Lambert check.

## Outputs

- `efflux_snapshot` (every 50 ticks): per-molecule `{id, k, s, x, y}` (state
  `s`: 0 inside / 2 cleared-leaving) + `waste_inside`/`waste_cleared`/
  `retained_inside`.
- `efflux_summary` (run end): the log-linear `fit` (`rate_per_tick`,
  `r_squared`, `half_life_ticks`, `permeability_eff_units_per_tick`), the
  `geant4` and `pubchem` anchors, the full `series`, and a `validation` block
  (`first_order_kinetics`, `waste_cleared`, `essentials_retained`,
  `geant4_param_present`, `geant4_event_drive_present`,
  `lipophilicity_selectivity`).
- `analytic_checks` in `trech_scores.jsonl`: the live Geant4 μ values.
- `build/dev/pubchem_cache/<slug>.json` + optional `.png`: the fetched PubChem
  properties + 2D structures. Fetch with
  `PYTHONPATH=tools/pubchem python3 -m trech_pubchem fetch --cache-dir build/dev/pubchem_cache benzene "D-glucose"`.

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
