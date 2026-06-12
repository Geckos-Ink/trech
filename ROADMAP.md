# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.
`docs/trech-roadmap.md` is the initial roadmap concept and is reference-only.

## Sputnik milestone (north star)

- Simulate a single H2O melecule starting from its elementar particle: their behavior and bonds prediction over the time should be stable without "exploding". **[first deliverable landed]** `examples/experiments/h2o_molecule_stability.js` evolves the three nuclei (O, H, H) under a classical flexible-water force field (harmonic O-H bonds r0=0.957 Å + H-O-H angle θ0=104.52°, velocity-Verlet NVE) in the deterministic hook layer; over 400 fs the bonds ring around equilibrium (mean 0.958 Å, max 1.157 Å), the angle stays at 104.5°, and total energy drifts <0.5% — **stable without exploding**, guarded by the `h2o_molecule_bonds_stable` validation case. Honest scope: Geant4 transports particles but cannot form/evolve bound molecular states, so the bonds are classical MD (the "physics for comparison"), with Geant4 as the deterministic per-tick clock. Next: thermal ensembles, more atoms, and bringing the force field closer to measured spectroscopy.
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`. **[electronic-structure step landed 2026-06-12]** `examples/experiments/cnt_band_structure.js` computes, per (n,m) chirality, the diameter / chiral angle / metallic-vs-semiconducting character / band gap via hook-layer tight-binding zone-folding, and reproduces the two textbook+measured results: the metallicity rule (metallic iff (n-m) mod 3 == 0) and the gap law (semiconducting E_g = 2·a_cc·γ0/d → E_g·d ≈ 0.82 eV·nm, measured 0.7-0.9), with STM anchors matched within ~1% (rendered `tools/viz/demos/cnt_band_structure.png`, guarded by `cnt_band_structure`). Honest scope: Geant4 transports electrons but does not compute band structure; leading-order zone-folding (curvature/Kataura family splits are next).
- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical. **[molecular-scale step landed]** `examples/experiments/h2o_cluster_fluid.js` extends the single molecule to an 8-molecule ensemble with intermolecular forces (LJ on O-O + Coulomb on SPC charges, thermostatted, with a soft droplet boundary standing in for the bulk); it settles into a stable, hydrogen-bonded liquid-like droplet (~10.5 O-O contacts, Rg ~2.9 Å bounded, ~313 K) that neither evaporates nor collapses over 2400 fs, guarded by `h2o_cluster_fluid_stable`. Same honest scope: classical MD in the hook layer (Geant4 as the per-tick clock). **[bulk step landed]** `examples/experiments/h2o_bulk_water.js` takes it to true bulk: 48 molecules in a periodic box at liquid density with minimum-image and damped-shifted-force (DSF) electrostatics (a real-space alternative to Ewald). It reproduces the measured liquid **structure** — the O-O radial distribution function g(r) has its first peak at **2.798 Å** (experiment 2.8 Å, the hydrogen-bond distance), at a controlled temperature, guarded by `h2o_bulk_water_structure`. **[comparison video landed 2026-06-11]** the scenario emits deterministic `md_snapshot` sidebands (wrapped positions + running g(r) histogram; physics byte-identical) and `tools/viz/demos/render_bulk_water.py` renders the box next to the engine's accumulating g(r) vs the measured 2.80 Å peak (`h2o_bulk_water_gr.mp4|.gif`, embedded in README). **[scale-up landed 2026-06-11]** N 48 → 108 molecules (box 14.8 Å), cutoff 5.4 → 7.0 Å, g(r) range to 7.4 Å: the **~4.5 Å tetrahedral second shell is now resolved** (flagged `second_shell_near_tetrahedral`, reported not gating), with the production-phase mean T 303 K (now averaged after equilibration, excluding the lattice-melt transient). **[SPC/E parameterisation landed 2026-06-11]** moved the force field from plain-SPC to **flexible SPC/E** (Berendsen 1987 charges q_O=-0.8476 + tetrahedral 109.47° geometry) which deepened the inter-shell depletion (min g(r) 0.95 → 0.85). **[rigid SPC/E via SHAKE/RATTLE landed 2026-06-11]** made the canonical *rigid* SPC/E by holding the geometry with holonomic constraints (SHAKE on positions + RATTLE on velocities) instead of stiff harmonic bonds. Removing the O-H stretch that smears intermolecular structure brought the O-O g(r) onto experiment: first-peak height 2.48 → **3.00** (exp ~2.6-3.1), inter-shell minimum **0.85 → 0.775 (experiment ~0.75)** now located at **3.38 Å (experiment ~3.4)**, and coordination **4.73 to both the own-minimum and the 3.4 Å convention — squarely in the measured ~4.3-4.7 band** (second shell 4.36 Å, mean T 305 K). Killing the stiffest motion also let the timestep go 0.2 → **2 fs**, so each run now samples 5000 fs (10× more physical time) at comparable cost. Rigidity is *proven* not assumed: the max post-SHAKE bond residual (~1e-9) is emitted and gates `bulk_water_stable` via `rigid_constraints_held`. **[self-diffusion (dynamics) landed 2026-06-11]** added the first *dynamic* observable — the self-diffusion coefficient from the production-phase O-atom mean-squared displacement (Einstein relation, MSD = 6 D t; the unwrapped `atom.p` trajectory makes this a direct difference). It comes out **D = 2.57×10⁻⁹ m²/s**, essentially on the SPC/E literature value (~2.5×10⁻⁹) and within ~12% of experiment (2.3×10⁻⁹, 298 K), with the run sitting at ~305 K (D rises with T) and a single-origin/finite-size caveat stated. Emitted (`self_diffusion_m2_per_s`, `msd_curve`) + range-checked (`self_diffusion_physical`) + rendered as a standalone MSD comparison plot (`tools/viz/demos/h2o_self_diffusion.png`). **[Green-Kubo cross-check landed 2026-06-12]** the same run now also measures D the OTHER way — the **Green-Kubo** route, D = (1/3)∫⟨v(0)·v(t)⟩dt from the molecular COM-velocity autocorrelation (the first observable built on the new shared MD core). The two independent estimates agree: **Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s** (~8%), both near experiment 2.3; and the VACF carries the textbook **negative cage-backscattering dip** (−0.09 at ~300 fs) — the dense-liquid signature of molecules rebounding off their hydrogen-bond cage. Guarded by `green_kubo_consistent_with_einstein`, rendered as `tools/viz/demos/h2o_vacf_diffusion.png`. **[D(T) multi-point trend landed 2026-06-12]** `examples/experiments/h2o_diffusion_temperature.js` sweeps three temperatures in one deterministic anneal (melt once, then per block: multi-ps equilibration + a **multi-time-origin** MSD measurement) — a single state point can be lucky, a trend cannot. D rises monotonically and tracks the measured water curve (Holz et al. 2000): **1.24 / 2.66 / 4.64 ×10⁻⁹ m²/s at 281 / 297 / 313 K vs measured 1.43 / 2.27 / 3.26** — absolute values within ~15-45%, and the rise (×3.74 over the span) is the known SPC/E slightly-too-steep D(T) vs measured ×2.28. Two implementation lessons (both honestly recorded): single-origin MSD is far too noisy for per-block D (multi-origin fixed it), and each block must equilibrate longer than water's ~2-3 ps structural relaxation or a melt-like (too-mobile) structure inflates D. Guarded by `h2o_diffusion_temperature_trend`, rendered as `tools/viz/demos/h2o_diffusion_temperature.png`; slow (~20 min), `SKIP_DIFFUSION_T`-gated. **[shared MD core extracted 2026-06-12]** the rigid-SPC/E integrator (force loop, SHAKE/RATTLE, velocity-Verlet) now lives in one `examples/experiments/trech_water_md.js` include that both the bulk run and the D(T) sweep build on — no more duplicated physics; verified bit-identical (bulk trajectory md5 unchanged, D(T) block-0 reproduces 1.24e-9). Next: full Ewald-PME / larger box for the second-shell height; the macroscopic-transport `h2o_fluid.js` (Geant4) remains the complementary continuum-scale view.
- Define a "system" abstraction: stable, point-agnostic ensemble behavior that bridges particle runs to macro-scale predictions.
- In parallel, learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Optimize large-scale molecule simulations with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize the available physics within library boundaries and maintain provenance parity.
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.
- **Reduce simulation degeneration constantly** (see the standing objective below): every run should sample a real distribution, and learned/derived physics should converge toward measured behaviour rather than collapsing to trivial (identical-photon, n≈1) outputs.

## Anti-degeneration (standing objective — keep working on this every iteration)

This is a **primary, never-"done" goal**: continuously reduce the ways a TRECH
run collapses into a degenerate, low-information result, and continuously raise
the realism of its Geant4 sampling, training, and inference. Treat the metrics
below as regression signals — re-measure them whenever physics/optics/ML
changes, and never let them slide back toward degeneracy.

Two distinct degeneration failure modes, tracked separately:

1. **Simulation-sampling degeneration** — every primary identical, so a run of N
   events carries the information of 1 (the glass-of-water baseline emitted 4000
   byte-identical straight photons: 1 distinct exit point, 0° angle spread, 0 nm
   wavelength spread). *Lever: Geant4 simulation variety.*
2. **Learned/derived-physics degeneration** — the engine's optical/material
   constants collapse to trivial values (visible-band `n≈1.0`, infinite
   absorption/scatter lengths) because the derivation/training has too little
   signal, so transport produces near-straight, colourless tracks. *Levers:
   training and inference.*

### Workstreams (rotate through these; each iteration should push at least one)

- **Geant4 simulation variety**
  - [landed] Beam source variety: `beam.originMm` + `beam.spread`
    (`spotRadiusMm`, `divergenceDeg`, `energySpreadFractional`) sample primaries
    over a disk / divergence cone / energy band from Geant4's seeded engine
    (reproducible scores; see `examples/experiments/glass_of_water_varied.js`).
  - [landed] Optical-photon polarization sampling: `beam.polarization`
    (`""`/`unpolarized` → a random transverse linear state per event drawn from
    the seeded engine; `linear` + `polarizationAngleDeg` → fixed; `none` →
    legacy). The default **kills the `ZeroPolarization` fallback** on every
    optical photon while staying reproducible. Verified physical, not a no-op: a
    *fixed* s-pol vs p-pol run reflects ~2.2× differently at the 30° air→glass
    face (classical Fresnel R_s/R_p ≈ 2.36), and the unpolarized ensemble
    averages back to the unpolarized-Fresnel reference (aggregate inverse-Fresnel
    n unchanged). Conditional serialization keeps existing config hashes;
    round-trip covered in `tests/test_config_roundtrip.cpp`.
  - [landed] Emission spectra: `beam.spectrum` is a weighted line list
    (`{energyMeV|energyEv|wavelengthNm, weight}`); each event samples one line
    by weight from the seeded engine (binary search over a cumulative table),
    then `energySpreadFractional` still broadens it. JS helper `spectra`
    generates the table (`blackbody(T)` Planck-weighted, `whiteVisible()` flat,
    `lines(list)` explicit) so the engine stays physics-agnostic. Demo
    `examples/experiments/glass_of_water_spectral.js` fires a 5778 K sunlight
    spectrum through the cup: wavelength stddev 22.9 nm → **102 nm** (full
    visible band), and the derived `n(λ)` gives real normal dispersion (violet
    refracts more: glass Δn≈+0.0063, water Δn≈+0.0047 across 387–775 nm — right
    sign/order, ~2–3× under handbook, the residual the surrogate tracks).
  - [landed 2026-06-11] Beam-profile presets in helpers:
    `helpers.beamProfiles.spread(name, overrides)` bundles named source
    varieties for `beam.spread` (`pencil` — the degenerate baseline, `laser`,
    `ledLamp`, `flashlight`, `sunbeam` with the 0.27° solar half-angle; pair
    with `spectra.*` for the energy axis). `glass_of_water_varied.js` now uses
    the `ledLamp` preset, which matches its historical hand-rolled values
    exactly — verified hash-preserving (canonical beam JSON byte-identical).
  - Next: variance-reduction-aware variety so spread improves statistics
    without exploding event counts.
- **Training** (feed the surrogate real signal)
  - [landed] f-sum-rule valence oscillator in `MolecularOptics.cpp` fixed the
    `n≈1` root cause physics-side (recovery ~1% → ~100% for water/glass; root
    cause + model in `docs/viz_refraction.md`). KK-floor lowering was tried and
    *rejected* (sub-100 eV Geant4 photoabsorption is 1/E^3.5 garbage).
  - [landed] Curated material→optical dataset: `optics_training_panel.js`
    derives optics for 14 materials; the engine now emits
    `element_mass_fractions` per material so training needs no NIST lookup
    table. Handbook anchors in `data/optics_handbook_anchors.json` (targets
    only, never transport). Trainer `--anchors` learns measured n.
  - Next: a microscale visible-band Geant4 sub-simulation track to *measure*
    low-energy cross sections (close the residual without handbook anchors).
  - Next: CI retrain step when the extractor/dataset changes (ties into "Torch
    surrogate adoption" in `In progress`).
- **Inference** (make predictions non-trivial and honest)
  - [landed] Hold-out validation `scripts/validate_optics_surrogate.py`:
    leave-one-out composition→handbook-n recovers materially more refraction
    than the extractor (mean |Δn| 0.141 → 0.084) — the promotion signal. Honest
    about the air OOD failure. Report committed under `docs/`.
  - [landed] Wired the validated anchor-trained surrogate into transport
    **without LibTorch**: since the validated model is a ridge regression (a
    standardised linear `n = bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ`), `OpticsSurrogate`
    grew a ridge `.json` backend alongside the TorchScript one.
    `scripts/validate_optics_surrogate.py --export` writes
    `data/optics_surrogate_ridge.json`; set `optics.derive.surrogateModelPath`
    to it and the engine shifts the derived dispersion curve to the surrogate's
    level in transport (RINDEX). Cross-checked bit-faithful C++↔Python (max
    |Δn|=5.6e-8 across the 14-material panel); e.g. NaI, where the f-sum
    extractor fails (n≈1.33), is corrected to ≈1.77 (handbook 1.775). Opt-in,
    off by default; headline physics demos never set it.
  - Separate predictable from exceptional events so only outliers are
    re-simulated (north-star item) — a degeneracy reducer for compute, not just
    output.

### Degeneration metrics to watch (regression signals)

Measure with `scripts/degeneration_metrics.py RUN_DIR` (or
`--baseline BASE RUN` to diff two runs); it reports both failure modes from a
run's `trech_viz_trajectories.jsonl` (+ `trech_viz_scene.json` for optics).

- Sampling diversity per run: count of **distinct primary exit points**,
  **incidence-angle stddev**, **wavelength stddev**. Baseline degenerate run =
  1 / 0° / 0 nm; `glass_of_water_varied` @2000 ev = ~1950 / 0.75° / 22.9 nm.
- Optics realism: **fraction of handbook refraction recovered**
  `(n_derived-1)/(n_handbook-1)` per material. **Now ~99% (water) / ~103%
  (glass) / ~131% (air)** after the f-sum-rule valence oscillator landed (was
  ~1%); the glass-of-water demo rays now coincide. Remaining work is the
  *material-specific* residual on a broader panel (polymers under-, fluorides
  over-recover) — tracked by `scripts/validate_optics_surrogate.py`.
- [landed] Added as explicit validation cases so `docs/validation_report.md`
  traces the trend: `sampling_diversity_non_degenerate` (category
  `degeneration`) runs `glass_of_water_varied` and asserts >1 distinct exit
  point / incidence-angle stddev >0 / wavelength stddev >0 (vs the degenerate
  baseline 1 / 0° / 0 nm); the optics-recovery side is tracked by the
  `optics_n_*` cases. The diversity metric uses the first-segment displacement
  (robust), matching `scripts/degeneration_metrics.py`.

## In progress

- **Validation report curation**: 25 cases now (17 at first commit — 12 pass, 4 info, 1 was wrong-spec and is now structural numeric replay — plus an h2o_fluid brine scenario guard, two fluid-physics scenario guards (Pascal's principle, osmosis), an end-to-end optics-surrogate transport guard, an anti-degeneration sampling-diversity guard, and the three Sputnik molecular-scale guards: single-molecule bond stability, multi-molecule cluster fluid stability, and bulk-water g(r) structure). Expand coverage as new outputs/scenarios land. Treat `docs/validation_report.md` as a regression artefact: re-generate via `scripts/run_validation_suite.sh` whenever the engine or scenarios change, and commit the regenerated report alongside the code change.
- **Torch surrogate adoption**: the `OpticsSurrogate` C++ path + the Python trainer are wired and degrade gracefully when Torch is unbuilt. (a) curated dataset **landed** (`optics_training_panel.js` + engine-emitted `element_mass_fractions` + `data/optics_handbook_anchors.json`); (c) held-out validation **landed** (`scripts/validate_optics_surrogate.py`, in `run_validation_suite.sh`); (d) **transport feed landed without LibTorch** — a ridge `.json` backend (`data/optics_surrogate_ridge.json`) makes the validated model feed transport in a stock build (`TRECH_ENABLE_TORCH` no longer required for the surrogate path), cross-checked C++↔Python and guarded by `tests/test_optics_surrogate.cpp`; (b) **CI retrain/re-export landed** — `run_validation_suite.sh` re-fits + re-exports the ridge model from the freshly-derived panel each run (so `git diff data/optics_surrogate_ridge.json` flags drift), and a new end-to-end suite case (`optics_surrogate_transport_applied`, via `examples/experiments/optics_surrogate_demo.js`) asserts the learned NaI n (~1.77, where the f-sum extractor fails at ~1.33) actually reaches transport's RINDEX samples. Remaining: (optionally) building LibTorch only for the TorchScript `.pt` backend / multi-output (abs, scat) models.

## Short-term next steps

- Use `docs/validation_summary.md` to track baseline H2O run metrics and watch for regressions as physics/optics work expands.
- Refresh validation outputs after example refreshes (container volumes, explicit materials, nested geometry).
- Continue expanding hook runtime guardrails after `ctx` + deterministic patch/emit landing (next: patch whitelist growth). Stricter emit payload validation and per-callback emit caps are implemented via `hooks.maxEmitsPerCallback` and `hooks.maxEmitPayloadBytes`.
- Extend determinism controls beyond mode selection (strict/predictive implemented) and add guardrails for mixed runtime workflows.
- Define the TorchScript model output contract (label string or 1-2 value tensor) and add a LibTorch-backed smoke test once LibTorch is available.
- Expand system observables beyond current density + event energy moments (mean/variance/stddev) as new per-run accumulables land.
- Keep `CHARTS.md` aligned with runtime changes (workflow, Geant4 wiring, outputs, stratification/prediction).
- Stage a CNT milestone track in parallel to validate config/output coherence without diverging from the H2O baseline.
- Improve geometry authoring beyond primitive shapes: scene graph/nesting, imports (GDML), and procedural generators for complex assemblies.
- Continue de-colliderizing terminology: parser now accepts `environment`/`medium` aliases for `detector`; next extend alias visibility across examples/docs/CLI hints without breaking existing configs.
- Expand flow-oriented JS authoring (`TRECH_FLOW`) beyond current helpers (defaults/derive/normalize/finalize/require) with reusable validation presets while preserving the JS -> JSON boundary.
- Extend nuclear-cycle analysis beyond static consistency/Q-value checks by adding event-level transmutation/decay tallies (Geant process attribution) for scenario-level closure metrics.
- Bootstrap the real-time 3D lab runtime path: support a live command stream (`patch`, `simulate`, `snapshot`, `quit`) over canonical JSON config so users can interact without a fixed JS scenario.
- Use LibTorch/TorchScript for fluid-scale statistical modeling; wire incremental learning as the runtime evolves.
- Long-term: keep the C++ config surface physics/chemistry agnostic, relying on JS scenarios and lab command streams to express combinations.

## Validation status

- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 5`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 50`, output `build/dev/out_h2o_single`).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 50`, output `build/dev/out_h2o_optics`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use container volumes with explicit materials (diameter 3.0 nm, wallCount 5) and a 0.8 MeV electron beam, rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5) and `volume_edep_mev` scoring, rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- `examples/experiments/h2o_fluid.js` SIGSEGV **fixed** (2026-06-06): root cause was `G4_SODIUM_CHLORIDE`, which is *not* a Geant4 NIST material — `buildCustomMaterials` silently skipped the unresolvable component, leaving a `G4Material` declared with more components than it actually added, which crashed Geant4's cut/table builders right after physics construction. Fixed two ways: (a) `MaterialComponentConfig.element` lets scenarios build compounds Geant4 lacks from elements (salt = Na+Cl, brine = water+Na+Cl by mass fraction); (b) fail-safe material building resolves every component up front and warns + renormalizes (or skips) unresolvable ones, so a malformed material is never constructed (verified: a bogus component now warns and the run exits 0). h2o_fluid now runs clean (@50 events: 50/50 primaries transmitted, total_edep 12.66 MeV).
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Nitrogen-carbon cycle scenario run completed with `examples/experiments/config_nitrogen_carbon_cycle.js` (`--events 5`, output `build/dev/out_nitrogen_cycle`); run scores/provenance now include `nuclear_cycle_count`, `nuclear_consistent_cycle_count`, and detailed `nuclear_cycles` reaction/Q-value metrics.
- Geant4 build/install is available at `build/geant4-install` from submodule `thirds/geant4`; point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- When Geant4 is needed, check `thirds/geant4` first before fetching elsewhere.
- `Geant4Config.cmake` is generated by the build/install (currently at `build/geant4-install/lib/cmake/Geant4/Geant4Config.cmake`); the template lives at `thirds/geant4/cmake/Templates/Geant4Config.cmake.in`.
- Prefer building in `build/geant4-build` and installing to `build/geant4-install` to avoid submodule changes.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` alias fields under canonical `detector`.
- Hook runtime extension smoke run completed with `examples/experiments/config_hook_dispatch.js` (`--output build/dev/out_hook_runtime_ext`); scores/provenance include `hook_on_*` counters plus `hook_patch_count`/`hook_emit_count`, `hooks.maxStepCallbacks` guardrail fields, and deterministic hook emits in `trech_hook_emits.jsonl`.
- Hook emit guardrails extended: `hooks.maxEmitsPerCallback` + `hooks.maxEmitPayloadBytes` now bound `ctx.emit` per callback, oversize/over-cap emits are dropped deterministically, and scores/provenance include `hook_emit_dropped_count` plus emit guardrail metadata (`hooks_guardrail_max_emits_per_callback`, `hooks_guardrail_max_emit_payload_bytes`).
- System observables now include event energy moments (`system_event_count`, `system_event_edep_mean_mev`, `system_event_edep_variance_mev2`, `system_event_edep_stddev_mev`) in run scores/provenance.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` function and expanded `TRECH_FLOW` helpers (`defaults`, `derive`, `ensureArray`, `selectBeam`, `normalizeDetectorAliases`, `finalize`, `require`).
- Determinism/provenance smoke run completed with `examples/experiments/config_stratify_ml.js` (`--events 1`, output `build/dev/out_determinism`); emitted `determinism_mode`, `predictive_mode`, stratify model hash metadata, and stratify source counters in provenance.
- Real-time lab bootstrap landed in CLI/core: `trech lab` now runs without JS scenarios, loading optional JSON config (`--config`) and line-delimited command streams (`--commands`) with actions `patch`, `simulate`, `snapshot`, `help`, and `quit`; covered by new `trech_lab_session` and updated `trech_cli_parse` tests.
- Refraction viz demo landed (`examples/experiments/viz_refraction_demo.js`): air/glass/water materials by composition only, `optics.derive.enable` runs `MolecularOpticsExtractor` (G4EmCalculator photoelectric+Compton+Rayleigh → Kramers-Kronig n), `viz.enable` writes `trech_viz_scene.json` + `trech_viz_trajectories.jsonl`. Python viewer at `tools/viz/` (PyVista). Smoke run with `--events 60` derives glass/water/air n ordered correctly; after the f-sum valence oscillator the absolute values sit at ~handbook (glass≈1.472, water≈1.331, air≈1.0004), up from the earlier KK-truncation-low ~1.006 (see `docs/viz_refraction.md`).
- Viewer generalized: tube + sphere primitives, per-segment wavelength coloring along trajectories, time-slider widget for interactive playback (`tools/viz/`).
- Glass-of-water comparison demo landed (`tools/viz/demos/render_glass_of_water.py`): the headline `compare` mode overlays the **physics target** (classical Snell, handbook `n_glass=1.46`/`n_water=1.333`, amber) against the **actual TRECH-simulated** photon (verbatim replay of `trech_viz_trajectories.jsonl`, green). Both rays start from the same emission point in the air above the cup. **Updated after the f-sum-rule valence oscillator landed**: the engine now derives `n_glass≈1.47`, `n_water≈1.33` (~100% of handbook), TRECH refracts at the textbook Snell angles, and the two rays now coincide (ray gap < 1 mm; HUD reports recovery ~100%). The demo selects a representative full transmission (reaches the world boundary, beam-aligned, fewest bounces) and measures the gap as the perpendicular separation between the parallel exit rays. `--mode physics` / `--mode trech` render each story alone (`glass_of_water_physics.mp4`, `glass_of_water_trech.mp4`). The remaining material-specific residual (broader panel) is tracked by the optics surrogate validation.
- Beam source variety landed (anti-degeneration workstream 1): `BeamConfig` gains `originMm` + `spotRadiusMm`/`divergenceDeg`/`energySpreadFractional` (flat keys or a nested `beam.spread` object). `TrechPrimaryGeneratorAction` now samples emission position over a disk, direction over a divergence cone (uniform in solid angle), and energy over a Gaussian band, all from Geant4's seeded engine. Serialization is conditional (only emits non-default fields) so existing scenarios keep their exact config hash; round-trip + nested-alias + flat-precedence covered in `tests/test_config_roundtrip.cpp` (passing). Demo scenario `examples/experiments/glass_of_water_varied.js` (`--events 2000`, output `build/dev/out_gow_varied`) cuts the degeneracy hard vs the baseline: **distinct exit points 1 → 526, incidence-angle stddev 0° → 0.75°, wavelength stddev 0 nm → 22.9 nm**, full air→glass→water→glass→air crossings (7-point trajectories) instead of one repeated 4-point straight line. Same-seed reproducibility verified: `trech_scores.jsonl` byte-identical across reruns and the trajectory set identical (only MT flush line-order differs).
- Optical-photon polarization sampling landed (anti-degeneration workstream 1): `BeamConfig` gains `polarization` (`""`/`unpolarized`/`linear`/`none`) + `polarizationAngleDeg`, parsed as a bare string or `{mode, angleDeg}` object. `TrechPrimaryGeneratorAction` now sets the optical photon's polarization explicitly — a random transverse linear state per event from Geant4's seeded engine for the unpolarized default — instead of leaving it null and triggering Geant4's `ZeroPolarization` random fallback (warning count now 0, was 1/photon). Non-optical particles are untouched; serialization is conditional so existing config hashes hold; round-trip covered in `tests/test_config_roundtrip.cpp`. **Verified physical:** a fixed s-pol (angle 90°) vs p-pol (0°) validation run reflects 51 vs 23 photons at the 30° air→glass face (~2.2×, matching classical Fresnel R_s/R_p≈2.36), the inverse-solved n bracketing handbook 1.46 (1.556 s / 1.345 p); the unpolarized ensemble averages back so the committed `validation_glass_of_water` inverse-Fresnel/Snell numbers are unchanged to ULP. Stale demo outputs (Jun-3 `out_gow_varied` predated the f-sum fix and showed ~1% recovery) regenerated with the current engine — **optics recovery now water 99.3% / glass 102.6%, sampling diversity 1959 distinct exits / 0.75° / 22.4 nm** — and the `render_glass_of_water.py` videos + gif re-rendered (HUD: rays coincide, gap 0.0 mm).
- Emission spectra + viewer fixes landed (anti-degeneration workstream 1): `BeamConfig.spectrum` (`std::vector<BeamSpectralLine>`) + a cumulative-weight sampler in `TrechPrimaryGeneratorAction`; parser accepts `energyMeV`/`energyEv`/`wavelengthNm` per line, serialization is conditional (empty spectrum keeps single-energy hashes), round-trip covered in `tests/test_config_roundtrip.cpp`. JS `spectra` helper builds blackbody/white/line tables. `glass_of_water_spectral.js` (`--events 3000`) samples the full visible band (wavelength stddev **102 nm**) and the 3D viewer renders the chromatic fan. Two pre-existing `tools/viz` CLI bugs fixed while validating it: the `Beam` dataclass missing `active` (crashed `renderer.py`), and `_build_polyline_with_segment_colors` adding implicit vertex cells so per-segment `rgb` failed the length check (n_points+n_seg vs n_seg) — both broke *every* multi-trajectory screenshot, now `trech-viz --screenshot` works.
- `run.threads` + surrogate suite integration landed: `run.threads` (0 = MT default; `GeantRunner::SetNumberOfThreads` when >0, conditionally serialized) fixes a real non-determinism — the hook-MD Pascal/osmosis scenarios accumulate one tick per event, and MT event-completion order made a fixed seed give different results (osmosis flux 77/67/73); `threads: 1` makes them reproducible and the committed report byte-stable. Separately, `run_validation_suite.sh` now re-exports the ridge surrogate model from the fresh panel each run (drift shows in `git diff`) and runs `optics_surrogate_demo.js`, so the `optics_surrogate_transport_applied` case guards the end-to-end transport feed (NaI learned n ~1.77 reaches RINDEX). Round-trip covers `run.threads`; suite 25 cases, ctest 9/9.
- OnlineEventStats added (`trech_ml`): per-event-feature Welford moments, optionally backed by `torch::Tensor` when `TRECH_ENABLE_TORCH` is on. `event_feature_stats` + `event_feature_stats_torch_backed` emitted in `trech_scores.jsonl`. Per-event feature accumulation is now unconditional (previously gated on `stratify.enable`).
- Optics surrogate landed (`OpticsSurrogate`): TorchScript inference path for (composition → n, abs, scat). When `optics.derive.surrogateModelPath` is set the surrogate predictions override the extractor's scalar fields; spectrum samples remain extractor-derived. Trainer at `tools/torch/trech_torch/train_optics_surrogate.py` consumes scene manifests.
- Optics surrogate LibTorch-free ridge backend landed: the inference workstream's "feed transport" step, delivered without building LibTorch. `OpticsSurrogate::load` dispatches on the model file — a `.json` ridge model (standardised linear, `n = bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ`) is parsed via nlohmann/json and evaluated in plain C++; a `.pt` still needs Torch. The composition schema was unified to 14 element slots (added `I` for NaI-class high-Z optics) across the C++ surrogate, the TorchScript trainer, and the ridge validator. `scripts/validate_optics_surrogate.py --export` fits the ridge on the full panel and writes `data/optics_surrogate_ridge.json` (committed). `GeantRunner` now shifts the *whole* derived dispersion curve (`result.samples[].refractiveIndex`) to the surrogate's level so transport's RINDEX actually uses the learned n while keeping the f-sum dispersion shape; the ridge predicts n only (abs/scat keep extractor values via a negative sentinel). Cross-checked bit-faithful C++↔Python (max |Δn| = 5.6e-8 over 14 materials); `tests/test_optics_surrogate.cpp` guards the ridge math + the element-order/feature-length loaders (ctest 9/9). Opt-in and off by default — the glass-of-water demos stay pure f-sum physics.
- Validation suite landed (`tools/validation/`): 25 cases covering optics derivation vs handbook, KK window sanity, n ordering / n>=1 invariants, nuclear cycle conservation + Q-value closure, determinism replay under MT ULP tolerance, primaries accounting closure, system-density arithmetic, event-feature mean consistency, viz schema + trajectory record invariants, composition-fraction normalisation, Torch-backed stats flag, an h2o_fluid brine **scenario** regression guard (runs-to-completion + brine deposition + primary closure, catching a return of the material SIGSEGV), and two **fluid-physics** scenario guards reading hook emits — Pascal's principle (rigid wall transmits pressure undiminished while the Hookean-deformable wall expands and damps it; rigid≪deformable displacement) and osmosis (dimensional exclusion of the solute + a net water shift toward the solute side); and an **optics-surrogate transport guard** (`optics_surrogate_transport_applied`) that runs the opt-in ridge surrogate and asserts the learned high-Z n for NaI (~1.77) reaches transport's RINDEX samples (the f-sum extractor alone gives ~1.33); and an **anti-degeneration** guard (`sampling_diversity_non_degenerate`) that asserts a varied-beam run samples a real distribution (>1 distinct exit / incidence-angle stddev >0 / wavelength stddev >0 vs the degenerate 1 / 0° / 0 nm baseline); and the two **Sputnik molecular-scale** guards: `h2o_molecule_bonds_stable` (single classical-MD H2O molecule stays bound and energy-conserving — bonds near 0.957 Å, angle near 104.52°, energy drift <2%) `h2o_cluster_fluid_stable` (an 8-molecule ensemble forms a stable, hydrogen-bonded, thermostatted droplet — bounded Rg, ~10 O-O contacts, ~313 K), and `h2o_bulk_water_structure` (periodic-box bulk water reproduces the measured O-O g(r) first peak at ~2.8 Å). Orchestrator `scripts/run_validation_suite.sh` (which also re-exports the ridge model so model drift shows in `git diff`; the slow bulk-water run is gated by `SKIP_BULK`). The report `docs/validation_report.md` + sidecar `docs/validation_report.json` are committed to git so `git diff` traces physics regression/improvement.

