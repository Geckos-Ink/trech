# Reaction oscillator validation — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Oscillating chemistry validation snapshot

- Briggs–Rauscher oscillating-reaction cascade landed (2026-07-25): the **chemistry** arm of the
  multi-scale cascade workstream. `examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js` is told only
  the beaker recipe (KIO₃/H₂O₂/malonic/H₂SO₄/MnSO₄ molarities) and the Geant4-built
  reagent/mixture materials; `materialProbe` reports the dissolved iodine (1.5e20/cm³) + manganese
  (6.9e19/cm³) and `optics.derive` the colourless colour, and a two-stage `ctx.cascade`
  (`data/briggs_rauscher_cascade/nano_reagent_descriptors.json` → `macro_oscillator_response.json`,
  both `generic_surrogate_v1`, both reporting `inDomain`/`domainMeasured:false`) infers the
  coefficients of a reduced FKN/Oregonator relaxation oscillator (f, ε, q, iodide
  regeneration/consumption, iodine production/removal, triiodide–starch coupling, reservoir
  depletion, seconds-per-τ). The cascade emits **no** period, cycle count, colour, or phase
  schedule: a deterministic hook-layer integrator advances the oscillator + emergent [I₂]/[I⁻]/
  reservoir species, and the observable **emerges** — 8 completed colourless→amber(free I₂)→
  deep-blue(triiodide·starch) cycles, amber always before blue (0 violations), ~10.5 s period, then
  a clean settle when the reservoir depletes. Deterministic (`threads:1`, predictive), byte-identical
  across reruns, `hook_predict_count=2` / `hook_predict_out_of_domain_count=0`. Emits `br_frame` +
  `briggs_rauscher_summary`; rendered by `tools/viz/demos/render_briggs_rauscher.py` →
  `tools/viz/demos/briggs_rauscher.gif` (beaker colour + live [I₂]/[I⁻] traces + phase band, 1.4 MB);
  guarded by `briggs_rauscher_oscillation` (category `chemistry`, **10/10** checks); added to
  `scripts/run_validation_suite.sh`. `ctest --preset dev` **11/11** (no config-surface change — the
  scenario uses existing fields, so config hashes are byte-stable). Honest scope: Geant4 does not
  solve aqueous radical/non-radical iodine chemistry — the Oregonator is a labelled "physics for
  comparison" model whose coefficients are inferred from the Geant4 base; the macro response surface
  is a compact **illustrative** map (σ=0.12 emitted), and the amber/blue-black display swatches are
  labelled representation while the colour *timing/sequence* is the emergent, graded result. Follow-up:
  a wider trained oscillating-chemistry panel (graduate the illustrative macro map to a
  held-out-validated per-band chain).
