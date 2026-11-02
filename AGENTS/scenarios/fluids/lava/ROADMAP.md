# Lava lamp thermofluid — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

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
- **[landed 2026-08-15] General engine precision profiles.** `config.precision` is now a
  physics-agnostic contract: a rung (`preview`/`balanced`/`high`/`convergence`, or `custom`) plus
  the axes a scenario maps onto it, each carrying a role (`spatial`/`temporal`/`output`/
  `statistical`/`representation`), the control it drives, its unit, the resolved value and the
  `balanced` reference. C++ owns the vocabulary, the invariants and the reporting
  (`PrecisionConfig`/`PrecisionAxisConfig` in `src/core/Config.cpp`, conditionally serialized so
  every existing scenario keeps its config hash; `precision_profile` + `precision_axes` in
  `trech_scores.jsonl`; `precision_profile` + `precision_axis_count` in `trech_provenance.jsonl`).
  The *ladder* lives in scenario JS (`helpers.precision.resolve`), because only the scenario knows
  what refining its own axis means — so no global “particle count” is pretended to mean the same
  thing across Geant4 transport, MD, PBF, chemistry and observer replays. Invariants: a
  `representation` axis is forced display-only by the parser (a render knob can never read as
  improved physics), an unknown profile name normalizes to `custom`, and an explicit control
  override marks its axis and turns the reported profile `custom` — a rung only half-followed is
  not that rung. `lava_lamp.js` is the worked adoption (spatial parcels / temporal step / output
  ticks / representation-only surface grid, with `balanced` == its historical defaults so the
  default run is unchanged); the validation suite now drives its refinement run through
  `--param precision_profile='"high"'` instead of hand-set knobs. Studio surfaces the profile and
  every axis in the run summary, the preview status line and each capture sidecar. Round-trip +
  normalization + conditional-serialization coverage in `tests/test_config_roundtrip.cpp`.
  **Remaining:** only lava_lamp has adopted it; the other multi-axis scenarios (foams, PBF water,
  MD, MRI) still declare bare knobs and should map them onto the same profile.
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
