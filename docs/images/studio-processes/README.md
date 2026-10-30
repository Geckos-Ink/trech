# Studio experiment preview provenance

These are historical 2D-airflow/inventory captures. The salt trays are retired from active
playback and the README gallery; no validated measured interface time sequence is bundled.
Current airflow source evolves 3D independent Euler state. New source cannot reproduce the old
images byte-for-byte; retain their manifests rather than relabel them as new 3D/microscopy output.

`nacl-workspace.png` and `aerodynamics-workspace.png` are unmodified native macOS Studio
window captures, including the Metal surface. They were captured through the computer-use
window screenshot API on 2026-10-30. The sharing badge, when present, is part of macOS.
No viewport, UI text or physics values were composited into these window screenshots.

The `*-render.png` images and the two GIFs under `studio/tests/reference/` use Studio's actual
offscreen wgpu renderer. Their optional footer contains the same held-frame annotations shown
in Processes. It is an explicitly declared capture overlay; it does not change rendered state.
The GIFs are 360×240, four display seconds at 10 fps; native-resolution stills are 960×640.
No interpolation or optical-flow frames are generated. Camera, colour/arrow/glyph choices and
screen playback duration are representation; source clocks/numbers remain engine output.

| Native window | Held frame | Meaning |
| --- | --- | --- |
| `nacl-workspace.png` | step 48 / frame 49 of 81 | 42 solid + 22 dissolved salt parcels, 51 solvent parcels; three separated display inventories |
| `aerodynamics-workspace.png` | final / frame 51 of 51 | Mach 1.5, 200 CFL steps, ~0.533 ms, gas temperature 278.0–481.9 K |

NaCl uses illustrative capacity/attachment kinetics and no calibrated physical clock.
Airflow uses independent 2D ideal-gas Euler comparison physics, without viscosity, solid heat
transfer, fracture or reactive flow. Their separate Geant4 material probes/tallies do not turn
these comparisons into particle-trained predictions. Both runs use seed 424242, serial strict
transport, zero learned inference and zero dropped emits. [Scope](../../process_references.md).

`manifest.json` records source SHA-256 hashes, run config identity, run-output hashes, media
hashes/dimensions, preview sampling and reproduction commands. Runtime data remains under
`build/`. The GIF JSON sidecars are retained next to the GIFs; existing reference media is not
refreshed incidentally.

## Reproduce

From the repo root, with the built engine and Studio Python installed:

```sh
studio/run_examples_suite.sh aerodynamics

# Only when intentionally refreshing the two committed GIF references:
studio/run_examples_suite.sh --update-refs aerodynamics
```

Set `TRECH_BIN=build/rel/trech` and `STUDIO_PY=<python-with-Studio>` if auto-location does not
match your installation. Previews go to `build/studio/examples_suite/captures`, runs to its
`runs` directory, with a manifest and index. No network services are required. The documentation
capture session used `--out build/studio/process_preview_suite --width 960 --height 640
--seconds 6 --fps 12`; compact-reference settings are fixed in the suite for these two IDs.

Open a native workspace, for example:

```sh
python -m trech_studio --engine-bin build/rel/trech \
  --scenario examples/experiments/aerodynamics_reference.js \
  --open build/studio/examples_suite/runs/aerodynamics
```

Use **Preview → Export image…** for the final frame or **Export animation (GIF + MP4)…** for
the whole timeline. Choose the output folder. Exports run asynchronously through Studio's
capture CLI, with a fresh name, standard fixed camera, selected material stream, annotations
and JSON sidecar. They do not rerun simulation. A healthy ffmpeg is required for video export;
the still PNG works without it. Exports do not yet clone manually orbited cameras or every
quantum/density-display setting; those limits remain in Studio's roadmap.

To refresh native images, open the same scenario/run, keep Options and Processes visible,
pause at the stated frame, and use an unmodified native window capture. Preserve source/clock
labels. Update this manifest deliberately rather than through routine test runs.
