# Scenario law migration ledger — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Operator migration contract](../../engine/operators/migration/ROADMAP.md) · [Operator migration prerequisites](../../engine/operators/prerequisites/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

- [x] Register the learned `particle_observer_cascade` property-only hook in the audit inventory.
  Its experimental observer gates and coverage residuals belong to [inference](../../engine/inference/ROADMAP.md);
  no state-dynamics migration is claimed by that property pass.

Apply the [shared migration contract](../../engine/operators/migration/ROADMAP.md) to every row. Shared engine prerequisites are tracked [separately](../../engine/operators/prerequisites/ROADMAP.md).

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P1** · R3 · Row 2 — CNT material → device → circuit cascade (cheap deterministic scenarios with validation cases). ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P1** · R3 · Row 3 — magnetic-resonance forward dynamics. ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P1** · R3 · Row 6 remainder — osmosis membrane response: replace the authored `integrateMembrane` pressure/area/bending law with membrane-node operators (efflux promoted 2026-07-26; osmotic particle velocity response and channel passage promoted 2026-11-26). It is the run's hot path (642 vertices × 6 substeps × 6,000 ticks), so cost the per-substep inference before choosing the operator's granularity. ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R3 · Seed-averaged osmotic pair: `osmotic_operators_match_reference` grades one trajectory per side, so its water/shrink tolerances (10 molecules, 0.20) are set from a three-seed sweep. Over seeds 31073101/101/202 the operator's mean shrink was 0.43 against the reference's 0.49 (0.405/0.324/0.550 vs 0.423/0.500/0.557), a possible low bias from the motion operator's residual glucose drift (≈0.013). Grade the means over ≥8 seeds per side and tighten the tolerances. ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R2 · The osmotic operators take no particle-derived input: the bath runs on a 0 MeV geantino and the velocity and passage responses are distilled from the authored teacher alone. Condition them on Geant4-derived material facts, as the efflux crossing operator does with attenuation coefficients and event activation. ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P3** · R3 · The osmotic channel-passage operator's clamped verdict is inexact for 23 of 178,761 fresh rows more than 0.05 from the size threshold, all of them a very small (radius ≈0.2) wrong-polarity molecule in a very wide channel (≈1.15). No declared species is there; fix it before the queued pore-width runs reach that corner. ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R3 · The promoted efflux operators let one essential (retained) molecule cross at seed 201 (29/30 retained, `essentials_retained` false; found 2026-11-22 while pairing the closed-loop deploy run). The suite runs only the default seed, where 30/30 hold. Grade the crossing operator's selectivity over several seeds and fix the leak in the operator, not with a JS guard. ([detail](../../engine/inference/ROADMAP.md#efflux-closed-loop-deployment-2026-11-22))
- **P2** · R3 · Row 4 — catalytic and oscillatory chemistry (elephant's toothpaste, Briggs–Rauscher). ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R3 · Row 7 — lava lamp and two-liquid phase/transport (needs the bounded integrator prerequisite). ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R3 · Row 8 — molecular water, PBF water and pressure baths (needs the bounded integrator prerequisite). ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))
- **P2** · R3 · Row 1 — polyurethane mechanics and shared foam bonds (candidate implemented, promotion failed). ([detail](#scenario-migration-ledger--exact-authored-laws-and-learned-targets))

## Scenario migration ledger — exact authored laws and learned targets

Work through this order to rotate families while adding only the shared machinery each later row
needs.

- [ ] **1 — Polyurethane mechanics and shared foam bonds**
  ([`polyurethane_foam.js`](../../../examples/scenarios/polyurethane_foam/polyurethane_foam.js),
  [`trech_foam_solver.js`](../../../js/trech_foam_solver.js)).
  **Local constitutive candidate implemented, not promoted (2026-10-19):**
  `referenceApplyMechanicsCoupling` (creep, drag and strength, including
  `1 + 2000*rigidity²` and the `4e6` drag ceiling) has an opt-in per-parcel meso operator
  conditioned on chemistry state and inferred context. Log-space drag + generic C++ decoding
  address the target's five-order range; growth is a derivative of the expansion state.
  Nominal height/lean and hot lean still fail the separate seven-observable promotion gate
  despite R²≥0.998 ([candidate details](../fluids/foams/ROADMAP.md#2026-10-19--learned-constitutive-candidate-and-3d-vector-replay)), so the comparison law remains the default.
  Next improve full-trajectory fidelity with independent conditions/seeds and independent physical
  response data. Then represent each persistent foam bond as an element and
  replace authored rest-length growth, Maxwell creep, failure strain and material contact response
  with bond/operator outputs. Keep neighbour construction, equal-and-opposite application,
  gravity, contact projection and ground/wall geometry as reusable numerical machinery. Extend
  `polyurethane_operator_matches_reference` to mechanics observables (rise/lean, broken-bond
  fraction, detached/table parcels, stress and volume) and run the same solver gate through
  elephant's-toothpaste.

- [ ] **2 — CNT material → device → circuit cascade**
  ([`cnt_band_structure.js`](../../../examples/scenarios/cnt_band_structure/cnt_band_structure.js),
  [`cnt_logic_gates.js`](../../../examples/scenarios/cnt_logic_gates/cnt_logic_gates.js)).
  Replace `tubeProps` (diameter/chiral-angle/zone-folding and curvature gap),
  `makeDevice`/`fetG`, the hand-authored Fermi turn-on transfer curve and temperature-dependent
  `exp(Eg/2kT)` on/off response with trained atomic→nano→micro stages. Inputs are chirality,
  Geant4 material/composition probes, temperature, gate/bias context and device geometry; targets
  are diameter/chiral descriptors, band gap/metallicity confidence and device conductance/leakage.
  Keep circuit topology, series/parallel composition, voltage division and Boolean truth-table
  grading declarative. Add independent held-out chiralities and temperatures to
  `cnt_band_structure`/`cnt_logic_gates`; require that device and logic stages consume lower-stage
  outputs rather than repeated JS formulas.

- [ ] **3 — Magnetic-resonance forward dynamics**
  ([`testscenario_magnetic_resonance.js`](../../../examples/scenarios/testscenario_magnetic_resonance/testscenario_magnetic_resonance.js),
  [`testscenario_magnetic_resonance_imaging.js`](../../../examples/scenarios/testscenario_magnetic_resonance_imaging/testscenario_magnetic_resonance_imaging.js),
  [`testscenario_magnetic_resonance_tissues.js`](../../../examples/scenarios/testscenario_magnetic_resonance_tissues/testscenario_magnetic_resonance_tissues.js),
  [`testscenario_magnetic_resonance_brain.js`](../../../examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js)).
  Replace `blochPulseResponseMxy`, `curieMagnetization`, hand-authored exponential FID/T2* envelopes
  and the forward `synthesizeReadout` signal with per-isochromat/voxel atomic→micro evolution over
  `Mx,My,Mz`, conditioned on Geant4-derived proton density, B0/B1, detuning, pulse duration,
  T1/T2/T2* and temperature. Tissue and brain scenarios consume the same operator; do not make
  tissue-specific C++ branches. Keep seeded measurement noise, Fourier/DFT reconstruction,
  peak/T2 fitting and image-quality metrics as signal processing. Extend
  `magnetic_resonance_water`, `magnetic_resonance_tissue_contrast`,
  `magnetic_resonance_image_line` and `magnetic_resonance_brain_image` with paired frequency,
  relaxation, contrast and localisation gaps.

- [ ] **4 — Catalytic and oscillatory chemistry**
  ([`elephants_toothpaste.js`](../../../examples/scenarios/elephants_toothpaste/elephants_toothpaste.js),
  [`briggs_rauscher_oscillator.js`](../../../examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js)).
  For elephant's-toothpaste, replace `stepReaction` Arrhenius acceleration, peroxide/O2 ledger
  rates, iodine intermediate, trapping/drainage and heat-generation/loss response with one or more
  atomic→meso operator stages over peroxide, catalyst/intermediate, gas, liquid/foam and
  temperature state. For Briggs–Rauscher, replace `stepOscillator`'s six authored Oregonator/FKN
  derivatives (`x`, `z`, iodide, iodine, reservoir and feedback) with a learned reaction-state
  operator. Keep elemental/stoichiometric conservation and the visible colour mapping as declared
  invariants/representation. Add source pairs to `elephants_toothpaste_eruption` and
  `briggs_rauscher_oscillation`; perturb temperature, catalyst/iodide loading and timestep, and
  grade induction, peak heat, O2/foam volume, cycle count/period/order and depletion settling.

- [x] **5 — Discrete H2O electrolysis/combustion. [landed 2026-07-26]**
  ([`testscenario_h2o_electrolysis_combustion.js`](../../../examples/scenarios/testscenario_h2o_electrolysis_combustion/testscenario_h2o_electrolysis_combustion.js)).
  The default `reaction_source=operator` path now evaluates
  `data/discrete_operators/h2o_cycle_transition_operator.json` through contextual `ctx.react`
  over 90 two-water reaction cells. Raw Geant4 event facts, live interaction anchors,
  electrode/spark conditions and phase progress feed the meso model; the engine owns seeded draws,
  availability, atomic mutation and declared H/O conservation. The normal path contains no
  reaction probability function. The retired functions are prefixed `reference*`, reachable only
  through `reaction_source=reference`, and are duplicated in the reproducible distillation tool as
  validation-only teachers. Independent 6,000-row holdout worst-output R² is 0.9973. The nominal
  operator run performs 270,000 inferences with zero OOD, produces 180 H2 + 90 O2 across both
  cathodes and recovers all 180 waters. `h2o_cycle_operator_matches_reference` passes 4/4 observer
  gaps and 22/22 trust/accounting checks; the original conservation/Geant4 gate remains green.

- [partial: efflux promoted 2026-07-26; osmotic particles promoted 2026-11-26; membrane remains] **6 — Cellular efflux and osmosis**
  ([`testscenario_efflux.js`](../../../examples/scenarios/testscenario_efflux/testscenario_efflux.js),
  [`testscenario_osmotic.js`](../../../examples/scenarios/testscenario_osmotic/testscenario_osmotic.js)).
  **Efflux landed:** `physics_source=operator` is now the default. A committed micro
  `ctx.evolve` model advances `x/y/rvx/rvy` from state, seeded noise and experiment context; a
  separate micro `ctx.react` model consumes raw Geant4 event facts, PubChem XLogP and
  membrane/cytosol probes to decide conserved inside→cleared transitions. JS retains initialization,
  candidate topology, non-penetration projection, packet identity, rendering and the validation-only
  first-order fit. Former OU/advection/drift/crossing functions are `reference*` and reachable only
  with `physics_source=reference`. Independent 6,000-row holdouts carry worst-output R² 0.9978
  (transport) and 0.9827 (crossing); the operator run reports 351,232 exact run-accounted
  inferences, zero OOD/starvation, 76/80 waste cleared, 30/30 essential retained and R²=0.984.
  `efflux_operators_match_reference` passes 4/4 observer gaps + 22/22 trust checks.
  **Osmotic particles landed (2026-11-26):** `physics_source=operator` is the default. A micro
  `ctx.evolve` model (`osmotic_thermostat_operator`, holdout R² 0.9998) returns each molecule's
  velocity change from its velocity, mass and three seeded unit innovations; a micro `ctx.react`
  model (`osmotic_crossing_operator`) decides channel passage for every molecule at the membrane
  from its radius, polarity, pore contact and the channel's declared width (0.6) and polarity
  (+1). The species table lost its `crossable` flag: which species pass is the operator's verdict.
  Certain passage/blocking is trained 0.25 past the [0,1] hazard bound, so the engine clamp makes
  it exact for every declared species. JS keeps pore placement, free flight, bath walls, the
  reflection of a molecule that stays, and pressure scoring. The retired `referenceApplyLangevinThermostat`
  and `referenceStepParticle` run only with `physics_source=reference`, which reproduces the
  previous run's 546 emits exactly. Default run: 1,373,463 run-accounted inferences (1,350,000 motion + 23,463 passage), zero OOD,
  all 9 `osmotic_shift_observed` flags, and `osmotic_operators_match_reference` 4/4 gaps + 22/22
  trust (inside water 10 vs 16, no solute crossed, shrink 0.405 vs 0.423, late kinetic energy
  1.209 vs 1.210). Seeds 101 and 202 pass all 9 flags on both paths. A first motion fit that
  output the new velocity directly carried a 0.008 glucose bias, which the velocity memory
  amplified 25× into a drift that pinned outside glucose to a bath wall and stopped the shrink;
  the committed fit learns the velocity change on mirrored (−v, −noise) pairs.
  **Osmosis remains:** replace the `integrateMembrane` pressure/area/bending response with
  membrane-node operators; pores and inside/outside accounting remain declared topology.
  Extend `efflux_first_order_kinetics` and `osmotic_shift_observed` with independent compound,
  concentration, temperature and pore-width runs; grade selectivity, clearance rate/half-life,
  flux direction, pressure delta, turgor/crenation and solute retention.

- [ ] **7 — Lava-lamp and two-liquid phase/transport**
  ([`lava_lamp.js`](../../../examples/scenarios/lava_lamp/lava_lamp.js),
  [`beaker_water_n_pentane.js`](../../../examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js)).
  Lava: replace `phaseEquilibrium`, wax/carrier density response,
  `advanceCarrierThermalField`, `applyThermalAndPhaseState`, `applyPairDynamics`,
  `carrierFlowAt` and the material response inside `advanceParcelDynamics` with staged thermal,
  phase, interface and buoyancy/drag operators. Keep the spatial grid, boundary projection,
  component labelling and render surface reconstruction as reusable numerical/presentation code.
  Beaker: retain pour/camera interpolation as representation, but replace the single inferred
  60-second endpoint plus authored phase disposition with a time-resolved evaporation/dissolution/
  phase-transfer operator driven by Geant4 material probes, exposed area, agitation and ambient
  conditions. Extend `lava_lamp_inferred_thermofluid` across normal/cool heater, duration and
  precision controls; add a paired beaker gate for mass balance, phase separation, evaporation
  trajectory and endpoint.

- [ ] **8 — Molecular water, PBF water and pressure baths**
  ([`h2o_molecule_stability.js`](../../../examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js),
  [`h2o_cluster_fluid.js`](../../../examples/scenarios/h2o_cluster_fluid/h2o_cluster_fluid.js),
  [`trech_water_md.js`](../../../js/trech_water_md.js),
  [`h2o_bulk_water.js`](../../../examples/scenarios/h2o_bulk_water/h2o_bulk_water.js),
  [`h2o_diffusion_temperature.js`](../../../examples/scenarios/h2o_diffusion_temperature/h2o_diffusion_temperature.js),
  [`glass_of_water_shaken.js`](../../../examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js),
  [`testscenario_pascal.js`](../../../examples/scenarios/testscenario_pascal/testscenario_pascal.js)).
  First consolidate the duplicate flexible-water bond/angle force loops and the shared rigid-SPC/E
  LJ+Coulomb/DSF force loop behind pair inference; SHAKE/RATTLE, Verlet, temperature control and
  periodic/boundary projection become reusable engine algorithms. Train atom/pair increments from
  the current force-field teachers first (`measured:false`), then replace them with independent
  ab-initio/experimental structural and diffusion data. Next replace the glass PBF density/
  pressure, viscosity/cohesion and XSPH response with micro/meso neighbour stages while retaining
  container geometry and non-penetration. Finally replace Pascal's Berendsen/Brownian bath
  response and `advanceSensorWall` Hookean/plastic constitutive law with particle and wall-segment
  operators; piston schedule, collision momentum conservation and pressure tally remain declared
  experiment machinery. Preserve and pair the existing `h2o_molecule_bonds_stable`,
  `h2o_cluster_fluid_stable`, `h2o_bulk_water_structure`,
  `h2o_diffusion_temperature_trend`, `glass_of_water_shaken_waves` and
  `pascal_principle_holds` gates, adding energy/momentum drift, RDF/coordination, diffusion,
  wave/containment, pressure transmission, elastic recovery and plastic residual gaps.
