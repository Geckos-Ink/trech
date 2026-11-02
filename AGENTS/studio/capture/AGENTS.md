# Preview export and native media — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Classic and Studio media refresh](../../tooling/media/AGENTS.md) · [Rendering, appearance and playback](../rendering/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Reproducible Studio previews:** `engine/preview.py` runs the ordinary capture CLI asynchronously
from Preview (image / GIF+MP4 / cancel), preserving a selected material stream and exporting a
standard fixed camera. Pure `render/frame_notes.py` supplies held phase/clock/HUD/legend text to
Processes and the optional Qt capture footer. The two comparison scenarios are registered in the
capture suite; their gated GIFs retain JSON sidecars. Native windows and renderer PNGs in
`docs/images/studio-processes/` have SHA-256/source/run provenance; they are not painted mockups.
Keep quantitative comparison limitations in captions and refresh media deliberately.

**Preview export and readouts:** `studio/trech_studio/engine/preview.py` owns the cancellable QProcess export job;
`capture.py` owns offscreen wgpu rendering and the optional Qt text footer. Both use pure
`studio/trech_studio/render/frame_notes.py` for held engine phase/clock/HUD/legend strings; no Qt/engine import enters
that pure layer. The Processes dock follows timeline and stream changes. Exports use the final
frame/full horizon and a standard camera, not an implicit viewport screenshot. Missing video
artifacts are reported as incomplete. Compact reference captures retain their JSON sidecars.
Native experiment screenshots and manifests live in `docs/images/studio-processes/`, separately
from chemistry and the gated reference GIFs. Relative engine overrides resolve before changing
to a scenario subprocess directory. Default side docks are bounded and non-chemistry scenarios
hide the Chemistry dock so native previews retain a usable viewport.

##### [`studio/trech_studio/capture.py`](../../../studio/trech_studio/capture.py)

**Headless** counterpart of the viewport: drives the same `SceneRenderer` offscreen (via
`rendercanvas.offscreen`) to render a run's scene + playback to a still PNG and an MP4/GIF (ffmpeg),
writing a `<prefix>.json` provenance sidecar. App-level orchestrator (imports `engine`/`scene`/
`render`, never `ui`); basis of [`studio/run_examples_suite.sh`](../../../studio/run_examples_suite.sh).

- **Key symbols:** `capture_run` (still + animation), `capture_reference` (CLI `--reference` — a
  compact committed GIF: ~320×220 · 10 fps · 3 s, box-downsampled supersampled frames, lossless
  raw frames with `dither=none`, **gated** on `--update-refs`), `CaptureResult`, `main`.
- **Common mistakes:** `TRECH_FFMPEG` may name an explicit encoder; a broken executable merely on
  `PATH` must not crash capture. Never write references on an ordinary run.