- Comparison re-run (2026-06-11): ctest 9/9; full validation suite (incl. bulk) 25 cases, 21 pass / 0 fail — report diff vs the previous commit is timestamp/SHA + last-ULP float noise only (no physics drift; `data/optics_surrogate_ridge.json` byte-identical). Glass-of-water comparison videos re-rendered from the fresh runs (`glass_of_water_beam.mp4|gif`, `_physics.mp4`, `_trech.mp4`): exit angles physics 30.00° vs TRECH 30.00°, ray gap 0.0 mm. New bulk-water comparison video (`tools/viz/demos/render_bulk_water.py` → `h2o_bulk_water_gr.mp4|gif`) replays the new deterministic `md_snapshot` emits and shows the engine's O-O g(r) first peak landing on the measured 2.80 Å hydrogen-bond line (TRECH 2.798 Å), with the coordination over-count stated on the end card.

## Photon transport milestones (optical physics plan)

- Phase 1: add `optics.enable` config flag and wire Geant4 optical physics when enabled.
- Phase 2: map water optical properties (absorption, scattering, refraction) into materials.
- Phase 3: add photon-focused scoring summaries and validation runs.
- Phase 4: support spectral optics tables (energy/wavelength dependent properties) for color response.
- Phase 5: derive material optical constants statistically from Geant4 atomic cross sections (photoelectric + Compton + Rayleigh) and Kramers-Kronig dispersion — no hardcoded n at run time. See `docs/viz_refraction.md`.
- Phase 6: 3D visualization pipeline: sampled photon trajectory capture (`trech_viz_trajectories.jsonl`) + scene manifest (`trech_viz_scene.json`) + accessible Python viewer in `tools/viz/`. Materials forced as visualization-only on tagged volumes (`viz_emitter`, `viz_forced_white`).

