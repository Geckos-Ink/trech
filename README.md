# TRECH

![Light beam through glass water refraction simulation](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/glass_of_water_beam.gif?raw=true)

TRECH is a **C++ simulation and learning toolkit** that couples **Geant4** particle transport with a stable, scriptable experiment layer and a provenance-first data trail. The core idea is simple: experiments can be authored in **JavaScript**, where scenarios can compute and compose configuration—covering unit conversions, dynamic assembly, and multi-entity layouts—before handing that configuration to the **deterministic-by-default C++ runtime** via JSON serialization.

In parallel, the runtime now includes a first `lab` command path that accepts live JSON commands like `patch`, `simulate`, `snapshot`, and `quit`. This enables the bootstrapping of **interactive 3D-lab workflows** without requiring a fixed JS scenario file.

**Prediction layers** can relax determinism in a controlled way, with all changes logged in the provenance trail. The JS runtime utilizes a standard-compliant engine (**QuickJS**) which allows it to evolve without changing the configuration surface. To ensure accountability, hook registrations and deterministic callback dispatch points (init/run/event/step) are logged alongside run-level guardrails, patch/emit counters, hook-emit dropped counters, and hook-emit payload records.

Essential project points are:
- The simulation must relies less as possible on pre-determined physical and chemical formulas but has to obtain the behaviour at elementary particels level with GEANT4 and then changing simulation scale step by step determining statistical behaviours at larger scales. Physical and chemical laws can be used for comparison and validation purposes.
- TRECH has to costantly enforce GEANT4 simulation quality and statistical training and inference through ad hoc algorithms and using torch, learning when a prediction can be accurate and when is needed another statistical behaviour training on the run.

**Current stage: H2O baseline with optics/stratification, initial Geant4-DNA wiring, and nuclear cycle consistency analysis**

![A cell clearing a lipophilic waste molecule by passive membrane permeation, simulated count vs the first-order clearance law](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/efflux_clearance.gif?raw=true)

*The thesis in miniature: a biological cell rids itself of a lipophilic **waste** molecule (**benzene**) by passive permeation across its lipid bilayer (Overton's rule), while keeping its polar **essential** molecule (**D-glucose**) — drift-diffusion MD in the deterministic hook layer (one Geant4 event = one tick), with the molecules drawn as ring glyphs that swirl in a coherent cytoplasmic flow and drain outward (no random jitter). **Two real anchors drive it:** runtime-fetched **PubChem XLogP** (octanol-water partition coefficient — benzene +2.1 vs glucose −2.6) decides WHICH molecule permeates, and **Geant4** scales HOW FAST via both `G4EmCalculator` membrane-vs-cytosol interaction ratios and per-event `ctx.event` transport statistics (emitted live; this rate mapping is illustrative and flagged). **Right panel:** the simulated internal count N(t) (green) vs the classical **first-order clearance law** N₀·e^(−kt) (amber, Fick's law) — the microscopic permeation reproduces the macroscopic kinetics (R² ≈ 0.99). Real PubChem 2D structures are shown on the molecule passport cards when PNGs are present in the build-local cache. Render with `tools/viz/demos/render_efflux.py`; substance properties via `tools/pubchem`.*

![Magnetic resonance of a water cube: discovered Larmor line, FID decay, and Geant4-derived proton-density tissue contrast](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/magnetic_resonance.png?raw=true)

*The thesis again, in an MRI: a 5 cm³ **water cube** in a static field. Geant4 builds the phantom + a copper receiver coil and — through the new material-composition surface (`ctx.materials`) — supplies the **¹H (proton) number density** (6.686×10²² /cm³, exactly the literature value, never hard-coded); the deterministic hook layer runs the **Bloch spin dynamics**. **We tell it only the proton gyromagnetic ratio γ (a particle constant) and the machine field B₀** — the resonance is not assumed. **Left:** a swept-RF spectroscopy pass locates a broad resonance; the precise **Larmor line is DISCOVERED** from the free-induction-decay carrier (the magnetization precesses at γB₀), recovering **γ/2π = 42.5768 MHz/T** vs CODATA 42.5775 (0.001%). **Middle:** the FID decays with a recoverable T2*; its detected RF signal is the "output". **Right:** swap in NIST tissues and the **Geant4-derived proton-density contrast** falls straight out — adipose/muscle/brain near water, **cortical bone the classic MRI-dark 0.58×**. Geant4 does not simulate nuclear spin; the spin dynamics are hook-layer physics-for-comparison, and the textbook values grade the gap only. Render with `tools/viz/demos/render_magnetic_resonance.py`.*

![MRI tissue contrast from REAL Geant4-detected photons: relative signal per tissue tracks Geant4 proton density, cortical bone dark](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/magnetic_resonance_tissues.png?raw=true)

*Stage 2 makes the output photons **REAL**: for each NIST tissue the number of excitation primaries is set proportional to that tissue's **Geant4-computed proton density** (an "ignorant" material fact — Geant4 has no idea it's for NMR), Geant4 then produces **every consequent photon** (Compton scatter, fluorescence, secondary bremsstrahlung…), and a NaI detector shell scores the **real deposited energy** of all of it. The per-tissue detected signal (green) is thus a genuine Monte-Carlo tally, not a formula — and because the emission count came from Geant4's proton prediction, it reproduces MRI proton-density weighting: **cortical bone lands at 0.60× water** (the classic dark tissue), and the detected signal tracks proton density with **r = 0.9995**. The small bone gap (0.60 detected vs 0.58 proton ratio) is the honest radiographic photon-yield term. Multi-run driver `scripts/run_magnetic_resonance_tissues.py`; render with `tools/viz/demos/render_magnetic_resonance_tissues.py`.*

![1D MRI image line: a field gradient encodes position, and DFT of the readout reconstructs the proton-density profile with air gap black and cortical bone dark](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/magnetic_resonance_imaging.png?raw=true)

*Stage 3 turns the contrast into an **actual image**. Geant4 builds a real phantom — a row of NIST-tissue voxels along the readout axis, including an **air gap** (no protons) and **cortical bone** — and supplies each voxel's ¹H density. The hook layer applies a **field gradient** so the Larmor frequency becomes position-dependent (`ω(x)=γ(B₀+G$_x$·x)`), synthesizes the frequency-encoded readout, and **DFT-reconstructs the 1D proton-density profile** — a genuine MRI image line. Each voxel's position is recovered from its peak frequency to **0.001 mm** (right panel, on the diagonal), the amplitudes track proton density (r = 1.0), and the image reads bright · bright · **BLACK (air)** · bright · **dark (bone)** · bright · bright. We feed only γ, B₀ and the gradient — the frequency→position map and the picture emerge. Render with `tools/viz/demos/render_magnetic_resonance_imaging.py`.*

## Why TRECH

- **Reproducible**: every run writes provenance (config JSON + hashes + seeds + versions).
- **Determinism modes**: strict simulation runs remain reproducible; predictive ML layers can be enabled with explicit provenance capture.
- **Programmable**: JS can compute and assemble configs (helpers, unit conversions, loops) while C++ remains in control.
- **Extensible**: initial Geant4-DNA physics wiring is available (guarded by `TRECH_ENABLE_DNA_CHEM`); chemistry and ML stubs remain.
- **Agnostic config**: long-term, keep the C++ config surface physics/chemistry agnostic while JS scenarios and lab sessions express combinations; define physics/chemistry classes, properties, and extensions in authoring layers.
- **System abstraction**: point-agnostic, ensemble-level metrics (densities) connect particle-scale runs to macro-scale predictions.
- **Online learning**: LibTorch/TorchScript is the chosen ML runtime for learning from simulation outputs (slower inference, but richer training loops).

## "Sputnik" milestone (north star)

![Bulk H2O molecular dynamics reproducing the measured O-O g(r) first peak](https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/h2o_bulk_water_gr.gif?raw=true)

