# Classic and Studio media refresh — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Unified engine / Studio media refresh

- [x] One shell entry point `scripts/update_experiment_media.sh`, backed by an inventory-driven
  controller; classic registry plus runnable JS scenarios, fresh isolated outputs, slow runs
  included, staged promotion, logs, content hashes and resumable matching source identity.
- [x] Classic registry now also names previously unregistered lava lamp, polyurethane and
  toothpaste GIFs, plus the two labelled NaCl/Euler diagnostics. Studio publishes an indexed
  per-scenario preview set and refreshes the explicitly gated reference IDs.
- [x] Full refresh executed: 41 engine GIF/PNG pairs; 63 Studio scenarios inspected and run
  (47 animated, 15 static geometry, one blocked recipe), with seven curated references retaining
  their authored dimensions/cadence. SHA-256 and complete image decoding audit passed; no dropped
  hook emits or refresh failures. Native window screenshots remain deliberate historical captures.
- [ ] General process models and true spatial crystallization/3D airflow remain absent; the
  media driver reports such limits rather than generating synthetic physical motion.
- [ ] Refresh historical native desktop screenshots deliberately when needed; automated
  offscreen captures must not be pasted into a UI to substitute for native recapture.

## 2026-09-29 (later) README animations made legible: charts, context, higher resolution

- **[landed] Side chart panel** (`tools/viz/trech_viz/charts.py`): 1280×720 GIFs with 2D charts
  composited next to the 3D view. `material_frame` gained `samples`, `charts`, `curves`, `labels`,
  a phase `grid` (one smooth surface/grain cloud per solver cell class) and mesh `vertex_rgba`
  (`docs/output_schema.md`); every hook-layer README scenario now charts its own observables
  (Briggs–Rauscher concentrations, bulk-water g(r), D(T) vs Holz 2000, efflux log-counts,
  electrolysis inventory, furnace phase counts, Pascal pressure ratio/bulge, osmotic volume,
  MR spectrum/FID, MRI signal/image, CNT transfer curves, beaker evaporation, MD bond/angle/T/Rg).
- **[landed] Legible Geant4 track replay** (`tracks_view.py`, `track_charts.py`): fading trails,
  interaction-history colouring, process-marked vertices, `find_reactions` nuclide labels,
  `bundle_optical`, composition glyphs (representation), split panes, captions; charts are
  recorded-track statistics revealed on the Geant4 clock vs the engine's formula (Kaplan–Meier
  attenuation — censoring fixes the early-interaction bias —, Bragg curve, channel split, inverted-
  Snell dispersion, reaction timeline, per-volume deposits, tissue contrast). Tests:
  `tools/viz/tests/test_tracks_charts.py`.
- **[landed] Recorder fidelity.** Optical boundary points carry the `G4OpBoundaryProcess` outcome
  (`boundary`); the birth point records the pre-step (emission) kinetic energy (step 1's loss was
  invisible).
- **[landed] Nitrogen-carbon cycle on neutron-HP.** Scenario-selectable `physics.list` +
  `physics.radioactiveDecayThresholdYears` (conditionally serialized, round-trip tested);
  `config_nitrogen_carbon_cycle.js` runs `QGSP_BIC_HP` so thermal ¹⁴N(n,p)¹⁴C (36 of 20,000
  events) and the ¹⁴C β⁻ decay are Geant4-sampled. Supersedes the "[open] Nuclear cycle capture"
  item below.
- **[landed] Scenario clarity.** Briggs–Rauscher: stirrer drawn (spin labelled representation) and a
  saturating colour weight so the classified deep-blue regime is visibly blue. MR stage 1: B₀ field
  lines and poles, B_eff and the Bloch solver's own pulse path, FID isochromats (Lorentzian
  offsets whose mean is the solver's envelope; representation). MRI stage 3: slow-motion precession
  evaluated from the readout law at display times. Pascal: walls coloured by their own displacement,
  drawn ×3 against their rest planes. Electrolysis: product droplets sink into the bath; explicit
  liquid surface. Glass furnace: grains/melt/glass surfaces instead of balls. CNT: electrons with
  count ∝ model I_d (representation).
- **[landed] Validation after the legibility pass** (`BUILD_PRESET=rel`, render venv on PATH):
  49 cases, 45 pass / 0 fail / 4 info. The first pass failed `cnt_logic_gates`: the longer
  transfer sweep overflowed `hooks.maxEmitsPerCallback` and the summary emit was dropped; the CNT
  (256) and MRI-imaging (160) caps were raised and every run now reports
  `hook_emit_dropped_count` 0.
- **[open] Nuclear forward-leg guard.** No validation case asserts that the (n,p) leg is actually
  sampled (the scores carry no reaction tallies); add a per-reaction tally to `trech_scores.jsonl`
  and a `nuclear_cycle_forward_leg_sampled` case.
- **[open] Optical time-of-flight lag.** In recorded optical tracks, c·Δt/Δs over a segment equals
  the index of the *previous* medium (glass segments run at c, water segments at n_glass):
  investigate whether Geant4's optical velocity update or the recorder's point time lags one step
  before any time-of-flight observable relies on it (the dispersion chart uses geometry, not time).
- **[open] Beaker kinematics.** `beaker_water_n_pentane.js` pour/intermix/plume motion is still
  illustrative (labelled in the HUD); replace with a two-fluid PBF solve like the shaken glass.
- **[open] Representation still in replays.** MR isochromats (a real isochromat-ensemble Bloch solver
  would replace the envelope law); CNT electrons (Geant4's e⁻ transport through the channel is not
  shown); composition glyphs; Briggs–Rauscher stir bar.
