# Foam mechanics and validation — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Learned state and pair operators](../../../engine/operators/ROADMAP.md) · [Multi-scale inference](../../../engine/inference/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## 2026-10-19 — learned constitutive candidate and 3D vector replay

- **[landed] Generic output links in C++.** `GenericSurrogate` now reads portable v2 models
  with `identity`/`exp` output transforms after destandardisation. Nested `network.layers`
  makes old readers reject encoded values. Overflow rejects a prediction without publishing
  partial outputs; v1 arithmetic and wire format remain unchanged. The generic trainer supports
  `--log-outputs` and optional learning-rate decay, and measures holdout errors in physical units.
  C++ tests cover mixed links, overflow, reload and invalid schemas; Python covers training/export
  and optional TorchScript parity.
- **[experimental, NOT promoted] Foam local constitutive response.** An opt-in contextual
  `ctx.evolve` stage assigns creep/drag/strength from six parcel/context inputs, replacing those
  three authored updates only when `mechanics_source=operator`. Three learned heads are fused
  into one ordinary portable model; drag is fitted in log space. The source script and model
  manifest retain `measured:false` and the exact reduced-law teacher. The 18,006 fitting and 6,006
  independent held-out rows are synthetic teacher samples, not independent physics observations.
  Worst-output holdout R²=0.9980 is migration fit quality only.
- **[promotion failed]** Under the unchanged observer tolerances, nominal height differs by
  **5.35% (limit 5%)** and lean by **6.07° (limit 1.5°)**. At 305 K lean differs by **3.20°**;
  zero-g passes all seven gaps. All three pairs pass 22/22 trust/accounting checks, with zero
  OOD among 2,812,320 constitutive evaluations per run. `mechanics_source=reference` remains the
  default. `bash scripts/validate_foam_mechanics.sh` runs six fresh simulations and the explicit
  `foam-mechanics-candidate` suite, retaining failures and a non-zero exit. The default suite
  continues grading promoted behavior. Chemistry pairs now also hold mechanics source and gravity
  fixed, preventing unlike runs from being compared.
- **[landed] Studio vectors.** Held-frame arrows preserve emitted origin, magnitude/direction
  and axis/units; bounds include all vector frames. Bounded GPU caches and capture metadata
  disclose vector counts and arrowhead/tint choices. Pure replay/precision tests and five GPU
  capture tests pass, including reverse scrubbing; a real MR capture was inspected.
- **[validated defaults]** CTest 18/18, Studio playback 17/17 and precision 3/3 pass; trainer
  tests also ran with NumPy/Torch (including TorchScript decoding parity). Fresh nominal,
  chemistry-reference and zero-g foam runs reproduce every prior default validation result.
  The refreshed 49-case report is 42 pass / 0 fail/error / 4 info / 3 skip; other cases reuse the
  preceding pass's cached runs. The separate six-run candidate report is 1 pass / 2 fail, with no
  skipped promotion checks. Its failing exit confirms the candidate remains unpromoted.
- **[open] Constitutive promotion and physical truth.** Improve trajectory-sensitive fidelity
  across independent conditions/seeds before promotion; row-level R² alone is insufficient.
  Bond growth/creep/failure, contacts and thermal diffusion remain authored comparison laws.
  Independent measured/Geant4-linked response data, general learned pair operators and a
  mesh-objective fracture criterion remain required; this candidate does not complete ledger row 1.