## CNT milestone parallel track (consistency check)

- Define a CNT experiment stub that stays within the JS -> JSON boundary and reuses the shared config structure (detector/beam/optics/stratify).
- Express CNT geometry as a generic `geometry.volumes` entry (tube shell) with `scoreEdep` enabled.
- CNT placement stays scenario-defined: use `placement.parent = "medium"` to sit inside the medium box, `placement.parent = "world"` for world placement, or named container volumes for nested assemblies.
- Run-level scores stay schema-agnostic; CNT observables are tracked via `volume_edep_mev` on the named volume.
- Validate that CNT runs exercise the same physics wiring order and that optics/stratify toggles behave identically across medium/CNT media.
- Mixed testing: add a CNT + optics stub to confirm photon scoring fields coexist with `volume_edep_mev` on the same engine.
- Gate: proceed with CNT implementation only if it improves overall consistency (shared config surface, shared scoring outputs, fewer special cases).
- CNT smoke run: `./build/dev/trech run examples/experiments/config_cnt_stub.js --events 5 --output build/dev/out_cnt`.
- CNT world smoke run: `./build/dev/trech run examples/experiments/config_cnt_world_stub.js --events 5 --output build/dev/out_cnt_world`.
- CNT optics smoke run: `./build/dev/trech run examples/experiments/config_cnt_optics_stub.js --events 5 --output build/dev/out_cnt_optics`.
- Expected scoring: `trech_scores.jsonl` includes `total_edep_mev`, `volume_edep_mev`, `optics_enabled`, optical photon counts, `n_events`, `seed`, `physics_list`.
- Expected provenance: `trech_provenance.jsonl` includes `config_json` (with `geometry.volumes` and hook registrations when present), `config_hash`, `geant4_version`, `physics_list`, `seed`, `n_events`.
- **[electronic structure landed 2026-06-12]** `cnt_band_structure.js` advances the track from geometry/transport stubs to the actual "electron behaviour differences / Fermi gap" physics: a hook-layer tight-binding zone-folding model over a 26-tube (n,m) panel reproduces the metallicity rule ((n-m) mod 3) and the E_g ∝ 1/d gap law on STM-measured anchors (within ~1%). Guarded by the `cnt_band_structure` validation case (category `cnt`), plotted as `cnt_band_structure.png`. Next on this track: curvature secondary gaps in nominally-metallic tubes (~1/d²) and the trigonal-warping family (Kataura) split of the semiconducting gaps.

