# Rendering, appearance and playback — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Recorded process and scalar views](../processes/AGENTS.md) · [Chemistry workspace and field inspection](../chemistry/AGENTS.md) · [Classic and Studio media refresh](../../tooling/media/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Bulk material rendering:** observer-scale liquids/gases and solid material charges must declare
recorded spatial support and continuous representation through supplied meshes,
`material_frame.grid`, `render_surface`, or disjoint
`material_groups` (explicit point indices, phase, RGBA and Gaussian hint). Studio's pure
`studio/trech_studio/render/materials.py` extracts separate recorded class/group boundaries; `replaces_points`
suppresses grid cell glyphs. Water/pentane emits separate liquid and vapor groups; the furnace
uses translucent batch/melt/glass boundaries. Transparency is for inspection, not measured optics.
Molecular/particle diagnostics retain individual glyphs. Never invent phase, geometry or motion
from inventories: NaCl still requires supplied calibrated interface data. Display refinement does
not refine simulation; remaining rollout/optics/occlusion work is in the [rendering roadmap](ROADMAP.md).

**Visible sampling/merge controls:** `particle_count_factor` is a typed spatial control for
shaken water (actual integer lattice count reported, balanced total water mass retained), and a
representation-only representative count for water/pentane. Furnace `cells_per_side` displays its
N³ total explicitly. Studio's Precision and resources dock separates surface/mesh detail from
parcel merge radius (`RenderBudget.merge_radius_scale`, 0.5–2). Both viewers' material capture CLIs
accept `--render-detail` / `--merge-radius-scale`; Studio Preview passes the selected detail,
radius and memory allowance to export. Width overrides change apparent connections, never
recorded membership/physics; original neck samples are disabled and topology counts stay authored.
High-count convergence remains a roadmap gate, not a consequence of adding more particles.

- **`viz_*` tags never alter Geant4 transport.** Visualization-only forcing (`viz_forced_white`/
  `viz_emitter` in C++; `viz_*` render hints consumed by Studio) is a rendering choice, labelled
  as such.

**Interactive scalar-field inspection:** generic C++ `scalarFieldStatistics` / authoring
`TRECH_FIELD_STATS(values,spacing)` computes signed integrals and 1–99% absolute-mass ranked
thresholds, including full ties and actual enclosed fractions. JS ignores imported statistics and
recomputes them, with no model inference or normalization. Optional signed real `amplitude`
point samples accompany cell-average orbital |ψ|². `density_difference` fields explicitly name
their reference; ordinary densities remain nonnegative. The optional PySCF tool supplies joint
minus isolated-fragment density on a common grid (own fragment bases; not a bonding test).
Studio's `studio/trech_studio/ui/density_explorer.py` / pure `studio/trech_studio/render/density.py` provide movable numeric heatmap
sections, log legends and enclosed-mass controls. `studio/trech_studio/render/density_gpu.py` + `studio/trech_studio/render/shaders/density.wgsl`
ray-march recorded fields; `+ψ/−ψ` lobes and orbital overlays retain the supplied signs. The
maximum-scaled float16 GPU texture/interpolation/alpha are representation; original CPU values
and C++ statistics are unchanged. Scalar contours use outward winding and separate display
lighting, not material optics. Probability contours are not extra quantum energy levels.
Chemistry raises its explicit per-record emit budget to 8 MiB for phase/difference records;
full multi-frame grids remain in provenance, with existing streaming residuals in the [Chemistry roadmap](../chemistry/ROADMAP.md).

**Grouped bulk materials:** `studio/trech_studio/render/materials.py` validates explicit phase grids and builds
per-class continuous boundaries, including anisotropic spacing, x-fastest data and closed outer
faces. `playback.py` retains disjoint `material_groups` with explicit point membership and Gaussian
display hints. `renderer.py` combines class/group meshes with per-vertex display RGBA, sorts their
triangles on camera changes and disables translucent depth writes; cell/group points are replaced
as declared. Solid charge transparency is a visibility choice. Existing single-fluid Gaussian
surfaces also use translucent sorting; scene volumes sort by object depth. Clear-shell Fresnel
uses the absolute view/normal angle on both faces to avoid opaque back-face fill. Intersecting separate
objects still need order-independent transparency. Shared live/export metadata records grouping,
opacity and display sampling. Neither grouping nor refinement changes emitted state or time.