*108 periodic-box rigid-SPC/E water molecules (classical MD in the deterministic hook layer, SHAKE/RATTLE constraints, Geant4 as the per-tick clock) growing the O-O radial distribution function: the first peak lands at 2.74 Å vs the measured 2.80 Å hydrogen-bond distance, the inter-shell minimum (g≈0.78) and coordination (≈4.7) match the measured liquid, and the ~4.5 Å tetrahedral second shell is resolved. The same run measures the **self-diffusion coefficient** two independent ways — Einstein (MSD) and Green-Kubo (velocity autocorrelation) — which agree at D ≈ 2.6–2.8×10⁻⁹ m²/s, on the SPC/E literature value, with the VACF showing the dense-liquid cage-backscattering dip (`h2o_self_diffusion.png`, `h2o_vacf_diffusion.png`). A companion temperature sweep (`h2o_diffusion_temperature.js`) shows D(T) tracking the measured trend across 281–313 K (`h2o_diffusion_temperature.png`). Render with `tools/viz/demos/render_bulk_water.py`.*

- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical.
- Secondary reference ("Vostok" milestone): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`. **Electronic-structure step advanced:** `examples/experiments/cnt_band_structure.js` reproduces the metallic/semiconducting classification ((n−m) mod 3 rule), the semiconducting primary band-gap ∝ 1/diameter law on STM-measured anchors, and the curvature-induced secondary gap for nominally metallic non-armchair tubes (`E_curv ∝ |cos(3θ)|/d²`, armchairs remain zero-gap) via hook-layer tight-binding (`cnt_band_structure.png`). **Logic-gate step landed:** `examples/experiments/cnt_logic_gates.js` turns that band structure into working CNTFET devices and digital logic — the full static-CMOS gate family and half/full/2-bit-adder circuits whose simulated truth tables are confirmed against the canonical boolean/arithmetic functions, with the on/off ratio set by Fermi-Dirac statistics (`~exp(E_g/2kT)`), the recovered subthreshold swing on the ~60 mV/dec Fermi limit, and a metallic tube shown to short the logic. It now emits `visual_topologies` for each gate so `cnt_circuit.gif` renders NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR from the scenario's CMOS networks instead of a fixed inverter-chain template (`cnt_logic_gates.png`; `cnt_structure.gif` / `cnt_circuit.gif` — see the [scenario animation gallery](#scenario-animation-gallery)).
- Learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Scale to large molecule counts with multi-scale acceleration (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Prioritize photon transport accuracy (scattering, absorption, refraction, color response) within molecular volumes.
- "Apollo" milestone: totally generic physical simulator able to simulate and predict complex systems (chemistry on high volumes) and physical interactions 

## Architecture (short version)

1. **Authoring input** is either a JS experiment (`run`) or a live JSON command stream (`lab`).
2. **C++ core** parses config, applies deterministic patches/overrides, and tracks lab/session metadata.
3. **Geant4 layer** runs the canonical lifecycle and emits scoring + provenance.
4. **System aggregation** computes point-agnostic ensemble metrics for ML and multiscale stages.

See `docs/structure.md` for the detailed skeleton and `docs/trech-roadmap.md` for the full plan.
Mermaid diagrams of the workflow, Geant4 wiring, prediction loop, and ML scale-up path live in `CHARTS.md`.

## Quick start

```
git submodule update --init --recursive
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
./build/dev/trech lab --config examples/lab/realtime_lab_bootstrap.json
```

Build artifacts live under `build/` and are ignored by git.

## CLI

```
trech run <experiment.js> [--macro <file>] [--ui] [--output <dir>] [--seed <n>] [--events <n>]
trech lab [--config <file>] [--commands <file>] [--macro <file>] [--ui] [--output <dir>] [--seed <n>] [--events <n>]
```

Examples:

```
./build/dev/trech run examples/experiments/hello_world.js --output out
./build/dev/trech run examples/experiments/water_box.js --seed 42 --events 100
./build/dev/trech run examples/experiments/h2o_fluid.js
./build/dev/trech run examples/experiments/hello_world.js --macro examples/macros/minimal.mac
./build/dev/trech lab --config examples/lab/realtime_lab_bootstrap.json
./build/dev/trech lab --config examples/lab/realtime_lab_bootstrap.json --commands examples/lab/realtime_lab_commands.jsonl
```

`lab` mode command schema (JSON object per line, stdin or `--commands` file):
- `{"action":"patch","patch":{...}}` merge a config patch into the live session state.
- `{"action":"simulate","events":N,"seed":S}` run Geant4 with the current state.
- `{"action":"snapshot"}` print the current canonical config JSON.
- `{"action":"help"}` print supported actions.
- `{"action":"quit"}` close the lab session.

## Config examples

- `examples/experiments/hello_world.js`: minimal baseline.
- `examples/experiments/water_box.js`: container volume holding explicit water material (non-chemical boundary).
- `examples/experiments/config_optics.js`: medium box with optics enabled (includes `optics.spectrum` sample) and explicit water material.
- `examples/experiments/h2o_fluid.js`: H2O fluid stub with container + brine mixture + nested solute seed.
- `examples/experiments/h2o_single_molecule.js`: single-molecule proxy stub with container + nested sphere proxy.
- `examples/experiments/h2o_optics_beam.js`: optical photon beam through water (spectrum-enabled, explicit water material).
- `examples/experiments/config_stratify.js`: event stratification thresholds/labels.
- `examples/experiments/config_stratify_ml.js`: stratification with TorchScript model path stub.
- `examples/experiments/config_chemistry_stub.js`: chemistry/DNA wiring (DNA physics when enabled; chemistry stage still stubbed by default).
- `examples/experiments/config_multiscale_stub.js`: multi-scale stub wiring config.
- `examples/experiments/config_nitrogen_carbon_cycle.js`: nitrogen gas <-> carbon-14 cycle scenario (`N-14 + n -> C-14 + p`, `C-14 -> N-14 + e- + anti_nu_e`) with Geant-backed consistency/Q-value reporting.
- `examples/experiments/analytic_beer_lambert.js`: complex test scenario with a **classical-formula cross-check** — a narrow 100 keV gamma beam through a 50 mm water slab, where the engine compares the textbook Beer-Lambert prediction `T = exp(-mu*x)` (with `mu` summed from Geant4's own atomic cross sections via `G4EmCalculator`) against the run's measured Monte-Carlo uncollided-primary fraction. Both numbers + the gap land in `trech_scores.jsonl` under `analytic_checks` (classical 0.4265 vs Geant4 0.4217, ~1.1% — Poisson-limited).
- `examples/experiments/analytic_csda_range.js`: charged-particle **CSDA-range cross-check** — a 20 MeV proton fully stops in water; the engine derives the CSDA range from Geant4's own stopping power (`G4EmCalculator::GetCSDARange`) and compares it to the measured mean primary track length (a new per-primary path-length tally). Derived 4.28 mm vs measured 4.27 mm (~0.4%); emitted under `analytic_checks` (`type: "csda_range"`), guarded by `analytic_csda_range_cross_check`.
- `examples/experiments/analytic_photo_fraction.js`: photon **process-branching cross-check** — a 30 keV gamma beam (near water's photoelectric/Compton crossover) where the engine predicts the photoelectric share of the total interaction cross section `sigma_phot/sigma_total` from the same `G4EmCalculator` cross sections and compares it to the measured fraction of primaries whose first discrete interaction is photoelectric (classified through QBBC's `G4GammaGeneralProcess` wrapper by EM subtype). Derived 0.391 vs measured 0.393 (~0.6%); emitted under `analytic_checks` (`type: "photo_fraction"`), guarded by `analytic_photo_fraction_cross_check`. Unlike the attenuation/range checks, this tests the process *choice* and is slab-thickness independent.
- `examples/experiments/config_cnt_stub.js`: CNT stub modeled in a fluid container with explicit materials and nested volumes.
- `examples/experiments/config_cnt_world_stub.js`: CNT stub volume placed in a void container in the world (no medium box).
- `examples/experiments/config_cnt_optics_stub.js`: CNT geometry + optics mixed testing stub (medium box + optics enabled).
- `examples/experiments/cnt_band_structure.js`: CNT electronic-structure comparison panel; emits metallicity, primary semiconducting gaps, curvature secondary gaps for quasi-metallic tubes, and validation flags to `trech_hook_emits.jsonl`.
- `examples/experiments/cnt_logic_gates.js`: **CNT logic gates + circuits** — builds CNTFETs from the tight-binding band gap, the full static-CMOS gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR as resistive-divider pull-up/pull-down FET networks), and three circuits (half adder, full adder, 2-bit ripple-carry adder), then **confirms the truth table the electrons produce at every output**. The transistor on/off ratio is Fermi-Dirac-set (`~exp(E_g/2kT)`), the subthreshold swing recovered from the simulated `I_d(V_gs)` lands on the ~60 mV/dec room-temperature Fermi limit, and a **metallic** tube dropped into the same topology collapses the outputs to ~Vdd/2 and breaks the logic (the metallic-short manufacturing problem of `docs/CNT/BackToTheCarbon.md`). Geant4 transports the e- beam through the representative (16,0) channel each event. Emits `cnt_device` + `cnt_gates_summary` with `visual_topologies` and `visual_source`; rendered by `tools/viz/demos/render_cnt_logic_gates.py` → `cnt_logic_gates.png` and `tools/viz/demos/render_cnt_circuit.py` → `cnt_circuit.gif`; guarded by the `cnt_logic_gates` case.
- `examples/experiments/config_flow_language.js`: flow-style scenario using `TRECH_FLOW` chaining (`set`, `defaults`, `merge`, `push`, `derive`, `ensureArray`, `normalizeDetectorAliases`, `finalize`, `require`) and function-based `TRECH_CONFIG`.
- `examples/experiments/config_hook_dispatch.js`: hook runtime smoke example (`ctx`, deterministic `emit`, `onInit` override patch, and hook guardrails: `hooks.maxStepCallbacks`, `hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`).
- `examples/experiments/testscenario_efflux.js`: **headline biological comparison** — a cell clearing a lipophilic waste molecule (**benzene**) by passive lipid-bilayer permeation (Overton's rule) into an extracellular sink, while retaining a polar essential (**D-glucose**). Two real anchors: **PubChem XLogP** (benzene +2.1 vs glucose −2.6, loaded via `TRECH_PUBCHEM` from a build-local cache) decides which molecule permeates; Geant4 `G4EmCalculator` membrane/cytosol EM interaction ratios plus per-event `ctx.event` transport statistics scale the rate. The drift-diffusion hook MD (coherent cytoplasmic streaming + outward efflux drift — directed, not jittery) reproduces the classical first-order clearance law `N(t)=N₀·e^(−kt)` (Fick), validated by a log-linear fit (`R²≈0.99`). Emits `efflux_snapshot`/`efflux_summary` for `tools/viz/demos/render_efflux.py` (TRECH-vs-law comparison video with PubChem 2D structures). Guarded by the `efflux_first_order_kinetics` case.
- `examples/experiments/testscenario_h2o_electrolysis_combustion.js`: H2O reaction-cycle test — a deterministic hook-layer inference bath electrolyzes water across **two cathodes** plus an oxygen collector, then ignites H2/O2 back into H2O. `TRECH_PUBCHEM("water"|"hydrogen"|"oxygen")` reads a real-time fetched cache for formulas/CIDs; Geant4 event-level e- energy deposition and track statistics from `ctx.event` plus `G4EmCalculator` interaction fingerprints for H2O/H2/O2 (`analytic_checks`) directly scale the stochastic reaction rates. Emits `electrolysis_snapshot` with sampled H2/O2/product-H2O molecule packets for the renderer, plus `h2o_cycle_summary`; guarded by `h2o_electrolysis_combustion_cycle` (2:1 H2/O2, both cathodes active, atom conservation, full water recovery, positive Geant4 event drive). Honest scope: Geant4 constrains the proxy; it is not a full aqueous electrochemistry/flame solver.
- `tools/pubchem` (`python -m trech_pubchem fetch <names>`): PubChem property + 2D-structure cache helper. Use `--cache-dir` or `TRECH_PUBCHEM_CACHE_DIR` for build-local real-time fetches (the validation suite uses `build/dev/pubchem_cache`); new fetched records are ignored by git by default.
- `examples/experiments/testscenario_magnetic_resonance.js`: **magnetic resonance (Stage 1)** — NMR/MRI of a 5 cm³ water cube. Geant4 builds the phantom + a copper receiver-coil volume and, through the new material-composition surface (`materialProbe`/`ctx.materials`), supplies the ¹H (proton) number density that sets the equilibrium magnetization; a `G4EmCalculator` beer_lambert anchor + per-event transport are the clock. The deterministic hook layer runs the Bloch spin dynamics: a swept-RF spectroscopy pass and a free-induction-decay pass whose lab-frame carrier is measured to **discover** the Larmor line — feeding only the proton gyromagnetic ratio γ (a particle constant) and the machine field B0, so γ/2π = 42.5768 MHz/T (vs CODATA 42.5775, 0.001%), the Geant4 water proton density 6.686e22/cm³ (= literature, 0.006%), and T2* all emerge and are graded against the textbook values. `mr_summary.tissue_preview` already shows the Geant4-derived proton-density contrast (cortical bone 0.58× water) for the upcoming tissue stage. Emits `mr_spectrum`/`mr_fid`/`mr_summary`; guarded by `magnetic_resonance_water`. Honest scope: Geant4 does not simulate nuclear spin — the spin dynamics are hook-layer physics-for-comparison.
- `examples/experiments/testscenario_magnetic_resonance_tissues.js` + `scripts/run_magnetic_resonance_tissues.py`: **magnetic resonance (Stage 2)** — virtual-tissue contrast with REAL Geant4 photon emission (multi-run, no C++). The driver reads each NIST tissue's Geant4-computed ¹H number density from `material_probes` (an ignorant material fact), runs the scenario per tissue with the excitation-primary count set **proportional to that proton density**, and Geant4 then produces **every consequent photon** which a NaI detector shell scores as real deposited energy (`receiver_coil` `volume_edep_mev`). The per-tissue detected signal is a genuine Monte-Carlo tally that reproduces MRI proton-density contrast (cortical bone 0.60× water, corr 0.9995), byte-reproducible. Aggregate emitted as `mr_tissue_contrast`; guarded by `magnetic_resonance_tissue_contrast`. Honest scope: the excitation-per-proton is a labelled proxy (Geant4 can't make spins radiate RF); what is REAL is the Geant4-set emission count and the Geant4-transport detection tally.
- `examples/experiments/testscenario_osmotic.js`: validation scenario for a biological cell osmotically dehydrating in a hypertonic bath (`docs/testscenario_osmotic-todo.md`); a coarse-grained 2D MD bath of H2O + glucose + wrong-polarized ions around a **selectively permeable, turgor-driven spring membrane** runs inside the hook layer (one Geant4 event = one MD tick). A Langevin thermostat keeps the 310 K kinetic proxy bounded while the cell expels water through its pores, **crenates** (the membrane contracts and buckles as water leaves — an emitted physical state), and **expels wrong-polarized molecules** (glucose by size, small ions by polarity). `final_summary` validates 9 behaviours — dimensional + polarity exclusion, early pore crossings, macroscopic water flux, osmotic shift, bounded energy, late pressure bias, membrane crenation and stability. `osmotic_particles` emits (positions, polarity, `membrane` node radii, `expelled` strikes) feed `tools/viz/demos/render_osmotic.py` for an evident-cell replay video, with no fixed osmotic law driving the animation.
- `examples/experiments/testscenario_pascal.js`: validation scenario for Pascal's principle and material deformation (`docs/testscenario_pascal-todo.md`); three vessel models (ideal-rigid, Hookean/plastic, finer micro/macro structural mesh) are advanced through `thermalize → baseline → compress → hold → release` phases with per-bucket deterministic initialization, emitting live pressure windows, wall profiles, elastic/plastic displacement, and `pascal_summary` flags (`pascal_principle_holds`, `plastic_damping_observed`, `macro_mesh_consistent`).
- `examples/experiments/trech_helpers.js`: JS helper module (units, constants, material presets, geometry helpers).
- `examples/experiments/config_multi_beam_units.js`: unit conversion + multi-beam composition example (uses `beams` array normalization).
- `examples/experiments/include_error_demo.js`: `TRECH_INCLUDE` stack demo (intentional failure via `include_error_helper.js`).
- `examples/lab/realtime_lab_bootstrap.json`: JSON bootstrap config for `trech lab` (no JS authoring required).
- `examples/lab/realtime_lab_commands.jsonl`: sample real-time lab command stream (`patch`/`simulate`/`snapshot`).

Helper modules are single-file today; load them with `TRECH_INCLUDE("trech_helpers.js")` to keep line numbers stable.

Optics can be constant or spectral. Use `optics.spectrum` with `energyEv` or `wavelengthNm`
entries to override refractive index/absorption/scatter per wavelength while keeping the
config JSON canonical.
H2O stubs author `system` blocks in JS to label ensembles and keep aggregation point-agnostic.

CNT runs are still a parallel track for schema/physics coherence, but they now use the
generic `geometry.volumes` surface. Volumes declare shapes (box/tube/sphere), materials,
placements, and optional `scoreEdep` flags. The CNT stubs steer the beam across a tube
shell volume to exercise `volume_edep_mev` while keeping comparisons focused on electron
transport; photon counts are a secondary comparison in mixed tests.

## Essential test scenarios

This is the canonical set of physics/chemistry scenarios the validation suite
exercises, grouped by **how much each one learns from Geant4 vs. relies on a
pre-written law**. The project thesis (see the top of this file) is to obtain
behaviour from Geant4 particle transport and use classical formulas only for
**comparison/validation** — so each scenario below is labelled with Geant4's
role. Re-run them all and regenerate `docs/validation_report.md` with
`scripts/run_validation_suite.sh`; each row's **validation case** is the
pass/fail guard. Honest scope is stated per tier — Geant4 transports particles
but cannot itself form bound molecules, compute band structure, or evolve a
chemical network, so those tiers use a hook-layer model with Geant4 as an
anchor/clock, never a fitted rule standing in for the physics.

Every scenario below has an **evident animation** under `tools/viz/demos/`
(e.g. `cnt_structure.gif`/`cnt_circuit.gif` — nanotubes with electrons flowing
and a panning CNTFET circuit; `csda_bragg.gif` — a proton stopping at its Bragg
peak; `beer_lambert.gif`, `h2o_molecule.gif`, `electrolysis.gif`, …). See
[`tools/viz/demos/README.md`](tools/viz/demos/README.md); regenerate with
`render_physics_anims.py` + the per-scenario renderers.

**Tier 1 — behaviour *derived from* Geant4 (no pre-written physical law drives the result; the classical formula is only the cross-check):**

| Scenario | Validates | Geant4 role | Validation case |
|---|---|---|---|
| [`viz_refraction_demo.js`](examples/experiments/viz_refraction_demo.js) | refractive index `n(λ)` of air/water/glass, ordering, `n ≥ 1`, KK window | `G4EmCalculator` photo/Compton/Rayleigh cross sections → Beer-Lambert extinction → **Kramers-Kronig** dispersion → `n`. No `n` is ever hardcoded. | `optics_n_water/glass/air`, `optics_index_ordering`, `optics_index_above_one`, `optics_kk_integration_window` |
| [`analytic_beer_lambert.js`](examples/experiments/analytic_beer_lambert.js) | photon attenuation `T = exp(-μx)` | μ summed from Geant4's **own** atomic cross sections; classical `T` vs the run's measured Monte-Carlo uncollided-primary fraction (≈1% gap) | `analytic_beer_lambert_cross_check` |
| [`analytic_csda_range.js`](examples/experiments/analytic_csda_range.js) | charged-particle range `R_CSDA = ∫dE/(dE/dx)` (20 MeV proton in water) | CSDA range from Geant4's **own** stopping power (`GetCSDARange`) vs the run's measured mean primary track length (a per-primary tally); ≈0.4% gap | `analytic_csda_range_cross_check` |
| [`analytic_photo_fraction.js`](examples/experiments/analytic_photo_fraction.js) | photon process branching `f = σ_phot/σ_total` (30 keV gamma in water) | photoelectric fraction from Geant4's **own** per-process cross sections vs the run's measured fraction of primaries whose first interaction is photoelectric (`G4GammaGeneralProcess` sub-process by EM subtype); ≈0.6% gap | `analytic_photo_fraction_cross_check` |
| [`config_nitrogen_carbon_cycle.js`](examples/experiments/config_nitrogen_carbon_cycle.js) | nuclear cycle `N-14 + n → C-14 + p`, `C-14 → N-14 + e⁻ + ν̄` | Geant4 isotope masses → Q-values + charge/baryon conservation | `nuclear_cycle_conservation`, `nuclear_cycle_q_value_closure` |

**Tier 2 — Geant4-*anchored* mesoscale (a hook-layer model whose rate/selectivity is scaled by live Geant4 data; validated against a closed-form law):**

| Scenario | Validates | Geant4 role | Validation case |
|---|---|---|---|
| [`testscenario_efflux.js`](examples/experiments/testscenario_efflux.js) | passive membrane efflux → first-order clearance `N(t)=N₀e^{-kt}` (Fick/Overton) | per-event `ctx.event` transport stats + `G4EmCalculator` membrane/cytosol μ-ratio scale the permeation rate (illustrative, flagged); PubChem XLogP sets selectivity | `efflux_first_order_kinetics` |
| [`testscenario_h2o_electrolysis_combustion.js`](examples/experiments/testscenario_h2o_electrolysis_combustion.js) | electrolysis + inverse combustion: 2 H₂O → 2 H₂ + O₂ → 2 H₂O, atoms conserved | event-level e⁻ energy-deposition/track stats + `G4EmCalculator` H₂O/H₂/O₂ anchors scale the reaction rates; PubChem formulas drive stoichiometry | `h2o_electrolysis_combustion_cycle` |
| [`testscenario_magnetic_resonance.js`](examples/experiments/testscenario_magnetic_resonance.js) | **NMR/MRI of a 5 cm³ water cube**: hook-layer Bloch dynamics **discover** the Larmor line (γ/2π = 42.577 MHz/T, 0.001% gap) from the FID carrier; signal scaled by proton density | Geant4 builds the phantom + receiver coil and, via the new material-probe surface (`ctx.materials`), supplies the ¹H (proton) number density (6.686e22/cm³ = literature); `G4EmCalculator` beer_lambert anchor + per-event clock | `magnetic_resonance_water` |
| [`testscenario_magnetic_resonance_tissues.js`](examples/experiments/testscenario_magnetic_resonance_tissues.js) + [driver](scripts/run_magnetic_resonance_tissues.py) | **MRI tissue contrast, REAL photons**: per NIST tissue the excitation count ∝ Geant4's proton density, Geant4 produces **every consequent photon**, a NaI shell detects the real energy → cortical bone **0.60× water** (MRI-dark), corr 0.9995 | Geant4 computes ¹H density (`material_probes`) that sets the emission count, then really transports + detects all consequent radiation (`receiver_coil` `volume_edep_mev`) | `magnetic_resonance_tissue_contrast` |
| [`testscenario_magnetic_resonance_imaging.js`](examples/experiments/testscenario_magnetic_resonance_imaging.js) | **1D MRI image line**: a field gradient encodes position (`ω(x)=γ(B₀+G$_x$·x)`); DFT of the readout reconstructs the proton-density profile — positions recovered to **0.001 mm**, air gap **black**, cortical bone **dark** | Geant4 builds the real NIST-tissue phantom row + transports the probe, and supplies each voxel's ¹H density (`ctx.materials`) that weights the image | `magnetic_resonance_image_line` |

**Tier 3 — molecular-dynamics ladder (classical MD in the hook layer, Geant4 as the deterministic per-tick clock; validated against measured liquid/mechanical data):**

| Scenario | Validates | Geant4 role | Validation case |
|---|---|---|---|
| [`h2o_molecule_stability.js`](examples/experiments/h2o_molecule_stability.js) | a single H₂O stays bound (bond ≈0.957 Å, angle ≈104.5°, energy drift <2%) | per-tick clock | `h2o_molecule_bonds_stable` |
| [`h2o_cluster_fluid.js`](examples/experiments/h2o_cluster_fluid.js) | 8-molecule hydrogen-bonded droplet (bounded Rg, ~10 contacts, ~313 K) | per-tick clock | `h2o_cluster_fluid_stable` |
| [`h2o_bulk_water.js`](examples/experiments/h2o_bulk_water.js) | periodic bulk water O-O `g(r)` first peak ≈2.8 Å, self-diffusion (Einstein + Green-Kubo) | per-tick clock | `h2o_bulk_water_structure` |
| [`h2o_diffusion_temperature.js`](examples/experiments/h2o_diffusion_temperature.js) | self-diffusion `D(T)` rises with T, tracks measured water | per-tick clock | `h2o_diffusion_temperature_trend` |
| [`testscenario_pascal.js`](examples/experiments/testscenario_pascal.js) | Pascal's principle (rigid transmits pressure; deformable damps it) | per-tick clock | `pascal_principle_holds` |
| [`testscenario_osmotic.js`](examples/experiments/testscenario_osmotic.js) | osmosis: water leaves a hypertonic cell, crenation, size/polarity exclusion | per-tick clock | `osmotic_shift_observed` |

**Tier 4 — CNT electronics (Vostok; hook-layer tight-binding + Fermi-Dirac statistics, Geant4 transports electrons through the channel geometry):**

| Scenario | Validates | Geant4 role | Validation case |
|---|---|---|---|
| [`cnt_band_structure.js`](examples/experiments/cnt_band_structure.js) | metallic/semiconducting `(n−m) mod 3` rule, `E_g ∝ 1/d` law, curvature secondary gaps | transports e⁻ through a representative (10,0) tube | `cnt_band_structure` |
| [`cnt_logic_gates.js`](examples/experiments/cnt_logic_gates.js) | **CNT circuit**: full CNTFET gate family + half/full/2-bit-adder **truth tables confirmed**; ~60 mV/dec Fermi swing; metallic tube shorts the logic | transports e⁻ through the (16,0) channel each event | `cnt_logic_gates` |

**Tier 5 — learning, anti-degeneration & engine invariants (keep runs honest and non-degenerate):**

| Scenario | Validates | Validation case |
|---|---|---|
| [`optics_surrogate_demo.js`](examples/experiments/optics_surrogate_demo.js) | the ridge-learned high-Z `n` (NaI ≈1.77, where the f-sum extractor fails at ≈1.33) reaches transport RINDEX | `optics_surrogate_transport_applied` |
| [`glass_of_water_varied.js`](examples/experiments/glass_of_water_varied.js) | a varied beam samples a real distribution (not 1 identical primary) | `sampling_diversity_non_degenerate` |
| [`h2o_fluid.js`](examples/experiments/h2o_fluid.js) | brine/element-component material build closes without the historical SIGSEGV | `h2o_fluid_brine_run_closes` |
| `viz_refraction_demo.js` (reused) | determinism replay, primaries accounting, system-density arithmetic, event-feature stats, viz schema, material composition | `determinism_replay`, `primaries_accounting_closure`, `system_volume_density_arithmetic`, `event_feature_*`, `viz_*`, `material_composition_sums_to_one` |

> **Next on-thesis additions:** the charged-particle CSDA-range check above (Tier 1) landed as the companion to Beer-Lambert. The next data-driven analytic checks (`AnalyticCheckResult` stays extensible via `measuredField`) are the **Compton edge / Klein-Nishina** spectrum and **photofraction vs energy**. Tracked in `ROADMAP.md`.

## Scenario animation gallery

Every essential test-suite scenario has an **evident animation** — it shows what
the scenario simulates, with the live validated status overlaid. Regenerate with
`tools/viz/demos/render_physics_anims.py` plus the per-scenario renderers (see
[`tools/viz/demos/README.md`](tools/viz/demos/README.md)).

**Tier 4 — CNT electronics (Vostok): nanotube structures with electrons, and a CNTFET circuit**

<table>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/cnt_structure.gif?raw=true" width="400"/><br/><sub><b>cnt_structure</b> — three chirality archetypes rolled from their <i>real</i> (n,m) honeycomb (armchair (5,5) / zigzag (9,0) / zigzag (16,0) — wrapping asymmetry, not just diameter); a labelled e⁻ <b>source contact (the base)</b> injects electrons toward the drain, metallic current passes while semiconducting electrons reflect at the red band-gap barrier</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/cnt_circuit.gif?raw=true" width="400"/><br/><sub><b>cnt_circuit</b> — emitted NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR CMOS topologies, one truth row at a time (held, static camera, progress bar + output-node readout) with active CNTFET paths from validated truth rows</sub></td>
</tr>
</table>

**Tier 1 — behaviour derived from Geant4 (classical formula only as the cross-check)**

<table>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/csda_bragg.gif?raw=true" width="400"/><br/><sub><b>csda_bragg</b> — a 20 MeV proton slows to its Bragg-peak stop; Geant4 CSDA range vs measured track length</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/beer_lambert.gif?raw=true" width="400"/><br/><sub><b>beer_lambert</b> — γ beam attenuating in a 50 mm water slab; ~41% transmitted, matching exp(−μx)</sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/nuclear_cycle.gif?raw=true" width="400"/><br/><sub><b>nuclear_cycle</b> — ¹⁴N + n → ¹⁴C + p, then ¹⁴C → ¹⁴N + e⁻ + ν̄ (Geant4 Q-value closure)</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/glass_of_water_beam.gif?raw=true" width="400"/><br/><sub><b>glass_of_water</b> — a photon refracting through the cup at the Geant4-derived n(λ)</sub></td>
</tr>
</table>

**Tier 2 — Geant4-anchored mesoscale (validated against a closed-form law)**

<table>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/efflux_clearance.gif?raw=true" width="400"/><br/><sub><b>efflux</b> — a cell clears a lipophilic molecule by passive permeation → first-order law</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/electrolysis.gif?raw=true" width="400"/><br/><sub><b>electrolysis</b> — sampled H₂/O₂ molecule packets converge at ignition and recombine into bonded H₂O</sub></td>
</tr>
</table>

**Tier 3 — molecular-dynamics ladder (Geant4 as the per-tick clock)**

<table>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/h2o_molecule.gif?raw=true" width="400"/><br/><sub><b>h2o_molecule</b> — O–H bonds vibrating around 0.957 Å / 104.5° while staying bound</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/h2o_cluster.gif?raw=true" width="400"/><br/><sub><b>h2o_cluster</b> — 8 molecules in a stable hydrogen-bonded droplet (~313 K)</sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/h2o_bulk_water_gr.gif?raw=true" width="400"/><br/><sub><b>h2o_bulk_water</b> — periodic bulk water growing the O–O g(r) onto the measured 2.8 Å peak</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/diffusion_temperature.gif?raw=true" width="400"/><br/><sub><b>diffusion_temperature</b> — molecules diffusing faster at 281 / 298 / 313 K (D rises with T)</sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/pascal_press.gif?raw=true" width="400"/><br/><sub><b>pascal_press</b> — hook-emitted pressure gauges and a deformable wall that keeps plastic rounded set after release</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/osmotic_dehydration.gif?raw=true" width="400"/><br/><sub><b>osmotic</b> — a cell crenating in a hypertonic bath, expelling water through its pores</sub></td>
</tr>
</table>

**Tier 5 — learning & anti-degeneration**

<table>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/optics_surrogate.gif?raw=true" width="400"/><br/><sub><b>optics_surrogate</b> — the learned ridge n(NaI) lifting 1.33 → ~1.77 and refracting the ray more</sub></td>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/sampling_diversity.gif?raw=true" width="400"/><br/><sub><b>sampling_diversity</b> — a degenerate single ray vs a varied beam fanning out in position / angle / wavelength</sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/Geckos-Ink/trech/blob/main/tools/viz/demos/brine_deposit.gif?raw=true" width="400"/><br/><sub><b>brine_deposit</b> — hydrated Na⁺/Cl⁻ ion pairs in water; EM deposits stay on the beam path through brine</sub></td>
<td></td>
</tr>
</table>

## Outputs

- `trech_provenance.jsonl`: run provenance records (config JSON/hash, seed, Geant4/runtime metadata, determinism mode, stratify model path/hash, stratify source counters, hook registration/dispatch counters with step/emit guardrail metadata, `hook_patch_count`/`hook_emit_count`/`hook_emit_dropped_count`, nuclear cycle summary counts, and system event moment summaries).
- `trech_scores.jsonl`: scoring summaries (total energy deposit, per-volume energy deposits when `scoreEdep` is enabled, optical photon counts/track length when optics are enabled, determinism mode, stratify model hash metadata, hook dispatch counters/guardrail fields including emit guardrails, `hook_patch_count`/`hook_emit_count`/`hook_emit_dropped_count`, system-level density metrics plus Geant4-merged `event_feature_stats`, chemistry/DNA flags, stratify counts, and nuclear cycle consistency/Q-value payloads).
- `trech_hook_emits.jsonl`: deterministic hook `ctx.emit(tag, payload)` records (hook name, event/step context, tag, parsed payload).
- `trech_event_scores.jsonl`: per-event scoring summaries when `stratify.enable` is true.
- `trech_event_features.jsonl`: per-event features when `stratify.dumpFeatures` is true.
- TorchScript models consume the feature vector in `FeaturePipeline::kSchemaId` order (`trech_event_features_v1`: `total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`).
- `trech_resim_queue.jsonl`: exceptional event queue when `stratify.dumpResimQueue` is true.

By default these are written to the current working directory; use `--output` to redirect.
Schema details: `docs/output_schema.md`.
System aggregation uses `system.volumeMm3` when provided; otherwise it derives volume from the medium box (if present) or the world cube.
Hook registrations are recorded in the config JSON; determinism and stratify model provenance fields are emitted directly by the runtime.

## Scenario authoring direction

- JS is a full authoring runtime: use helpers to convert units, assemble multi-entity configurations, and gate choices on runtime arguments.
- Experiments set `globalThis.TRECH_CONFIG` to an object, JSON string, or function returning one; `globalThis.TRECH_HOOKS` is optional and recorded for provenance.
- `TRECH_FLOW(initial)` is available globally for flow-like authoring with deterministic fluent transforms and checks: `set`, `defaults`, `merge`, `push`, `ensureArray`, `derive`, `selectBeam`, `normalizeDetectorAliases`, `finalize`, `require`/`assert`, `when`, `tap`, and `build`.
- Determinism is explicit via `determinism.mode` (`"strict"` default, `"predictive"` to enable ML inference paths when configured).
- Use `geometry.volumes` to describe named shapes and placements; enable `scoreEdep` to capture per-volume energy deposits.
- Build recursive scenes by assigning `placement.parent` to other volume names; container volumes (vacuum material) can bound fluids without modeling container chemistry.
- Use `materials` to define simple mixtures (density + component fractions) when NIST materials are insufficient; optional `smiles` is a placeholder for future registry metadata.
- `beams` is supported for array definitions (normalized to the active/first entry); `beam` remains as a single-entry alias.
- Use `nuclear.cycles` for isotope-cycle consistency analysis. Reactions are declared with `reactants`/`products` participants (`{z,a}` ions or `particle` names) and TRECH computes Geant-backed Q-values plus charge/baryon conservation checks.
- `detector` remains the canonical runtime key, but top-level `environment` and `medium` are accepted as authoring aliases and normalized by the loader.
- `G4_*` materials refer to the Geant4/NIST database; wrap them with JS presets when clarity matters.
- Collections should use plural names and accept either a single object or an array; loaders normalize single objects into arrays (materials/components/tags/optics.spectrum/hooks.registered accept single values).
- Multi-beam, multi-source, and layered systems are intended targets; the engine should grow toward generic particle/source definitions without schema fragmentation.
- Use `TRECH_INCLUDE` to load helper modules while preserving per-file line numbers.
- JS runtime errors include stack traces with filenames (including `TRECH_INCLUDE` sources).
- Hook callback dispatch points are wired at init/run/event/step boundaries and exported as deterministic run-level counters (`hook_on_*`) with `hooks.maxStepCallbacks` guardrails.
- Hook callbacks receive deterministic context (`ctx.config`, `ctx.runtime`, optional `ctx.event`, optional `ctx.step`, persistent `ctx.state`, deterministic `ctx.rng.uniform/int`, `ctx.emit(tag, payload)`, and — when `materialProbe` is enabled — `ctx.materials`), with per-callback emit guardrails (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) and dropped-emit accounting. `onEventEnd` exposes Geant4 event metrics on `ctx.event` (`edepMeV`, track/step counts and lengths), and `ctx.materials["<name>"]` exposes Geant4-derived material composition (density, `numberDensityPerCm3.H`, electron density, mean excitation I), so hook-layer inference can consume live transport data and material physics.
- `TRECH_PUBCHEM(name)` loads a PubChem JSON cache record from `TRECH_PUBCHEM_CACHE_DIR` first, then the legacy `data/pubchem` cache, so scenarios can use real fetched substance metadata without committing new cache files.
- `onInit` supports deterministic config patching through return value `{ override: { ... } }`; patch application is intentionally whitelisted (`beam`, `run`, `optics`, `system`, `stratify`) and tracked in outputs.
- Hook API proposal: `docs/scenario_hooks.md` (names, allowed operations, provenance requirements).

## Dependencies

- **Geant4**: tracked as a required submodule under `thirds/geant4`.
  You still need a Geant4 build/install to build TRECH; set `Geant4_DIR` or `CMAKE_PREFIX_PATH` (for example, to the submodule build/install).
  Build with `-DTRECH_ENABLE_DNA_CHEM=ON` to enable Geant4-DNA physics when `chemistry.enable` is true.
  If a local clone exists under `thirds/geant4`, prefer it before fetching elsewhere.
  `Geant4Config.cmake` is generated by the Geant4 build/install; the template lives at `thirds/geant4/cmake/Templates/Geant4Config.cmake.in`.
  Recommended: build in `build/geant4-build` and install to `build/geant4-install` to keep the submodule clean.
- **QuickJS**: required for JS experiments. Either vendor it under `thirds/quickjs/quickjs`
  or configure with `-DTRECH_FETCH_DEPS=ON` (enabled by presets).
- **LibTorch**: optional for `TRECH_ENABLE_TORCH`. Provide `Torch_DIR` or `CMAKE_PREFIX_PATH` for the LibTorch install.
- **nlohmann/json**: used for config parsing. Vendor under `thirds/json` or fetch.

## Repository layout

```
include/trech/        public headers
src/                 C++ implementation
apps/trech-cli/       CLI entrypoint
examples/experiments  JS experiments
tests/                unit tests
docs/                 roadmap and structure
thirds/               submodules and vendored dependencies
```

## Testing

```
ctest --preset dev
```

Fallback if presets are unavailable:

```
ctest --test-dir build/dev
```

## Validation script

```
scripts/run_validation.sh
```

Env overrides: `BUILD_PRESET` (default `dev`), `EVENTS` (default `100`), `SCORES_FILE` (default `trech_scores.jsonl`), `PROVENANCE_FILE` (default `trech_provenance.jsonl`), `SUMMARY_FILE` (default `docs/validation_summary.md`).
Requires Ninja, a C++ compiler, Python 3, and Geant4 for the H2O run.
Successful runs write `docs/validation_summary.md` via `scripts/update_validation_summary.py`.

## Smoke test script

```
scripts/run_smoke.sh
```

Env override: `BUILD_PRESET` (default `dev`). Requires Ninja and a C++ compiler. Runs `ctest` after building.

## Validation status

- Magnetic-resonance Stage 3 — 1D MRI image line via frequency encoding landed (2026-07-05, no C++): `testscenario_magnetic_resonance_imaging.js` builds a real NIST-tissue phantom row (incl. an air gap + cortical bone), reads each voxel's Geant4 ¹H density (`ctx.materials`), applies a readout gradient (`ω(x)=γ(B₀+G_x·x)`) and **DFT-reconstructs the 1D proton-density image line**: positions recovered from peak frequency to **0.001 mm**, amplitude↔proton corr **1.0**, air gap **0.01** (black) / cortical bone **0.59** (dark). Guarded by `magnetic_resonance_image_line` (6/6, category `resonance`); report regenerated to **37 cases, 33 pass / 0 fail / 4 info / 0 skip**. Rendered `magnetic_resonance_imaging.png`. Completes the magnetic-resonance track (discover Larmor → real-photon tissue contrast → image); honest scope: the gradient encoding + reconstruction are hook-layer signal processing on Geant4-supplied proton densities + a real Geant4 phantom/transport.
- Magnetic-resonance Stage 2 — virtual-tissue contrast with REAL Geant4 photon emission landed (2026-07-04, no C++): shared scenario `testscenario_magnetic_resonance_tissues.js` + multi-run driver `scripts/run_magnetic_resonance_tissues.py`. Per NIST tissue the excitation-primary count = `round(base · Geant4 ¹H density(T)/density(water))` (an ignorant `material_probes` fact); Geant4 produces **every consequent photon** and a NaI shell scores the REAL deposited energy. Over 6 tissues: water 1.00 / adipose 0.97 / muscle 0.95 / brain 1.00 / lung 0.98 / **cortical bone 0.60×** (MRI-dark), corr(detected signal, proton density) **0.9995**, byte-reproducible. Guarded by `magnetic_resonance_tissue_contrast` (5/5, category `resonance`); report regenerated to **36 cases, 32 pass / 0 fail / 4 info / 0 skip**. Rendered `magnetic_resonance_tissues.png`. Honest scope: the excitation-per-proton is a labelled proxy; REAL = the Geant4-set emission count + the Geant4-transport detection tally.
- Magnetic-resonance Stage 1 + Geant4 material-composition surface landed (2026-07-04): new engine surface (`MaterialProbe.{hpp,cpp}`, `materialProbe`/`ctx.materials`) exposes Geant4's per-material composition — density, per-element atoms/cm³ (¹H = proton density), electron density, mean excitation I, radiation length — to hooks and to `trech_scores.jsonl` (`material_probes`), opt-in so existing scenarios stay byte-identical. `testscenario_magnetic_resonance.js` builds a 5 cm³ water phantom + copper coil and runs hook-layer Bloch dynamics that **discover** the Larmor line from the FID carrier (feeding only proton γ + machine B0): γ/2π **42.5768 MHz/T** vs CODATA 42.5775 (0.001%), Geant4 water proton density **6.686e22/cm³** = literature (0.006%), T2* recovered 0.1%, receiver-coil Geant4 tally 0.947 MeV, byte-reproducible under `threads:1`. Guarded by `magnetic_resonance_water` (category `resonance`, 7/7 incl. a `material_probes`↔`ctx.materials` cross-check). `ctest --preset dev` 10/10; validation report regenerated to **35 cases, 31 pass / 0 fail / 4 info / 0 skip**.
- Full suite/media refresh completed on 2026-06-30: `scripts/run_validation_suite.sh` reran the default slow suite with bulk water and D(T) enabled and reported **32 cases, 28 pass / 0 fail-error / 0 skip / 4 info**. The glass-of-water validator and optics-surrogate held-out validator were regenerated (`surrogate LOO MAE 0.0839 < extractor MAE 0.1406`), and the scenario GIF/MP4/PNG gallery under `tools/viz/demos/` was refreshed from the new `build/dev/out_*` outputs.
- Scenario execution audit (2026-06-30): fresh probes confirmed `trech run` initializes Geant4 and executes `BeamOn`, while several H2O/CNT/biology cases honestly remain hook-layer MD/device/reaction proxies driven by Geant4 event metrics or `G4EmCalculator` anchors. Fixed a real audit gap: run-end `event_feature_stats` now use Geant4 accumulables so MT worker features merge into `trech_scores.jsonl` (12-event stratify probe count/means match event rows), and `scripts/run_validation_suite.sh` no longer swallows selected scenario/export failures with `|| true`.
- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 50`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 50`, output `build/dev/out_h2o_single`).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 50`, output `build/dev/out_h2o_optics`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use container volumes with explicit materials (diameter 3.0 nm, wallCount 5) and a 0.8 MeV electron beam, rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5) and `volume_edep_mev` scoring, rerun to refresh outputs.
- CNT electronic-structure comparison rerun completed with `examples/experiments/cnt_band_structure.js` (`--events 5`, output `build/dev/out_cnt_band_structure`): 12 nominal-metal / 14 semiconducting tubes, semiconducting `E_g*d = 0.8236 eV*nm`, quasi-metallic curvature `E_curv*d^2 = 0.050 eV*nm^2`, max secondary gap 0.1007 eV; `cnt_band_structure` validation passes and `tools/viz/demos/cnt_band_structure.png` was regenerated.
- CNT logic-gates run completed with `examples/experiments/cnt_logic_gates.js` (`--events 8`, output `build/dev/out_cnt_logic_gates`): working **(16,0)** CNTFET on/off `3.33e5`, all 8 gate truth tables + half/full/2-bit-adder tables confirmed, recovered subthreshold swing `60.27 mV/dec` (ideal 59.53), metallic armchair (5,5) on/off 1.0 collapses outputs to ~Vdd/2 and breaks the logic, Geant4 e- drive 8 events / 32 steps / 8.0 mm; `cnt_logic_gates` validation passes (10 flags). The run now emits 8 `visual_topologies` plus `visual_source` (`PubChem` not applicable to CNT chirality/device structure); `cnt_logic_gates.png`, `cnt_structure.gif`, and the data-driven `cnt_circuit.gif` were regenerated. Current validation reporter over `build/dev`: 32 cases, 28 pass / 0 fail-error / 4 info / 0 skip.
- CSDA-range analytic cross-check landed (2026-06-30): `examples/experiments/analytic_csda_range.js` fires a 20 MeV proton into water; the engine derives the CSDA range from Geant4's own stopping power (`G4EmCalculator::GetCSDARange`, with `SetBuildCSDARange(true)` enabled only when a `csda_range` check is configured) and compares it to a **new per-primary track-length tally** (`primary_mean_track_length_mm`, summed over `parentID==0` steps in `SteppingAction`). Derived **4.282 mm** vs measured **4.266 mm** (**0.38%**), all 5000 protons contained (0 transmitted), stopping power 2.59 MeV/mm (≈ NIST PSTAR). Deterministic (`threads:1`, byte-identical reruns). Guarded by `analytic_csda_range_cross_check` (category `analytic`); `ctest --preset dev` 9/9; report now **32 cases, 28 pass / 0 fail / 4 info / 0 skip**.
- Osmotic scenario refinement completed on 2026-06-28: the Brownian bath now uses a Langevin thermostat instead of unbounded random heating, and validation later tightened to the biological-cell 9/9 check set (`net_water_flux_out=71`, first crossing at tick 3, bounded KE, late pressure bias, polarity exclusion, crenation, membrane stability). `ctest --preset dev` passed 9/9; current validation reporter over `build/dev` is green at 32 cases, 28 pass / 0 fail-error / 4 info / 0 skip.
- Osmotic biological-cell replay video landed: `tools/viz/demos/render_osmotic.py` consumes the scenario's `osmotic_particles` hook emits and writes `tools/viz/demos/osmotic_dehydration.mp4` (+ `.gif`), replaying an evident top-down cell — crenating lipid membrane, cytoplasm/nucleus/organelles, channel pores expelling water into the hypertonic glucose bath, and flash markers where the membrane expels wrong-polarized molecules — directly from TRECH output. The spring/mesh membrane is now simulated in the scenario (turgor-driven crenation emitted as physical state), not just visualized; the wrong-polarized `ion` species is rejected by polarity selectivity. Validation tightened to 9/9 checks.
- Membrane-efflux comparison scenario landed (`examples/experiments/testscenario_efflux.js`): a cell clears a lipophilic waste molecule (benzene) by passive lipid permeation (Overton's rule), reproducing the classical first-order clearance law `N(t)=N₀·e^(−kt)` (log-linear fit R²≈0.99, 72/80 cleared, 30/30 essentials retained). **PubChem XLogP** (benzene +2.1 vs D-glucose −2.6, loaded via `TRECH_PUBCHEM` from `TRECH_PUBCHEM_CACHE_DIR`) decides which molecule permeates; Geant4 `G4EmCalculator` membrane/cytosol EM ratio (μ_lipid≈0.0291/mm vs μ_water≈0.0377/mm at 30 keV → 1.30, emitted live as `analytic_checks`; illustrative) and per-event Geant4 transport metrics (`ctx.event`, 12,789 steps / 4.99 MeV in the refreshed run) scale the rate. The molecules move by drift-diffusion (coherent cytoplasmic streaming + outward efflux drift — directed flow, not jitter) and are drawn as ring glyphs with real PubChem 2D structure cards. Rendered by `tools/viz/demos/render_efflux.py` → `efflux_clearance.mp4`/`.gif`. Guarded by `efflux_first_order_kinetics` (6/6 checks incl. lipophilicity selectivity + Geant4 event drive); `ctest --preset dev` 9/9.
- CNT animation clarity refresh (2026-07-01): the two CNT GIFs were reworked for readability. **`cnt_structure.gif`** now rolls each tube from its *own* chiral vector `C = n·a1 + m·a2` (faithful `build_tube_chiral`), so armchair vs zigzag **wrapping asymmetry** is visible rather than only diameter; it renders all three emitted archetypes (metallic armchair `(5,5)` / quasi-metallic zigzag `(9,0)` / semiconducting zigzag `(16,0)`) and adds a clearly-labelled electron **source contact (the base)** + drain electrode plates so it is obvious where the particles come from and which way current flows, with per-tube status cards (chirality kind, θ, d, gap, behaviour). **`cnt_circuit.gif`** was de-frenetified: gate/truth-row selection moved from a continuous `int(t·len)` mapping (which strobed) to a held step-plan (`--hold` frames per row, default 6) with a **static camera**, a bottom progress bar, and a lit output node (`Y=` green 1 / red 0) + `✓ MATCH`/`✗ MISMATCH` readout, and it re-encodes against a shared palette with `disposal=1` to fall from ~7 MB to ~1.4 MB. Regenerated `cnt_structure.gif` (915 atoms) and `cnt_circuit.gif` (28 truth rows, 168 frames).
- Scenario animation clarity refresh (2026-06-30): electrolysis snapshots now carry sampled H2/O2/product-H2O packets so the burn shows correlated molecule consumption/recombination; Pascal snapshots carry pressure gauges, wall profiles, and plastic displacement; the CNT structure GIF now reads the `(5,5)`/`(16,0)` devices from `cnt_gates_summary`, and the CNT circuit GIF now renders the emitted per-gate CMOS topologies instead of a fixed inverter-chain template; brine shows hydrated Na+/Cl- pairs with deposits limited to the visible brine/beam path. Regenerated `electrolysis.gif`, `pascal_press.gif`, `brine_deposit.gif`, `cnt_structure.gif`, and `cnt_circuit.gif`.
- H2O electrolysis + inverse-combustion reaction-cycle scenario landed (`examples/experiments/testscenario_h2o_electrolysis_combustion.js`): real-time fetched PubChem formulas for water/hydrogen/oxygen drive a deterministic hook-layer reaction ledger, while Geant4 event-level e- energy deposition/track statistics (`ctx.event`) and live `G4EmCalculator` H2O/H2/O2 interaction anchors directly scale the stochastic split/recombination rates. Validation `h2o_electrolysis_combustion_cycle` passes: 180 H2O → 180 H2 + 90 O2, both cathodes active (92/88 H2, imbalance 0.022), combustion recovers 180 H2O, atoms conserved, analytic labels emitted, and Geant4 event drive positive (24.0 MeV deposited). Validation report now has 32 cases, 28 pass / 0 fail / 4 info.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- `examples/experiments/h2o_fluid.js` SIGSEGV fixed: it referenced `G4_SODIUM_CHLORIDE` (not a Geant4 NIST material), and `buildCustomMaterials` left a malformed mixture that crashed Geant4. Fixed via element components (`MaterialComponentConfig.element`, so salt = Na+Cl) and fail-safe material building; h2o_fluid now runs clean and the full scenario sweep is green (except the by-design `include_error_demo`).
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Nitrogen-carbon cycle scenario run completed with `examples/experiments/config_nitrogen_carbon_cycle.js` (`--events 5`, output `build/dev/out_nitrogen_cycle`); scores now include `nuclear_cycles` with forward/backward Q-values (~0.626 MeV and ~0.156 MeV) and macro transition consistency (`gas_to_solid`).
- Geant4 build/install is available at `build/geant4-install` (from submodule `thirds/geant4`); point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` to `detector` and preserved flow-composed optics/materials/beam fields.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` + `TRECH_FLOW`.
- `trech lab` bootstrap smoke run completed with `examples/lab/realtime_lab_bootstrap.json` + `examples/lab/realtime_lab_commands.jsonl` (`--output build/dev/out_lab_boot`); command stream applied live patches, ran simulation, and emitted snapshot JSON without JS scenario authoring.
- Determinism/provenance smoke run completed with `examples/experiments/config_stratify_ml.js` (`--events 1`, output `build/dev/out_determinism`); outputs now include `determinism_mode`, `predictive_mode`, `stratify_model_hash`, and provenance stratify source counters.
- Hook runtime extension smoke run completed with `examples/experiments/config_hook_dispatch.js` (`--output build/dev/out_hook_runtime_ext`); scores/provenance now include `hook_patch_count` and `hook_emit_count`, and `trech_hook_emits.jsonl` captures deterministic emit payloads.
- Hook emit guardrails now enforce per-callback caps and payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`); scores/provenance include `hooks_guardrail_max_emits_per_callback`, `hooks_guardrail_max_emit_payload_bytes`, and `hook_emit_dropped_count` (`ctest --preset dev` passed).
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.

## Benchmark references

Long-form validation benchmarks live under `docs/benchmarks/` as plain
text snapshots. They are the canonical baselines that future commits
diff against: when a run moves any number, the `.txt` shows the delta
inline in the PR so engine regressions or improvements are caught in
code review. The companion `.md` is human-readable and the `.json`
sidecar is the machine-readable form consumed by tooling.

Conventions for adding a benchmark:

- The scenario lives under `examples/experiments/<name>.js`.
- The validator lives under `scripts/validate_<name>.py` and emits
  three artifacts in one pass: `docs/<name>.md` (markdown report),
  `docs/<name>.json` (sidecar), `docs/benchmarks/<name>.txt`
  (committed reference). The `.txt` must be deterministic given the
  same run inputs so the diff stays clean.
- The validator is wired into `scripts/run_validation_suite.sh` with
  a `SKIP_<NAME>` env knob so CI can opt out individually.

| Benchmark | Scenario | Validator | Reference | Status |
|---|---|---|---|---|
| Glass-of-Water optical inverse | [validation_glass_of_water.js](examples/experiments/validation_glass_of_water.js) | [validate_glass_of_water.py](scripts/validate_glass_of_water.py) | [`docs/benchmarks/validation_glass_of_water.txt`](docs/benchmarks/validation_glass_of_water.txt) | informational; after the f-sum valence oscillator the engine derives n_water ≈ 1.331 / n_glass ≈ 1.472 (≈99% / ≈103% of handbook, up from ≈1.001) — inverse-Snell recovers n within ≤1.1% rel err at every interface (4000 events / seed 20260525) |

Future benchmarks should be appended as new rows. Tighten the status
column to `pass` / `fail` once a benchmark has a numeric tolerance the
PR check enforces (today the row is informational and the diff is the
signal).

## Roadmap

- Short-term next steps: `ROADMAP.md` (editable source of truth)
- Initial roadmap concept: `docs/trech-roadmap.md` (reference-only)
- H2O experiment spec (initial): `examples/experiments/h2o_fluid_spec.md`
- CNT parallel track for schema/physics coherence: `ROADMAP.md`

## License

See `LICENSE`.

<!--
> ⚠️ **IMPORTANT NOTICE: UPCOMING LICENSE CHANGE** ⚠️
> 
> Currently, this project is distributed under the MIT License. Please be advised that in a future release, the licensing terms will change. The new license will strictly prohibit the use of this software, directly or indirectly, by Italian law enforcement agencies, if not for educational purposes. 
> 
> Users who require compliance with standard Open Source Initiative (OSI) definitions should plan accordingly for future versions.
-->