## Long-term structure

- core/ (config, provenance, storage)
- js/ (runtime + bindings)
- sim/ (Geant4 integration and scoring)
- chem/ (species registry, reaction network, RD engine, DNA bridge)
- ml/ (TorchScript runtime + feature pipelines)
- data/ (PubChem cache + dataset builders)
- bench/ (benchmarks, manifests, reproducible datasets)
- docs/ (architecture, APIs, user guides)
- thirds/ (submodules and vendored dependencies)

## Completed

- Mermaid architecture charts added in `CHARTS.md` (workflow, Geant4 wiring, outputs, stratification/prediction).
- Geant4 submodule initialized and documented.
- Dependency acquisition decision: default FetchContent via presets, with vendoring optional.
- CLI flags for macro execution, output directory, seed override, and event count.
- Provenance logging expanded (physics list, RNG engine, CLI args).
- First scoring output (total energy deposit summary).
- Event-level scoring and stratification hooks added (`trech_event_scores.jsonl`, `stratify.enable`).
- Stratification expanded with richer event features, thresholds, labels, and ML hook stubs.
- ML feature pipeline + TorchScript stub added for event stratification.
- Chemistry/DNA wiring stub added (`chemistry.enable`, `chemistry.model`, `chemistry.solver`).
- Multi-scale wiring stub added (`multiscale.enable`, `multiscale.method`, `multiscale.mode`).
- Initial Geant4-DNA wiring added (`chemistry.enable`, `TRECH_ENABLE_DNA_CHEM`, solver-gated chemistry stage).
- Run-level scoring now includes chemistry/DNA flags and option metadata.
- Run-level scoring now includes stratification summary counts.
- CTest presets added to avoid passing `--test-dir` flags.
- Stratification feature dumps + resim queue outputs added (`trech_event_features.jsonl`, `trech_resim_queue.jsonl`).
- Unit tests for CLI parsing, JS config evaluation, and provenance output.
- Stratification unit tests and smoke script now run `ctest`.
- Draft initial H2O experiment spec (`examples/experiments/h2o_fluid_spec.md`).
- Initial H2O experiment stub (`examples/experiments/h2o_fluid.js`).
- H2O single-molecule proxy stub (`examples/experiments/h2o_single_molecule.js`).
- H2O optics beam stub (`examples/experiments/h2o_optics_beam.js`).
- H2O config schema extended (medium box, environment, beam direction, optics) with updated spec and stub.
- Detector now supports medium box geometry, environment settings, and optical material properties.
- Optical physics wiring and photon scoring fields (tracks, steps, track length) added.
- Spectral optics support added for energy/wavelength dependent refractive index, absorption, and scattering.
- Optics spectrum example added in `examples/experiments/config_optics.js`.
- Geometry volumes and custom materials added (`geometry.volumes`, `materials`) to keep the schema agnostic.
- Per-volume energy deposit scoring added (`volume_edep_mev`), keyed by volume name.
- CNT stubs now model tube-shell geometry volumes with `scoreEdep` enabled; examples cover medium, world, and container placements with explicit materials.
- LibTorch/TorchScript selected as the ML runtime for online learning from detailed simulations.
- CNT optics stub added to validate optics + volume scoring on the same engine.
- H2O single-molecule proxy and optics-beam stubs run; baseline scores/provenance captured in `build/dev/out_h2o_single` and `build/dev/out_h2o_optics`.
- TorchScript feature schema defined (`FeaturePipeline::kSchemaId = trech_event_features_v1`) and a minimal LibTorch inference hook added behind `TRECH_ENABLE_TORCH`.
- ML scale-up flowchart added to `CHARTS.md` (Geant4 -> Torch training -> inference gate).
- System config block (`system.*`) added with point-agnostic aggregation, and `trech_scores.jsonl` now emits `system_*` density metrics.
- Event summary accumulables now feed system moment metrics (event count + energy mean/variance/stddev) in `trech_scores.jsonl` and `trech_provenance.jsonl`.
- Generic nuclear cycle config + Geant-backed analyzer added (`nuclear.cycles`): reaction participant mass/Q evaluation, charge/baryon conservation checks, and macro phase/density consistency metrics in scores/provenance.
- Validation automation script added (`scripts/run_validation.sh`).
- Validation summary template + updater script added (`docs/validation_summary.md`, `scripts/update_validation_summary.py`) and wired into `scripts/run_validation.sh`.
- Smoke test script added (`scripts/run_smoke.sh`).
- Output JSON schema documented (`docs/output_schema.md`).
- Minimal batch macro example added (`examples/macros/minimal.mac`) and `--ui` flag implemented.
- Config example experiments added (optics, stratify, ML stub, chemistry stub, multiscale stub, nitrogen-carbon cycle).
- Hook API proposal documented (`docs/scenario_hooks.md`).
- JS helper module and multi-beam unit conversion example added (`examples/experiments/trech_helpers.js`, `examples/experiments/config_multi_beam_units.js`).
- JS helpers expanded with physical constants + material presets (including SMILES placeholders).
- JS include helper (`TRECH_INCLUDE`) added to load scenario modules with stable file/line references.
- JS runtime now accepts object-based `TRECH_CONFIG` and registers `TRECH_HOOKS`; error stacks still surface include filenames/line numbers with test coverage in `tests/test_js_runtime.cpp`.
- Hook dispatcher telemetry is wired at init/run/event/step boundaries with deterministic run-level counters and `hooks.maxStepCallbacks` guardrails in scores/provenance outputs.
- Hook runtime extension now dispatches deterministic `ctx` payloads (`config/runtime/event/step/state/rng`), supports whitelisted `onInit` override patching, records `hook_patch_count`/`hook_emit_count` in scores+provenance, and writes `trech_hook_emits.jsonl`.
- Hook runtime guardrails now include per-callback emit caps + payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) with dropped emit telemetry in scores/provenance.
- JS runtime now bootstraps `TRECH_FLOW` (fluent `set`/`defaults`/`merge`/`push`/`ensureArray`/`derive`/`selectBeam`/`normalizeDetectorAliases`/`finalize`/`require`/`assert`/`when`/`tap`/`build`) and accepts function-based `TRECH_CONFIG` for flow-like scenario authoring.
- Core runtime now supports a lab-session command channel (`trech lab`) for real-time JSON-driven interaction without fixed JS scenarios; config schema includes `lab.*` metadata (`enable`, `mode`, command schema/channel, targetHz).
- Determinism config added (`determinism.mode`: `strict`/`predictive`) with stratifier gating (`strict` disables model inference path even when `stratify.modelPath` is set) and provenance/scores metadata (`stratify_model_hash`, source counts, predictive flags).
- Beams array normalization added in the config loader (`beams` array selects active/first; `beam` remains an alias).
- Config loader now accepts top-level `environment` and `medium` aliases for `detector` (canonical serialization remains `detector`).
- Collection normalization expanded beyond `beams` (materials/components/tags/optics.spectrum/hooks accept single object/string forms).
- Material registry fields extended with optional `smiles` metadata for future schema expansion.
- Include error demo added (`examples/experiments/include_error_demo.js`, `examples/experiments/include_error_helper.js`).
- Example scenarios refreshed with container volumes, explicit substances, nested geometry, and system volume declarations.
- Master run action now initializes in MT mode; accumulables merge from workers and provenance captures Geant4 version.
- Geant4 build/install completed under `build/geant4-install` and H2O validation run succeeded.
- Build outputs under `build/` are gitignored and treated as local-only artifacts.
