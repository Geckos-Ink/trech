# Multi-scale inference — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Coverage, uncertainty and trust | [AGENTS.md](trust/AGENTS.md) | [ROADMAP.md](trust/ROADMAP.md) |

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P1** · R3 · Emergent grouping by default (root principle *A scenario forces nothing*). Done 2026-11-20: the furnace defaults to `grouping: "domain"`; foam, electrolysis and efflux no longer force `element_kind` in their operator calls. Remaining:
  - Furnace pair conduction routes by domain since 2026-11-20 (see the dated record). The opt-in set-network conduction (`cell_conduction_set`, `ctx.evolve`) still passes cell materials: measure routing domains for its three set models the same way, from the members' facts, and grade against declared kinds.
  - At high precision, routed pair conduction disagrees with the declared pair materials on 33 of 11.4 M pair evaluations. Most are `glass|melt` routed as `batch|glass`, where the classifier's glass rule and the melt threshold meet. The run then ends with 170 glass units against 171 and a mean temperature 2.2 K lower than with declared conduction. Narrow that boundary (more high-precision harvest, or a joint membership model).
  - Audit scenario `system`/ensemble declarations and process-library kind labels the same way.

  ([detail](#emergent-grouping-default-2026-11-20))
- **P2** · R3 · `ctx.cascade` rival arbitration sees one context per call, so its per-context choice converges slowly: after 80 calls the late misses lie within 0.175 of the laws' crossing, and more calls do not shrink them monotonically (320 calls: RMSE 0.032 vs 0.052 at 80). Let a population cascade (one call over many contexts) feed one arbiter step, or warm-start it from an exported state. Also, a same-band consumer of a rival's output reads the last writer before the band's choice. ([detail](../../../docs/engine/scenario_hooks.md))
- **P2** · R3 · No scenario feeds `options.reference` to `ctx.cascade` rivals. Give a family two candidate models for one property in one band, and grade them against evidence that is not one of the rivals. ([detail](AGENTS.md))
- **P2** · R3 · No scenario routes `ctx.interact` by domain or feeds it `reference_pairs`. `glass_from_sand` declares per-element kinds. Route a pair family from an undeclared same-role pool (the lava lamp parcels or the furnace conduction cells), and grade its rivals against pair evidence that is not one of them. Evidence for neighbour pairs must name them explicitly, because only links have a stable order. ([detail](AGENTS.md))
- **P2** · R3 · No scenario feeds `reference_hazards` to `ctx.react`: hazard-rival arbitration is exercised only by `trech_discrete_transition` and `trech_js_runtime`. Give a chemistry family two candidate hazard laws for one channel and grade them against an evidence source that is not one of the rivals (held-out Geant4-derived or measured transition rates). ([detail](AGENTS.md))
- **P2** · R3 · No scenario has overlapping `ctx.evolve` rivals today: the glass furnace's trained laws split its population cleanly, so rival arbitration is exercised only by `trech_state_evolution`. Exercise it on a family with two candidate operator families for one quantity and an evidence source that is not one of the rivals (a held-out Geant4-derived or measured rate). The scenario-chosen `physics_source` families of the furnace are the obvious place to retire into emergent selection. ([detail](AGENTS.md))
- **P2** · R3 · Rival arbitration covers rate outputs (`ctx.evolve`), hazard/weight outputs (`ctx.react`), shared outputs (`ctx.cascade`) and accumulating pair outputs (`ctx.interact`) only. Intermediates and `set_` assignments of every covering rival still apply, so a chosen rival's higher-band consumers may read a rejected rival's intermediate. In `ctx.react`, a hazard output that a non-rival stage also writes is recomposed as if only the set's members wrote it. Arbitrate the whole rival output, and re-run the higher bands from the chosen rival's intermediates. ([detail](../../../docs/engine/scenario_hooks.md))
- **P1** · R2 · Close residual CHNO observer coverage holes and validate transfer across composition, geometry and source context. The larger campaign reduced error and measured sparse coverage, and 29 of 48 new conditions still show per-feature starvation with 10 jointly starved. ([study](../../../docs/inference/multiscale_domain_study.md#final-runs-and-validation))
- **P1** · R2 · Worked cascades for the families that still have none: biology (efflux/osmosis cell observables), CNT electronics (gap → device → logic) and magnetic resonance (proton density → image). ([detail](#workstreams-rotate-through-these-each-iteration-should-push-at-least-one))
- **P1** · R2 · Graduate the illustrative stage maps (Briggs–Rauscher, polyurethane, elephant's toothpaste, glass from sand, glass of water) to trained, held-out-validated per-band chains. ([detail](#workstreams-rotate-through-these-each-iteration-should-push-at-least-one))
- **P2** · R2 · Improve recursive hierarchy transfer and calibration. The experimental CHNO scenario runs Geant4-trained atom → nano group → meso observer chains with both atomic backends. Their error and interval coverage lag the dense observer on unseen compositions. ([study](../../../docs/inference/multiscale_domain_study.md#final-runs-and-validation))
- **P2** · R2 · Domain routing beyond glass from sand: route a second family (lava lamp wax/carrier, membrane efflux) and measure routing domains from particle-derived rows rather than from the scenario's own labelled harvest; let elements outside every envelope queue a Geant4 experiment plan and a `trech arch` job for the uncovered regime. ([detail](#domain-routing-2026-11-18))
- **P2** · R2 · Record each routed call's routing summary (rival sets, unnamed groups, per-element or per-pair group ids) in run outputs beside the `__cascade` traces, so Studio's detected-domains view needs no scenario emit. `ctx.interact` now routes pairs by their own context; also let it compose pair kinds from the elements' detected groups automatically. ([detail](#domain-routing-2026-11-18))
- **P2** · R2 · Particle-derived teachers for the online domain learner. `ctx.learnDomains` now learns dynamically changing operator responses (furnace thermal law, lamp parcels, efflux transport), but every teacher is an authored or distilled operator. Feed Geant4-derived rows (CHNO observer, atomic tables) and grade the learned domains against held-out Geant4 runs. Expose the TorchScript specialist index in engine traces and turn recurring uncovered regimes into experiment requests. ([detail](#online-response-domain-learning-2026-11-18))
- **P2** · R3 · Closed-loop deployment of learned-domain operators beyond the furnace thermal law and efflux transport (landed 2026-11-22): chemistry (`ctx.react` hazards) and the lamp parcel dynamics, each behind a paired observer gate, with compounding error measured over long horizons, not only per step. The efflux learner saturated the 24-domain capacity: decide whether capacity should grow with evidence or whether merges should be stricter. ([detail](#efflux-closed-loop-deployment-2026-11-22))
- **P3** · R3 · `study_domain_learning.py` still marks efflux `deploy: False` and compares only furnace observers, so efflux deploy runs are graded by the suite case alone. Make the campaign's observers per scenario and run the deploy pass for efflux. ([detail](#efflux-closed-loop-deployment-2026-11-22))
- **P2** · R4 · Calibrate the learner's `predictionStd`: the ±1.96σ interval covers 99% of rows in-run but 70–88% under transfer (furnace 1820 K, lamp 318 K), while on the efflux held-out seed it over-covers (~99.5%, bands too wide); add per-domain conformal half-widths from held-out calls and carry them into a deployed state. ([detail](#online-response-domain-learning-2026-11-18))
- **P2** · R3 · The two-pass furnace learner (2026-11-20) fixed the 1820 K deploy (+2.3 K mean, minimum fusion +1.9 K, case 10/10). At held-out 1560 K the first glass forms 6 ticks early (27 vs 33; operator tolerance 3), where the one-pass learner matched exactly, and the minimum fusion temperature sits at +4.8 K against 5 K. Grade a 1560 K deploy in the suite, and reduce the early-fusion bias without training on a held-out point. ([detail](#furnace-learner-bias-fixed-by-a-two-pass-campaign-2026-11-20))
- **P3** · R2 · Catch-all domains (wide boxes mixing materials whose laws agree in-sample) transfer poorly; split on joint-support density or a learned membership model, not only on in-sample error. The lava-lamp frame-scale response remains a weak case (velocity 13% worse than pooled inside the training range). ([detail](#online-response-domain-learning-2026-11-18))
- **P3** · R7 · Learner cost grows with reservoir rows and domains: incremental sufficient statistics for refits and split scoring, and amortised merge checks, so 10^4-element populations stay per-frame. ([detail](#online-response-domain-learning-2026-11-18))
- **P3** · R2 · Extend density lineage to changing element inventories and cross-platform numerical replay. Block-wise density discovery now handles 65,536 rows per parent. ([detail](#live-statistical-domain-subdivision))
- **P3** · R2 · Overlapping rival coverage on non-rate outputs (`set_*`, intermediates, and `ctx.react` hazards when no evidence was given) is last-writer-wins; decide nearest-domain selection or blending, and whether a learned membership model should replace the per-model coverage test. ([detail](#domain-routing-2026-11-18))
- **P2** · R2 · Engine architecture generation from Geant4 runs: `trech arch` jobs that name run directories and a harvest spec (source/tag/expand) instead of tables, with whole-run train/selection/test splits, then a committed generated model for a non-optics family. ([detail](#engine-architecture-generation-2026-11-17))
- **P2** · R2 · Let scenarios declare a generated model (a JS `defineModel({architecture: "generate"})` → `trech arch` job in the `trech-ml` store) so the cascade gets models whose structure the engine chose, with the classic reference kept beside it. ([detail](#engine-architecture-generation-2026-11-17))
- **P3** · R2 · Native classic family breadth: DeepSets/MPNN reference structures for set inputs, a `joint` density block in the native `input_domain`, and learned (not fixed) native stopping fed from the Evolvo knowledge file. ([detail](#engine-architecture-generation-2026-11-17))
- **P3** · R7 · Windows worker bridge (`CreateProcess` with a job object for timeouts); today `trech arch` fails on Windows (`not_started`). ([detail](#engine-architecture-generation-2026-11-17))
- **P2** · R4 · Group-hierarchy trust depth: propagate per-group uncertainty instead of reporting only the chained top-level holdout/interval; report which members' lineage made a group out of domain. ([detail](#recursive-group-lifting-2026-11-17))
- **P3** · R2 · Neighbour-aware grouping: halo/overlapping groups or inter-group message passing at each level, and adaptive (octree) partitions, so cross-group behaviour need not travel through latents alone. ([detail](#recursive-group-lifting-2026-11-17))
- **P2** · R2 · Default-on, override-on-demand: infer the relevant behaviour from context without per-scenario model declarations; the per-material selection mechanism exists, trained chains do not. ([detail](#workstreams-rotate-through-these-each-iteration-should-push-at-least-one))
- **P2** · R2 · Observer physical validation: measured references and varied density/geometry/source context; other families and general chemistry/state dynamics. ([detail](#workstreams-rotate-through-these-each-iteration-should-push-at-least-one))
- **P2** · R2 · Turn distilled/illustrative maps into Geant4-trained response models (the 2026-10-18 change removed fabricated inputs only). ([detail](#2026-10-18--real-input-dependencies-and-continued-3d-replay-parity))


## Furnace learner bias fixed by a two-pass campaign (2026-11-20)

- [x] Diagnosis with signed shadow errors (now in the deploy summary by material, run third and
  learner domain): glass carried the bias, +1.08 K per step. Domain 23, a catch-all holding batch
  and glass rows, accounted for most of it, while the glass-only domain was unbiased (+0.075).
- [x] Probes that were not kept:
  - keeping the inside law outside a domain's box: no change;
  - a set-common distance unit for nearest-law routing: routed the glass cells to batch;
  - more memory: the per-domain reservoir is bounded by refit work, not memory.
- [x] Fix: `study_domain_learning.py --passes 2` over the same training points and pinned budget,
  published with `publish_domain_learner.py`, which now records `passes`. At 1820 K the glass bias
  falls to +0.43 K per step, the mean gap from +16.0 to +2.3 K, and the minimum fusion gap from
  5.13 to 1.86 K. CO2 and carbonates are within 0.14 %, and the case passes 10/10.
- Residual (queued above): the first glass forms 6 ticks early at 1560 K.

## Deploy mode under emergent grouping (2026-11-20)

- [x] Diagnosis: in `learn_domains=deploy` the frozen learner's `d_melt_fraction_dt` was applied
  to every cell, including glass, whose operator (`thermal_glass`) rates temperature only.
  - Under the deploy run's temperatures it pushed glass melt fractions down, as far as 0. No
    operator reaches those states.
  - Domain routing then sent glass cells and pairs to melt laws: 17 % of pairs misrouted, a melt
    shadow RMSE of 0.34, and less CO2 released.
  - Declared labels had hidden the same states.
  - A probe was not kept: measuring every rival's gap overflow in a set-common unit routed those
    glass cells to the batch law instead.
- [x] Fix: a learned law that stands in for an operator drives a field only on the cells whose
  operator rates it. `TRECH_DOMAIN_LEARNING.applyRates` takes a per-field `mask`.
  `operatorRatesField` builds it from the shadow call's own report: the routed group path per
  cell, or the stage bound to the cell's material, and each stage's `integratedFields`. The
  shadow's routing is recorded like the applied call's.
- [x] Results at 1820 K:
  - declared and domain deploy are now identical;
  - cell and pair routing agreement is 1.0, and every scenario check passes;
  - CO2 and carbonates equal the operators';
  - the melt shadow RMSE is 0.001.
  - The case's remaining failure is the learner's temperature bias (queued above). The suite no
    longer pins the deploy run.

## Furnace pair conduction routed by domain (2026-11-20)

- [x] Engine: `PairInteraction` exposes `lo_<name>`/`hi_<name>`, the smaller and larger of the two
  members' values of every element field and aux fact. An unordered pair then has facts that do
  not depend on member order. `trech_pair_interaction` shows the values are order-independent,
  and that a `routing_domain` over them selects the right law in either member order.
- [x] `glass_from_sand`, domain mode: the conduction `ctx.interact` passes the cells'
  `melt_fraction` and `glass_silica_fraction` as aux and no kinds. Declared mode is unchanged
  (byte-identical emits; only the model content IDs differ). Training-row runs emit
  `pair_state_sample_<pair>` rows. The summary's `domain_routing.pair_routing` grades routed
  pairs against the classifier's pair materials.
- [x] Routing domains of the six pair laws, measured with `trech-measure-routing-domain` over
  `lo_`/`hi_` melt and converted-silica fractions. The rows come from seven declared
  training-row runs: `build/glass_routing/pair_train_{1500,1600,1700,1750,1880}` and
  `pair_train_high_{1600,1880}`. That is 4,225–1,172,060 rows per law. The domains are disjoint,
  with thin gaps where the nearest law runs.
- [x] Results:
  - **Default and 1820 K:** 324,000 pair evaluations each with zero disagreements and none
    untouched. The default's observables equal the declared run's.
  - **Held-out high-precision run at 1750 K:** 33 disagreements in 11.4 M evaluations (queued
    above).
  - **Cases:** all eight furnace cases pass. `glass_domain_routing_matches_declared` (also at
    1820 K) gains `pair_routing_agrees_with_classifier`. The suite also pins the learn run to
    declared, because its case compares states exactly.
- [x] Probe that was not kept: domains measured from balanced-precision runs only left 943k
  high-precision glass pairs untouched (agreement 0.917), so high-precision rows were added.

## Emergent grouping default (2026-11-20)

- [x] `glass_from_sand` defaults to `grouping: "domain"`: thermal and chemistry route by measured
  domain with no material label, and declared grouping is the validation reference. The suite
  pins `grouping="declared"` on the runs paired with that reference: the baseline, the 1820 K
  baseline, the reference-law run, the set-conduction run and the learned-deploy run.
- [x] `polyurethane_foam` (reaction and mechanics), `testscenario_h2o_electrolysis_combustion` and
  `testscenario_efflux` (transport and crossing) dropped `element_kind` from their operator
  calls. The role alone selects the same operator; the models keep their kind as a category
  label.
- [x] Evidence, with a pinned compute budget:
  - **Foam (default and mechanics operator), electrolysis, efflux:** 219/219/235/425 emits are
    identical before and after once operator-selection metadata (`selection`, `elementKind`,
    `requestedFor`) is stripped. Scores, prediction counts and config hashes are identical, and
    `validate_scenario.py` passes.
  - **Furnace default:** byte-identical to an explicit `grouping=domain` run. Its observables and
    `field_evolution` record equal the declared run's (arbitrated 28.060 K, oracle 13.791 K, 648
    glass units), so the pinned lattice record stands.
  - **Furnace cases:** `glass_domain_routing_matches_declared` (also at 1820 K, 14/14),
    `glass_operator_matches_reference` (22/22), `glass_set_conduction_matches_pair` (17/17),
    `glass_from_sand_material_creation`, `glass_domain_learning_unlabelled` and
    `glass_charge_preserved_under_refinement` pass.
  - **Learned deploy:** `glass_domain_learner_deploy_held_out_1820k` passes in declared mode and
    fails in domain mode (queued above).
- Not run: the full validation suite (only the furnace cases were graded on these runs).

## Rival arbiters across runs (2026-11-20)

- [x] `MethodArbiter::exportState`/`fromState` (`trech_method_arbiter_v1`) save options, error
  learners, and leader and policy scores. A frozen arbiter selects and grades, but learns
  nothing. Its summary carries `frozen` only when it is set, so existing field-evolution emits
  are unchanged.
- [x] `RivalArbitration::exportState`/`restore` (`trech_rival_arbitration_v1`). A frozen pool
  creates no arbiter and keeps its scales. A restored arbiter that meets another context shape
  leaves its set unchanged and reports `error`.
- [x] `ctx.arbitrationState({rows})` and `ctx.restoreArbitration(state, {frozen})` cover the
  evolve, react, cascade and interact pools. Restore validates every pool before replacing any.
- [x] Results:
  - `trech_state_evolution`: a frozen restore deploys on held-out calls 100–119 with mean RMSE
    0.0000, and only its call clock moves. A restore with rows continues byte-identically for
    10 calls. An unseen set is unchanged, and an unknown format throws.
  - `trech_js_runtime`, two runtimes: run 1 trains `ctx.react` rivals and exports; run 2 reads
    the state with `TRECH_READ_JSON`, restores it frozen and deploys a 32/32 split. A graded
    held-out call reaches RMSE 6e-18 without changing the arbiter. A bad state is rejected.
- Residual: `ctx.evolveField` field arbiters and their methods' learned state (done the same day; see the [lattice handbook](../lattice/AGENTS.md#cross-run-state-2026-11-20)).

## Pair routing and rival arbitration for ctx.interact (2026-11-20)

- [x] `PairInteraction` routes with `DomainRouter` over canonical pairs (`routeByDomain`). It
  reports `routing` (one group per pair) and the canonical `pairs`. `ctx.interact` routes an
  undeclared same-role pool, and `group_by: "declared"` keeps `ambiguous`.
- [x] Arbitration covers the accumulating outputs (`d_f_dt`, `add_f`, `d_p_dt`) that two or more
  members of a set produce. Each candidate's value is the pair's total contribution (other stages
  plus the candidate). A choice is applied as a correction with the declared symmetry, and link
  state integrates after arbitration. Without a choice the arithmetic is unchanged.
- [x] `ctx.interact` accepts `reference_pairs` (rows default to the declared links; outputs must
  belong to selected models) and `report_arbitration`, and keeps its own pool.
- [x] Results:
  - `trech_pair_interaction`: the routing split matches the trained regimes, and the uncovered
    pair is untouched. On late calls 30–39, alternatives reach RMSE 0.0000 on heat and bond state
    with a 0.00 sum share. Cooperation reaches RMSE 0.0000 with a 1.00 sum share.
    Antisymmetric cancellation stays exact, and a call without evidence is byte-identical.
  - `trech_js_runtime`: the routed call reports domain grouping and 64 canonical pairs. A
    deployed ungraded call reaches heat RMSE 3e-17.
  - `glass_from_sand`'s declared-kind `ctx.interact` is unchanged (offline validation passes).
- With this item, every multi-method engine path selects through `MethodArbiter`; `ctx.predict`
  names one model.
- Residuals (queued above): no scenario routes or grades pair rivals; assignments and
  intermediates are not arbitrated; arbiters are not exported.

## Rival arbitration for ctx.cascade (2026-11-20)

- [x] `ScaleCascade` plans rival sets per band (loaded stages connected by a shared output).
  When a band ends it hands each set where two or more members ran to
  `CascadeOptions::arbitrateRivals`. It applies the chosen values before any higher band reads
  them, and lets their trust lineage follow the members that produced them.
- [x] Candidates are each member alone and `ensemble_mean`. Sets carry their own feature names,
  the union of the members' inputs. `RivalArbitration::Call` gains `combination`.
  `RivalCandidates` now lives in its own header.
- [x] `ctx.cascade` options accept `reference` and `report_arbitration`, and the result reports
  `__cascade.rival_arbitration`. The cascade keeps a third pool, separate from evolve and react.
- [x] Results:
  - `trech_scale_cascade`, late calls 60–79: alternatives reach RMSE 0.052, against 0.385 for the
    best single rival. The higher band reads the chosen value (obs error exactly 2×). Misses fall
    only where the laws differ by ≤ 0.175. The ensemble case reaches RMSE 0.0000 with a 1.00
    mean share, and the no-evidence result is unchanged.
  - `trech_js_runtime`: an ungraded call at x = 0.9 moves `y` from the last writer's 0.9 to
    the right law's 0.1, and `obs` becomes 0.2.
- [x] Probe: changing the arbiter's per-call forgetting (0.97 / 0.99 / 0.995) did not change the
  80-call result, so the knob was not kept.
- Residuals (queued above): slow single-context convergence; same-band consumers read the last
  writer; no scenario feeds cascade evidence; arbiters are not exported.

## Rival arbitration for ctx.react (2026-11-20)

- [x] `DiscreteTransition` evaluates every cell, then arbitrates, then draws once per cell in cell
  order. Without a choice the arithmetic and RNG sequence are unchanged.
- [x] Candidates per overlapping cell are per-channel transition probabilities: each rival
  alone (the set's hazard/weight outputs recomposed from that rival only) and their cooperating
  combination (base odds without the set, plus each rival's change, renormalized above 1).
- [x] `RivalCandidates` moved to `DomainRouting.hpp`. `RivalArbitration` now writes the
  combination's index instead of -1. For `ctx.evolve` the sum total equals the unarbitrated rate,
  so results are unchanged.
- [x] `ctx.react` accepts `reference_hazards` and `report_arbitration`, keeps its own arbiter pool
  and reports `rival_arbitration`.
- [x] Results:
  - `trech_discrete_transition`, late calls 30–39: alternatives reach RMSE 0.0000 with a 0.00
    combined share; cooperation reaches RMSE 0.0000 with a 1.00 combined share.
  - A replay with the same evidence is byte-identical. A call with no evidence and no learned
    arbiter matches the plain call in state, draws and accepted transitions.
  - `trech_js_runtime`: after 40 graded calls, an ungraded call deploys a 32/32 split between the
    two laws.
- Residuals (queued above): no scenario feeds hazard evidence; intermediates and non-rival hazard
  writers are not arbitrated; arbiters are not exported.

## Rival arbitration for ctx.evolve (2026-11-19)

- [x] `StateEvolution` defers integration. For every routed element covered by two or more
  rivals of a set, it records each rival's total rate and the cooperating sum
  (`RivalCandidates`), and applies the choice an `arbitrateRivals` callback returns.
  Without a callback the arithmetic is unchanged.
- [x] `RivalArbitration` keeps one `MethodArbiter` per rival set (members and rated fields, no
  caller-chosen name). It is fed by `ctx.evolve`'s optional `reference_rates` and reported as
  `rival_arbitration`.
- [x] `trech_state_evolution`:
  - two rivals that are right in different context domains: the late selections reproduce the
    truth exactly and never use the sum;
  - two cooperating rivals: the sum is kept;
  - no evidence and no learned arbiter: byte-identical.

  The existing routing and evolution tests are unchanged.
- Residuals (queued above): `ctx.react`, `ctx.interact` and `ctx.predict` paths; no scenario
  with overlapping rivals; intermediates are not arbitrated; arbiters are not exported.

## Efflux closed-loop deployment (2026-11-22)

- [x] `testscenario_efflux` `learn_domains=deploy`: the frozen learner
  (`data/efflux_domain_learner/transport.json`, published from the 2026-11-18 campaign on seeds
  101 and 102 with `publish_domain_learner.py`) predicts each particle's new velocity and
  displacement rate and drives the bath; the transport operator runs on a copy from the same
  state and noise as a shadow, never applied. Particles with no finite prediction are counted
  `untouched`. The summary's `domain_learning.shadow` carries per-step RMSE (position and
  velocity), maxima and the RMSE per run third; `inference.transport_driver` names the driver.
- [x] Suite case `efflux_domain_learner_deploy_closed_loop` (run `out_efflux_learned_deploy`)
  pairs it with the operator-driven `out_efflux`. Thresholds were set before the runs: shadow
  RMSE below the pooled law's held-out RMSE, no growth from the first to the last third, every
  operator tolerance on the clearance observables, every scenario check.
- Results (6,000 ticks, 2026-11-22). Default seed: 11/11, 339,396 particle-steps all predicted,
  shadow RMSE velocity 0.00225 (pooled 0.0163) and position 0.0145 per tick (pooled ≥ 0.0361), by
  third 0.0144 / 0.0179 / 0.0074 (position) and 0.00223 / 0.00232 / 0.00221 (velocity), final
  waste 2 → 3, half-life gap 75 ticks (tolerance 600), largest waste-series gap 12 packets
  (reported). Seed 201: the same shadow figures, but 10/11, because the operator-driven run itself
  let one essential molecule cross (29/30 retained); the deployed run kept 30/30. That operator
  failure is queued in the [migrations roadmap](../../scenarios/migrations/ROADMAP.md#priority-queue).
  A deploy run takes 237 s against 12 s for the operator.

## Online response-domain learning (2026-11-18)

- [x] `DomainLearner` + `ctx.learnDomains` (`src/ml/DomainLearner.cpp`): online model-based
  recursive partitioning. Domains are created where one response law stops explaining a
  population; laws are weighted ridge over an affine/quadratic basis with LibTorch batched solves,
  plus an optional online LibTorch residual MLP. Splits come from feature, principal and
  residual-regressed directions with refined cuts, BIC + two-fold CV + material-variance gates and
  multi-call support. Same-law siblings merge, ids persist with lineage. Grading is prequential
  against a pooled law. Per-domain predictor selection by context runs over ridge, ridge+MLP,
  pooled and ridge+bias-tendency, with asymmetric extrapolation trust and a far-outside pooled
  rule. Change points come from own-law error with a fast window. Stationary reservoirs carry
  across runs; per-domain tendencies cover population, features, targets, error, value at the
  mean and raw-unit sensitivities. Export/warm start/frozen deployment is fail-closed;
  `interval_coverage` is reported.
- [x] `ComputeBudget` + `trech budget`: model capacity follows the host (threads, memory, measured
  LibTorch matmul rate); `TRECH_COMPUTE_BUDGET` pins it; specialists take `--width/--epochs auto`.
- [x] `ctx.evolve` `report_rates`: per-element pre-bound rates, so learners learn laws, not clamps.
- [x] Block-wise density discovery for `ctx.detectDomains` up to 65,536 rows per parent.
- [x] Scenarios: furnace `learn_domains=learn|evaluate|deploy`, lava lamp and efflux
  `learn|evaluate`; `js/trech_domain_learning.js` (agreement/ARI, accumulators, rate application).
- [x] Tooling: `trech_torch.domain_learner` (extract, NumPy twin replay, offline PyTorch residual
  specialists with temporal holdout), `study_domain_learning.py` campaigns for the three scenarios.
- Verification (2026-11-18): CTest `trech_domain_learner`, `trech_domain_learner_numpy`
  (6.7 × 10⁻¹⁶), `trech_js_runtime`, `trech_state_evolution`, `trech_cli_parse`. Default runs of the
  furnace, lamp and efflux are byte-identical to HEAD's scenario sources with learning off.
  Results and the faults found live in the
  [domain study](../../../docs/inference/multiscale_domain_study.md#online-response-domain-learning).
- [x] Warm-started learners no longer re-serialise their stored state every call (options are read
  only on creation); this fault stalled the second efflux training run for 3+ hours. Efflux campaign: training on
  seeds 101/102, frozen held-out seed 201 at 73–78% (position rate) and 85–91% (velocity) steady
  gain vs pooled, parity 4.4 × 10⁻¹⁶; 23/24 specialists accepted. Purity is not independent there
  (fate flags are inputs) and the learner hit its 24-domain capacity.

## Engine architecture generation (2026-11-17)

- [x] `trech arch <job.json>` and `ArchitectureGenerator` in `trech_ml`:
  - a classic reference family trained natively and deterministically;
  - the Evolvo GFSL-NN worker launched as a subprocess (`posix_spawn`, timeout, request SHA-256
    binding), seeded with the classic genomes;
  - the engine re-scores the evolved model and keeps it only if it beats the reference;
    a losing model keeps the reference. Since the mandatory-LibTorch change, every other
    outcome fails the job (see below). The engine-native-only mode and the classic fallback
    were removed then.
  - Contract in [`docs/inference/evolvo_architectures.md`](../../../docs/inference/evolvo_architectures.md#in-the-engine-trech-arch).
- Verification:
  - CTest `trech_architecture_generator` (fake workers cover accept, lying-reject, mismatch,
    unavailable, crash and timeout), `trech_architecture_evolvo_live` and `trech_cli_parse`.
  - Synthetic job (300/100/100 rows, after the plateau fix): the classic `mlp2` selection MSE
    is 0.00516 (test R² 0.994 / 1.000). Evolvo's TorchScript `mlp(32, depth 4)` + `concat`
    reached 0.000252 (R² 0.9996 / 1.0000) in both the Release and the dev Debug build
    (2026-11-18), and the engine re-scored it itself before accepting it.
  - Fixed (2026-11-17): the classic trainer and Evolvo's `PlateauStopper` stopped slow, steady
    descent as a "plateau". The classic `mlp2` above used to stop at MSE 0.122. Progress is now
    measured from the last counted improvement.
- Residual (queued above): run-directory jobs and Geant4 data; a scenario/JS entry point and
  store registration; set-input classic structures; a native `joint` domain; learned native
  stopping; Windows bridge.

## Domain routing (2026-11-18)

- [x] Unnamed, dynamically detected element groups for `ctx.evolve` and `ctx.react`
  (`DomainRouting.hpp`, `StateEvolution`/`DiscreteTransition` `routeByDomain`, JsRuntime
  selection). An undeclared call over several kinds of one role, or over unlabelled operator
  models, selects the pool and routes per element. Same-band stages with a shared output are
  rivals, and a rival runs only where its training-domain check covers the element's current
  context. Decisions climb the bands in execution order, so upper bands see lower-band
  intermediates. Groups are paths of covering rivals with content-hash ids. Uncovered elements
  stay untouched and counted. `group_by: "declared"` keeps the old ambiguous verdict, and calls
  that already selected are byte-identical.
- Verification: `trech_state_evolution` covers a nano→meso ladder with separate regimes,
  cooperating rivals, an uncovered meso step, an element outside every nano domain, content ids
  and determinism. `trech_discrete_transition` checks that routed hazards reproduce the labelled
  per-material result, and `trech_js_runtime` exercises routed selection, `group_by`, unlabelled
  models and the error path.
  Re-running glass from sand (default and set conduction), efflux, the H2O cycle and
  polyurethane foam reproduced the suite's hook emits byte for byte (the H2O cycle apart from
  PubChem `fetched_at_utc`). Dev CTest passed 64/64.
- Residual (queued above): uncovered regimes do not yet trigger experiment planning or generation;
  routing summaries are not in run outputs; `ctx.interact` did not route (routes since 2026-11-20); overlapping non-rate
  outputs are last-writer-wins.
- [x] Routing domains and the first routed scenario (2026-11-18):
  - `GenericSurrogate` loads an optional `routing_domain`, and malformed blocks fail closed.
    `DomainRouter` adds it to coverage and applies the envelope + nearest gap rule.
  - `trech-measure-routing-domain` (`trech_torch.routing_domain`) measures the block from
    harvested rows and records the runs and tag beside it.
  - The five glass-furnace thermal/chemistry operators (both families) carry `melt_fraction` +
    `glass_silica_fraction` routing domains, measured from the scenario's teacher harvest at
    1500/1600/1700/1750/1880 K (`emit_training_rows`).
  - Measured ranges: batch melt fraction 0–0.492, converted silica 0; melt 0.512–1, 0–0.8;
    glass 1, 0.9.
  - `glass_from_sand.js` `grouping: "domain"` names no material for thermal and chemistry.
- Verification (2026-11-18):
  - At the default 1750 K, routing agrees with the scenario's classifier on 100% of 259,200
    routed cell evaluations (8 boundary-gap cells ran the nearest law).
  - Every observable equals the declared run's, and the 31,223 glass-cell chemistry
    evaluations stay unclaimed.
  - The declared run's hook emits are byte-identical to before.
  - At 1560 K (never measured) and with the reference family, observables are identical. With
    set-network conduction, 2 cells at melt fraction 0.49965 went to melt (nearest-gap boundary)
    and observables are identical.
  - The 1820 K difference came from declared chemistry reading the material class before its
    thermal update. After correcting the call order, all eight observer values match and the
    two-mode comparison is a regression case.
    [Process roadmap](../../scenarios/processes/ROADMAP.md#priority-queue).
  - Validation 63 cases: 60 pass, 3 info. CTest 65/65 including `trech_routing_domain`. Model
    audit and fresh-run re-check reports regenerated (identities only; verdicts unchanged).

## Live statistical domain subdivision

- [x] 2026-11-18: `ctx.detectDomains` uses projected gaps and LibTorch PCA to recursively
  partition the live feature rows, optionally inside the groups reported by `ctx.evolve` or
  `ctx.react`. Subdivision paths identify leaves within one call. Predictive-mode diagnostics
  emit once per frame when `detect_domains=true` in the furnace and lava lamp.
- Live C++/NumPy assignment parity over 98,400 element snapshots in 440 frames, including
  1750 K / 1560 K furnace runs and the nominal / 315 K, 90 s lava-lamp runs. Ordinary hook emits
  match the paired runs byte for byte. The lamp's initial four droplets were recovered after
  adding a conservative diagonal fallback for overlapping projected axes. The default lamp's
  projected group count matched the separate distance-based topology count on 54 of 121 frames.
  Nominal scenario checks passed 11/11 (furnace) and 19/19 (lamp). The shortened cool-lamp run
  passed 12/19 full-cycle checks, identically with discovery enabled and disabled. Dev CTest 65/65.
- [x] Screened a frozen within-parent split for specialist training. Five whole furnace runs
  furnished 12,539 formed-glass teacher rows. A gap at 1662.4–1725.3 K split the training data;
  all 2,088 hotter rows came from the 1880 K run. A 161-parameter pooled MLP and two 81-parameter
  MLPs were compared on fresh 1560 K and 1820 K runs. At 1820 K, 536 rows landed inside the
  training gap and RMSE rose from 0.00396 to 0.434 K/s under the two-model candidate. Least
  squares fit the underlying teacher to numerical precision. The candidate stays experimental.
  See [the reproducible validation](../../tooling/validation/AGENTS.md#statistical-domain-validation).

- [x] Density-connected discovery resolves overlapping projections. The lava lamp preserves
  spatial units with a shared distance scale and emits persistent domain IDs with predecessor
  counts. NumPy reproduced 38,400 assignments in 147 frames and the complete lineage on three
  lamp configurations. All paired ordinary emits were byte-identical.
- [x] The projected-gap trainer freezes recurring populations and dispatches named TorchScript
  specialists in LibTorch. On two withheld CHNO energy grids it selected both atomic experts.
  The furnace thermal teacher selected the pooled affine fit. See the
  [multi-scale domain study](../../../docs/inference/multiscale_domain_study.md).

## Required LibTorch (2026-11-18)

- [x] LibTorch is a required dependency, so development validation never runs on a simplified
  learning path:
  - CMake: `TRECH_ML_BACKEND` (only `torch`; the seam for a future library) replaces
    `TRECH_ENABLE_TORCH`, `Torch_DIR` defaults to `thirds/torch`, and configure fails unless
    LibTorch is found and `TRECH_ML_PYTHON` imports torch + NumPy.
  - Engine: the `#ifdef` torch branches are the only code; the per-event tensor mirror in
    `OnlineEventStats` and its `event_feature_stats_torch_backed` score were removed.
  - `trech arch`: `generator` is `evolvo` (default) or `classic`. Any Evolvo failure
    (`not_started`, `unavailable`, `mismatch`, `no_result`, `timeout`, `error`) sets
    `ok = false`, `generator = "none"`, no model, non-zero exit. A losing evolved model keeps the
    classic reference (`ok = true`). `auto`, `require_engine_native` and the worker's
    `engine_native_only` were removed and are refused.
  - Tests: CTest torch tests use `TRECH_ML_PYTHON` and fail instead of skipping;
    `scripts/run_validation_suite.sh` runs every Python step through the same interpreter.
- Verification (2026-11-18, macOS ARM64, LibTorch 2.14.1, torch 2.8.0 in `build/render-venv`):
  - `build/dev` (Debug, Geant4) CTest 64/64; `build/torch-check` (Release, no Geant4) 57/58
    before the purity index was regenerated.
  - Full scenario suite (`scripts/run_validation_suite.sh`, about 1 h 40 min): 62 cases,
    59 pass, 3 info, 0 fail/skip. `data/optics_surrogate_ridge.json` re-exported byte-identical.
- Residual: none specific to this change. The bulk-water Green-Kubo drift seen in the same run
  is queued in the [validation roadmap](../../tooling/validation/ROADMAP.md#priority-queue).

## Recursive group lifting (2026-11-17)

- [x] `GroupHierarchy` + `ctx.lift`: a population is lifted scale by scale. Each level partitions
  the current elements (lattice `cell_size`, explicit ids, or all) and runs a trained v3 set
  network carrying `group_lift` on every group's members. Groups become the next level's elements
  (outputs + learned latents, weight-centroid, summed weight). Member geometry is synthesized as
  dimensionless `rel_x/y/z`. Over-capacity groups and groups with blocked members are blocked,
  never truncated. Missing features/context/positions stop the hierarchy with a named reason.
  Out-of-domain and starved lineage propagate to the observer. Without `levels`, the engine plans
  the hierarchy from declared `operator_role: "group_lift"` models by scale. Contract:
  [`docs/inference/group_hierarchy.md`](../../../docs/inference/group_hierarchy.md).
- [x] Trainer `trech_torch.hierarchy` (`trech-train-hierarchy`): all levels end to end in torch,
  each on the chain's own predictions, with mixed supervised/latent outputs, whole-run selection
  early stopping, chained holdout and a run-level interval measured on the exported JSON.
  Training is tooling-owned ([training roadmap](../../tooling/training/ROADMAP.md#recursive-group-hierarchies-2026-11-17)).
- [x] Verification: C++ parity with the NumPy reference at every level ≤ 1e-9 on a committed
  DeepSets/MPNN/DeepSets fixture (CTest `trech_group_hierarchy`), plus blocking, lineage, order
  invariance and loader rejections. `trech_group_hierarchy_py` and the `ctx.lift` case in
  `trech_js_runtime` also pass. The fixture regenerates byte-identically on this machine.
- Synthetic demonstration (architecture only, not physics): 500 train / 100 selection / 200 held-out systems, chained held-out R² cell 0.938 / block 0.718 /
  system 0.530, run-level 90% intervals with the guarantee (9 runs). The learned system level is
  **worse** than g × Σ of its own predicted block energies (R² 0.620; 0.875 with true block
  labels). The cross-scale correction does not yet pay for itself, and the block level is the
  bottleneck. A first 800-system DeepSets run without early stopping overfit (system 0.35). See
  [the demo record](../../../docs/inference/group_hierarchy.md#synthetic-demonstration-architecture-only).
- [ ] Residuals, queued above: no Geant4-harvested hierarchy and no scenario user; no
  propagated per-group uncertainty; groups do not see neighbouring groups; one fixed lattice per
  level.

## Cascade dependency trust

- [x] Final per-output uncertainty and measured coverage (2026-11-16).
  `ctx.cascade` reports RMSE and marginal interval metadata from each prediction's last
  successful producer, and `null` when both are unavailable. Briggs–Rauscher, polyurethane,
  elephant's toothpaste, the lava lamp and the water/n-pentane beaker now disclose this
  evidence through the cascade metadata. Their illustrative response maps no longer emit
  authored uncertainty columns. The R2 work above tracks training and held-out validation.
  Debug CTest passed 57/57. The five focused scenario validators passed on fresh strict-config
  runs, including the lava-lamp horizon/precision/heater controls and the Release polyurethane
  gravity pair. The committed all-family physics report was left as a historical snapshot.

- [x] Generic v2 sigmoid inverse links support fraction outputs alongside identity/exp,
  with stable finite-logit saturation and atomic rejection of non-finite encoded values.
  The trainer's explicit `--logit-outputs` rejects endpoint/non-finite labels and overlapping
  transforms, and reports held-out errors in decoded units. Bounding a fraction is a numerical
  invariant, not an accuracy or calibration claim; learned observer validation remains separate.

- [x] Out-of-domain evidence now propagates through the actual consumed facts even when a
  lower-stage output fits a later model's numeric hull. The trace distinguishes local coverage
  from inherited evidence; hook OOD accounting uses both. See the
  [trust workstream](trust/ROADMAP.md#dependency-trust-propagation) for semantics, regression
  coverage and the remaining cross-call/persistent-state lineage gaps.
- [x] Starvation (per-feature or joint) and off-trained-band evidence also follow consumed facts,
  with separate effective/local fields and sorted inherited input names. Their stage counters
  include inherited evidence; hull-domain/OOD accounting remains independent. See the same
  trust workstream for regression coverage and validation limits.

## 2026-10-18 — real input dependencies and continued 3D replay parity

- **[landed] No implicit zero physics.** `ScaleCascade`, `StateEvolution`, `DiscreteTransition`
  and `PairInteraction` skip predictions whose declared inputs are absent. Intermediate availability
  is tracked per element/pair and material kind, so registering a producer for one material cannot
  supply fake zeros to another. Traces retain `missingInputs`; only actual evaluations count as
  `ran`/inferences, and blocked discrete evaluations consume no draw. Neighbours have no persistent
  pair state unless linked; link geometry requires supplied positions. Explicit numeric zero inputs
  remain valid. Regression coverage includes biased missing-input models and material-local chains.
- **[landed] Point inference starts from Geant4 context.** `ctx.predict(name, features?)` now uses
  ambient event/material/optics facts just like cascade/operators. The surrogate demo replaces its
  fixed water density/composition with live Geant4 element mass fractions and density, waits for
  material initialization, and exposes a water/ethanol material control with a paired validation gate.
  This grades input sensitivity/provenance, not new accuracy validation for ethanol.
- **[landed] Studio radius/bond replay.** Emitted radii draw instanced sphere meshes, declared
  bonds follow held-frame centres, camera bounds include radii, and non-mm streams hide the
  unrelated Geant4 mm scene. GPU frame caches are bounded; malformed bond rows are dropped.
- **[validated]** `ctest --preset dev` 17/17; Studio's pure/UI suites and four Mac-GPU
  animation/capture tests pass. A real molecular-run capture was visually checked. Refreshed
  `docs/validation/validation_report.{md,json}`: 49 cases, **42 pass / 0 fail/error / 4 info / 3 skip**;
  efflux, H2O-cycle, polyurethane and glass operator/reference gates all pass. The skips are the
  slow bulk-water, diffusion-temperature and shaken-glass scenarios; they were not rerun here.
- **[landed] Offline validation inputs.** `PUBCHEM_MODE=cache-only` preflights the selected
  local records and skips network refresh, failing before builds/output deletion on incomplete
  inputs. Default online behavior remains. See the [validation contract](../../tooling/validation/AGENTS.md).
- **[open] Training remains the larger gap.** This change removes fabricated missing-input
  predictions and one fixed feature vector; it does not replace the scenario migration ledger's
  authored material laws or turn distilled/illustrative maps into Geant4-trained response models.
  Continue the foam/CNT/resonance/chemistry migrations with independent data and observer gates.
- **[open] 3D parity remains partial.** Vectors landed 2026-10-19; moving apparatus/meshes, chart/label/grid overlays,
  stream selection, unit-labelled scale bars and transparent-sphere sorting remain in
  [desktop milestones](../../studio/ROADMAP.md#studio-desktop-ui). Sphere tessellation and bond line width are representation choices.

The standing objective retains its original baseline and dated landings. Current runtime contracts are in the [inference handbook](AGENTS.md); the [process workstream](../../scenarios/processes/ROADMAP.md) records later artifact and binding extensions.

## Multi-scale statistical inference (standing objective — the core engine thesis)

**This is the reason TRECH exists**, and like anti-degeneration it is a **primary, never-"done"
goal**: every iteration should make the statistical/ML layer predict *more of a context
automatically*, cascading a precise Geant4 particle/nano base up the dimension ladder
(atomic → nano → micro → meso → macro) to the scale of the observer/experiment — so a user can
pose a macroscopic question ("what does this glass of water do while I stir it — the fluid
motion, the waves?") and get an answer inferred from the microscopic truth, **without
hand-specifying every intermediate model** (only overriding when they *want* to be specific).

### The gap we are closing

Today the ML in the tree is **narrow point-predictors**: `OpticsSurrogate` (composition→n), the
event stratifier (features→p(exceptional)), and per-call `ctx.predict(name, features)`. Each is
correct, but each predicts *one hardcoded quantity the scenario must ask for by hand*. That is
"statistics used only for certain too-precise operations" — the opposite of a general-purpose
engine that predicts everything relevant in a context by default. The **cascade** is the bridge
from the former to the latter.

### Foundations landed

- **[landed 2026-07-05] Scale-cascade subsystem (first cut).** `ScaleCascade`
  (`include/trech/ml/ScaleCascade.hpp` + `src/ml/ScaleCascade.cpp`) chains the scenario's
  declared models **by scale band** into one deterministic pass: seed the context with
  Geant4-derived facts, evaluate stages in ascending scale order, and each stage's named
  outputs merge into the context so the next-higher scale consumes them automatically. Exposed
  to hooks as `ctx.cascade(seed) -> {...context, __cascade{stagesRun, trace}}`; the per-model
  band is a new physics-agnostic `ModelConfig.scale` (`atomic/nano/micro/meso/macro`, unscaled
  runs last, conditionally serialized so existing config hashes hold). Strict-mode-gated,
  counts each ran stage as a `hook_predict_count` inference, degrades to the bare seed when no
  models load. Guarded by `tests/test_scale_cascade.cpp` (C++, Geant4-free: chaining, scale
  ordering independent of declaration order, missing-input recording) and a two-stage
  `ctx.cascade` case in `tests/test_js_runtime.cpp`. This is the *plumbing* for the doctrine;
  the models that ride it are the ongoing work below.

### Workstreams (rotate through these; each iteration should push at least one)

1. **Seed the cascade from Geant4 automatically. [landed 2026-07-11]** `ctx.cascade()` now
   **auto-seeds from the ambient Geant4 base** with no argument: `buildAmbientGeant4Seed` in
   `src/js/JsRuntime.cpp` populates the seed from the active hook context's per-event tallies
   (`edep_mev`, `track_length_mm`, `step_count`, `track_count`, `optical_photon_{steps,tracks,
   track_length_mm}`) and, when the scenario opted into `materialProbe`, the material probes
   (`material.<name>.{density_g_per_cm3, electron_density_per_cm3, mean_excitation_energy_ev,
   radiation_length_mm, number_density.<Element>}`). An explicit `ctx.cascade(seed)` argument
   still overrides/augments per key (override-on-demand), and the seed keys are surfaced on
   `__cascade.seedKeys` (sorted) for provenance. The bottom of the ladder is now *always* the
   real Geant4 base — the scenario copies nothing by hand. `cascade_multiscale_demo.js` was
   switched to the argument-free call (physics identical: edep 1 → `ionization_density` 0.6 →
   `bulk_response` 2.4). Deterministic (pure function of the numeric Geant4 facts), strict-mode
   still returns null. Guarded by a new argument-free `ctx.cascade()` case in
   `tests/test_js_runtime.cpp` (ambient event + material seeding, seed-key provenance).
2. **Train real chained stages, not toy ones.** Land at least one genuine two-band chain where a
   lower-scale surrogate trained on Geant4 output feeds a higher-scale one (e.g. material EM/optical
   facts → droplet/bulk property → observable). Reuse `trech-train-surrogate` per stage; validate
   each band held-out (LOO / beats-baseline), and gate promotion like the optics ridge.
   **Bounded real chain now exists:** the shared CHNO atomic/nano Geant4-table response is extended
   by `particle_observer_cascade` to a Geant4-MC-trained meso transport observer. It predicts
   transmission and deposited-energy fractions from lower learned outputs before a comparison
   run, with no attenuation/deposition formula supplying either target or runtime behavior.
   A failed first campaign remains archived; 192 fitting / 12 explicit development / 18 untouched
   whole-composition/energy/geometry final cases pass unchanged acceptance gates. Fresh Geant4
   realizations pass too. [Details and limits](../../../docs/inference/particle_observer.md).
   **Still open:** fourteen of eighteen fresh observer queries are per-feature-starved and five
   jointly starved, despite passing bounded error checks. Sample those gaps and reserve fresh
   independent conditions before broader promotion. Physical measurement validation, varied
   density/geometry/source context, other families and general chemistry/state dynamics remain open.
   Verification: Debug and Release builds / CTest **38/38 each** pass. CTest's Python self-skips
   two NumPy numerical gates; both pass separately in the existing render Python environment,
   including actual Python TorchScript link parity. The optional C++ LibTorch matrix, other
   platforms and full manual all-family physics suite were not rerun; committed broad physics
   reports were not refreshed. Dedicated observer manifests/manual reports carry the new evidence.

3. **Coverage/uncertainty per band:** follow the [trust workstream](trust/ROADMAP.md#workstream-3--coverage-and-uncertainty) for the full mechanism, remaining adoption and calibration work. Independent event resim policies now act on starvation and wrong-scale evidence; automatic resimulation/retraining remains open.
4. **Worked cascades across the scenario families — NOT just optics/fluids.** The cascade is
   domain-agnostic; land real per-band chains in several families, not one. The canonical thesis
   example is the "glass of water" (fluid movement/waves inferred from a Geant4-derived
   microscopic base). **[canonical glass-of-water landed 2026-07-11]**
   `examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js` pours ~1 L of water into a wide glass and shakes
   it, answering the thesis question directly: a short rigid-SPC/E nano MD **measures** water's
   number density (0.0334/Å³) and hydrogen-bond coordination (≈4.86, g(r) peak 2.77 Å),
   `ctx.cascade` lifts those facts **nano→micro→macro (3 bands in one pass, zero hand-wiring)** into
   the macroscopic fluid parameters, and a Position-Based-Fluid solver (uniform spatial grid,
   ~4,300 particles at ~6 mm) plays three phases the video shows — **pour** (water falls from a
   faucet and fills the tumbler), **settle**, **shake** (smooth-but-random) — with waves and
   splashes that stay contained (mass conserved) and stable. **No macroscopic water property is
   hand-typed**: the rest density comes out at 999.2 kg/m³ (a *grounded* n→ρ coarse-graining, 0.10%
   off measured water — a check, not an input), and the cohesion (which merges drops on contact,
   drawn as a **2 mm metaball isosurface**) + viscosity come from the measured coordination.
   Illustrative stage models under `data/glass_cascade/` (density grounded, cohesion/viscosity
   labelled illustrative — same honesty as `cascade_demo`); rendered by
   `tools/viz/demos/render_glass_of_water_shaken.py`; guarded by `glass_of_water_shaken_waves`
   (category `fluid`). **Chemistry now has a cascade too (landed 2026-07-25):**
   `examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js` lifts the Geant4-built reagent/mixture
   materials + declared recipe through a two-stage cascade (`data/briggs_rauscher_cascade/`) into
   the coefficients of a reduced FKN/Oregonator oscillator; the oscillation (8 colourless→amber→
   deep-blue cycles, amber-before-blue, ~10.5 s period, settle on reagent depletion) is emergent,
   not typed, and guarded by `briggs_rauscher_oscillation` (category `chemistry`, 10/10). **Two
   reactive-foam cascades landed 2026-07-25:** `examples/scenarios/polyurethane_foam/polyurethane_foam.js`
   (`data/polyurethane_cascade/`; dual gel+blow reactions → 26.9× expansion, cream→gel→solid
   ordering, rigid porous endpoint; guarded by `polyurethane_foam_expansion`, 15/15) and
   `examples/scenarios/elephants_toothpaste/elephants_toothpaste.js` (`data/elephants_toothpaste_cascade/`;
   iodide-catalysed runaway → 8e4× acceleration, 18.4× steaming lather eruption, drains and never
   solidifies; guarded by `elephants_toothpaste_eruption`, 16/16) — the pair demonstrates emergent
   *consistency* (rigid sponge vs soft lather) from the same doctrine, and — since the foam
   mechanics upgrade — emergent **gravity/imperfection consequences** (leaning, cracking, shedding
   pieces onto the table) graded against a zero-gravity control. Still open
   on this workstream: biology (efflux/osmosis cell observables), CNT electronics
   (gap→device→logic), and magnetic resonance (proton density→image) each have the same
   micro→observer arc and should get a cascade too, and the chemistry + fluid stage models should
   graduate from illustrative maps (Briggs–Rauscher's macro response surface is a compact
   illustrative map, as are the polyurethane and elephant's-toothpaste response surfaces.
   A wider trained reactive-foam / catalytic-kinetics
   panel is the follow-up) to **trained, held-out-validated** per-band chains. See the
   scenario-family table in the AGENTS.md "Multi-scale statistical inference" doctrine.
5. **Default-on, override-on-demand.** Progress the API so a scenario opts into "predict the
   relevant behaviour for this context" and only specifies models/scales when it wants to
   constrain them — the "without requiring to be specified (if not forced by user)" target.
   **[per-material dynamic selection landed 2026-08-15]** The inference level is no longer fixed
   for a run: `ctx.evolve`'s `element_kind` accepts a per-element array, and the engine selects an
   operator **per material** from that material's own context, binding each group's stages to its
   own elements (`EvolutionStage.elementKindIndex`). Two materials sharing one state array are
   advanced by different trained operators in the same deterministic pass; a material that selects
   nothing is reported (`selection.groups[]`, run status `partial`) and left **bit-identical**
   rather than being pushed through another material's law, and `hook_predict_count` grows by
   matched element-stages only. Guarded by `tests/test_state_evolution.cpp` (per-kind operators,
   an unclaimed kind, a kind-free stage composing with per-kind ones) and a JS-boundary case in
   `tests/test_js_runtime.cpp`. **[extended 2026-08-15]** the same per-element kind selection now
   covers `ctx.react` (an unclaimed cell consumes no RNG draw and mutates nothing, so the other
   cells' seeded draws are unaffected), and `ctx.interact` selects per canonical **pair kind** —
   the engine composes the unordered material combination (`melt|sand`) from the two members and
   binds each stage to one combination, because a grain-grain, a grain-melt and a melt-melt contact
   are three different interactions. Every operator now reports its per-kind groups, and each stage
   trace carries the kind it served and how many elements/pairs it actually evaluated. Guarded by
   new groups in `tests/test_state_evolution.cpp`, `tests/test_discrete_transition.cpp`,
   `tests/test_pair_interaction.cpp` and the JS-boundary case in `tests/test_js_runtime.cpp`.
   **Landed with a scenario that needs it:** `examples/scenarios/glass_from_sand/glass_from_sand.js` ([material-creation milestone](../../scenarios/processes/ROADMAP.md#2026-08-15-material-creation-a-run-that-makes-a-new-material)).
   **Remaining:** the stage models there are hand-authored illustrative maps — a *trained*
   per-material chain is still the open workstream-2 gap.
6. **Move the hard-coded per-element physics/chemistry OUT of scenario JavaScript and into
   engine-side trained inference. [mechanism + first trained operator + paired fidelity gate
   landed 2026-07-25; broader operators pending]** See the [engine-side operator workstream](../operators/ROADMAP.md#engine-side-inference-operator--removing-hard-coded-js-physicschemistry).

### Cascade metrics to watch (regression signals)

- **Scales bridged in one run**: how many distinct bands a single cascade chains (baseline
  narrow-ML = 1). Growth here is the headline signal that the engine is becoming multi-scale.
- **Hand-wired predictions eliminated**: fraction of a scenario's predictions that come from
  `ctx.cascade` (auto-chained) vs. individual hand-built `ctx.predict` calls.
- **Per-band held-out accuracy** and **fraction of stages flagged low-confidence** (once
  workstream 3 lands) — so a longer cascade cannot silently trade accuracy for reach.
- **Stages flagged jointly starved** (in range on every axis, far from any training point) and the
  count of committed models that carry a joint reference at all — an unchecked model is not a clean
  one. `plan_experiments --models` converts both into the operating points to simulate next.
  The generated [model audit](../../../docs/validation/ml_model_audit.md) tracks the count (14 of 50 on
  2026-11-11) together with complete/partial/absent trust profiles (14/8/28).
- **Fraction of final cascade outputs with held-out RMSE or a calibrated interval** is recorded
  as `measuredUncertaintyFraction` and carried into the affected validation cases. A zero fraction
  means predictions ran with no recorded error metrics. A null fraction means no predictions ran.
- **Model evaluations per second** (the inference core is now the inner loop of operator-backed
  scenarios: a polyurethane run performs 2.8M evaluations). Reproduce with the `-O2` A/B harness in
  the [batched-inference-core entry](../operators/prerequisites/ROADMAP.md#engine-prerequisites--land-in-this-order); a regression here shows up as run time, not as a wrong
  number, so nothing else will catch it.
