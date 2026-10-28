# Native Studio Chemistry screenshots

These JPEGs are unmodified captures of the actual macOS TRECH Studio window, including
its native Metal viewport. They are documentation images, separate from the gated GIF
regression references in `studio/tests/reference/`. Diagnostic and source/browser docks were
closed for a clearer view; the Chemistry inspector, view selector and timeline remain visible.
The macOS window-sharing badge is part of the native capture. No viewport was composited into
an editor screenshot and no physics data or UI text was painted onto an image.

| File | Selected view and cursor | Meaning |
| --- | --- | --- |
| `structure-editor.jpg` | `structure`, parameter 0 / frame 1 of 3, Structure tab | Authored water/D2 atom positions, isotope mass numbers and declared bonds |
| `electron-density.jpg` | `density:joint_electrons`, parameter 2 / frame 3 of 3, Scene JSON tab | Threshold surface of the independent joint RHF/6-31g density comparison |
| `electron-samples.jpg` | `samples:joint_electrons`, parameter 2 / frame 3 of 3, Scene JSON tab | 1600 visualization samples, not 1600 electrons or electron trajectories |
| `electron-orbitals.jpg` | `density:mo_6`, parameter 2 / frame 3 of 3, States & particles | Selected occupied orbital, full energy/occupation table, counts and independent RHF dipole |
| `joint-density-gradient.jpg` | `density:joint_electrons`, parameter 2, Field explorer | Log density, numerical Y section and recorded MO 6 phase overlay |
| `orbital-phase-gradient.jpg` | `density:mo_6`, parameter 2, Field explorer | Signed real amplitude, node and Y section; sign is not charge |
| `density-redistribution.jpg` | `density:density_redistribution`, parameter 2, Field explorer | Joint-minus-isolated-fragment density comparison, signed gradient and numeric Z section |
| `electron-level-diameter.jpg` | `density:energy_density`, snapshot 0, Electron levels | Ne computed occupied groups (2/2/6 electrons), log diameter density, X, span 1.2 Å |
| `electron-level-radial.jpg` | `density:energy_density`, snapshot 0, Electron levels | Ne spherical radial distribution, linear ordinate, span 1.2 Å; includes 4πr² |
| `nuclear-ensemble.jpg` | `nuclear:O:16:both`, ensemble sample 7 / frame 8 of 8, States & particles | One nucleus, 8 protons + 8 neutrons, species RMS and radial counts; extent guides are representation |

Historical water/D2 screenshots use `chemistry_probability_reference.js` with three Geant4
events and eight nuclear configurations per supported explicit nuclide. The 2026-10-28 field
captures use a fresh three-event run with nuclear sampling disabled. Atomic profile captures
use `chemistry_atomic_levels_reference.js` with one event and no nuclear sampling. All sessions
use seed 20261027, zero learned evaluations and zero dropped emits. Molecular/electronic positions use Å;
the nuclear view uses fm without an artificial scale overlay. The parameter scan is authored,
and ensemble indices are not physical time. Density thresholds, point colors and glyph sizes
are display choices. Neither the electronic comparison nor the nuclear initializer establishes
a coupled atomistic reaction-dynamics prediction.

`manifest.json` records source hashes, run metadata, each selected view/cursor, image dimensions
and JPEG SHA-256 hashes. Generated run outputs remain under `build/` and are not source assets.

## Refresh deliberately

Use the current release binary rather than a potentially older development build:

```bash
cmake --build --preset rel
build/render-venv/bin/python scripts/validate_chemistry_probability.py
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio \
  --engine-bin "$PWD/build/rel/trech" \
  --scenario "$PWD/examples/experiments/chemistry_probability_reference.js" \
  --open "$PWD/build/chemistry_probability_validation/predictive_8"
```

Use the selector to choose each view and keep playback paused. The Structure screenshot uses
Rewind; selecting the other views starts at their last recorded frame. Keep the Chemistry
source/clock text and timeline in frame. Use a native window screenshot tool so the GPU surface
is included: `QWidget.grab()` alone can produce an empty viewport on macOS. Save the native
JPEG directly, inspect it, update the manifest's hashes/metadata and verify the README links.
Do not regenerate these JPEGs during ordinary test or capture runs.


The orbital/nuclear screenshots were refreshed on **2026-10-28** after the state/particle
inspection improvements. The original structure/density/sample images retain their 2026-10-27
source run. The original sample image remains here as a documented comparison; the root gallery now uses
the quantitative gradient, phase and occupied-level profiles. The manifest
associates each artifact with its own capture session, fixture/config hash and source state.


Five gradient/profile images deliberately refresh the gallery on 2026-10-28. Cloud energy
colors mix occupation-weighted local contributions; gradient colors, opacity, cutaway faces,
interpolation and finite-grid thresholds are representation choices. The atomic reference
resolves nonuniform core/outer distributions without fixed radii. The molecular density
redistribution uses separate fragment bases and is not a bond or entanglement measure. Profiles
are finite-grid/finite-radius RHF comparisons, not Geant4-derived bound-electron predictions.
The original flat-threshold images remain documented historical assets.

For the atomic captures, create a fresh run and open it with the same engine override:

```bash
build/rel/trech run examples/experiments/chemistry_atomic_levels_reference.js \
  --output build/chemistry_neon_final --param events=1
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio \
  --engine-bin "$PWD/build/rel/trech" \
  --scenario "$PWD/examples/experiments/chemistry_atomic_levels_reference.js" \
  --open "$PWD/build/chemistry_neon_final"
```

Select Electron levels and switch Diameter/Radius; keep span at 1.2 Å. The default cloud uses
occupied-energy colors and a Z cutaway. Field captures use volume/phase controls, log window
4 decades, display opacity 0.6 and enclosed mass 90%; the manifest records each section/overlay.
Scroll the inspector to show the complete numerical legend; preserve the source clock below.