- **[open] 3D parity.** Moving apparatus/meshes, labels/charts/grids, stream selection, native-unit
  scale bars and transparent-sphere sorting remain in [desktop milestones](../../../studio/ROADMAP.md#studio-desktop-ui). The offline PubChem
  [validation refresh gap](../../../engine/inference/ROADMAP.md#2026-10-18--real-input-dependencies-and-continued-3d-replay-parity) also remains open.

- Foam mechanics: gravity + imperfection consequences landed (2026-07-25), with the tuning debt
  written down rather than hidden. New shared module
  [`js/trech_foam_solver.js`](../../../../js/trech_foam_solver.js)
  (`TRECH_FOAM.create`) replaces the two foam scenarios' kinematic volume mapping with a **growing
  viscoelastic bonded-parcel network under standard gravity**: bond rest lengths grow with each
  parcel's own gas generation, creep away stress while the material is fluid, lock as it cures, and
  **break permanently** past the inferred failure strain with crack-tip load concentration;
  contact/wall/ground constraints carry the material's volume (Gauss-Seidel, so the volume is set by
  physics and not by the iteration budget); detached fragments switch to ballistic substepped
  integration and land on the table. The material inside the body is integrated **overdamped** (exact
  terminal-creep solution), which is what makes a minutes-long chemical process tractable at a
  bounded step. Imperfection is a **spatially correlated field** (patchy, like real mixing), so the
  macroscopic consequence does not average away when the mesh is refined. Both scenarios now run
  per-parcel chemistry with heat diffusing along bonds and leaking from the free surface, so a hot
  core and a cooler skin arise unprompted. Precision raised across the board (parcels, step,
  constraint iterations, fragment substeps, ticks, render grid — each a separate typed axis).
  Gravity enters as a labelled physical constant (9806.65 mm/s², like γ in the MRI track); every
  material coefficient is cascade-inferred, and the polyurethane cascade macro model was extended
  with the mechanics outputs. A `gravity_scale=0` control run is part of the suite and the guard
  compares nominal vs control, so the sag/crack/fall is demonstrably **caused** by gravity.
  Scope note: **only `polyurethane_foam.js` runs on the solver today** — the elephant's-toothpaste
  port was attempted and reverted (item 6).
  **Explicitly deferred (do NOT hand-fit these again):**
  1. **The mechanics coefficients were reached by parameter sweeps, which is exactly what the
     cascade is supposed to do.** `macro_bond_failure_strain`, `macro_imperfection_dispersion`,
     `macro_structural_damping_per_s`, `macro_stress_relaxation_per_s` and the gel/blow balance are
     hand-authored biases in `data/polyurethane_cascade/` and `data/elephants_toothpaste_cascade/`.
     They must be **harvested and trained** (`tools/torch` harvest → `train_surrogate.py`) against
     measured foam-rise/fracture data so the coefficients come out of the inference cascade with a
     measured domain, occupancy and held-out accuracy, instead of being fitted by hand.
  2. **Lather sloughing is not modelled.** A blob detaching from an elephant's-toothpaste column is
     a capillary (Rayleigh-Plateau) filament breakup; the bonded network only has a tensile failure
     strain, so `sloughs_blobs` / `blobs_fall_to_the_tray` are emitted and **reported but not
     gated** in `elephants_toothpaste_eruption`. Needs a surface-tension/necking term.
  3. **Fracture siting is discretisation-sensitive** (the classic mesh-dependence of discrete
     fracture): the aggregate response (leans, cracks, sheds a few percent, cures rigid) is stable
     across resolutions, but which bonds break is not. Needs an energy-regularised (mesh-objective)
     failure criterion before per-crack claims are allowed.
  4. **Contact convergence for deep stacks** still depends on the sweep count; the Gauss-Seidel pass
     converges quickly but a pressure-projection or multigrid pass would make it iteration-free.
  4b. **Attached material cannot spill down the OUTSIDE of the vessel.** The wall is a one-sided
     constraint that holds attached parcels inside the column; only detached pieces clear it. A
     two-sided thin-wall contact was tried and reverted because resolving attached parcels to the
     outer face leaks material through the wall and relieves exactly the stress that makes the bun
     crack (measured: cracking fell from 31% of bonds to 9% and shedding stopped entirely). Doing
     it properly needs per-parcel wall *sidedness* carried across steps.
  5. **A gravity sweep** (0.5g / 2g, not just 0g vs 1g) would grade the *scaling* of lean and shed
     mass rather than only their presence.
  6. **Porting elephant's toothpaste to the same solver is deferred.** The lather was moved onto
     the bonded network and reverted: with a film strength thin enough to never set, the network
     shreds (measured: 97% of bonds broken, 1039 of 1100 parcels detached, and the column never
     reached the cylinder rim). A lather is held together by surface tension and drains by film
     thinning — neither is in the solver — so `elephants_toothpaste.js` stays on its validated
     volume-conserving formulation until item 2 (a capillary/necking term) lands. The polyurethane
     sponge is the scenario that carries the gravity/imperfection mechanics today.
  7. **Residual creep in the cured network.** A set sponge's bulk motion collapses by roughly an
     order of magnitude from its peak but not to zero (~9% in the reference run): part is cracked
     flaps genuinely settling, part is position-solver residual in a deep stack. A quasi-static
     (equilibrium) solve for the cured phase would drive it to zero and let the guard assert a
     stronger freeze than "an order of magnitude".
- Two reactive-foam cascades landed (2026-07-25): the **"solid sponge" vs "soapy lather"** pair —
  the same doctrine producing two opposite emergent *consistencies*, extending the chemistry arm of
  the multi-scale cascade workstream. **(1) `examples/scenarios/polyurethane_foam/polyurethane_foam.js`** is told
  only the two-part recipe (hydroxyl number, water pphp, isocyanate index, catalyst/surfactant) and
  the Geant4-built solution/mixture materials; `materialProbe` reports the isocyanate nitrogen
  (8.44e21/cm³ in Solution B) and the A/B density contrast (1.08 vs 1.22 g/cm³), `optics.derive` the
  mixed liquid's colour, and a two-stage `ctx.cascade` (`data/polyurethane_cascade/`, both
  `generic_surrogate_v1`, both `inDomain`/`domainMeasured:false`) infers the coefficients of a
  reduced dual-reaction foaming model (gel + blow rate constants, Arrhenius activation, per-reaction
  exotherms, CO₂ capacity/saturation, Flory gel point, Castro-Macosko viscosity exponent, surfactant
  trapping, expansion mobility, autocatalysis, solid conversion). No expansion ratio, milestone time,
  colour, or consistency is an output: the hook-layer integrator makes them **emerge** — 18.15 s
  dissolution induction then cream, rise to **26.9×** (96.3% gas), gel at 64.6 s, solid at 105.3 s,
  +54.3 K exotherm, 93.0% of the CO₂ trapped by the rising viscosity, and a rigid sponge whose late
  frame-to-frame parcel displacement is 0.00 mm. Guarded by `polyurethane_foam_expansion`
  (**15/15**). **(2) `examples/scenarios/elephants_toothpaste/elephants_toothpaste.js`** is told only the peroxide/soap
  + KI recipe; Geant4 reports the dissolved iodine (1.30e21/cm³) and potassium (1.29e21/cm³) and the
  O-rich peroxide density, and a two-stage cascade (`data/elephants_toothpaste_cascade/`) infers the
  catalytic-decomposition coefficients (catalysed/uncatalysed rates, activation, exotherm, heat loss,
  O₂ foam capacity, trapping efficiency, drainage, iodine shunt). Emergent: **8.03e4×** catalytic
  acceleration, eruption over the rim at 0.81 s, 90% conversion at 9.71 s, an **18.4×** lather column
  433 mm above the rim, a steaming 368.9 K peak, a transient iodine tinge peaking before completion,
  and drainage to 74% of peak with motion continuing — it **never solidifies**. The one authored
  comparison-layer constant (an evaporative clamp at the carrier boiling band) has its contribution
  **measured and emitted** rather than hidden: it removes 8.2 K, and the unclamped exotherm would
  reach 375.7 K, so the sub-boiling result is mostly the inferred exotherm/heat-loss balance
  (`evaporative_clamp_contribution_disclosed` is a validation check).
  Guarded by `elephants_toothpaste_eruption` (**16/16**). Both
  are deterministic (`threads:1`, predictive), byte-identical across reruns,
  `hook_predict_count=2` / `hook_predict_out_of_domain_count=0`, and use PubChem for **structure
  identity only** (CID/SMILES/formula, element-set cross-checked against the declared Geant4
  composition; a validation check asserts no physical property crossed into the payload). Both emit
  `material_frame` (persistent parcels + a Gaussian `render_surface` whose centres sit one
  surface-bulge inside the foam envelope) and render through the **classic `trech-viz` 3D path** —
  no bespoke renderer — to `tools/viz/demos/polyurethane_foam.gif` (0.77 MB) and
  `elephants_toothpaste.gif` (0.71 MB). Two viewer-side changes, both display-only
  (`tools/viz/trech_viz/renderer.py`): (i) the material-animation camera now frames the union of the
  scene bounds and the **full replayed material extent** at a distance derived from the actual
  vertical FOV and window aspect (plus the turntable's worst-case footprint circle) instead of a
  magic multiplier — an expanding foam rises far above the tallest apparatus volume and used to clip
  at the top; (ii) the GIF writer quantizes onto one shared adaptive palette with `disposal=1`.
  `lava_lamp_trech_viz.gif` was regenerated from the same committed README run to pick both up: the
  lamp cap and base are no longer cut off, and the file drops **3.37 MB → 0.63 MB** with identical
  replayed content.
  `ctest --preset dev` **11/11**; validation reporter **44 cases, 40 pass / 0 fail-error / 4 info /
  0 skip**; both added to `scripts/run_validation_suite.sh`. No config-surface change (existing
  fields only → config hashes byte-stable). Honest scope: Geant4 does not solve urethane kinetics,
  bubble rheology, aqueous redox kinetics, or foam drainage — both reduced models are labelled
  "physics for comparison" whose coefficients are inferred from the Geant4 base; the macro response
  surfaces are compact **illustrative** maps (σ=0.14 and σ=0.15 emitted), and the cream/tan and
  white/amber swatches are labelled representation while their *timing* is the emergent, graded
  result. Follow-up: a wider trained reactive-foam / catalytic-kinetics panel (graduate both
  illustrative macro maps to held-out-validated per-band chains).
