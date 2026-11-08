# Recorded process and scalar views — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Reusable solution and material processes](../../scenarios/processes/AGENTS.md) · [Independent process references](../../scenarios/references/AGENTS.md) · [Rendering, appearance and playback](../rendering/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Process recipes:** `water_salt_recipe.js` exposes library-owned process roles and engine reports;
missing operators block without fabricated spatial output. `studio/trech_studio/recipe_status.py`
summarises recorded `process_recipe_state` emits per planned stage (status counts, engine error
code, selection status, inference/draw accounting) for the Processes dock; it re-runs nothing
and its counts do not imply physical accuracy. Committed steps carrying a declared `no_op`
(e.g. an empty spatial neighbourhood) are counted separately as "no-op" commits. Salt trays are retired from active spatial playback;
`interface_file` supplies calibrated measured native-um triangles inspected by C++, with source and
validation declarations retained. A single photograph supplies no depth/time calibration.
`studio/trech_studio/render/interfaces.py` computes display normals, never growth. `trech_euler3d_reference.js`
evolves an independent 3D comparison; `studio/trech_studio/render/scalar.py` validates regular x-fastest scalar grids,
units, active masks, linear ranges, slice/surface/volume controls and authored camera yaw/pitch.
Optional `render_camera.projection` selects perspective (legacy default) or orthographic.
`studio/trech_studio/render/camera.py` matches target-plane scale across projections; shared WGSL uses parallel
volume/section rays and facing/shading in orthographic mode. Capture metadata records authored
and effective projection. Airflow Options exposes CFL/physical duration for engine reruns;
the exact periodic entropy/shear convergence fixture verifies the independent numerical solver,
not obstacle accuracy or a trained aerodynamic response. `scripts/validate_euler3d.py`
records the studies and common-time obstacle diagnostics; residuals remain in the [independent references roadmap](../../scenarios/references/ROADMAP.md).
The existing density GPU path displays those records; transparency and float16 filtering remain
representation. Shared live/export semantics supply no learned flow or experimental validity.
Recipe sequencing/physics stays in JS/engine, never Studio.