- **[open] Studio parity for the chart/label/grid contract** (see [desktop milestones](../../studio/ROADMAP.md#studio-desktop-ui)).
- **[open] Media size.** 1280×720 GIFs with orbiting cameras compress poorly: the 27 README GIFs
  total ~106 MB (largest ~7.6 MB; the densest MD/PBF/grain scenes are trimmed to 8 fps / 48
  colours). WebP/MP4 alongside, or a static camera for dense scenes, would cut the README weight.

## 2026-09-29 every experiment output is a 3D replay of a real run

- **[landed] Observation-only capture.** `trech run … --viz | --viz-all | --viz-max-trajectories N`
  (`RunOptions`/`applyRunOverrides`, `tests/test_cli_parse.cpp`) turns on the trajectory recorder +
  scene manifest for any scenario without editing it; the default config/hash is untouched, and a
  captured run's `config_json` honestly records `viz` enabled.
- **[landed] Classic viewer, two faithful GIF paths** (`tools/viz/trech_viz/animate.py`, tests in
  `tools/viz/tests/test_playback.py`): Geant4 trajectories revealed on the recorded Geant4 clock
  (activity-quantile playback, true time in the HUD, species/energy colouring, discrete vertices,
  rare-event selection stated in the HUD, two-run comparison overlays, auto-zoom past enclosing
  media, engine analytic/nuclear/edep/derived-n HUD lines), and held `material_frame` replay with
  the new optional contract (`length_unit`/`positions`, `up_axis`, `radii`, `bonds`, `vectors`,
  `apparatus` incl. moving segments/meshes, `legend`, `hud_lines`, `clock_text`, `stream`,
  `render_surface.clip_cylinder.center_mm`), documented in `docs/output_schema.md`.
- **[landed] Scenario emitters** for the MD ladder, shaken glass, Briggs–Rauscher, CNT band panel +
  CNTFET sweep + CMOS netlists, MRI stages 1/3 (Bloch vector, gradient phase winding), MRI stage 4
  volumetric k-space reconstruction (`scripts/run_magnetic_resonance_brain.py --out-gif`), and a
  `optics_surrogate_demo` beam-tilt/`use_surrogate` pair (defaults byte-identical).
- **[landed] Planar solvers lifted to 3D.** Osmosis: 3D bath + a 642-vertex membrane moved by the
  measured collision-pressure difference at held area (the scripted `cos(8θ)` crenation target is
  gone; crenation emerges); the pressure check now grades the bias while the cell shrinks. Efflux:
  spherical cell, 3D teacher + re-distilled 3D transport operator (64 hidden, 2,400 epochs,
  held-out R²min 0.9993; the old fit's OU γ≈0.987 vs teacher 0.982 doubled 3D clearance, now
  0.980), comparison key `efflux_v2_sphere`, P = kR/3. Pascal: 3D baths, rim-clamped tensioned
  Hookean patch walls. Electrolysis: 3D packet kinematics from physical rules (diffusion, buoyant
  bubbles from electrodes, burn nearest the spark) instead of target-seeking packets. Glass furnace:
  6³ charge with 6-neighbour conduction pairs.
- **[landed] Media.** All scripted 2D renderers + their MP4/PNG outputs retired;
  `tools/viz/demos/render_readme_3d.py` regenerates all 27 README GIFs from real runs.
- **[open] Studio parity.** Studio accepts the `positions` alias and per-frame `up_axis`;
  Processes now selects one recorded stream. Radii/bonds and vectors landed October 18–19,
  and held legend/HUD text is available in Processes/capture. Moving apparatus meshes,
  in-viewport text and simultaneous streams remain open (see [desktop milestones](../../studio/ROADMAP.md#studio-desktop-ui)).
- **[superseded] Nuclear cycle capture** (neutron-HP landed above). QBBC samples thermal-neutron elastic scattering and radiative
  capture but not ¹⁴N(n,p)¹⁴C in `config_nitrogen_carbon_cycle.js`; the forward leg is Q-value-only.
  Needs a high-precision neutron physics option (G4NDL is installed) before the GIF can show it.
- **[open] Remaining representation in replays.** Electrolysis packet positions are still
  representation (no packet-transport operator); the Briggs–Rauscher reactor is well mixed (a
  spatial reaction–diffusion solver would be needed for waves); CNT glow is the device model, not
  simulated carrier transport; the MRI brain anatomy is a procedural phantom; the 3D glass charge is
  laterally uniform (floor-only heating), so its layers are identical — add side losses/charge
  heterogeneity.
- **[open] Osmotic membrane limits.** Radial vertex DOF cannot represent non-star shapes; the
  membrane touches its radial safety bounds (reported `clamp_hits`); water flux is diffusive with no
  explicit solute-driven chemical potential. Retrain/validate the efflux crossing hazard against 3D
  encounter statistics as well.
- **[landed] Validation report refreshed** (`BUILD_PRESET=rel`): **49 cases, 45 pass / 0 fail /
  4 info / 0 skip**, including `osmotic_shift_observed` 9/9, `efflux_first_order_kinetics` 9/9,
  and every paired operator gate (efflux, H2O cycle, glass furnace: all gaps, 22/22 trust).
  `glass_of_water` and the ridge re-export were rerun (the committed ridge is byte-identical).
- **[open] Suite interpreter.** `scripts/run_validation_suite.sh` calls bare `python3` for the
  numpy-dependent ridge/glass/validator steps and hides their output; on a machine whose system
  python lacks numpy it exits 1 before writing the report. Prefer `build/render-venv/bin/python`
  when present (as the MR-brain step already does) and surface the failing step.
- **[superseded] Media size** — tracked in the later 2026-09-29 section.
