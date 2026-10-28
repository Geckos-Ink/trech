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
| `nuclear-ensemble.jpg` | `nuclear:O:16:both`, ensemble sample 7 / frame 8 of 8, States & particles | One nucleus, 8 protons + 8 neutrons, species RMS and radial counts; extent guides are representation |

All screenshots use `chemistry_probability_reference.js` and a validated predictive
run in their recorded capture session: three Geant4 events, seed 20261027, eight nuclear configurations per supported explicit
nuclide, zero learned evaluations and zero dropped emits. Molecular/electronic positions use Å;
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
source run. The root gallery now uses the orbital screenshot instead of the combined-density
sample cloud; the original sample image remains here as a documented comparison. The manifest
associates each artifact with its own capture session, fixture/config hash and source state.