**Precision controls:** `studio/trech_studio/ui/adaptive_controls.py` names surface/mesh detail and Gaussian parcel
merge radius separately, reports the recorded particle count, and points to typed Scenario
options for particle/cell counts requiring a rerun. Grid-only frames disable the Gaussian-radius
control. Long typed-option labels wrap inside the dock. `RenderBudget.merge_radius_scale` is validated in [0.5,2]; width overrides disable authored
neck samples and disclose apparent-topology changes without editing recorded counts or positions.
`studio/trech_studio/engine/preview.py` forwards the selected detail/radius/memory settings to fixed capture. Shaken
water declares a spatial particle multiplier and a display-only grid spacing; beaker sample counts
are explicitly representation-only. Their original default counts remain 4301 and 440.

#### `studio/trech_studio/scene/` — the editable scenario model (pure)

##### [`studio/trech_studio/scene/model.py`](../../../studio/trech_studio/scene/model.py) · [`loader.py`](../../../studio/trech_studio/scene/loader.py)

`SceneModel` is the in-memory truth; `loader.py` builds it from `trech_viz_scene.json`. Key types:
`VolumeNode` (`path_length_mm` = the volume's own thickness), `RenderHint` (parsed `viz_*` tags).
Precedence in `SceneModel.volume_color`: physics-derived appearance → engine viz tags
(`viz_forced_white`/`viz_emitter`) → scenario `viz_*` hints (win last); `volume_surface` returns
`(reflectance R0, gloss, emissive)` for the shader.

##### [`studio/trech_studio/scene/appearance.py`](../../../studio/trech_studio/scene/appearance.py)

Turns a material's engine-emitted `derived_optics` into an **honest look** (numpy only). Answers
the observer questions from the physics: transparency via Beer–Lambert `exp(-thickness/attenuation)`
(`_mu_per_mm`, `_transmittance_grid`), reflectivity via Fresnel `R0=((n-1)/(n+1))²` (`_fresnel_r`),
colour via CIE integration of visible-band transmittance **normalised so a flat spectrum is neutral**
(`_cie_xyz`, `derive_appearance`, `rgba`). Where the EM base doesn't resolve differential absorption
(pure water/glass), the honest result is colourless and the inspector says so. **Grade the gap;
don't fake the blue.**

- **Tests:** [`studio/tests/test_appearance.py`](../../../studio/tests/test_appearance.py).

#### `studio/trech_studio/render/` — the wgpu viewport (pure rendering)

##### [`studio/trech_studio/render/renderer.py`](../../../studio/trech_studio/render/renderer.py) · [`viewport.py`](../../../studio/trech_studio/render/viewport.py) · [`camera.py`](../../../studio/trech_studio/render/camera.py)

`SceneRenderer` receives a `SceneModel` + `Playback` and draws; it never reads engine files or
computes physics. `viewport.py` is the wgpu Qt canvas (falls back to a message widget if wgpu is
absent). The camera frames the **placed volumes** (not the whole world box) incl. rotated apparatus
+ particle bounds.

##### [`studio/trech_studio/render/mesh.py`](../../../studio/trech_studio/render/mesh.py) · [`metaballs.py`](../../../studio/trech_studio/render/metaballs.py)

`mesh.py` CPU mesh generation — **true annular tube meshes** (both radii, inner walls, annular
faces) so a Geant4 beaker stays hollow, not a solid display cylinder. `metaballs.py` extracts the
interpolated marching-tetrahedra surface for Gaussian `render_surface` contracts and anisotropic
class grids. `materials.py` validates grids, extracts separate boundaries and combines display-RGBA
layers for triangle sorting. Liquid clipping has a closed empty-padded boundary.

- **Tests:** [`studio/tests/test_mesh.py`](../../../studio/tests/test_mesh.py), [`studio/tests/test_metaballs.py`](../../../studio/tests/test_metaballs.py),
  [`studio/tests/test_materials.py`](../../../studio/tests/test_materials.py).

##### [`studio/trech_studio/render/playback.py`](../../../studio/trech_studio/render/playback.py)

Builds the time-indexed `Playback` (trajectory ribbons + fluid/material particle frames). Key
symbols: `particle_instances`/`bond_segments` (pure held-frame GPU buffers), `build_playback`, `build_trajectory_playback`, `build_material_frame_playback`,
`build_particle_playback`, `count_at`, `frame_count`, and the **z-up→y-up remap** `_to_yup` /
`_surface_to_yup` (fluid clouds are z-up but the viewport is y-up — without this the shaken glass
lies on its side). Air is labelled/thinner; scatter emphasis requires a recorded `scatter` process.

- **Radius/bond playback:** valid `radii` use a depth-tested instanced unit sphere
  (`studio/trech_studio/render/shaders/spheres.wgsl`); `bonds` use only declared, validated point-index pairs. `length_unit`
  stays native for non-mm streams, whose unrelated Geant4 scene is hidden and excluded from
  camera fitting. Radii expand bounds; particle and bond GPU resources use eight-frame LRUs.
- **Common mistakes:** don't emphasise a bend as scattering; don't apply the render-surface mode to
  frames that didn't request it, and never let necking/surface splats move centres or join graph
  components (representation-only, identical semantics to classic `trech-viz`).
- **Tests:** [`studio/tests/test_playback.py`](../../../studio/tests/test_playback.py).

##### [`studio/trech_studio/render/shaders/`](../../../studio/trech_studio/render/shaders)

WGSL shaders: [`surface.wgsl`](../../../studio/trech_studio/render/shaders/surface.wgsl) (Fresnel specular +
grazing-angle rim; suppresses flat fill for low-alpha media so beams read through clear glass),
[`trajectory.wgsl`](../../../studio/trech_studio/render/shaders/trajectory.wgsl) (additive wavelength-coloured beam
ribbons), [`particles.wgsl`](../../../studio/trech_studio/render/shaders/particles.wgsl) (camera-facing sprite
billboards), [`lines.wgsl`](../../../studio/trech_studio/render/shaders/lines.wgsl).

### Material appearance & render hints

Studio's default already reads optics well (glowing beam ribbons, see-through dielectrics), so the
authored `viz_*` tags are the **"forced parameters, easy to disable"** emphasis channel — applied
*over* the physics look and labelled a rendering choice (the inspector shows them as authored
overrides). Parsed by `scene.model.RenderHint`:

| tag | effect |
| --- | --- |
| `viz_hidden` | do not draw the volume |
| `viz_solid` | force an opaque body (alpha ~1) |
| `viz_shell` / `viz_wireframe` | force a clear glass **shell** (edges/Fresnel only) so contents read through |
| `viz_emissive` / `viz_glow` | self-lit (skips shading) |
| `viz_opacity=<0..1>` | force display alpha |
| `viz_color=<#rgb\|#rrggbb\|r,g,b>` | replace the base colour |
| `viz_tint=<colour>` | multiply the derived colour by a tint |

- **Adaptive precision/resources:** `studio/trech_studio/ui/adaptive_controls.py` owns the Precision and resources
  dock. Continuous scenario factors and predictive time budgets go through engine CLI flags;
  `studio/trech_studio/render/adaptive.py` uses measured CPU preparation/submission time, viewport size, particle
  count and estimated memory allowance to adjust representation tessellation/surface grid/cache
  lengths. GPU time is unmeasured. Emitted state/time stay unchanged; fixed capture options can
  override track/segment caps and detail without timing adaptation. Actual detail and timing are
  visible in the dock; run summary/precision reports include completed/requested event counts.
  `cascade.py` displays engine `skipReason` badges for deliberately limited stages. Full contract:
  [`docs/adaptive_precision.md`](../../../docs/adaptive_precision.md). Test: `studio/tests/test_adaptive.py`.

- **Fused lava surface — Shipped (representation-only).** `render_surface` contract → Gaussian
  splat → marching-tetrahedra mesh via the same depth-tested `surface.wgsl`; disclosed in precision
  metadata; identical semantics to classic `trech-viz`.
