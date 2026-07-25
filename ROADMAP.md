# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.
`docs/trech-roadmap.md` is the initial roadmap concept and is reference-only.

> ## ⭐ Engine thesis — the "why" behind every milestone (keep this alive)
>
> Everything in this file serves one goal: **turn a precise Geant4 particle/nano base into
> predictions at the scale a human observes, by inferring UP the dimension ladder
> (atomic → nano → micro → meso → macro) with statistics/ML** — a general-purpose,
> context-driven predictor, not narrow per-output models the user must wire by hand. A user
> should be able to ask a macroscopic question (a stirred glass of water → fluid motion + waves)
> and have it inferred from the microscopic truth by default.
>
> Sputnik (below) is the concrete milestone; the **"Multi-scale statistical inference"** standing
> objective is the doctrine + the plan to get there. This callout is intentionally redundant with
> that section (and with the AGENTS.md thesis callout) so the intent survives even if the file is
> trimmed or an agent starts with no memory — **if you ever prune ROADMAP, keep that standing
> objective and this callout.**

## Sputnik milestone (north star)

- Simulate a single H2O melecule starting from its elementar particle: their behavior and bonds prediction over the time should be stable without "exploding". **[first deliverable landed]** `examples/experiments/h2o_molecule_stability.js` evolves the three nuclei (O, H, H) under a classical flexible-water force field (harmonic O-H bonds r0=0.957 Å + H-O-H angle θ0=104.52°, velocity-Verlet NVE) in the deterministic hook layer; over 400 fs the bonds ring around equilibrium (mean 0.958 Å, max 1.157 Å), the angle stays at 104.5°, and total energy drifts <0.5% — **stable without exploding**, guarded by the `h2o_molecule_bonds_stable` validation case. Honest scope: Geant4 transports particles but cannot form/evolve bound molecular states, so the bonds are classical MD (the "physics for comparison"), with Geant4 as the deterministic per-tick clock. Next: thermal ensembles, more atoms, and bringing the force field closer to measured spectroscopy.
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`. **[electronic-structure step landed 2026-06-12; curvature step landed 2026-06-26]** `examples/experiments/cnt_band_structure.js` computes, per (n,m) chirality, the diameter / chiral angle / metallic-vs-semiconducting character / band gap via hook-layer tight-binding zone-folding. It reproduces the metallicity rule (metallic iff (n-m) mod 3 == 0), the semiconducting primary gap law (E_g = 2·a_cc·γ0/d → E_g·d ≈ 0.82 eV·nm, measured 0.7-0.9), STM anchors within ~1%, and the curvature-induced secondary gap for nominally metallic non-armchair tubes (`E_curv*d² = 0.050 eV·nm²`, max 0.1007 eV; armchairs stay zero-gap). Rendered `tools/viz/demos/cnt_band_structure.png`, guarded by `cnt_band_structure`. Honest scope: Geant4 transports electrons but does not compute band structure; trigonal-warping/Kataura family splitting is next. **[logic gates + circuits landed 2026-06-29; emitted topology viz fixed 2026-06-30]** `examples/experiments/cnt_logic_gates.js` takes the track from band structure to working **devices and digital logic**: it builds CNTFETs from the tight-binding gap (the channel's `E_g` sets the transistor's Fermi-statistics on/off ratio `~exp(E_g/2kT)`), assembles the full static-CMOS gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR as resistive-divider pull-up/pull-down FET networks — the gate output is a real voltage, not an assumed boolean), wires them into a half adder, full adder and 2-bit ripple-carry adder, and **confirms the truth table the electrons produce at every output**. It now emits `visual_topologies` from those same primitive CMOS networks so `render_cnt_circuit.py` draws distinct gate structures rather than a fixed inverter-chain template. It reproduces three textbook results at once: every gate + adder table matches the canonical boolean/arithmetic function; the subthreshold swing recovered from the simulated `I_d(V_gs)` is **60.3 mV/dec** vs the ideal `ln(10)·kT/q` = 59.5 (the room-temperature ~60 mV/dec Fermi limit), rising with T (Fermi smearing); and the on/off ratio is gap-controlled — the working **(16,0)** tube switches by **3.3e5** with clean rails while a **metallic armchair (5,5)** dropped into the same topology has on/off = 1.0, collapses every output to ~Vdd/2 and **destroys the logic** (the metallic-tube short that `docs/CNT/BackToTheCarbon.md` calls the central manufacturing problem). Geant4 transports the e- beam through the representative CNT channel each event; deterministic (`threads:1`, strict, byte-identical reruns). Guarded by `cnt_logic_gates` (category `cnt`, 10 flags). Honest scope (same contract): Geant4 transports electrons but does not compute band structure / Fermi level / device switching, and PubChem is not part of the CNT chirality/device path. Next: sequential logic (a CNTFET latch/flip-flop), Schottky-contact (the second `BackToTheCarbon.md` barrier) and chirality-distribution yield modelling.
- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical. **[molecular-scale step landed]** `examples/experiments/h2o_cluster_fluid.js` extends the single molecule to an 8-molecule ensemble with intermolecular forces (LJ on O-O + Coulomb on SPC charges, thermostatted, with a soft droplet boundary standing in for the bulk); it settles into a stable, hydrogen-bonded liquid-like droplet (~10.5 O-O contacts, Rg ~2.9 Å bounded, ~313 K) that neither evaporates nor collapses over 2400 fs, guarded by `h2o_cluster_fluid_stable`. Same honest scope: classical MD in the hook layer (Geant4 as the per-tick clock). **[bulk step landed]** `examples/experiments/h2o_bulk_water.js` takes it to true bulk: 48 molecules in a periodic box at liquid density with minimum-image and damped-shifted-force (DSF) electrostatics (a real-space alternative to Ewald). It reproduces the measured liquid **structure** — the O-O radial distribution function g(r) has its first peak at **2.798 Å** (experiment 2.8 Å, the hydrogen-bond distance), at a controlled temperature, guarded by `h2o_bulk_water_structure`. **[comparison video landed 2026-06-11]** the scenario emits deterministic `md_snapshot` sidebands (wrapped positions + running g(r) histogram; physics byte-identical) and `tools/viz/demos/render_bulk_water.py` renders the box next to the engine's accumulating g(r) vs the measured 2.80 Å peak (`h2o_bulk_water_gr.mp4|.gif`, embedded in README). **[scale-up landed 2026-06-11]** N 48 → 108 molecules (box 14.8 Å), cutoff 5.4 → 7.0 Å, g(r) range to 7.4 Å: the **~4.5 Å tetrahedral second shell is now resolved** (flagged `second_shell_near_tetrahedral`, reported not gating), with the production-phase mean T 303 K (now averaged after equilibration, excluding the lattice-melt transient). **[SPC/E parameterisation landed 2026-06-11]** moved the force field from plain-SPC to **flexible SPC/E** (Berendsen 1987 charges q_O=-0.8476 + tetrahedral 109.47° geometry) which deepened the inter-shell depletion (min g(r) 0.95 → 0.85). **[rigid SPC/E via SHAKE/RATTLE landed 2026-06-11]** made the canonical *rigid* SPC/E by holding the geometry with holonomic constraints (SHAKE on positions + RATTLE on velocities) instead of stiff harmonic bonds. Removing the O-H stretch that smears intermolecular structure brought the O-O g(r) onto experiment: first-peak height 2.48 → **3.00** (exp ~2.6-3.1), inter-shell minimum **0.85 → 0.775 (experiment ~0.75)** now located at **3.38 Å (experiment ~3.4)**, and coordination **4.73 to both the own-minimum and the 3.4 Å convention — squarely in the measured ~4.3-4.7 band** (second shell 4.36 Å, mean T 305 K). Killing the stiffest motion also let the timestep go 0.2 → **2 fs**, so each run now samples 5000 fs (10× more physical time) at comparable cost. Rigidity is *proven* not assumed: the max post-SHAKE bond residual (~1e-9) is emitted and gates `bulk_water_stable` via `rigid_constraints_held`. **[self-diffusion (dynamics) landed 2026-06-11]** added the first *dynamic* observable — the self-diffusion coefficient from the production-phase O-atom mean-squared displacement (Einstein relation, MSD = 6 D t; the unwrapped `atom.p` trajectory makes this a direct difference). It comes out **D = 2.57×10⁻⁹ m²/s**, essentially on the SPC/E literature value (~2.5×10⁻⁹) and within ~12% of experiment (2.3×10⁻⁹, 298 K), with the run sitting at ~305 K (D rises with T) and a single-origin/finite-size caveat stated. Emitted (`self_diffusion_m2_per_s`, `msd_curve`) + range-checked (`self_diffusion_physical`) + rendered as a standalone MSD comparison plot (`tools/viz/demos/h2o_self_diffusion.png`). **[Green-Kubo cross-check landed 2026-06-12]** the same run now also measures D the OTHER way — the **Green-Kubo** route, D = (1/3)∫⟨v(0)·v(t)⟩dt from the molecular COM-velocity autocorrelation (the first observable built on the new shared MD core). The two independent estimates agree: **Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s** (~8%), both near experiment 2.3; and the VACF carries the textbook **negative cage-backscattering dip** (−0.09 at ~300 fs) — the dense-liquid signature of molecules rebounding off their hydrogen-bond cage. Guarded by `green_kubo_consistent_with_einstein`, rendered as `tools/viz/demos/h2o_vacf_diffusion.png`. **[D(T) multi-point trend landed 2026-06-12]** `examples/experiments/h2o_diffusion_temperature.js` sweeps three temperatures in one deterministic anneal (melt once, then per block: multi-ps equilibration + a **multi-time-origin** MSD measurement) — a single state point can be lucky, a trend cannot. D rises monotonically and tracks the measured water curve (Holz et al. 2000): **1.24 / 2.66 / 4.64 ×10⁻⁹ m²/s at 281 / 297 / 313 K vs measured 1.43 / 2.27 / 3.26** — absolute values within ~15-45%, and the rise (×3.74 over the span) is the known SPC/E slightly-too-steep D(T) vs measured ×2.28. Two implementation lessons (both honestly recorded): single-origin MSD is far too noisy for per-block D (multi-origin fixed it), and each block must equilibrate longer than water's ~2-3 ps structural relaxation or a melt-like (too-mobile) structure inflates D. Guarded by `h2o_diffusion_temperature_trend`, rendered as `tools/viz/demos/h2o_diffusion_temperature.png`; slow (~20 min), `SKIP_DIFFUSION_T`-gated. **[shared MD core extracted 2026-06-12]** the rigid-SPC/E integrator (force loop, SHAKE/RATTLE, velocity-Verlet) now lives in one `examples/experiments/trech_water_md.js` include that both the bulk run and the D(T) sweep build on — no more duplicated physics; verified bit-identical (bulk trajectory md5 unchanged, D(T) block-0 reproduces 1.24e-9). Next: full Ewald-PME / larger box for the second-shell height; the macroscopic-transport `h2o_fluid.js` (Geant4) remains the complementary continuum-scale view. **[macroscopic "glass of water while you shake it" landed 2026-07-11]** `examples/experiments/glass_of_water_shaken.js` closes the ladder to the observer scale: it takes the *nanoscale* facts this MD track measures (number density, hydrogen-bond coordination) and — via `ctx.cascade` nano→micro→macro, **hand-typing no macroscopic water property** — pours ~1 L of water into a wide glass and shakes it with a Position-Based-Fluid solver (uniform spatial grid, ~4,300 particles at ~6 mm): pour → settle → shake, waves + splashes, contained, stable, drawn as a 2 mm metaball isosurface. It is the same fluid family arriving at the canonical thesis question; see the multi-scale cascade workstream 4 landing note below. Guarded by `glass_of_water_shaken_waves`.
- H2O chemical reaction-cycle prediction. **[electrolysis + inverse combustion landed 2026-06-28; Geant4 event-drive tightened 2026-06-28; molecule-packet viz sideband landed 2026-06-30]** `examples/experiments/testscenario_h2o_electrolysis_combustion.js` exercises the PubChem+Geant4→hook-inference path on a familiar but nontrivial reaction loop: water is electrolyzed across two cathodes (H2 collected left/right, O2 at an oxygen collector), then H2/O2 are ignited back to water. Real-time fetched PubChem cache entries for water/hydrogen/oxygen provide formula/CID metadata through `TRECH_PUBCHEM`; the hook layer parses formulas and conserves atoms instead of relying on a C++ reaction rule; Geant4 event-level e- energy deposition/track statistics from `ctx.event` plus live `G4EmCalculator` H2O/H2/O2 interaction anchors (`analytic_checks`) directly scale the stochastic reaction rates. Refreshed run: 180 H2O → 180 H2 + 90 O2, cathodes 92/88 H2 (imbalance 0.022), combustion recovers 180 H2O, atoms conserved, Geant4 event drive positive (24.0 MeV deposited, mean activation 0.807). `electrolysis_snapshot` now also carries sampled H2/O2/product-H2O packets so `tools/viz/demos/electrolysis.gif` shows correlated molecule consumption/recombination instead of independent bubbles. Guarded by `h2o_electrolysis_combustion_cycle` (category `fluid`, 9/9 checks). Honest scope: Geant4 constrains the mesoscale proxy; TRECH still needs a learned/validated chemistry model before claiming generic electrochemical/flame prediction.
- Define a "system" abstraction: stable, point-agnostic ensemble behavior that bridges particle runs to macro-scale predictions.
- In parallel, learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Optimize large-scale molecule simulations with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize the available physics within library boundaries and maintain provenance parity.
- **Complex test scenarios cross-checked against classical formulas.** **[analytic cross-check landed 2026-06-19]** A run can now carry a closed-form physics prediction and have the engine compare it, in C++, to the run's own Monte-Carlo statistical result — the "expected results from classical formulas vs the predictions from Geant4 statistical runs" surface. The first check is **Beer-Lambert photon attenuation**: `examples/experiments/analytic_beer_lambert.js` fires a narrow 100 keV gamma beam through a 50 mm water slab; the engine sums the linear attenuation coefficient `mu` from Geant4's own atomic cross sections (photoelectric + Compton + Rayleigh + pair, via `G4EmCalculator`) and predicts the uncollided transmission `T = exp(-mu*x)`, then compares it to the measured uncollided-primary fraction (a new `primaries_uncollided` tally: primaries reaching the world boundary with **no discrete interaction**, detected per-primary in `SteppingAction`). They agree to **classical 0.4265 vs Geant4 0.4217 (1.1% relative, Poisson-limited)** — `mu/rho ≈ 0.1704 cm²/g` matches NIST XCOM. Config block `analytic.{enable,checks}` (conditionally serialized, round-trip tested); predictions computed post-`Initialize` in `GeantRunner` and paired with the measured tally at run end; emitted as `analytic_checks` + `analytic_checks_within_tolerance` in `trech_scores.jsonl`. Guarded by the `analytic_beer_lambert_cross_check` validation case (category `analytic`). The framework is extensible (the result carries a `measuredField` so new check types — CSDA range, Compton edge, etc. — stay data-driven). Honest scope: this validates the engine's transport+scoring chain against textbook physics fed by Geant4's *own* data — a self-consistency check, not an external-anchor calibration.
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.
- **Reduce simulation degeneration constantly** (see the standing objective below): every run should sample a real distribution, and learned/derived physics should converge toward measured behaviour rather than collapsing to trivial (identical-photon, n≈1) outputs.
- **Grow the multi-scale inference cascade constantly** (see the standing objective directly below): statistics/ML must trend toward a *general-purpose, context-driven* predictor — Geant4 base → learned scale-by-scale lift → observer scale — not a set of narrow per-output models the user must wire by hand.

## 2026-07-16 duration-independent lava-lamp thermofluid correction

- **[corrected] Replace the authored replay with persistent inferred state.** The prior
  `lava_lamp_10_minutes.js` implementation was rejected: it embedded one horizon in the scenario
  identity, inferred a target period/excursion, selected authored rise/fall phases, and rebuilt
  display particles around analytic blob centres on every frame. Renamed `lava_lamp.js` now
  probes a real Geant4 custom reference blend and water carrier, then uses `ctx.cascade` only to
  infer thermophysical coefficients. A bounded-step solver advances the same ordered 240 parcel
  IDs through a carrier thermal field, parcel heat exchange, phase fraction, thermally varying
  density, buoyancy/drag, cohesion, inferred 3D carrier circulation/vorticity,
  interfacial velocity coupling,
  neighbour topology, velocity, and boundaries. No cycle
  period, target excursion, phase schedule, trajectory, particle birth, or regeneration remains.
  `duration_s` is only the integration horizon; heater and ambient are independent conditions.
- **[landed] Independent precision axes + fixed inventory.** Parcel count used to change physical
  wax volume because its lattice spacing/support radii were fixed. `wax_representatives` now
  refines a constant 4723.92 mm³ inventory with N⁻¹ᐟ³ length scaling; `max_physics_step_s`
  independently refines integration, `simulation_ticks` controls output sampling, and
  `render_surface_grid_mm` is representation-only. A 480-parcel/0.2 s 60-second run preserves
  inventory and stays within 0.0131 mean liquid fraction / 0.00023 g/cm³ density of the default
  240-parcel/0.4 s response, with no velocity-cap activation. Increasing count alone is not a
  complete precision strategy.
- **[landed] Falsifiable duration and condition controls.** `lava_lamp_inferred_thermofluid`
  guards 23/23 checks. A separate 60 s / 12-tick run has the same bounded internal steps as the
  first 60 s of the default horizon and matches its parcel positions within 1e-9 mm. A second
  same-material 60 s control changes only the heater from 333.15 K to 310 K: the hot run reaches
  mean liquid fraction 0.263 and crosses carrier density, while the control stays at 0.0025,
  remains denser than the carrier, and records no lighter-than-carrier step. This makes a Studio
  condition change alter the inferred physics rather than select or retime an animation.
- **[landed] One emitted timeline, two real 3D render paths.** Studio's WGSL capture writes
  `studio/tests/reference/lava_lamp.gif`; classic `trech-viz` now reads `material_frame`, retains
  physical/playback clocks and per-particle RGBA, applies true volume rotations/parent transforms
  plus Studio's labelled `viz_*` hints, and writes `tools/viz/demos/lava_lamp_trech_viz.gif`.
  Both consume the same run. Studio camera bounds now respect rotations and frame apparatus +
  particles together; capture treats a broken `ffmpeg` executable as unavailable and accepts
  `TRECH_FFMPEG` before falling back to built-in PNG.
- **[landed] Fused wax surface instead of particle glyphs.** `material_frame.render_surface`
  declares a Gaussian kernel, sigma, iso-level, clip cylinder, surface grid and optical look as
  representation-only metadata. Studio reconstructs a marching-tetrahedra mesh and uses the
  existing depth-tested WGSL surface shader; classic `trech-viz` contours the identical density
  contract with PyVista, following the water-metaball precedent. Neither path moves or creates a
  parcel. Frames without the hint retain their existing sprite fallback.
- **[landed] Continuous fluid-interface necking without discarding parcel detail.** The earlier
  fine Gaussian parcel interface remains a separately emitted and validated lineage (README:
  19 merges, 18 splits, 43/101 merged frames). A wider observer interface now declares
  `fluid_necking`: two distance-faded Gaussian samples per eligible pair, with a smoothstep
  amplitude that reaches zero at the already-declared component connection radius. This creates
  a visible waist that grows during coalescence and thins during fission without moving parcel
  centres, joining previously disconnected components, or feeding the field into physics. Studio
  and classic `trech-viz` share the contract and report 8 observer-interface merges, 10 splits,
  and 90/101 merged frames for the README run.
- **[landed] Blob-scale circulation and falsifiable merge/split lineage.** The first fused-surface
  pass exposed disconnected parcels but left the solver dominated by vertical Stokes motion, so
  it still looked like frantic independent bubbles. The macro cascade now also infers carrier-roll
  speed/advection and interfacial velocity coupling; the solver consumes those coefficients at
  every bounded step. Each frame labels connected surface components from persistent parcel IDs
  and reports lineage merges/splits. On the README run, physical-topology churn falls from 59 to
  39 changes in the current README run, fine parcel-surface bodies range from 1 to 6, and 19 coalescences plus
  18 fissions occur with merged bodies present in 43/101 states. The renderers only reveal this
  emitted topology.
- **[corrected] Remove the axis-locked convection symmetry.** The first circulation correction
  still used an axisymmetric radial/vertical roll: individual parcels changed x/y, but the wax
  centroid spanned only 0.84 × 1.03 mm in a 60 mm-wide lamp, so the visible response remained a
  vertical column. The macro cascade now also infers carrier vorticity and lateral-plume strength.
  Initial parcel temperature/heat-transfer fluctuations select the horizontal convection axis and
  handedness deterministically; the solver combines radial turnover, the evolving lateral roll,
  azimuthal vorticity, and buoyancy in all three coordinates. The README centroid now spans
  38.73 × 36.52 mm, travels 123.41 mm laterally, and occupies 10/12 azimuth sectors while retaining
  the retained fine-interface 19 coalescences and 18 fissions. A dedicated validation flag rejects regression to one-axis
  motion; neither renderer supplies the lateral trajectory.
- **[next] General engine precision profiles.** The lava scenario proves the necessary axes, but
  TRECH still lacks a physics-agnostic `preview/balanced/high/convergence` profile that scenarios
  can map to their domain-specific spatial/temporal/output controls and report uniformly. Add a
  schema + run-summary contract without pretending one global “particle count” has equal meaning
  across Geant4 transport, MD, PBF, chemistry, and observer replays.
- **[corrected] README cadence and horizon come from the persistent solver.** The first revision
  stretched seven sparse states; the second increased cadence but retained the underlying scripted
  replay; the third used the corrected solver but stopped after its one-minute warm-up/rise onset.
  All were incomplete representations. README generation now performs a distinct full 600 s /
  100-tick run of the corrected stateful model at the default 333.15 K heater condition, emitting
  101 unique states at 6 s intervals. Both renderers map post-tick states 1..100 directly to the
  100 GIF frames over ten display seconds, showing repeated rise/fall reversals. No optical flow
  or temporal interpolation is used.
- **[open, concrete] Graduate the lava response beyond illustration.** Assemble a measured or
  resim-confirmed wax/carrier/heater panel, train and hold out each thermal/buoyancy band, report
  coverage/extrapolation per stage, and replace the compact σ=0.12 response surface before any
  quantitative thermal-fluid claim. Studio's soft sprites also remain subject to
  its M3 depth-occluded metaball/isosurface work; this does not block the current honest viewer.

## 2026-07-15 Studio fidelity, adaptive lab rounds, and liquid-pair checkpoint

- **[landed] Typed JavaScript scenario values and Studio override contract.** Scenarios can call
  `TRECH_VALUE.number/integer/boolean/string/choice` with defaults and UI metadata (groups, units,
  ranges, steps, choices). Ordinary `trech run` returns defaults; repeatable
  `--param name=<json>` values are type/range/choice validated in the QuickJS runtime before
  simulation. The Geant4-free `trech inspect` command evaluates the real scenario/includes and
  emits `{config,parameters}` for clients. Studio now uses that path for a right-sidebar Options
  panel and passes selections back on Run. Representative refraction, H2O-fluid, and CNT-fluid
  scenarios expose sizes/levels, temperatures, source and sampling controls without changing
  their defaults. Remaining visual scene-node mutation and live-lab reinitialization stay in the
  Studio M2 roadmap rather than being conflated with this authored override surface.
- **[landed] Medium/process-exact optical playback and precision reporting.** The trajectory
  recorder now emits each point's medium plus the Geant4 process/classified interaction ending
  the incoming segment. Studio distinguishes boundary refraction/world exit from true scattering,
  makes labelled air paths finer/translucent, and scales ribbon width/alpha with the sampled
  optical-track count so weak beams render tight and transparent. Preview inspector/status and
  capture JSON sidecars report MC events, trajectory sampling/caps, medium/process coverage,
  proportion standard errors, native spatial step, output raster and supersampling. Hollow
  Geant4 tubes now become true annular Studio meshes instead of placeholder solid cylinders.
  Loaded-vs-recorded tracks and exact render-segment budget truncation are disclosed too.
- **[landed] Adaptive real-time rounds in TRECH.** In `trech lab`, an omitted
  `simulate.events` measures actual wall time per completed round, updates an EWMA, and selects
  the next batch that fits `lab.targetHz`, within configured min/max bounds. Persistent
  `roundsPerTick` and per-command `simulate.events` overrides remain available. Machine-readable
  `lab_round_plan` telemetry and `lab.roundPlanner` snapshots expose actual/planned precision and
  throughput to Studio.
- **[landed, with mandatory uncertainty] Water + n-pentane beaker.**
  `beaker_water_n_pentane.js` uses Geant4 material/optics facts plus PubChem CID+SMILES only, then
  a two-stage scale cascade predicts colour, phase separation/layer order and the 60-minute
  evaporation endpoint for the declared beaker/air context. The lower stage now learns temperature
  from neighboring n-alkanes while holding n-pentane out at every temperature. At 303.15 K the
  held-out volatility gap is 6.3%; the inferred endpoint is 13.99% / 4.38 g evaporated with emitted
  fraction σ=0.08. Its 61 material-resolved frames now stage empty beaker → water pour → pentane
  pour → intermix/phase separation → moving/fading plume, and retain physical time beside an
  explicit 545× playback clock. The refreshed `beaker_water_pentane.gif` uses labelled blue/gold
  display tints while leaving cascade-driven layout and evaporation untouched.
- **[ ] Widen the liquid-pair/evaporation training domain before metrology claims.** Replace the
  compact illustrative macro response surface with a harvested panel spanning polarity,
  temperature, open-surface geometry, airflow/boundary layers and multiple liquid pairs; hold out
  whole substances/pairs, calibrate uncertainty, and keep runtime reference properties forbidden.
  Also close the current n-pentane derived-index residual (n≈1.218 vs validation-only 1.358)
  through the generic optics training path rather than injecting the handbook value.
- **[ ] Persist/adapt lab timing priors by stable config signature only if startup latency matters.**
  The landed planner learns the active scenario online and reacts to patches, but starts each lab
  process from the configured `run.nEvents`. A future cache must be optional, provenance-visible,
  machine-local, invalidated by config/engine changes, and must never be mistaken for physics ML.
- **[partial: compatible-batch kernel reuse landed] Finish safe live reconfiguration in
  `trech lab`.** `GeantLabRunner` now initializes Geant4 once and reuses it for later compatible
  `BeamOn` batches; event-count/seed/planner changes are allowed, every batch receives its own
  canonical config hash, and an exercised 25 / adaptive-1 / explicit-5 sequence completed without
  the Geant4 UI-singleton teardown crash. Kernel-bound patches (geometry, beam, physics, scoring,
  output) now fail explicitly and require a lab restart. Remaining: classify cheap beam edits,
  implement/test safe geometry/physics reinitialization without stale material/action state, and
  wire that restart/reinitialize handshake through Studio before claiming arbitrary live editing.
  Lab remains stdin/JSONL-driven; Geant4 macro/UI flags are deliberately run-mode-only rather
  than pretending they compose with the persistent command loop.

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
3. **Coverage/uncertainty per band. [mechanism landed 2026-07-24]** Each stage now reports when it
   is extrapolating out of its trained domain instead of silently guessing. `GenericSurrogate::coverage`
   compares each input's standardized deviation `|z|=(x-mean)/std` against the model's per-feature
   trained hull (`input_domain.standardized_radius`, exported by `trech-train-surrogate` from the
   training split; legacy/illustrative models with no hull fall back to a heuristic 3σ and report
   `domainMeasured:false`, so an unvalidated map cannot masquerade as a trained-domain guarantee).
   `ScaleCascade` fills per-stage `inDomain`/`domainMeasured`/`extrapolation`/`maxStandardizedDeviation`/
   `outOfDomainInputs` and a run-level `stagesExtrapolating`; the flag **propagates up the ladder**
   (a low stage's out-of-domain output makes the next stage's coverage flag too). Surfaced through
   the JS boundary on `__cascade.trace[i]` + `__cascade.stagesExtrapolating` and on `ctx.predict`'s
   reserved `__coverage`. Guarded by `tests/test_generic_surrogate.cpp` (measured-vs-heuristic,
   missing-input-out-of-domain), `tests/test_scale_cascade.cpp` (per-stage in/out + propagation +
   count), `tests/test_js_runtime.cpp` (JS-boundary fields); demonstrated in a real run by
   `cascade_multiscale_demo.js` (emits per-stage coverage). **[extended 2026-07-24]** the three
   originally-remaining items landed as a full per-stage **trust profile**: (a) the out-of-domain
   flag is now an auditable *run fact* — `hook_predict_out_of_domain_count` (subset of
   `hook_predict_count`) is plumbed to `trech_scores.jsonl` + `trech_provenance.jsonl` like the
   other hook counters (proven end-to-end: a forced-OOD run reports 4/4, an in-domain run 0);
   (b) the harvester's dimension-scale band is wired into per-stage confidence — the trainer exports
   `trained_scale_bands`, `GenericSurrogate` carries them, and `ScaleCascade` flags a stage applied
   OFF its trained band (`scaleMismatch`/`trainedScale`, run-level `stagesScaleMismatched`); (c)
   held-out accuracy now travels WITH the model — the trainer embeds `holdout{r2_min,n}`, the engine
   surfaces per-stage `holdoutR2`/`holdoutSamples` (null for illustrative maps, never a fake 0).
   Guarded by extended `tests/test_generic_surrogate.cpp` (carried bands/holdout), `test_scale_cascade.cpp`
   (scale-mismatch + surfaced holdout), `test_js_runtime.cpp` (run-level OOD count + JS-boundary
   fields); a **genuine train→load→run round-trip** confirmed it (a real model trained on meso-band
   Geant4 runs, declared at `nano`, is flagged `scaleMismatch:true`/`trainedScale:"meso"` with its
   held-out R² surfaced). **[further extended 2026-07-24]** the flags now *act*, not just surface:
   (1) **resim routing** — `stratify.resimOnLowConfidence` routes an event whose `onEventEnd`
   inference ran out-of-domain into `trech_resim_queue.jsonl` (`reason:"inference_out_of_domain"`,
   `source:"cascade_coverage"`) even when the feature-based stratifier labels it predictable, counted
   in `stratify_low_confidence_count` (a new accumulable, distinct from `stratify_exceptional_count`);
   `RunAction::DispatchHook` now returns the per-dispatch out-of-domain count so `EventAction` can act
   on it (proven end-to-end: 3/3 out-of-domain events queued, `stratify_low_confidence_count=3`).
   (2) **starved-region signal** — the trainer exports a per-feature `input_domain.occupancy`
   histogram; coverage flags an input that is *within* the trained range but in an unpopulated bin
   (`starvedInputs`, run-level `stagesStarved`) — density inside the hull, not just its edge, the
   planner's starved-region notion (proven: an in-range value in an empty bin is flagged starved
   while staying `inDomain`). **Remaining (workstream-2-gated):** per-band held-out accuracy only
   becomes *meaningful* once a real trained per-band chain lands (the mechanism is ready; illustrative
   maps still report null), and the planner could additionally feed *joint* (not just per-feature)
   starved regions.
4. **Worked cascades across the scenario families — NOT just optics/fluids.** The cascade is
   domain-agnostic; land real per-band chains in several families, not one. The canonical thesis
   example is the "glass of water" (fluid movement/waves inferred from a Geant4-derived
   microscopic base). **[canonical glass-of-water landed 2026-07-11]**
   `examples/experiments/glass_of_water_shaken.js` pours ~1 L of water into a wide glass and shakes
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
   `examples/experiments/briggs_rauscher_oscillator.js` lifts the Geant4-built reagent/mixture
   materials + declared recipe through a two-stage cascade (`data/briggs_rauscher_cascade/`) into
   the coefficients of a reduced FKN/Oregonator oscillator; the oscillation (8 colourless→amber→
   deep-blue cycles, amber-before-blue, ~10.5 s period, settle on reagent depletion) is emergent,
   not typed, and guarded by `briggs_rauscher_oscillation` (category `chemistry`, 10/10). **Two
   reactive-foam cascades landed 2026-07-25:** `examples/experiments/polyurethane_foam.js`
   (`data/polyurethane_cascade/`; dual gel+blow reactions → 26.9× expansion, cream→gel→solid
   ordering, rigid porous endpoint; guarded by `polyurethane_foam_expansion`, 15/15) and
   `examples/experiments/elephants_toothpaste.js` (`data/elephants_toothpaste_cascade/`;
   iodide-catalysed runaway → 8e4× acceleration, 18.4× steaming lather eruption, drains and never
   solidifies; guarded by `elephants_toothpaste_eruption`, 16/16) — the pair demonstrates emergent
   *consistency* (rigid sponge vs soft lather) from the same doctrine, and — since the foam
   mechanics upgrade — emergent **gravity/imperfection consequences** (leaning, cracking, shedding
   pieces onto the table) graded against a zero-gravity control. Still open
   on this workstream: biology (efflux/osmosis cell observables), CNT electronics
   (gap→device→logic), and magnetic resonance (proton density→image) each have the same
   micro→observer arc and should get a cascade too, and the chemistry + fluid stage models should
   graduate from illustrative maps (Briggs–Rauscher's macro response surface is a compact
   illustrative map, σ=0.12 emitted; the polyurethane σ=0.14 and elephant's-toothpaste σ=0.15
   response surfaces are equally illustrative — a wider trained reactive-foam / catalytic-kinetics
   panel is the follow-up) to **trained, held-out-validated** per-band chains. See the
   scenario-family table in the AGENTS.md "Multi-scale statistical inference" doctrine.
5. **Default-on, override-on-demand.** Progress the API so a scenario opts into "predict the
   relevant behaviour for this context" and only specifies models/scales when it wants to
   constrain them — the "without requiring to be specified (if not forced by user)" target.

### Cascade metrics to watch (regression signals)

- **Scales bridged in one run**: how many distinct bands a single cascade chains (baseline
  narrow-ML = 1). Growth here is the headline signal that the engine is becoming multi-scale.
- **Hand-wired predictions eliminated**: fraction of a scenario's predictions that come from
  `ctx.cascade` (auto-chained) vs. individual hand-built `ctx.predict` calls.
- **Per-band held-out accuracy** and **fraction of stages flagged low-confidence** (once
  workstream 3 lands) — so a longer cascade cannot silently trade accuracy for reach.

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

- **Validation report curation**: 44 cases now (40 pass / 0 fail / 4 info after the `polyurethane_foam_expansion` + `elephants_toothpaste_eruption` reactive-foam guards; 42 with 38 pass after the `briggs_rauscher_oscillation` guard; 41 with 37 pass after the `lava_lamp_inferred_thermofluid` guard; 40 with 36 pass after the beaker guard; 39 with 35 pass after `glass_of_water_shaken_waves`; 38 with 34 pass after the `magnetic_resonance_brain_image` guard; 37 with 33 pass after the `magnetic_resonance_image_line` guard; 36 with 32 pass after the `magnetic_resonance_tissue_contrast` guard; 35 with 31 pass after the `magnetic_resonance_water` guard; 34 with 30 pass after the `generic_surrogate_inference` guard; 33 with 29 pass after the photo-fraction analytic guard; 32 after the CSDA-range guard and scenario-viz refresh; 31 after CNT logic gates; 30 after the H2O electrolysis + inverse-combustion cycle and efflux runtime-PubChem/event-drive alignment; 17 at first commit — 12 pass, 4 info, 1 was wrong-spec and is now structural numeric replay — plus analytic Beer-Lambert, h2o_fluid brine, Pascal/osmosis/efflux/H2O-cycle fluid guards, end-to-end optics-surrogate transport, anti-degeneration sampling diversity, CNT electronic structure, and the Sputnik molecular-scale guards). The lava case adds 23/23 contracts over Geant4/cascade provenance, persistent state, duration independence, heater-condition response, bounded volumetric motion, non-axis-locked x/y/azimuth transport, retained parcel-scale lineage, fluid-interface coalescence/fission, temporally coherent topology, dense README cadence, independent precision axes, and fixed-inventory refinement convergence. Expand coverage as new outputs/scenarios land. Treat `docs/validation_report.md` as a regression artefact: re-generate via `scripts/run_validation_suite.sh` whenever the engine or scenarios change, and commit the regenerated report alongside the code change.
- **Torch surrogate adoption**: the `OpticsSurrogate` C++ path + the Python trainer are wired and degrade gracefully when Torch is unbuilt. (a) curated dataset **landed** (`optics_training_panel.js` + engine-emitted `element_mass_fractions` + `data/optics_handbook_anchors.json`); (c) held-out validation **landed** (`scripts/validate_optics_surrogate.py`, in `run_validation_suite.sh`); (d) **transport feed landed without LibTorch** — a ridge `.json` backend (`data/optics_surrogate_ridge.json`) makes the validated model feed transport in a stock build (`TRECH_ENABLE_TORCH` no longer required for the surrogate path), cross-checked C++↔Python and guarded by `tests/test_optics_surrogate.cpp`; (b) **CI retrain/re-export landed** — `run_validation_suite.sh` re-fits + re-exports the ridge model from the freshly-derived panel each run (so `git diff data/optics_surrogate_ridge.json` flags drift), and a new end-to-end suite case (`optics_surrogate_transport_applied`, via `examples/experiments/optics_surrogate_demo.js`) asserts the learned NaI n (~1.77, where the f-sum extractor fails at ~1.33) actually reaches transport's RINDEX samples. (e) **event-stratifier learned path + dimension-scale tooling landed 2026-07-02** (see landing note below): a LibTorch-free logistic `.json` stratifier backend, a shared dataset harvester, an event-stratifier trainer, an improved optics trainer, and an active-learning Geant4 experiment planner. (f) **generic surrogate — Torch usable in ANY scenario landed 2026-07-02** (see landing note below): `models: [{name, path}]` config + `ctx.predict` hook API + `GenericSurrogate` C++ + `trech-train-surrogate`, so any scenario (present or future) attaches a learned model without new engine call-sites. (g) **multi-scale inference cascade landed 2026-07-05** — `ScaleCascade` + `ModelConfig.scale` + `ctx.cascade` generalize the per-call `ctx.predict` point-predictors into an auto-chained, Geant4-seeded ladder (the general-purpose direction of the "Multi-scale statistical inference" standing objective); the remaining work there is training real per-band stages, not more plumbing. (h) **canonical glass-of-water cascade landed 2026-07-11** — `examples/experiments/glass_of_water_shaken.js` is the first *worked, rendered* observer-scale cascade: a nano MD measures water's number density + H-bond coordination, `ctx.cascade` lifts them nano→micro→macro into the fluid parameters of a Position-Based-Fluid (spatial grid, ~4,300 particles at ~6 mm) that pours ~1 L into a wide glass, settles, and shakes it (waves/splashes, contained, stable), with **no macroscopic water property typed** and the recovered rest density (999 kg/m³) landing 0.1% off measured as a check; stage models `data/glass_cascade/` (density grounded, cohesion/viscosity illustrative), guarded by `glass_of_water_shaken_waves`, rendered `tools/viz/demos/render_glass_of_water_shaken.py` (2 mm metaball isosurface). Remaining: (optionally) building LibTorch only for the TorchScript `.pt` backends / multi-output (abs, scat) optics models; resim-confirmed teacher labels feeding stratifier retraining.

## Magnetic-resonance (MRI/NMR) track — standing objective

Build up a magnetic-resonance experiment the TRECH way: Geant4 + material physics supply
everything that is genuinely measurable, and the "know-what" (Larmor constant, tissue relaxation)
is used only to grade the gap-to-truth.

- **[Stage 1 landed 2026-07-04]** `examples/experiments/testscenario_magnetic_resonance.js`: a
  5 cm³ water cube, a static-field + swept-RF apparatus, and detection of the free-induction-decay
  "output" signal. Geant4 builds the phantom + a copper receiver-coil volume and — through the new
  **material-composition engine surface** (`materialProbe`/`ctx.materials`, `MaterialProbe.{hpp,cpp}`)
  — supplies the ¹H (proton) number density that sets the equilibrium magnetization; the deterministic
  hook layer runs the Bloch spin dynamics. The Larmor line is **discovered** from the FID carrier
  (feeding only the proton gyromagnetic ratio γ + the machine field B0 — no water-specific know-what):
  γ/2π recovered **42.5768 MHz/T** vs CODATA 42.5775 (0.001%), Geant4 water proton density
  **6.686e22/cm³** = literature (0.006%), T2* recovered to 0.1%. Guarded by `magnetic_resonance_water`
  (category `resonance`, 7/7, incl. a `material_probes`↔`ctx.materials` cross-check). Honest scope:
  Geant4 does not simulate nuclear spin — the spin dynamics are the hook-layer physics-for-comparison.
- **[Stage 2 landed 2026-07-04]** virtual tissues with **REAL Geant4 photon emission** (no C++):
  shared scenario `testscenario_magnetic_resonance_tissues.js` + multi-run driver
  `scripts/run_magnetic_resonance_tissues.py`. Per NIST tissue the driver reads the Geant4-computed
  ¹H number density (`material_probes` — an ignorant material fact) and emits a **proportional** number
  of excitation primaries; Geant4 then produces **every consequent photon** and a NaI detector shell
  scores the REAL deposited energy (`receiver_coil volume_edep_mev`). The detected per-tissue signal is
  a genuine Monte-Carlo tally whose emission count came from Geant4's own proton prediction, and it
  reproduces MRI proton-density contrast — cortical bone **0.60× water** (proton ratio 0.583; the gap is
  the radiographic photon-yield term), corr(signal, proton density) **0.9995**, byte-reproducible.
  Guarded by `magnetic_resonance_tissue_contrast` (5/5). Honest scope: the excitation-per-proton is a
  labelled proxy (Geant4 can't make nuclear spins radiate RF); REAL = the Geant4-set emission count +
  the Geant4-transport detection tally.
- **[Stage 3 landed 2026-07-05]** spatial encoding → an **actual 1D image line** (no C++):
  `examples/experiments/testscenario_magnetic_resonance_imaging.js`. Geant4 builds a real
  multi-tissue phantom (a row of NIST-tissue voxels along the readout axis, incl. an **air gap** →
  black and **cortical bone** → dark) with real transport, and supplies each voxel's ¹H density via
  `ctx.materials`. The hook layer applies a readout gradient (`ω(x)=γ(B0+Gx·x)`), synthesizes the
  quadrature readout and **DFT-reconstructs the proton-density profile**: positions recovered from
  peak frequency to **0.001 mm**, amplitude↔proton corr **1.0**, air gap 0.01 (black) / cortical bone
  0.59 (dark) — a recognizable image, byte-reproducible. Guarded by `magnetic_resonance_image_line`
  (6/6).
- **[Stage 4 landed 2026-07-05]** a full **2D brain MRI image** (no C++):
  `examples/experiments/testscenario_magnetic_resonance_brain.js` + `scripts/run_magnetic_resonance_brain.py`.
  A procedural, [BrainWeb](https://brainweb.bic.mni.mcgill.ca/brainweb/anatomic_normal_20.html)-inspired
  axial head phantom (skull, scalp/fat, CSF, cortical grey-matter ribbon, white-matter core, lateral
  ventricles, deep grey nuclei) supplies the anatomy; **each pixel's brightness is the Geant4-computed
  mobile-¹H (proton) density** of its tissue (declared as water-content proxy materials, so Geant4
  turns the biological water fraction into an absolute ¹H number density); a 2D k-space acquisition +
  FFT reconstruct the image. Result: a genuine proton-density MRI — bright CSF/ventricles, grey > white
  matter, bright fat, dark skull, black background — with per-tissue intensity↔proton-density
  **r = 0.998** and reconstruction fidelity **r = 0.966**, byte-reproducible. Rendered
  `tools/viz/demos/magnetic_resonance_brain.png` (README hero). Guarded by
  `magnetic_resonance_brain_image` (7/7). Honest scope: the anatomy is a digital phantom and the
  k-space/FFT is signal processing; the contrast is Geant4-derived.
- **[optional future]** T1/T2-weighted sequences (relaxation contrast, needs a Geant4-anchored
  relaxation proxy), 2-D phase encoding from acquired k-space, and real BrainWeb data ingestion remain
  open MRI extensions.

## Short-term next steps

- Extend analytic cross-checks beyond Beer-Lambert (the framework is data-driven via `AnalyticCheckResult.measuredField`). **[charged-particle CSDA range landed 2026-06-30]** `analytic_csda_range.js` derives the CSDA range from Geant4's own stopping power (`G4EmCalculator::GetCSDARange`) and compares it to a new `primary_mean_track_length_mm` tally — 20 MeV proton in water, derived 4.282 mm vs measured 4.266 mm (0.38%); guarded by `analytic_csda_range_cross_check`. **[photofraction landed 2026-07-02]** `analytic_photo_fraction.js` predicts the photoelectric process-branching ratio `sigma_phot/sigma_total` from the SAME per-process cross sections Beer-Lambert sums and compares it to a new `primaries_photoelectric_first_fraction` tally (the fraction of primaries whose first discrete interaction is photoelectric, classified through QBBC's `G4GammaGeneralProcess` wrapper by EM subtype) — 30 keV gamma in water, derived 0.3908 vs measured 0.3931 (0.59%); guarded by `analytic_photo_fraction_cross_check`. Unlike the two attenuation/range checks this one tests the process CHOICE (branching), and is slab-thickness independent. Next data-driven check types: the Compton edge / Klein-Nishina scattered-spectrum edge, or the photofraction's energy dependence (a sweep) — each a new closed-form prediction compared to the run's Monte-Carlo tally.
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
- **TRECH Studio — the desktop UI for the above. [basis/skeleton landed 2026-07-11]** `studio/` is a PySide6 + wgpu-py (WebGPU → Vulkan/Metal via WGSL) app: a real-time 3D scenario editor, simulation viewer, and scenario code editor, in one window — the observer-scale window onto the cascade. It is a **client of the engine, never a second physics engine**: everything it draws comes from a `trech run` output dir or a live `trech lab` session, parsed from the documented outputs (studio/AGENTS.md enforces that honesty rule + the `ui → scene/engine/render` layering). Landed: app shell + dockable panels, engine locator (`$TRECH_BIN`/`build/**/trech`), `trech run` subprocess runner + real-time `trech lab` JSONL bridge, output parsing (provenance/scores/emits/viz-scene), editable `SceneModel` + `trech_viz_scene.json` loader, orbit camera + CPU mesh gen, and a wgpu viewport drawing lit volumes + grid (graceful fallback when wgpu is absent). Own roadmap `studio/ROADMAP.md` tracks the milestones: M1 view any run faithfully (trajectory playback + time slider, run summary, derived-optics opacity), **M2 real-time scenario editing (inspector → live `trech lab` patches, gizmos, and the `SceneModel → runnable .js` writer — the core deliverable)**, M3 make the cascade legible (scale-ladder widget, inferred-vs-measured with gap-to-truth, WGSL compute fluid overlay for `fluid_frame` emits). Stack rationale (wgpu over OpenGL/raw-Vulkan; Godot/GDExtension declined) recorded there.
- Use LibTorch/TorchScript for fluid-scale statistical modeling; wire incremental learning as the runtime evolves.
- Long-term: keep the C++ config surface physics/chemistry agnostic, relying on JS scenarios and lab command streams to express combinations.

## Validation status

- Foam mechanics: gravity + imperfection consequences landed (2026-07-25), with the tuning debt
  written down rather than hidden. New shared module
  [`examples/experiments/trech_foam_solver.js`](examples/experiments/trech_foam_solver.js)
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
  the multi-scale cascade workstream. **(1) `examples/experiments/polyurethane_foam.js`** is told
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
  (**15/15**). **(2) `examples/experiments/elephants_toothpaste.js`** is told only the peroxide/soap
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
- Briggs–Rauscher oscillating-reaction cascade landed (2026-07-25): the **chemistry** arm of the
  multi-scale cascade workstream. `examples/experiments/briggs_rauscher_oscillator.js` is told only
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
- Cascade flags now ACT (resim routing + starved region) landed (2026-07-24): the two actionable **workstream 3** follow-ups. **(1) Acting on the flag — resim routing:** new `stratify.resimOnLowConfidence` (conditionally serialized → config hashes byte-stable; round-trip guarded incl. an absence check) makes an event whose `onEventEnd` inference ran out-of-domain a resim candidate — `RunAction::DispatchHook` now returns the per-dispatch out-of-domain count, `EventAction` writes it to `trech_resim_queue.jsonl` (`reason:"inference_out_of_domain"`, `source:"cascade_coverage"`, `low_confidence_inference`, `inference_out_of_domain_count`) even when the feature-based stratifier labels the event predictable, and counts it in `stratify_low_confidence_count` (new `stratifyLowConfidenceCount_` accumulable → scores + provenance, distinct from `stratify_exceptional_count`). Proven end-to-end: 3 out-of-domain events → 3 resim candidates, `stratify_low_confidence_count=3`, `stratify_exceptional_count=0`. **(2) Starved-region signal (density inside the hull):** the trainer exports a per-feature `input_domain.occupancy` histogram (8 bins over [min,max]); `GenericSurrogate::coverage` flags an input within the trained range but in an unpopulated bin (`starvedInputs`), surfaced per stage + run-level `stagesStarved` on `__cascade` and on `ctx.predict` `__coverage`. Proven end-to-end with a real trained model: an in-range value in an empty bin is flagged `starved` while remaining `inDomain` with `extrapolation:0` (distinct from a beyond-the-edge extrapolation). `ctest --preset dev` **11/11** (extended `trech_config_roundtrip` for the flag + conditional-serialization absence check, `trech_generic_surrogate` for the starved/occupancy path, `trech_scale_cascade` for `stagesStarved`). `cascade_multiscale_demo.js` now emits `starved` + `stages_starved` too. No physics change; strict mode still returns null. Honest remaining: per-band held-out accuracy stays illustrative until workstream 2 lands a real trained chain.
- Cascade trust-profile extension landed (2026-07-24): completed the three originally-remaining **workstream 3** items on top of the coverage mechanism below. **(a) Run-level out-of-domain accountability:** `hook_predict_out_of_domain_count` (subset of `hook_predict_count`) is plumbed HookDispatchReport→RunOptions→RunAction accumulable→scores+provenance exactly like the predict count (`include/trech/js/JsRuntime.hpp`, `src/js/JsRuntime.cpp`, `src/sim/RunAction.{cpp,hpp}`, `src/core/{RunOptions.hpp,Provenance.cpp}`, `apps/trech-cli/main.cpp`) — proven end-to-end (a forced-OOD `ctx.cascade({edep_mev:100})` run reports 4/4; the in-domain demo reports 0). **(b) Trained-scale-band → per-stage confidence:** the trainer exports `trained_scale_bands` (from the harvester's per-run `dimension_scale` tags), `GenericSurrogate` carries them, and `ScaleCascade` flags a stage run OFF its trained band (`scaleMismatch`/`trainedScale`, run-level `stagesScaleMismatched`). **(c) Held-out accuracy carried with the model:** the trainer embeds `holdout{r2_min,n}`, the engine surfaces per-stage `holdoutR2`/`holdoutSamples` (null for illustrative maps, never a fake 0). All surfaced on `__cascade.trace[i]` + `__cascade.stagesScaleMismatched`. A **genuine train→load→run round-trip** verified it: a real linear model trained on meso-band Geant4 run scores, declared at scale `nano`, ran with `scaleMismatch:true`/`trainedScale:"meso"`/`domainMeasured:true` and its held-out R² surfaced. No config-surface change; the new run-level field is additive to scores/provenance. `ctest --preset dev` **11/11** (extended `trech_generic_surrogate` for carried bands/holdout, `trech_scale_cascade` for scale-mismatch + surfaced holdout, `trech_js_runtime` for the run-level OOD count + JS-boundary provenance fields). `cascade_multiscale_demo.js` now emits the full trust profile.
- Cascade per-band coverage / low-confidence flag landed (2026-07-24): **multi-scale workstream 3** — every learned prediction now reports whether its inputs fell inside the region the model was *trained on*, so an extrapolating stage is flagged low-confidence instead of silently guessing. `GenericSurrogate::coverage(inputs)` (`src/ml/GenericSurrogate.cpp`) returns `{inDomain, domainMeasured, extrapolation, maxStandardizedDeviation, outOfDomainInputs}`, comparing each input's standardized deviation `|z|=(x-mean)/std` (missing inputs default to 0, matching `predict`, so a defaulted-far input is honestly out-of-domain) against the per-feature trained hull `input_domain.standardized_radius` when present, else a heuristic `kDefaultStandardizedDomainRadius`=3σ with `domainMeasured:false` (an unvalidated map cannot masquerade as a trained-domain guarantee). `ScaleCascade` (`src/ml/ScaleCascade.cpp`) fills those per stage in `CascadeStageResult` + a run-level `stagesExtrapolating`; because a low stage's out-of-domain output feeds the next stage's context, the flag **propagates up the ladder**. Surfaced through the JS boundary on `__cascade.trace[i]` + `__cascade.stagesExtrapolating` (`ctx.cascade`) and a reserved `__coverage` on `ctx.predict` (`src/js/JsRuntime.cpp`). The trainer `train_surrogate.py` exports `input_domain.standardized_radius` (the training-split hull) so newly trained stages carry a *measured* domain. No config-surface change (config hashes unchanged); additive to the cascade/predict outputs; strict mode still returns null. Verified through a **real Geant4 run**: `cascade_multiscale_demo.js` now emits per-stage coverage (both stages `in_domain:true`, `domain_measured:false`, `stages_extrapolating:0`) with the physics byte-identical (`ionization_density` 0.6 → `bulk_response` 2.4). `ctest --preset dev` **11/11** (`trech_generic_surrogate` gains measured-vs-heuristic + missing-input-out-of-domain coverage; `trech_scale_cascade` gains per-stage in/out-of-domain + propagation + `stagesExtrapolating`; `trech_js_runtime` asserts the coverage fields cross the JS boundary). Honest scope: this is the *coverage mechanism* — acting on the flag (resim/exceptional-event routing) and per-band held-out *accuracy* still wait on the trained per-band stages of workstream 2.
- Cascade ambient Geant4 seeding landed (2026-07-11): **multi-scale workstream 1** — `ctx.cascade()` with no argument now auto-seeds from the real Geant4 base. `buildAmbientGeant4Seed` (`src/js/JsRuntime.cpp`) populates the cascade seed from the active hook context's per-event tallies (`edep_mev`, `track_length_mm`, `step_count`, `track_count`, `optical_photon_*`) and, when `materialProbe` is on, the material probes (`material.<name>.{density_g_per_cm3, electron_density_per_cm3, mean_excitation_energy_ev, radiation_length_mm, number_density.<Element>}`); an explicit `ctx.cascade(seed)` argument still overrides/augments per key, and the sorted seed keys are surfaced on `__cascade.seedKeys`. So the bottom of the ladder is *always* the Geant4 base with the scenario copying nothing by hand. `cascade_multiscale_demo.js` switched to the argument-free call — verified byte-identical through a **real Geant4 run** (`ionization_density` 0.6 → `bulk_response` 2.4, `seed_keys` = the 7 ambient event tallies, `stages_run:2`). Deterministic (pure function of the numeric facts); strict mode still returns null. `ctest --preset dev` **11/11** (`trech_js_runtime` gains an argument-free `ctx.cascade()` case asserting ambient event + material seeding and seed-key provenance).
- Multi-scale inference cascade subsystem landed (2026-07-05): first cut of the **core-doctrine engine** (see the "Multi-scale statistical inference" standing objective). `ScaleCascade` (`include/trech/ml/ScaleCascade.hpp` + `src/ml/ScaleCascade.cpp`) chains scenario-declared, `scale`-tagged `GenericSurrogate` models from the Geant4 base up the dimension ladder (atomic→nano→micro→meso→macro, unscaled last) in one deterministic pass; each stage's named outputs merge into a shared context so higher scales consume lower-scale predictions **without the scenario hand-wiring the chain**. New physics-agnostic `ModelConfig.scale` (conditionally serialized → pre-cascade config hashes byte-identical); hook API `ctx.cascade(seed) -> {...context, __cascade{stagesRun, trace}}` (strict-mode-gated; each ran stage = one `hook_predict_count`; missing inputs recorded). `ctest --preset dev` **11/11** (new `trech_scale_cascade` covers chaining, scale ordering independent of declaration order, missing-input recording, unscaled-last, unloaded-skip; `trech_js_runtime` gains a two-stage `ctx.cascade` case; `trech_config_roundtrip` extended for `scale`). Verified through a **real Geant4 run**: `examples/experiments/cascade_multiscale_demo.js` seeds the cascade with a per-event edep and gets `ionization_density` 0.6 (nano) → `bulk_response` 2.4 (meso), `scales:["nano","meso"]`, `stages_run:2`. Doctrine cemented in AGENTS.md + ROADMAP.md + CHARTS.md. Honest scope: the two demo stage models (`data/cascade_demo/`) are hand-authored illustrative linear maps (mechanism demo), not trained physics — the standing-objective workstreams track landing real, held-out-validated per-band chains.
- Photo-fraction analytic cross-check refresh (2026-07-02): `docs/validation_report.md` regenerated to **33 cases, 29 pass / 0 fail-error / 0 skip / 4 info** after adding `analytic_photo_fraction_cross_check` (the only delta vs the 2026-06-30 report is the new case row + metadata; all other cases byte-identical, confirming no physics drift from the additive engine change). `ctest --preset dev` 9/9.
- Full suite/media refresh (2026-06-30): default `scripts/run_validation_suite.sh` completed with **32 cases, 28 pass / 0 fail-error / 0 skip / 4 info**, including the slow bulk-water and D(T) scenarios. Glass-of-water and optics-surrogate validators were refreshed (`surrogate LOO MAE 0.0839 < extractor MAE 0.1406`), and the `tools/viz/demos/` GIF/MP4/PNG gallery was regenerated from fresh `build/dev/out_*` outputs.
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
- OnlineEventStats added (`trech_ml`): per-event-feature Welford moments, optionally backed by `torch::Tensor` when `TRECH_ENABLE_TORCH` is on. `event_feature_stats` + `event_feature_stats_torch_backed` emitted in `trech_scores.jsonl`. Per-event feature accumulation is now unconditional (previously gated on `stratify.enable`). Audit fix (2026-06-30): run-end feature count/sum/sum²/min/max are now Geant4 accumulables, so MT worker event features merge into the master summary; a fresh 12-event stratify run now reports count 12 and means matching `trech_event_scores.jsonl`.
- **Generic surrogate — Torch as a general capability in every scenario landed (2026-07-02)**: made learned inference available to *any* TRECH scenario (present or future) without a new C++ call-site per prediction. (1) **`GenericSurrogate`** (`include/trech/ml/GenericSurrogate.hpp` + `src/ml/GenericSurrogate.cpp`): a LibTorch-free evaluator for a portable `generic_surrogate_v1` JSON feed-forward model with **named inputs → named outputs**, input standardisation, dense layers (none/relu/silu/tanh/sigmoid), and output destandardisation; it also loads the committed `ridge_optics_n_v1`/`logistic_stratifier_v1` schemas so existing models are callable generically, and a `.pt` positionally when Torch is built. (2) **`models: [{name, path}]`** physics-agnostic config collection (normalized single-or-array, conditionally serialized; round-trip in `tests/test_config_roundtrip.cpp`). (3) **`ctx.predict(name, features) → {output: value}`** hook API (`src/js/JsRuntime.cpp`): the `JsRuntime` loads declared models into a `GenericSurrogate` registry after config eval (path resolved from CWD then the experiment dir); prediction is deterministic (pure function of weights + numeric inputs), **disabled in strict mode** (returns `null`; enabled only in `predictive`), degrades to `null` for undeclared/unloaded models, and is **logged** as `hook_predict_count` + `models_loaded` in scores/provenance (plumbed like the emit count via `HookDispatchReport.predictCount` → `RunOptions.hookInitPredictCount` → `RunAction::hookPredictCount_` accumulable). (4) **`trech-train-surrogate`** (`tools/torch/trech_torch/train_surrogate.py` + generic tabular harvester `dataset.harvest_table`): trains any-inputs→any-outputs from `trech_scores.jsonl`/`trech_event_features.jsonl`/`trech_hook_emits.jsonl` (`--source`/`--tag`), linear (numpy) or MLP (torch), baked-in standardisation, exports the portable `.json` (+ optional `.pt`) + model-size/held-out manifest. Verified end-to-end both ways: `examples/experiments/surrogate_generic_demo.js` calls the committed optics ridge through `ctx.predict` (water n≈1.330, `hook_predict_count=9`, `models_loaded=['optics_n']`); and a **brand-new** MLP trained by `trech-train-surrogate` from a 400-event run (predict `total_step_count` from edep + track length) loads back through `ctx.predict` and predicts ~4.2–4.5 steps vs actual 4–5. Guarded by `tests/test_generic_surrogate.cpp` (general schema + missing/extra inputs + committed ridge), `tests/test_js_runtime.cpp` (ctx.predict named IO, predict counting, strict-mode gating, undeclared→null), and a new suite case `generic_surrogate_inference` (runs `surrogate_generic_demo.js`, asserts `models_loaded` contains `optics_n`, `hook_predict_count>0`, and the predicted water n sits ~1.33). `ctest --preset dev` 10/10; validation suite **34 cases (30 pass / 4 info)** after adding the guard. New CHARTS.md "Generic surrogate" section documents it.
- **Torch training/inference at dimension scales landed (2026-07-02)**: extended the ML ladder from a single optics path to a **two-prediction, stock-build-capable** train→infer stack plus an active-learning planner. (1) **Event-stratifier learned path**: `TorchScriptStub` grew a **LibTorch-free logistic `.json` backend** (mirroring the optics ridge) — `p(exceptional) = sigmoid(bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ)` over the `trech_event_features_v1` schema, validated against `FeaturePipeline::FeatureNames()` at load — so a Geant4-trained event classifier runs via `stratify.modelPath` in a stock build (predictive mode, no `TRECH_ENABLE_TORCH`). End-to-end verified: trained on a 400-event water run (358 predictable / 42 exceptional, threshold teacher), the deployed `.json` drove a fresh 100-event run with `stratify_source_model_count=100`, 95/100 agreement with the threshold rule; the optional `.pt` twin is bit-parity 1.7e-7. Guarded by `tests/test_stratifier.cpp` (json load, sigmoid value, `source=="model"`, feature-order-mismatch → threshold fallback). (2) **Shared harvester + trainers** in `tools/torch/trech_torch/`: `dataset.py` centralises schema-locked harvesting of Geant4 outputs (optics samples from `trech_viz_scene.json`, event samples from `trech_event_features.jsonl`, run/scale metadata from provenance+scores) with dimension-scale bands (atomic/nano/micro/meso/macro from `system_volume_mm3`/`mediumBoxMm`); `train_event_stratifier.py` fits the logistic (numpy, deterministic, inverse-frequency class weights) behind a held-out `beats_majority_baseline` promotion gate + parameter/byte manifest; `train_optics_surrogate.py` reworked to bake input standardisation into the exported TorchScript module (engine feeds raw vectors), take a deterministic `--seed`, run a leave-one-out gate, and record model size. (3) **Active-learning planner** `plan_experiments.py` (`trech-plan-geant4-experiments`): reads the harvested datasets, finds where the models are starved (optics element/density coverage, LOO hotspots, missing anchors; event label balance, degenerate feature slots, beam-energy + dimension-scale coverage), and emits a ranked `geant4_experiment_plan.json` of concrete `trech run` requests — the "learn what to simulate in Geant4" reverse link (verified: flagged the air-OOD 644× density gap and the optical-feature degeneracy on the current panel/runs). `.json`/planner paths are numpy-only (stock env); `torch` is an optional `.[torch]` extra for `.pt` exports. Also fixed a real bug: `OpticsSurrogate::encodeComposition` renormalised only 13 of 14 element slots (off-by-one excluding `other`), now matches the Python harvester (guarded). New CHARTS.md section "Geant4 → training → inference linkage (per prediction, per dimension scale)" is the map. `ctest --preset dev` 9/9; validation suite unchanged at 33 cases (29 pass / 4 info), `data/optics_surrogate_ridge.json` byte-identical (no physics drift).
- Optics surrogate landed (`OpticsSurrogate`): TorchScript inference path for (composition → n, abs, scat). When `optics.derive.surrogateModelPath` is set the surrogate predictions override the extractor's scalar fields; spectrum samples remain extractor-derived. Trainer at `tools/torch/trech_torch/train_optics_surrogate.py` consumes scene manifests.
- Optics surrogate LibTorch-free ridge backend landed: the inference workstream's "feed transport" step, delivered without building LibTorch. `OpticsSurrogate::load` dispatches on the model file — a `.json` ridge model (standardised linear, `n = bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ`) is parsed via nlohmann/json and evaluated in plain C++; a `.pt` still needs Torch. The composition schema was unified to 14 element slots (added `I` for NaI-class high-Z optics) across the C++ surrogate, the TorchScript trainer, and the ridge validator. `scripts/validate_optics_surrogate.py --export` fits the ridge on the full panel and writes `data/optics_surrogate_ridge.json` (committed). `GeantRunner` now shifts the *whole* derived dispersion curve (`result.samples[].refractiveIndex`) to the surrogate's level so transport's RINDEX actually uses the learned n while keeping the f-sum dispersion shape; the ridge predicts n only (abs/scat keep extractor values via a negative sentinel). Cross-checked bit-faithful C++↔Python (max |Δn| = 5.6e-8 over 14 materials); `tests/test_optics_surrogate.cpp` guards the ridge math + the element-order/feature-length loaders (ctest 9/9). Opt-in and off by default — the glass-of-water demos stay pure f-sum physics.
- Validation suite landed (`tools/validation/`): current report is 32 cases covering optics derivation vs handbook, KK window sanity, n ordering / n>=1 invariants, nuclear cycle conservation + Q-value closure, determinism replay under MT ULP tolerance, primaries accounting closure, system-density arithmetic, event-feature mean consistency, viz schema + trajectory record invariants, composition-fraction normalisation, Torch-backed stats flag, an h2o_fluid brine **scenario** regression guard (runs-to-completion + brine deposition + primary closure, catching a return of the material SIGSEGV), and fluid-physics scenario guards reading hook emits — Pascal's principle (rigid wall transmits pressure undiminished while the Hookean/plastic wall expands, damps it, and keeps bounded permanent set; rigid≪deformable displacement) plus osmosis (9/9 expected-result checks after the cell upgrade); an **optics-surrogate transport guard** (`optics_surrogate_transport_applied`) that runs the opt-in ridge surrogate and asserts the learned high-Z n for NaI (~1.77) reaches transport's RINDEX samples (the f-sum extractor alone gives ~1.33); an **anti-degeneration** guard (`sampling_diversity_non_degenerate`) that asserts a varied-beam run samples a real distribution (>1 distinct exit / incidence-angle stddev >0 / wavelength stddev >0 vs the degenerate 1 / 0° / 0 nm baseline); and the Sputnik molecular-scale guards: `h2o_molecule_bonds_stable`, `h2o_cluster_fluid_stable`, `h2o_bulk_water_structure`, and `h2o_diffusion_temperature_trend`. Orchestrator `scripts/run_validation_suite.sh` re-exports the ridge model so model drift shows in `git diff`; selected scenario/export failures now fail the suite instead of being hidden by `|| true`; slow bulk/diffusion runs remain explicitly gated. The report `docs/validation_report.md` + sidecar `docs/validation_report.json` are committed to git so `git diff` traces physics regression/improvement.

- Comparison re-run (2026-06-11): ctest 9/9; full validation suite (incl. bulk) 25 cases, 21 pass / 0 fail — report diff vs the previous commit is timestamp/SHA + last-ULP float noise only (no physics drift; `data/optics_surrogate_ridge.json` byte-identical). Glass-of-water comparison videos re-rendered from the fresh runs (`glass_of_water_beam.mp4|gif`, `_physics.mp4`, `_trech.mp4`): exit angles physics 30.00° vs TRECH 30.00°, ray gap 0.0 mm. New bulk-water comparison video (`tools/viz/demos/render_bulk_water.py` → `h2o_bulk_water_gr.mp4|gif`) replays the new deterministic `md_snapshot` emits and shows the engine's O-O g(r) first peak landing on the measured 2.80 Å hydrogen-bond line (TRECH 2.798 Å), with the coordination over-count stated on the end card.
- **Photo-fraction** analytic cross-check landed (2026-07-02): the third analytic check and the first to test process *branching* rather than total attenuation/range. `analytic_photo_fraction.js` + `evaluatePhotoFraction` in `src/sim/AnalyticCrossCheck.cpp` predict the photoelectric share of the total interaction cross section `f = sigma_phot / (phot + compt + Rayl + conv)` from the SAME G4EmCalculator per-process cross sections Beer-Lambert sums (refactored into a shared `fillAttenuationBreakdown` helper), and pair it with `measuredField: "primaries_photoelectric_first_fraction"` — a new per-primary tally (`AddPrimaryFirstInteraction` + two `G4Accumulable<G4int>`) that, at each primary's first discrete interaction in `SteppingAction`, records whether it was photoelectric. Because QBBC's `G4EmStandardPhysics_option3` wraps the gamma processes in `G4GammaGeneralProcess`, the classifier reads the fired sub-process's EM subtype (`GetSubProcessSubType() == fPhotoElectricEffect`) instead of the wrapper's process name (falling back to `GetProcessSubType()` when unwrapped) — verified by the non-zero photoelectric count guard in the validation case. 30 keV gamma in water (near the photoelectric/Compton crossover): **derived 0.3908 vs measured 0.3931 (0.59%)**, 6702/17051 first interactions photoelectric. The branching ratio is slab-thickness independent, and both integer counts are MT-order-independent so the measured fraction is byte-reproducible under default MT (verified). Guarded by `analytic_photo_fraction_cross_check`; report 33 cases (29 pass / 0 fail / 4 info); ctest 9/9; round-trip already covered `analytic.checks` (no new config fields).
- Charged-particle **CSDA-range** analytic cross-check landed (2026-06-30): the second behaviour *derived from* Geant4 (Tier-1, no pre-written rule). `analytic_csda_range.js` + `evaluateCsdaRange` in `src/sim/AnalyticCrossCheck.cpp` derive the CSDA range from Geant4's own stopping power (`G4EmCalculator::GetCSDARange`; `GeantRunner` enables `SetBuildCSDARange(true)` only when a `csda_range` check is configured) and pair it with a new per-primary track-length tally (`primary_mean_track_length_mm`, accumulated over `parentID==0` steps in `SteppingAction`). 20 MeV proton in water: **derived 4.282 mm vs measured 4.266 mm (0.38%)**, 0/5000 transmitted (fully contained), dE/dx 2.59 MeV/mm (≈ NIST PSTAR). `threads:1` byte-reproducible. Guarded by `analytic_csda_range_cross_check`; report 32 cases (28 pass / 0 fail / 4 info); ctest 9/9; round-trip already covered `analytic.checks` (no new config fields).
- Analytic Beer-Lambert cross-check landed (2026-06-19): new C++ module `src/sim/AnalyticCrossCheck.cpp` + scenario `examples/experiments/analytic_beer_lambert.js` + validation case `analytic_beer_lambert_cross_check` (category `analytic`). The engine derives the photon linear attenuation coefficient from Geant4's own cross sections (`G4EmCalculator`: phot+compt+Rayl+conv) and compares the classical `T = exp(-mu*x)` to the measured Monte-Carlo uncollided-primary fraction (new `primaries_uncollided` tally). At 100 keV through 50 mm water: **classical 0.4265 vs Geant4 0.4217 (1.1% rel, Poisson-limited)**; suite count 25 → 28 cases, ctest 9/9, round-trip extended for `analytic.checks`.
- Osmotic validation refinement (2026-06-28): `testscenario_osmotic.js` replaced the unbounded Brownian impulse with a Langevin thermostat and the validation case now compares against the documented expected timeline/thermodynamics. Refreshed run: 6/6 osmosis checks, `net_water_flux_out=71`, first crossing tick 3, max mean KE 0.961 vs 0.81 target, late external/internal pressure ratio 1.46. `ctest --preset dev` passed 9/9; `python -m trech_validation --runs-dir build/dev` completed **28 cases, 24 pass / 0 fail-error / 4 info / 0 skip**.
- Osmotic 3D replay video landed (2026-06-28): `testscenario_osmotic.js` now emits rounded `osmotic_particles` snapshots every 50 ticks as a deterministic viz/training sideband, and `tools/viz/demos/render_osmotic.py` renders `osmotic_dehydration.mp4` from those emitted states plus pore flow glyphs and count history. The animation is a TRECH-output replay, not a closed-form osmotic-law drawing; larger-scale surrogates should train/gate on these Geant4-driven outputs.
- Third-party dependency refresh landed (2026-06-30): **nlohmann/json v3.12.0** (was 3.11.2; header-only, no source changes), **QuickJS 2026-06-04 release** (`04be246`; internal `quickjs.h` layout only — public C API unchanged, bindings recompiled as-is), **Geant4 v11.4.2** (was 11.4.0; patch series, no public API changes → no call-site migration; incremental rebuild into `build/geant4-install`). trech rebuilt + relinked; `ctest --preset dev` 9/9; `cnt_logic_gates` reproduces byte-identical Geant4 transport against 11.4.2. LibTorch (`thirds/torch`) deferred at 1.2.0 (x86_64, off-by-default, ridge backend covers it; 1.2→2.x is binary-swap-only since our torch API usage is stable).
- CNT logic-gates + circuit truth tables landed (2026-06-29): new scenario `examples/experiments/cnt_logic_gates.js` + validation case `cnt_logic_gates` (category `cnt`) + suite wiring in `scripts/run_validation_suite.sh` + render `tools/viz/demos/render_cnt_logic_gates.py` → `cnt_logic_gates.png`. CNTFETs are built from the tight-binding band gap (on/off ratio `~exp(E_g/2kT)`); the full static-CMOS gate family and three adder circuits confirm their truth tables; the recovered subthreshold swing is 60.3 mV/dec (ideal 59.5, the room-T Fermi limit); a metallic tube in the same topology breaks the logic. `cnt_device`/`cnt_gates_summary` now also carry 8 emitted `visual_topologies` plus `visual_source` so visualization consumes the same gate networks the scenario evaluates. Deterministic (`threads:1`, strict; byte-identical reruns incl. the Geant4 e- drive). Landing report was 31 cases, 27 pass / 0 fail-error / 4 info / 0 skip; current report is 32 cases after CSDA + scenario-viz refresh.
- Scenario animation clarity refresh landed (2026-06-30): `render_physics_anims.py` now consumes hook emits for electrolysis and Pascal where available. Electrolysis renders bonded H2/O2/H2O molecule packets tied to the reaction ledger; Pascal renders live piston/sensor pressure gauges plus wall-profile/plastic-set fields; brine renders a visible water network and hydrated Na+/Cl- ion pairs with deposits constrained to the beam path; `render_cnt_structure.py` reads the emitted `(5,5)` metallic and `(16,0)` semiconducting devices; `render_cnt_circuit.py` reads `cnt_gates_summary.visual_topologies` and cycles through all emitted gate structures instead of a fixed inverter-chain template. Regenerated `electrolysis.gif`, `pascal_press.gif`, `brine_deposit.gif`, `cnt_structure.gif`, and `cnt_circuit.gif`.
- CNT animation clarity refresh landed (2026-07-01): reworked the two CNT demo GIFs for legibility (viz sideband only — no scenario/C++ physics change). `render_cnt_structure.py` now rolls each tube around its own chiral vector `C = n·a1 + m·a2` (`build_tube_chiral`), so the **armchair-vs-zigzag wrapping asymmetry is faithful, not just the diameter**; it shows all three emitted archetypes (metallic armchair `(5,5)` / quasi-metallic zigzag `(9,0)` / semiconducting zigzag `(16,0)`) and draws a **labelled electron source contact (the base)** + drain electrode plates with per-tube status cards, so where the particles originate and which way current flows are explicit. `render_cnt_circuit.py` was de-frenetified: the strobing continuous gate/row mapping became a held step-plan (`--hold` frames/row, default 6) with a static camera, a progress bar, and a lit output node + `✓ MATCH`/`✗ MISMATCH` readout; a shared-palette `disposal=1` re-encode shrinks the GIF ~7 MB → ~1.4 MB. Regenerated `cnt_structure.gif` + `cnt_circuit.gif`.
- Membrane-**efflux comparison scenario aligned (2026-06-28)**: `examples/experiments/testscenario_efflux.js` reframes the cell-membrane demo from a (confusing) osmotic-dehydration story into a clean **classic biological phenomenon with a closed-form cross-check** — a cell clearing a lipophilic **waste** molecule by passive permeation across its lipid bilayer (Overton's rule) into an extracellular sink, while retaining its polar **essentials**. It exercises the TRECH thesis end-to-end: (a) **nanoscale** — lipid-membrane and cytosol EM interaction coefficients are computed by `G4EmCalculator` (the analytic-cross-check machinery, emitted live as `analytic_checks`: μ_lipid≈0.0291/mm vs μ_water≈0.0377/mm at 30 keV); (b) **event drive** — the same 30 keV gamma probe is transported each tick and `onEventEnd` consumes `ctx.event` edep/track/step statistics to modulate permeability (refreshed run: 12,789 steps, 4.99 MeV deposited, mean activation 0.947); (c) **mesoscale** — the Geant4 ratio + event activation scale per-encounter permeation in the hook-MD bath (an *illustrative* mapping, flagged: Geant4 EM transport is not molecular partitioning); (d) **macroscale** — the simulated internal count N(t) is fit log-linearly and reproduces the classical **first-order clearance law** `N(t)=N₀·e^(−kt)` (Fick), R²≈0.992, half-life ~1786 ticks, 72/80 cleared, 30/30 essentials retained. Guarded by `efflux_first_order_kinetics` (category `fluid`, 6/6 checks); deterministic (`threads:1`, seeded). Landing suite was 30 cases; current suite is tracked in the validation-report curation bullet above. Honest scope: same as every TRECH MD demo — Geant4 transports particles but cannot compute molecular partitioning/diffusion, so the permeation-rate mapping is illustrative; what is genuinely validated is that the microscopic permeation reproduces the macroscopic first-order law.
- Efflux **PubChem grounding + directed-motion upgrade landed (2026-06-28)**: (1) **PubChem integration** — helper `tools/pubchem` (`python -m trech_pubchem fetch`) fetches + caches substance properties and 2D structures; prefer `--cache-dir build/...` / `TRECH_PUBCHEM_CACHE_DIR` for real-time validation/runtime fetches and avoid committing new cache blobs. The efflux scenario uses **two real substances** — benzene (waste) and D-glucose (essential) — loaded at runtime with `TRECH_PUBCHEM`; their measured **XLogP** (octanol-water partition coefficient: +2.1 vs −2.6) **decides the selectivity** by Overton's rule (lipophilic permeates, polar retained), a real measured anchor distinct from the illustrative Geant4 rate scaling. `lipophilicity_selectivity` and `geant4_event_drive_present` are both validation flags (case now 6/6). (2) **Directed motion** — replaced the random Langevin jitter with a drift-diffusion (overdamped-Langevin) integrator: a persistent random velocity + a coherent **cytoplasmic-streaming** rotation (volume-preserving, so first-order-safe) + a mild outward **efflux drift** for the permeant. Molecules now swirl in an organized internal flow and drain outward instead of jittering. (3) **Visualization** — molecules render as hexagonal ring glyphs and the video carries a "molecule passport" strip with real PubChem 2D structures when PNGs are present in the build-local cache. Determinism preserved; ctest 9/9.
- Osmotic **biological-cell upgrade landed (2026-06-28)**: the scenario now reads as an evident dehydrating cell instead of a gas-in-a-box. (1) A **flexible turgor-driven spring membrane** (64-node elastic ring, sub-stepped + clamped so it is unconditionally stable) replaces the fixed circle: turgor follows a viscoelastically-lagged internal-water average, so as water leaves the ring contracts and buckles into lobes — the cell **crenates** (mean radius 28 → 21.3, area −41%). The node radii are an emitted physical state (`membrane` in snapshots, `final_summary.membrane`), closing the ROADMAP's "crenation as emitted state, not a renderer-only effect" item. Particle exclusion stays on the nominal pore ring (decoupled from the spring ODE) so the osmosis statistics are byte-stable (net flux 71, first crossing tick 3 unchanged). (2) A third **ion** species (small enough to fit the pore but **wrong polarity**) demonstrates the membrane **expelling wrong-polarized molecules** by polarity selectivity, distinct from glucose's size exclusion (3016 rejections; emitted `wrong_polarized_rejections`). The validation case `osmotic_shift_observed` is tightened to **9/9** checks (adds polarity exclusion, membrane crenation, membrane stability); ctest 9/9, report regenerated (28 cases, 24 pass / 0 fail). The renderer rewrite shows a top-down cell — crenating lipid bilayer, cytoplasm/nucleus/organelles, channel pores expelling water, hypertonic glucose bath, and flash markers where wrong-polarized molecules are rejected.

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
- **[electronic structure landed 2026-06-12; curvature secondary gaps landed 2026-06-26]** `cnt_band_structure.js` advances the track from geometry/transport stubs to the actual "electron behaviour differences / Fermi gap" physics: a hook-layer tight-binding zone-folding model over a 26-tube (n,m) panel reproduces the metallicity rule ((n-m) mod 3), the semiconducting E_g ∝ 1/d gap law on STM-measured anchors (within ~1%), and the small curvature-induced secondary gap for nominally metallic non-armchair tubes (`E_curv ~= 50 meV nm² * |cos(3θ)| / d²`; 7 quasi-metallic tubes, max gap 0.1007 eV; armchairs zero). Guarded by the `cnt_band_structure` validation case (category `cnt`), plotted as `cnt_band_structure.png`. Next on this track: trigonal-warping family (Kataura) split of the semiconducting gaps.
- **[logic gates + circuit truth tables landed 2026-06-29; topology-viz provenance fixed 2026-06-30]** `cnt_logic_gates.js` advances the track from band structure to working **CNTFET devices and digital logic**: the tube's `E_g` becomes the transistor's Fermi-statistics on/off ratio (`~exp(E_g/2kT)`), the full static-CMOS gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR) is built as resistive-divider pull-up/pull-down FET networks, and three circuits (half adder, full adder, 2-bit ripple-carry adder) propagate real output voltages whose thresholded levels **confirm the canonical truth/arithmetic tables**. The scenario emits `visual_topologies` serialized from the same primitive networks; `render_cnt_circuit.py` consumes that payload so gate visuals differ by emitted topology. The recovered subthreshold swing (60.3 mV/dec) sits on the ~60 mV/dec room-temperature Fermi limit; a metallic tube in the same topology collapses outputs to ~Vdd/2 and breaks the logic (the metallic-short manufacturing problem). Geant4 transports the e- beam through the representative (16,0) channel each event. Guarded by `cnt_logic_gates` (category `cnt`). Next on this track: sequential logic (latch/flip-flop), Schottky-contact barrier (the second `BackToTheCarbon.md` barrier), and chirality-distribution yield modelling.

## Long-term structure

- core/ (config, provenance, storage)
- js/ (runtime + bindings)
- sim/ (Geant4 integration and scoring)
- chem/ (species registry, reaction network, RD engine, DNA bridge)
- ml/ (TorchScript runtime + feature pipelines)
- data/ (curated datasets; new PubChem runtime fetches should go to build-local cache dirs)
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
